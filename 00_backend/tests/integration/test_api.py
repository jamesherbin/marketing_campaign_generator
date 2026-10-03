import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio

from campaign.auth import AuthenticatedUser, require_user
from campaign.config import DatabaseSettings, RunnerMode, Settings
from campaign.database import DatabaseStartupError
from campaign.models import CampaignBrief, CampaignState, Phase
from campaign.orchestrator import PlanningRunner
from campaign.postgres_repository import PostgresCampaignRepository
from campaign.runner_factory import build_phase_runners
from main import create_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
BRIEF = dict(brand='Example', campaign_goal='Grow', target_audience=['Audience'], duration_weeks=4, budget=100)


@pytest_asyncio.fixture
async def api(migrated_pool, restricted_pools, request):
    ids = {}
    owner = await migrated_pool.fetchval("INSERT INTO users (firebase_uid) VALUES ('approver') RETURNING user_id")
    ws = await migrated_pool.fetchval("INSERT INTO workspaces (name, slug, created_by_user_id) VALUES ('Main','main',$1) RETURNING workspace_id", owner)
    other = await migrated_pool.fetchval("INSERT INTO workspaces (name, slug, created_by_user_id) VALUES ('Other','other',$1) RETURNING workspace_id", owner)
    for role in ('viewer', 'editor', 'runner', 'approver'):
        uid = owner if role == 'approver' else await migrated_pool.fetchval('INSERT INTO users (firebase_uid) VALUES ($1) RETURNING user_id', role)
        ids[role] = uid
        await migrated_pool.execute("INSERT INTO workspace_members (workspace_id,user_id,role,status) VALUES ($1,$2,$3,'active')", ws, uid, role)
    foreign = (await PostgresCampaignRepository(migrated_pool, other).create(CampaignState(brief=CampaignBrief(**BRIEF)), owner)).state.campaign_id
    app = create_app()
    @asynccontextmanager
    async def test_pool(_settings):
        yield restricted_pools['runtime']
    with patch('main.database_pool', test_pool), patch('main.DatabaseSettings'):
        # The default factory was captured at definition time; pass it explicitly.
        app = create_app(database_settings_factory=lambda: None, settings_factory=lambda: Settings(campaign_runner_mode=getattr(request, 'param', 'deterministic'), _env_file=None))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                yield app, client, migrated_pool, ws, other, ids, foreign


def login(app, role):
    # Token roles intentionally lie: authorization must use database membership.
    app.dependency_overrides[require_user] = lambda: AuthenticatedUser(role, f'{role}@example.com', None, ('approver',))


def headers(ws):
    return {'X-Workspace-ID': str(ws)}


async def create(client, ws):
    result = await client.post('/api/v1/campaigns', headers=headers(ws), json={'brief': BRIEF})
    assert result.status_code == 201, result.text
    return result.json()['campaign_id']


async def test_full_lifecycle_and_verified_self_approval(api):
    app, client, db, ws, _, ids, _ = api
    login(app, 'approver')
    cid = await create(client, ws)
    waiting = await client.post(f'/api/v1/campaigns/{cid}/run', headers=headers(ws))
    assert waiting.status_code == 200, waiting.text
    assert waiting.json()['status'] == 'awaiting_approval'
    assert waiting.json()['created_by_user_id'] == str(ids['approver'])
    approved = await client.post(f'/api/v1/campaigns/{cid}/execution/approval', headers=headers(ws), json={'decision': 'approved'})
    assert approved.status_code == 200, approved.text
    event = approved.json()['approvals'][0]
    assert event['actor_firebase_uid'] == 'approver'
    assert event['identity_source'] == 'firebase_verified'
    assert event['actor'] == 'approver@example.com'
    finished = await client.post(f'/api/v1/campaigns/{cid}/run', headers=headers(ws))
    assert finished.json()['status'] == 'completed'
    assert await db.fetchval('SELECT count(*) FROM approval_events') == 1
    assert (await client.post(f'/api/v1/campaigns/{cid}/run', headers=headers(ws))).status_code == 409


