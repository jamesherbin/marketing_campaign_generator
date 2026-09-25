import asyncio
from datetime import timedelta, timezone
from uuid import uuid4
from unittest.mock import AsyncMock

import asyncpg
import httpx
import pytest

from campaign.config import DatabaseSettings
from campaign.database import database_pool
from campaign.migration import CampaignExport, SourceSnapshot, MigrationError, canonical, export_campaigns, load_export, write_export
from campaign.models import ApprovalDecision, CampaignBrief, CampaignState, utc_now
from campaign.operations import FirebaseIdentity, OperationError, OperatorService
from campaign.orchestrator import CampaignOrchestrator
from campaign.postgres_repository import PostgresCampaignRepository
from campaign.repository import InMemoryCampaignRepository

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def legacy_document():
    repo = InMemoryCampaignRepository()
    state = repo.create(CampaignState(brief=CampaignBrief(brand='Legacy', campaign_goal='Grow',
        target_audience=['Audience'], duration_weeks=4, budget=100), metadata={'creator':'untrusted-original'}))
    orchestrator = CampaignOrchestrator(repo)
    waiting = await orchestrator.run_until_blocked(state)
    approved = orchestrator.decide_execution(waiting, ApprovalDecision.APPROVED, 'Historical reviewer', 'Original note')
    complete = await orchestrator.run_until_blocked(approved)
    complete.created_at = complete.created_at.astimezone(timezone(timedelta(hours=2)))
    return CampaignExport(format_version=1, exported_at=utc_now(), sources=[SourceSnapshot(instance='old-1',url='http://localhost:8080',campaign_count=1)], campaign_count=1, campaigns=[complete])


def service(pools, **identity_overrides):
    async def lookup(uid):
        return FirebaseIdentity(uid, **identity_overrides)
    return OperatorService(pools['operator'], lookup)


async def test_workspace_and_membership_provisioning_is_explicit_and_repeatable(restricted_pools, migrated_pool):
    svc = service(restricted_pools)
    first, second = await asyncio.gather(svc.workspace_create('Team','team','new-user'), svc.workspace_create('Team','team','new-user'))
    assert first['workspace_id'] == second['workspace_id']
    assert sorted([first['created'],second['created']]) == [False, True]
    ws = first['workspace_id']
    assert await migrated_pool.fetchval('SELECT count(*) FROM workspace_members') == 0
    await svc.member_set(ws,'new-user','viewer')
    await svc.member_set(ws,'new-user','viewer')
    assert await migrated_pool.fetchval('SELECT count(*) FROM workspace_members') == 1
    await svc.member_set(ws,'new-user','runner')
    assert await migrated_pool.fetchval('SELECT role FROM workspace_members') == 'runner'
    svc.lookup = AsyncMock(side_effect=AssertionError('Suspension must not call Firebase'))
    await svc.member_suspend(ws,'new-user')
    await svc.member_suspend(ws,'new-user')
    assert await migrated_pool.fetchval('SELECT status FROM workspace_members') == 'suspended'
    with pytest.raises(OperationError):
        await service(restricted_pools).workspace_create('Different','team','new-user')
    with pytest.raises(OperationError):
        await service(restricted_pools).member_set(ws,'new-user','owner')


async def test_provisioning_rejects_identity_conflicts_and_disabled_accounts(restricted_pools, migrated_pool):
    first = service(restricted_pools, email='same@example.com')
    await first.workspace_create('One','one','first')
    with pytest.raises(OperationError, match='Email'):
        await first.workspace_create('Two','two','second')
    assert await migrated_pool.fetchval('SELECT count(*) FROM users') == 1
    with pytest.raises(OperationError, match='disabled'):
        await service(restricted_pools, disabled=True).workspace_create('Disabled','disabled','third')
    await migrated_pool.execute("UPDATE users SET status='disabled'")
    with pytest.raises(OperationError, match='disabled'):
        await first.workspace_create('Disabled','disabled','first')
    missing = OperatorService(restricted_pools['operator'], AsyncMock(side_effect=OperationError('Cannot verify Firebase user')))
    with pytest.raises(OperationError):
        await missing.workspace_create('Missing','missing','missing')
    assert await migrated_pool.fetchval('SELECT count(*) FROM workspaces') == 1


async def test_runtime_credentials_cannot_use_operator_commands(restricted_pools):
    svc = OperatorService(restricted_pools['runtime'], AsyncMock(return_value=FirebaseIdentity('new-user')))
    with pytest.raises(OperationError, match='Operator database privileges'):
        await svc.workspace_create('Denied','denied','new-user')
    with pytest.raises(OperationError, match='Operator database privileges'):
        await svc.import_campaigns(await legacy_document(),uuid4(),'Denied','denied','new-user',dry_run=True)


async def test_dry_run_is_read_only_and_real_import_preserves_all_state(restricted_pools, migrated_pool):
    doc = await legacy_document()
    svc = service(restricted_pools)
    import_id = uuid4()
    preview = await svc.import_campaigns(doc,import_id,'Migrated','migrated','new-owner',dry_run=True)
    assert preview['dry_run'] and preview['workspace_id'] is None
    for table in ('users','workspaces','campaigns','campaign_imports','legacy_approval_history'):
        assert await migrated_pool.fetchval(f'SELECT count(*) FROM {table}') == 0
    result = await svc.import_campaigns(doc,import_id,'Migrated','migrated','new-owner')
    restored = await PostgresCampaignRepository(restricted_pools['runtime'],result['workspace_id']).get(doc.campaigns[0].campaign_id)
    assert canonical(restored.state) == canonical(doc.campaigns[0])
    assert restored.approval_history[0].identity_source == 'legacy_unverified'
    assert restored.approval_history[0].actor_firebase_uid is None
    assert restored.approval_history[0].record.actor == 'Historical reviewer'
    assert await migrated_pool.fetchval('SELECT count(*) FROM approval_events') == 0
    assert await migrated_pool.fetchval('SELECT count(*) FROM workspace_members') == 0
    assert await migrated_pool.fetchval('SELECT firebase_uid FROM users WHERE user_id=$1',restored.created_by_user_id) == 'new-owner'
    assert (await svc.verify_import(doc,import_id))['verified']


