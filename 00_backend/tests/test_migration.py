import os
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from campaign.config import OperatorDatabaseSettings
from campaign.migration import (
    MigrationError, canonical, export_campaigns, export_hash, load_export, parse_json,
    read_session, validate_export, write_export,
)
from campaign.models import CampaignBrief, CampaignState
from campaign.manage import main


def snapshot():
    return CampaignState(brief=CampaignBrief(brand='Example', campaign_goal='Grow',
        target_audience=['Audience'], duration_weeks=4, budget=100)).model_dump(mode='json')


def document():
    return dict(format_version=1, exported_at='2026-09-25T10:00:00+00:00',
                sources=[dict(instance='old-1', url='http://localhost:8080', campaign_count=1)],
                campaign_count=1, campaigns=[snapshot()])


def test_operator_settings_do_not_fall_back_to_runtime_credentials():
    with patch.dict(os.environ, {'DATABASE_URL':'postgresql://runtime:secret@localhost/runtime'}, clear=True):
        with pytest.raises(ValidationError):
            OperatorDatabaseSettings()
    with patch.dict(os.environ, {'OPERATOR_DATABASE_URL':'postgresql://operator:secret@localhost/test'}, clear=True):
        assert 'secret' not in repr(OperatorDatabaseSettings())


@pytest.mark.parametrize('edit', [
    lambda d: d['campaigns'][0].pop('campaign_id'),
    lambda d: d['campaigns'][0].pop('created_at'),
    lambda d: d['campaigns'][0]['phase_runs'].pop('execution'),
    lambda d: d['campaigns'][0].update(workspace_id='untrusted'),
    lambda d: d['campaigns'][0]['brief'].update(currency='usd'),
    lambda d: d['campaigns'][0]['brief'].update(brand=' '),
    lambda d: d['campaigns'][0]['brief'].update(brand='bad\x00text'),
    lambda d: d['campaigns'][0].update(created_at='2026-09-25T10:00:00'),
    lambda d: d['campaigns'][0]['phase_runs']['planning'].update(status='running'),
    lambda d: d['campaigns'][0].update(status='completed'),
    lambda d: d['campaigns'].append(d['campaigns'][0]),
    lambda d: d.update(campaign_count=2),
    lambda d: d['campaigns'][0]['brief'].update(budget=float('inf')),
])
def test_invalid_exports_are_rejected_without_silent_defaults(edit):
    raw = document()
    edit(raw)
    with pytest.raises(MigrationError):
        validate_export(raw)


def test_strict_json_rejects_duplicate_keys_and_nonfinite_values():
    for text in ('{"id": 1, "id": 2}', '{"amount": NaN}', '{"amount": Infinity}'):
        with pytest.raises(MigrationError):
            parse_json(text)


def test_export_file_is_private_and_never_overwritten(tmp_path):
    path = tmp_path / 'snapshot.json'
    export = validate_export(document())
    write_export(path, export)
    assert path.stat().st_mode & 0o777 == 0o600
    assert export_hash(load_export(path)) == export_hash(export)
    with pytest.raises(FileExistsError):
        write_export(path, export)
    assert export_hash(load_export(path)) == export_hash(export)


def test_session_file_permissions_and_missing_secret(tmp_path):
    path = tmp_path / 'session'
    path.write_text('signed-cookie')
    path.chmod(0o644)
    with pytest.raises(MigrationError):
        read_session(path)
    path.chmod(0o600)
    assert read_session(path) == 'signed-cookie'
    with patch.dict(os.environ, {}, clear=True), pytest.raises(MigrationError):
        read_session(None)


@pytest.mark.asyncio
async def test_export_merges_identical_instances_and_preserves_complete_records():
    state = snapshot()
    calls = []
    def source(request):
        calls.append(request)
        return httpx.Response(200, json=[state])
    async with httpx.AsyncClient(transport=httpx.MockTransport(source)) as client:
        exported = await export_campaigns([('one','http://localhost:8080'),('two','http://localhost:8081')], 'signed-cookie', quiesced=True, client=client)
    assert len(calls) == 4
    assert all(r.headers['Authorization'] == 'FirebaseSession signed-cookie' for r in calls)
    assert exported.campaign_count == 1
    assert len(exported.sources) == 2
    assert exported.campaigns[0].campaign_id == CampaignState.model_validate(state).campaign_id


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['changing', 'redirect', 'unauthorized', 'conflicting', 'new-api'])
async def test_export_aborts_unsafe_or_inconsistent_snapshots(mode):
    state = snapshot()
    calls = 0
    def source(request):
        nonlocal calls
        calls += 1
        item = dict(state)
        if mode == 'redirect':
            return httpx.Response(302, headers={'location':'https://untrusted.example'})
        if mode == 'unauthorized':
            return httpx.Response(401)
        if mode == 'changing' and calls > 1 or mode == 'conflicting' and request.url.port == 8081:
            item['metadata'] = {'changed': True}
        if mode == 'new-api':
            item['workspace_id'] = 'must-not-be-stripped'
        return httpx.Response(200, json=[item])
    sources = [('one','http://localhost:8080')]
    if mode == 'conflicting':
        sources.append(('two','http://localhost:8081'))
    async with httpx.AsyncClient(transport=httpx.MockTransport(source)) as client:
        with pytest.raises(MigrationError):
            await export_campaigns(sources, 'secret', quiesced=True, client=client)
    if mode == 'redirect':
        assert calls == 1


@pytest.mark.asyncio
async def test_export_requires_quiescence_before_network_request():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: pytest.fail('Network called'))) as client:
        with pytest.raises(MigrationError):
            await export_campaigns([('one','http://localhost:8080')], 'cookie', quiesced=False, client=client)


def test_cli_error_does_not_echo_secrets_or_campaign_data(tmp_path, capsys):
    path = tmp_path / 'invalid.json'
    path.write_text('{"private-campaign-content": "secret"}')
    result = main(['campaigns-import','--file',str(path),'--import-id','00000000-0000-0000-0000-000000000001',
                   '--name','Migration','--slug','migration','--owner-uid','new-user'])
    assert result == 1
    assert 'private-campaign-content' not in capsys.readouterr().err


@pytest.mark.asyncio
async def test_firebase_lookup_is_read_only_and_reports_safe_errors():
    from types import SimpleNamespace
    from campaign.operations import lookup_firebase_user, OperationError
    with patch('campaign.operations.initialize_firebase', return_value='test-app'), patch('campaign.operations.auth.get_user') as lookup:
        lookup.return_value = SimpleNamespace(uid='verified-user', email=None, display_name='Person', photo_url=None, disabled=False)
        identity = await lookup_firebase_user('verified-user')
        assert identity.uid == 'verified-user'
        lookup.assert_called_once_with('verified-user', app='test-app')
        lookup.side_effect = RuntimeError('provider credential secret')
        with pytest.raises(OperationError) as error:
            await lookup_firebase_user('missing')
        assert 'provider credential secret' not in str(error.value)