@pytest.mark.parametrize('role', ['viewer', 'editor', 'runner', 'approver'])
async def test_all_routes_role_matrix_and_foreign_ids(api, role):
    app, client, db, ws, other, ids, foreign = api
    login(app, 'approver')
    cid = await create(client, ws)
    await client.post(f'/api/v1/campaigns/{cid}/run', headers=headers(ws))
    login(app, role)
    assert (await client.get('/api/v1/workspaces')).json()[0]['role'] == role
    assert (await client.get('/api/v1/campaigns', headers=headers(ws))).status_code == 200
    assert (await client.get(f'/api/v1/campaigns/{cid}', headers=headers(ws))).status_code == 200
    created = await client.post('/api/v1/campaigns', headers=headers(ws), json={'brief': BRIEF})
    assert created.status_code == (403 if role == 'viewer' else 201)
    run_id = cid if role == 'viewer' else created.json()['campaign_id']
    for suffix in ('/phases/planning/run', '/run'):
        result = await client.post(f'/api/v1/campaigns/{run_id}{suffix}', headers=headers(ws))
        assert result.status_code == (200 if role in ('runner', 'approver') else 403), result.text
    before = await db.fetchval('SELECT version FROM campaigns WHERE campaign_id=$1', UUID(cid))
    decision = await client.post(f'/api/v1/campaigns/{cid}/execution/approval', headers=headers(ws), json={'decision':'rejected'})
    assert decision.status_code == (200 if role == 'approver' else 403)
    if role != 'approver':
        assert await db.fetchval('SELECT version FROM campaigns WHERE campaign_id=$1', UUID(cid)) == before
    for foreign_id in (foreign, uuid4()):
        for method, suffix, body in [('GET','',None), ('POST','/run',None), ('POST','/phases/planning/run',None), ('POST','/execution/approval',{'decision':'approved'})]:
            result = await client.request(method, f'/api/v1/campaigns/{foreign_id}{suffix}', headers=headers(ws), json=body)
            assert result.status_code == 404, result.text
    assert (await client.get('/api/v1/campaigns', headers=headers(other))).status_code == 404


@pytest.mark.parametrize('session', ['missing', 'invalid', 'expired', 'revoked'])
async def test_session_failure_across_routes(api, session):
    app, client, db, ws, _, _, foreign = api
    from firebase_admin import auth
    exceptions = {'invalid': auth.InvalidSessionCookieError('bad'), 'expired': auth.ExpiredSessionCookieError('old', ValueError('expired')), 'revoked': auth.RevokedSessionCookieError('revoked')}
    with patch('campaign.auth.initialize_firebase', return_value=object()), patch('campaign.auth.auth.verify_session_cookie', side_effect=exceptions.get(session)):
        h = {} if session == 'missing' else {'Authorization': 'FirebaseSession cookie'}
        for method, path, body in [('GET','/api/v1/workspaces',None), ('GET','/api/v1/campaigns',None), ('POST','/api/v1/campaigns',{'brief':BRIEF}), ('GET',f'/api/v1/campaigns/{foreign}',None), ('POST',f'/api/v1/campaigns/{foreign}/run',None), ('POST',f'/api/v1/campaigns/{foreign}/phases/planning/run',None), ('POST',f'/api/v1/campaigns/{foreign}/execution/approval',{'decision':'approved'})]:
            result = await client.request(method, path, headers=h, json=body)
            assert result.status_code == 401, result.text
    assert await db.fetchval('SELECT count(*) FROM campaigns') == 1


async def test_forged_inputs_and_membership_status(api):
    app, client, db, ws, _, ids, _ = api
    login(app, 'approver')
    assert (await client.get('/api/v1/campaigns')).status_code == 422
    assert (await client.get('/api/v1/campaigns', headers={'X-Workspace-ID':'bad'})).status_code == 422
    assert (await client.post('/api/v1/campaigns', headers=headers(ws), json={'brief':BRIEF,'workspace_id':str(ws)})).status_code == 422
    cid = await create(client, ws)
    assert (await client.post(f'/api/v1/campaigns/{cid}/execution/approval', headers=headers(ws), json={'decision':'approved','actor':'forged'})).status_code == 422
    await db.execute("UPDATE workspace_members SET status='suspended' WHERE user_id=$1", ids['approver'])
    assert (await client.get('/api/v1/workspaces')).json() == []
    assert (await client.get('/api/v1/campaigns', headers=headers(ws))).status_code == 404
    await db.execute("UPDATE users SET status='disabled' WHERE user_id=$1", ids['approver'])
    assert (await client.get('/api/v1/workspaces')).status_code == 403
    login(app, 'unprovisioned')
    assert (await client.get('/api/v1/workspaces')).json() == []


class SlowRunner:
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.calls = 0

    async def run(self, state):
        self.calls += 1
        self.entered.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return await PlanningRunner().run(state)