async def test_concurrent_exact_import_retries_and_conflicting_inputs(restricted_pools, migrated_pool):
    svc = service(restricted_pools)
    doc, import_id = await legacy_document(), uuid4()
    results = await asyncio.gather(*(svc.import_campaigns(doc,import_id,'Migrated','migrated','new-owner') for _ in range(2)))
    assert sorted(r['imported'] for r in results) == [False, True]
    assert results[0]['workspace_id'] == results[1]['workspace_id']
    assert await migrated_pool.fetchval('SELECT count(*) FROM campaigns') == 1
    changed = doc.model_copy(deep=True)
    changed.campaigns[0].metadata['changed'] = True
    for payload, name, slug, owner in [(changed,'Migrated','migrated','new-owner'), (doc,'Other','migrated','new-owner'), (doc,'Migrated','other','new-owner'), (doc,'Migrated','migrated','different')]:
        with pytest.raises(OperationError, match='Import ID'):
            await svc.import_campaigns(payload,import_id,name,slug,owner)
    with pytest.raises(OperationError, match='new workspace'):
        await svc.import_campaigns(doc,uuid4(),'Migrated','migrated','new-owner')
    with pytest.raises(OperationError, match='Campaign ID'):
        await svc.import_campaigns(doc,uuid4(),'Other','other','new-owner')
    assert await migrated_pool.fetchval('SELECT count(*) FROM users') == 1


async def test_import_failure_rolls_back_everything_then_retry_succeeds(restricted_pools, migrated_pool):
    svc = service(restricted_pools)
    doc, import_id = await legacy_document(), uuid4()
    await migrated_pool.execute("""CREATE FUNCTION fail_ledger() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'simulated interruption'; END; $$;
        CREATE TRIGGER fail_import BEFORE INSERT ON campaign_imports FOR EACH ROW EXECUTE FUNCTION fail_ledger();""")
    with pytest.raises(asyncpg.RaiseError):
        await svc.import_campaigns(doc,import_id,'Migrated','migrated','new-owner')
    for table in ('users','workspaces','campaigns','campaign_briefs','planning_outputs','content_assets','phase_runs','legacy_approval_history','campaign_imports'):
        assert await migrated_pool.fetchval(f'SELECT count(*) FROM {table}') == 0
    await migrated_pool.execute('DROP TRIGGER fail_import ON campaign_imports')
    assert (await svc.import_campaigns(doc,import_id,'Migrated','migrated','new-owner'))['imported']


async def test_asset_collision_and_invalid_data_rejected_before_import(restricted_pools, migrated_pool):
    svc = service(restricted_pools)
    doc = await legacy_document()
    await svc.import_campaigns(doc,uuid4(),'First','first','new-owner')
    collision = doc.model_copy(deep=True)
    collision.campaigns[0].campaign_id = uuid4()
    with pytest.raises(OperationError, match='Asset ID'):
        await svc.import_campaigns(collision,uuid4(),'Second','second','new-owner',dry_run=True)
    collision.campaigns[0].brief.currency = 'usd'
    with pytest.raises(MigrationError):
        await svc.import_campaigns(collision,uuid4(),'Second','second','new-owner')
    assert await migrated_pool.fetchval('SELECT count(*) FROM workspaces') == 1


async def test_export_import_restart_rehearsal_and_drift_detection(restricted_pools, migrated_pool, isolated_database_url, tmp_path):
    original = await legacy_document()
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200,json=[c.model_dump(mode='json') for c in original.campaigns]))) as client:
        exported = await export_campaigns([('old-1','http://localhost:8080')],'test-session',quiesced=True,client=client)
    path = tmp_path / 'legacy.json'
    write_export(path,exported)
    loaded = load_export(path)
    svc, import_id = service(restricted_pools), uuid4()
    result = await svc.import_campaigns(loaded,import_id,'Migrated','migrated','new-owner')
    await svc.member_set(result['workspace_id'],'new-owner','approver')
    async with database_pool(DatabaseSettings(url=isolated_database_url,_env_file=None)) as reopened:
        assert (await OperatorService(reopened).verify_import(loaded,import_id))['verified']
        repo = PostgresCampaignRepository(reopened,result['workspace_id'])
        saved = (await repo.get(loaded.campaigns[0].campaign_id)).state
        saved.metadata['post-cutover'] = True
        await repo.save(saved)
    with pytest.raises(MigrationError,match='changed'):
        await svc.verify_import(loaded,import_id)
    retry = await svc.import_campaigns(loaded,import_id,'Migrated','migrated','new-owner')
    assert not retry['imported']
    assert (await PostgresCampaignRepository(migrated_pool,result['workspace_id']).get(saved.campaign_id)).state.metadata['post-cutover']


async def test_import_cannot_bypass_execution_approval(restricted_pools):
    doc = await legacy_document()
    doc.campaigns[0].approvals.clear()
    with pytest.raises(MigrationError, match='no approval'):
        await service(restricted_pools).import_campaigns(doc,uuid4(),'Invalid','invalid','new-owner',dry_run=True)
