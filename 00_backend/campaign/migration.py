"""Strict legacy snapshot format and read-only export from old in-memory APIs."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from enum import Enum
from uuid import UUID
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .models import CampaignState, PHASE_ORDER, Phase, PhaseStatus, utc_now


class MigrationError(ValueError):
    pass


class SourceSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid')
    instance: str = Field(min_length=1)
    url: str
    campaign_count: int = Field(ge=0)


class CampaignExport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    format_version: Literal[1]
    exported_at: datetime
    sources: list[SourceSnapshot] = Field(min_length=1)
    campaign_count: int = Field(ge=0)
    campaigns: list[CampaignState]


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MigrationError('Duplicate JSON object key')
        result[key] = value
    return result


def parse_json(text):
    def invalid_constant(_):
        raise MigrationError('Non-finite JSON number')
    try:
        return json.loads(text, object_pairs_hook=_object, parse_constant=invalid_constant)
    except (json.JSONDecodeError, UnicodeError):
        raise MigrationError('Invalid JSON document') from None


def _normalise(value):
    if isinstance(value, BaseModel):
        return _normalise(value.model_dump(mode='python'))
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {(key.value if isinstance(key, Enum) else str(key)): _normalise(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalise(item) for item in value]
    return value


def canonical(value) -> str:
    return json.dumps(_normalise(value), sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _complete(raw, parsed, path='campaign'):
    """Reject silent defaults/extra-field removal at every typed model boundary."""
    if isinstance(parsed, BaseModel):
        if not isinstance(raw, dict) or set(raw) != set(type(parsed).model_fields):
            raise MigrationError(f'{path}: missing or unknown fields')
        for key in type(parsed).model_fields:
            _complete(raw[key], getattr(parsed, key), f'{path}.{key}')
    elif isinstance(parsed, list):
        for index, item in enumerate(parsed):
            _complete(raw[index], item, f'{path}[{index}]')
    elif isinstance(parsed, dict):
        if set(raw) != set(parsed):
            raise MigrationError(f'{path}: missing or unknown keys')
        for key, item in parsed.items():
            _complete(key, key, f'{path}.key')
            _complete(raw[key], item, f'{path}.{key}')
    elif isinstance(parsed, str):
        if '\x00' in parsed or any(0xD800 <= ord(char) <= 0xDFFF for char in parsed):
            raise MigrationError(f'{path}: text cannot be represented in PostgreSQL')
    elif isinstance(parsed, datetime) and (parsed.tzinfo is None or parsed.utcoffset() is None):
        raise MigrationError(f'{path}: timezone is required')


def validate_campaigns(raw) -> list[CampaignState]:
    if not isinstance(raw, list):
        raise MigrationError('Expected a complete campaign list from the legacy API')
    campaigns = []
    campaign_ids, asset_ids = set(), set()
    for index, data in enumerate(raw):
        try:
            campaign = CampaignState.model_validate_json(canonical(data), strict=True)
            _complete(data, campaign, f'campaign[{index}]')
        except (ValidationError, TypeError, ValueError) as exc:
            if isinstance(exc, MigrationError):
                raise
            raise MigrationError(f'campaign[{index}]: invalid schema or JSON values') from None
        if campaign.campaign_id in campaign_ids:
            raise MigrationError(f'campaign[{index}]: duplicate campaign ID')
        campaign_ids.add(campaign.campaign_id)
        if not campaign.brief.brand.strip() or not campaign.brief.campaign_goal.strip():
            raise MigrationError(f'campaign[{index}]: brand and goal must not be blank')
        if not re.fullmatch('[A-Z]{3}', campaign.brief.currency):
            raise MigrationError(f'campaign[{index}]: currency must be three uppercase letters')
        if campaign.version > 2_147_483_647:
            raise MigrationError(f'campaign[{index}]: version exceeds PostgreSQL integer range')
        if campaign.updated_at < campaign.created_at:
            raise MigrationError(f'campaign[{index}]: updated_at precedes created_at')
        if any(not approval.actor.strip() for approval in campaign.approvals):
            raise MigrationError(f'campaign[{index}]: approval actor must not be blank')
        incomplete = False
        for phase in PHASE_ORDER:
            run = campaign.phase_runs[phase]
            if run.status == PhaseStatus.RUNNING:
                raise MigrationError(f'campaign[{index}]: running phase; quiesce writes and drain requests first')
            if run.started_at and run.completed_at and run.completed_at < run.started_at:
                raise MigrationError(f'campaign[{index}]: phase completion precedes start')
            if incomplete and run.status != PhaseStatus.NOT_STARTED:
                raise MigrationError(f'campaign[{index}]: phases are out of order')
            if run.status != PhaseStatus.COMPLETED:
                incomplete = True
            if run.status == PhaseStatus.AWAITING_APPROVAL and phase != Phase.EXECUTION:
                raise MigrationError(f'campaign[{index}]: approval gate must be execution')
            if run.status in {PhaseStatus.COMPLETED, PhaseStatus.AWAITING_APPROVAL} and getattr(campaign, phase.value) is None:
                raise MigrationError(f'campaign[{index}]: finished phase has no output')
            if run.status == PhaseStatus.NOT_STARTED and getattr(campaign, phase.value) is not None:
                raise MigrationError(f'campaign[{index}]: unstarted phase has output')
        statuses = [campaign.phase_runs[phase].status for phase in PHASE_ORDER]
        expected = ('completed' if all(s == PhaseStatus.COMPLETED for s in statuses) else
                    'awaiting_approval' if PhaseStatus.AWAITING_APPROVAL in statuses else
                    'failed' if PhaseStatus.FAILED in statuses else
                    'draft' if all(s == PhaseStatus.NOT_STARTED for s in statuses) else 'in_progress')
        if campaign.status.value != expected:
            raise MigrationError(f'campaign[{index}]: campaign status disagrees with phase statuses')
        execution_approvals = [a for a in campaign.approvals if a.phase == Phase.EXECUTION]
        if campaign.phase_runs[Phase.EXECUTION].status == PhaseStatus.COMPLETED:
            if not execution_approvals or execution_approvals[-1].decision.value != 'approved':
                raise MigrationError(f'campaign[{index}]: completed execution has no approval')
        completed = [phase for phase in PHASE_ORDER if campaign.phase_runs[phase].status == PhaseStatus.COMPLETED]
        remaining = [phase for phase in PHASE_ORDER if campaign.phase_runs[phase].status != PhaseStatus.COMPLETED]
        allowed_current = {completed[-1] if completed else Phase.PLANNING, remaining[0] if remaining else Phase.MONITORING}
        if campaign.current_phase not in allowed_current:
            raise MigrationError(f'campaign[{index}]: current phase is inconsistent')
        if campaign.development:
            for asset in campaign.development.assets:
                if asset.asset_id in asset_ids:
                    raise MigrationError(f'campaign[{index}]: duplicate asset ID')
                asset_ids.add(asset.asset_id)
        campaigns.append(campaign)
    return campaigns


def load_export(path: Path) -> CampaignExport:
    return validate_export(parse_json(path.read_text(encoding='utf-8')))


def validate_export(raw) -> CampaignExport:
    try:
        document = CampaignExport.model_validate_json(canonical(raw), strict=True)
        _complete(raw, document, 'export')
    except (ValidationError, TypeError, ValueError) as exc:
        if isinstance(exc, MigrationError):
            raise
        raise MigrationError('Invalid export envelope') from None
    document.campaigns = validate_campaigns(raw['campaigns'])
    if document.campaign_count != len(document.campaigns):
        raise MigrationError('Export campaign count does not match its records')
    if sum(source.campaign_count for source in document.sources) < document.campaign_count:
        raise MigrationError('Source counts cannot account for all campaigns')
    if len({source.instance for source in document.sources}) != len(document.sources):
        raise MigrationError('Source instance labels must be unique')
    for source in document.sources:
        validate_source_url(source.url)
    return document


def export_hash(document: CampaignExport) -> str:
    payload = json.loads(canonical(document))
    payload['campaigns'] = sorted(payload['campaigns'], key=lambda row: row['campaign_id'])
    payload['sources'] = sorted(payload['sources'], key=lambda row: row['instance'])
    return hashlib.sha256(canonical(payload).encode()).hexdigest()


def validate_source_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in {'', '/'}):
        raise MigrationError('Source URL must be a server origin without credentials, path, or query')
    if parsed.scheme == 'http' and parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise MigrationError('Remote source origins require HTTPS')


def read_session(path: Path | None) -> str:
    if path:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(descriptor) as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
                raise MigrationError('Session file must be owned by the current user and mode 0600')
            session = stream.read().strip()
    else:
        session = os.environ.get('CAMPAIGN_EXPORT_SESSION', '').strip()
    if not session or '\n' in session or '\r' in session:
        raise MigrationError('Provide a protected session file or CAMPAIGN_EXPORT_SESSION')
    return session


def write_export(path: Path, document: CampaignExport):
    # O_EXCL also refuses symlinks; never overwrite an earlier migration snapshot.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        stream.write(canonical(document) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


async def export_campaigns(sources: list[tuple[str, str]], session: str, *, quiesced: bool,
                           client: httpx.AsyncClient | None = None) -> CampaignExport:
    if not quiesced:
        raise MigrationError('Confirm writes are quiesced and all in-flight requests have drained')
    if not sources or len({label for label, _ in sources}) != len(sources) or any(not label.strip() for label, _ in sources):
        raise MigrationError('Provide unique, nonblank source instance labels')
    for _, url in sources:
        validate_source_url(url)

    async def fetch(http, url):
        try:
            result = await http.get(url.rstrip('/') + '/api/v1/campaigns',
                                    headers={'Authorization': f'FirebaseSession {session}'}, follow_redirects=False)
        except httpx.HTTPError:
            raise MigrationError('Unable to read legacy source; check connectivity and authentication') from None
        if result.status_code != 200:
            raise MigrationError(f'Legacy source returned HTTP {result.status_code}; export aborted')
        return validate_campaigns(parse_json(result.content))

    async def collect(http):
        snapshots, first = [], []
        for label, url in sources:
            items = await fetch(http, url)
            first.append(items)
            snapshots.append(SourceSnapshot(instance=label, url=url.rstrip('/'), campaign_count=len(items)))
        merged = {}
        for (_, url), items in zip(sources, first):
            again = await fetch(http, url)
            original = {str(c.campaign_id): canonical(c) for c in items}
            if original != {str(c.campaign_id): canonical(c) for c in again}:
                raise MigrationError('Legacy source changed between reads; keep writes paused and retry')
            for item in items:
                key = str(item.campaign_id)
                if key in merged and canonical(merged[key]) != canonical(item):
                    raise MigrationError('Conflicting campaign IDs across source instances')
                merged[key] = item
        document = CampaignExport(format_version=1, exported_at=utc_now(), sources=snapshots,
                                  campaign_count=len(merged), campaigns=[merged[key] for key in sorted(merged)])
        return validate_export(document.model_dump(mode='json'))

    if client is not None:
        return await collect(client)
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as http:
        return await collect(http)
