"""Operator-only provisioning and atomic legacy migration; no HTTP endpoints."""
from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from uuid import UUID

import asyncpg
from firebase_admin import auth

from .auth import initialize_firebase
from .authorization import ROLE_RANK
from .migration import CampaignExport, MigrationError, canonical, export_hash, validate_export
from .postgres_repository import PostgresCampaignRepository


class OperationError(ValueError):
    pass


@dataclass(frozen=True)
class FirebaseIdentity:
    uid: str
    email: str | None = None
    display_name: str | None = None
    photo_url: str | None = None
    disabled: bool = False


async def lookup_firebase_user(uid: str) -> FirebaseIdentity:
    def lookup():
        user = auth.get_user(uid, app=initialize_firebase())
        return FirebaseIdentity(user.uid, user.email, user.display_name, user.photo_url, user.disabled)
    try:
        return await asyncio.to_thread(lookup)
    except Exception:
        raise OperationError('Cannot verify Firebase user; check the UID and operator credentials') from None


def workspace_values(name, slug):
    if not name.strip() or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
        raise OperationError('Workspace requires a nonblank name and a lowercase hyphenated slug')


async def require_operator_schema(connection):
    versions = await connection.fetch('SELECT version FROM schema_migrations ORDER BY version')
    if [row['version'] for row in versions] != [1, 2, 3, 4]:
        raise OperationError('Apply migrations 001 through 004 before using operator commands')
    # Check each privilege separately: has_table_privilege with a comma list means ANY.
    requirements = {
        'users': ('SELECT', 'INSERT', 'UPDATE'),
        'workspaces': ('SELECT', 'INSERT', 'UPDATE'),
        'workspace_members': ('SELECT', 'INSERT', 'UPDATE'),
        'campaign_imports': ('SELECT', 'INSERT'),
        'legacy_approval_history': ('SELECT', 'INSERT'),
        'campaigns': ('SELECT', 'INSERT'),
    }
    for table in ('campaign_briefs', 'planning_outputs', 'development_outputs', 'content_assets',
                  'execution_outputs', 'scheduled_activities', 'monitoring_outputs', 'phase_runs'):
        requirements[table] = ('SELECT', 'INSERT')
    requirements['approval_events'] = ('SELECT',)
    for table, privileges in requirements.items():
        for privilege in privileges:
            if not await connection.fetchval('SELECT has_table_privilege(current_user, $1, $2)', 'public.' + table, privilege):
                raise OperationError('Operator database privileges are required; do not use runtime credentials')


async def _lock(connection, namespace, value):
    key = int.from_bytes(hashlib.sha256(f'{namespace}:{value}'.encode()).digest()[:8], 'big', signed=True)
    await connection.execute('SELECT pg_advisory_xact_lock($1)', key)