async def test_concurrent_run_and_revocation_during_run(api):
    app, client, db, ws, _, ids, _ = api
    login(app, 'runner')
    cid = await create(client, ws)
    slow = SlowRunner()
    app.state.runners[Phase.PLANNING] = slow
    first = asyncio.create_task(client.post(f'/api/v1/campaigns/{cid}/run', headers=headers(ws)))
    await asyncio.wait_for(slow.entered.wait(), 3)
    try:
        assert (await client.post(f'/api/v1/campaigns/{cid}/run', headers=headers(ws))).status_code == 409
        assert slow.calls == 1
        await db.execute("UPDATE workspace_members SET status='suspended' WHERE user_id=$1", ids['runner'])
    finally:
        slow.release.set()
    assert (await first).status_code == 404
    assert await db.fetchval('SELECT count(*) FROM planning_outputs') == 0
    await db.execute("UPDATE workspace_members SET status='active' WHERE user_id=$1", ids['runner'])
    app.state.runners[Phase.PLANNING] = PlanningRunner()
    assert (await client.post(f'/api/v1/campaigns/{cid}/run', headers=headers(ws))).json()['status'] == 'awaiting_approval'


async def test_lock_connection_loss_cancels_runner_and_can_retry(api):
    app, client, db, ws, _, _, _ = api
    login(app, 'runner')
    cid = await create(client, ws)
    slow = SlowRunner()
    app.state.runners[Phase.PLANNING] = slow
    first = asyncio.create_task(client.post(f'/api/v1/campaigns/{cid}/run', headers=headers(ws)))
    await asyncio.wait_for(slow.entered.wait(), 3)
    pids = await db.fetch("SELECT DISTINCT pid FROM pg_locks WHERE locktype='advisory' AND database=(SELECT oid FROM pg_database WHERE datname=current_database())")
    assert len(pids) == 1
    await db.fetchval('SELECT pg_terminate_backend($1)', pids[0]['pid'])
    result = await asyncio.wait_for(first, 3)
    assert result.status_code == 503
    assert slow.cancelled.is_set()
    assert await db.fetchval('SELECT count(*) FROM planning_outputs') == 0
    app.state.runners[Phase.PLANNING] = PlanningRunner()
    assert (await client.post(f'/api/v1/campaigns/{cid}/run', headers=headers(ws))).status_code == 200


async def test_failed_runner_persists_safe_error_and_retries(api):
    app, client, db, ws, _, _, _ = api
    login(app, 'runner')
    cid = await create(client, ws)
    class Broken:
        async def run(self, state):
            state.brief.brand = 'unauthorized mutation'
            raise RuntimeError('provider-secret')
    app.state.runners[Phase.PLANNING] = Broken()
    result = await client.post(f'/api/v1/campaigns/{cid}/run', headers=headers(ws))
    assert result.status_code == 502
    stored = (await client.get(f'/api/v1/campaigns/{cid}', headers=headers(ws))).json()
    assert stored['status'] == 'failed'
    assert stored['brief']['brand'] == 'Example'
    assert 'provider-secret' not in str(stored)
    app.state.runners[Phase.PLANNING] = PlanningRunner()
    assert (await client.post(f'/api/v1/campaigns/{cid}/run', headers=headers(ws))).status_code == 200


async def test_approval_rollback_and_duplicate_decisions(api):
    app, client, db, ws, _, _, _ = api
    login(app, 'approver')
    cid = await create(client, ws)
    waiting = (await client.post(f'/api/v1/campaigns/{cid}/run', headers=headers(ws))).json()
    await db.execute("""CREATE FUNCTION reject_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'secret failure'; END; $$;
        CREATE TRIGGER audit_fail BEFORE INSERT ON approval_events FOR EACH ROW EXECUTE FUNCTION reject_audit();""")
    path = f'/api/v1/campaigns/{cid}/execution/approval'
    failed = await client.post(path, headers=headers(ws), json={'decision':'approved'})
    assert failed.status_code == 503
    assert 'secret failure' not in failed.text
    assert (await client.get(f'/api/v1/campaigns/{cid}', headers=headers(ws))).json() == waiting
    await db.execute('DROP TRIGGER audit_fail ON approval_events')
    results = await asyncio.gather(*(client.post(path, headers=headers(ws), json={'decision':'approved'}) for _ in range(2)))
    assert sorted(r.status_code for r in results) == [200,409]
    assert await db.fetchval('SELECT count(*) FROM approval_events') == 1


async def test_actual_lifespan_rejects_unmigrated_database(isolated_database_url):
    app = create_app(database_settings_factory=lambda: DatabaseSettings(url=isolated_database_url, _env_file=None))
    with pytest.raises(DatabaseStartupError):
        async with app.router.lifespan_context(app):
            pytest.fail('Unmigrated database accepted')
    assert not hasattr(app.state, 'database_pool')