class OperatorService:
    def __init__(self, pool, lookup=lookup_firebase_user):
        self.pool, self.lookup = pool, lookup

    async def _identity(self, uid):
        if not uid or not uid.strip():
            raise OperationError('Firebase UID is required')
        identity = await self.lookup(uid)
        if identity.uid != uid or identity.disabled:
            raise OperationError('Firebase identity does not match or the account is disabled')
        return identity

    async def _check_identity(self, connection, identity):
        user = await connection.fetchrow('SELECT user_id, status FROM users WHERE firebase_uid=$1', identity.uid)
        if user is not None and user['status'] != 'active':
            raise OperationError('Application user is disabled; explicit account recovery is required')
        if identity.email:
            conflict = await connection.fetchval('SELECT firebase_uid FROM users WHERE lower(email)=lower($1)', identity.email)
            if conflict is not None and conflict != identity.uid:
                raise OperationError('Email belongs to another Firebase UID; accounts will not be merged')
        return user

    async def _upsert_user(self, connection, identity):
        await self._check_identity(connection, identity)
        try:
            user_id = await connection.fetchval('''
                INSERT INTO users (firebase_uid,email,display_name,photo_url) VALUES ($1,$2,$3,$4)
                ON CONFLICT (firebase_uid) DO UPDATE SET email=EXCLUDED.email,
                    display_name=EXCLUDED.display_name, photo_url=EXCLUDED.photo_url
                WHERE users.status='active' RETURNING user_id
            ''', identity.uid, identity.email, identity.display_name, identity.photo_url)
        except asyncpg.UniqueViolationError:
            raise OperationError('Identity conflict; accounts will not be merged') from None
        if user_id is None:
            raise OperationError('Application user is disabled')
        return user_id

    async def workspace_create(self, name, slug, creator_uid):
        workspace_values(name, slug)
        identity = await self._identity(creator_uid)
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await require_operator_schema(connection)
                await _lock(connection, 'workspace-slug', slug)
                existing = await connection.fetchrow('''
                    SELECT w.*, u.firebase_uid FROM workspaces w JOIN users u
                    ON u.user_id=w.created_by_user_id WHERE w.slug=$1
                ''', slug)
                if existing:
                    if existing['name'] != name or existing['firebase_uid'] != creator_uid or existing['status'] != 'active':
                        raise OperationError('Workspace slug already exists with different settings')
                    await self._check_identity(connection, identity)
                    return dict(workspace_id=existing['workspace_id'], created=False)
                user_id = await self._upsert_user(connection, identity)
                workspace = await connection.fetchval('''
                    INSERT INTO workspaces (name,slug,created_by_user_id) VALUES ($1,$2,$3) RETURNING workspace_id
                ''', name, slug, user_id)
                return dict(workspace_id=workspace, created=True)

    async def member_set(self, workspace_id: UUID, uid: str, role: str):
        if role not in ROLE_RANK:
            raise OperationError('Role must be viewer, editor, runner, or approver')
        identity = await self._identity(uid)
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await require_operator_schema(connection)
                status = await connection.fetchval('SELECT status FROM workspaces WHERE workspace_id=$1 FOR SHARE', workspace_id)
                if status != 'active':
                    raise OperationError('Workspace is missing or inactive')
                user_id = await self._upsert_user(connection, identity)
                await connection.execute('''
                    INSERT INTO workspace_members (workspace_id,user_id,role,status,joined_at)
                    VALUES ($1,$2,$3,'active',now()) ON CONFLICT (workspace_id,user_id)
                    DO UPDATE SET role=EXCLUDED.role,status='active',
                        joined_at=COALESCE(workspace_members.joined_at,EXCLUDED.joined_at)
                    WHERE workspace_members.role IS DISTINCT FROM EXCLUDED.role
                       OR workspace_members.status <> 'active'
                ''', workspace_id, user_id, role)
                return dict(workspace_id=workspace_id, user_id=user_id, role=role, status='active')

    async def member_suspend(self, workspace_id: UUID, uid: str):
        async with self.pool.acquire() as connection:
            async with connection.transaction():
                await require_operator_schema(connection)
                row = await connection.fetchrow('''
                    SELECT m.user_id,m.status FROM workspace_members m JOIN users u USING(user_id)
                    WHERE m.workspace_id=$1 AND u.firebase_uid=$2 FOR UPDATE OF m
                ''', workspace_id, uid)
                if row is None:
                    raise OperationError('Workspace membership not found')
                if row['status'] != 'suspended':
                    await connection.execute("UPDATE workspace_members SET status='suspended' WHERE workspace_id=$1 AND user_id=$2", workspace_id, row['user_id'])
                return dict(workspace_id=workspace_id, user_id=row['user_id'], status='suspended')

    async def _import_preflight(self, connection, document, import_id, name, slug, identity):
        await require_operator_schema(connection)
        fingerprint = export_hash(document)
        existing = await connection.fetchrow('''
            SELECT i.*, u.firebase_uid FROM campaign_imports i JOIN users u ON u.user_id=i.owner_user_id
            WHERE import_id=$1
        ''', import_id)
        if existing:
            if (existing['export_sha256'],existing['workspace_name'],existing['workspace_slug'],existing['firebase_uid']) != (fingerprint,name,slug,identity.uid):
                raise OperationError('Import ID was already used with different export, owner, or workspace settings')
            return dict(workspace_id=existing['workspace_id'], imported=False, campaign_count=existing['campaign_count'], export_sha256=fingerprint)
        await self._check_identity(connection, identity)
        if await connection.fetchval('SELECT EXISTS(SELECT 1 FROM workspaces WHERE slug=$1)', slug):
            raise OperationError('Import requires a new workspace; slug already exists')
        campaign_ids = [c.campaign_id for c in document.campaigns]
        assets = [a.asset_id for c in document.campaigns if c.development for a in c.development.assets]
        if await connection.fetchval('SELECT EXISTS(SELECT 1 FROM campaigns WHERE campaign_id=ANY($1::uuid[]))', campaign_ids):
            raise OperationError('Campaign ID already exists outside this import')
        if await connection.fetchval('SELECT EXISTS(SELECT 1 FROM content_assets WHERE asset_id=ANY($1::uuid[]))', assets):
            raise OperationError('Asset ID already exists outside this import')
        return None

    async def import_campaigns(self, document: CampaignExport, import_id: UUID, name: str,
                               slug: str, owner_uid: str, *, dry_run=False):
        # Revalidate even callers passing an already constructed/mutated model.
        document = validate_export(document.model_dump(mode='json'))
        workspace_values(name, slug)
        identity = await self._identity(owner_uid)
        async with self.pool.acquire() as connection:
            async with connection.transaction(isolation='repeatable_read' if dry_run else 'read_committed', readonly=dry_run):
                if not dry_run:
                    await _lock(connection, 'campaign-import', import_id)
                    await _lock(connection, 'workspace-slug', slug)
                existing = await self._import_preflight(connection, document, import_id, name, slug, identity)
                if existing:
                    return dict(existing, dry_run=dry_run, import_id=import_id)
                if dry_run:
                    return dict(import_id=import_id, dry_run=True, imported=False, workspace_id=None,
                                campaign_count=document.campaign_count, export_sha256=export_hash(document))
                owner = await self._upsert_user(connection, identity)
                workspace = await connection.fetchval('''
                    INSERT INTO workspaces (name,slug,created_by_user_id) VALUES ($1,$2,$3) RETURNING workspace_id
                ''', name, slug, owner)
                repository = PostgresCampaignRepository(self.pool, workspace)
                for campaign in document.campaigns:
                    without_history = campaign.model_copy(deep=True)
                    without_history.approvals = []
                    await repository.create_in_transaction(connection, without_history, owner)
                    for position, approval in enumerate(campaign.approvals):
                        await connection.execute('''
                            INSERT INTO legacy_approval_history
                            (campaign_id,workspace_id,position,phase,decision,actor,comment,decided_at)
                            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                        ''', campaign.campaign_id, workspace, position, approval.phase.value,
                            approval.decision.value, approval.actor, approval.comment, approval.decided_at)
                    restored = await repository._get(connection, campaign.campaign_id)
                    if canonical(restored.state) != canonical(campaign):
                        raise MigrationError('Imported campaign does not match its source snapshot')
                await connection.execute('''
                    INSERT INTO campaign_imports
                    (import_id,export_sha256,workspace_id,owner_user_id,workspace_name,workspace_slug,campaign_count)
                    VALUES ($1,$2,$3,$4,$5,$6,$7)
                ''', import_id, export_hash(document), workspace, owner, name, slug, document.campaign_count)
                return dict(import_id=import_id, workspace_id=workspace, imported=True, dry_run=False,
                            campaign_count=document.campaign_count, export_sha256=export_hash(document))

    async def verify_import(self, document: CampaignExport, import_id: UUID):
        document = validate_export(document.model_dump(mode='json'))
        async with self.pool.acquire() as connection:
            async with connection.transaction(isolation='repeatable_read', readonly=True):
                await require_operator_schema(connection)
                ledger = await connection.fetchrow('SELECT * FROM campaign_imports WHERE import_id=$1', import_id)
                if ledger is None or ledger['export_sha256'] != export_hash(document):
                    raise OperationError('Import ledger does not match this export and import ID')
                workspace = ledger['workspace_id']
                ids = await connection.fetch('SELECT campaign_id FROM campaigns WHERE workspace_id=$1', workspace)
                if {row['campaign_id'] for row in ids} != {c.campaign_id for c in document.campaigns}:
                    raise MigrationError('Imported campaign set has changed')
                repository = PostgresCampaignRepository(self.pool, workspace)
                for campaign in document.campaigns:
                    restored = await repository._get(connection, campaign.campaign_id)
                    if (restored.created_by_user_id != ledger['owner_user_id'] or canonical(restored.state) != canonical(campaign)
                            or any(item.identity_source != 'legacy_unverified' for item in restored.approval_history)):
                        raise MigrationError('Imported campaign state, ownership, or history has changed')
                return dict(import_id=import_id, workspace_id=workspace, campaign_count=len(ids), verified=True)
