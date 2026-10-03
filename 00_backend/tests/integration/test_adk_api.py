"""004-R4/R5/R7: real API, runtime DB grants and ADK adapters; no model calls."""
import asyncio
import json
from contextlib import asynccontextmanager
from copy import deepcopy
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
from google.adk.events import Event
from google.adk.sessions import InMemorySessionService
from google.genai import types

from campaign.auth import require_user
from campaign.config import Settings
from campaign.models import Phase
from main import create_app
from tests.integration.test_api import api, login, headers, BRIEF
from tests.test_agent_contracts import PAYLOADS

pytestmark = [pytest.mark.integration, pytest.mark.asyncio,
              pytest.mark.parametrize('api', ['adk'], indirect=True)]


class Events:
    def __init__(self, phase, calls):
        self.phase, self.calls = phase, calls
        self.session_service = InMemorySessionService()
        self.failure = None
        self.block = False
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.sessions = []
        self.contexts = []

    async def run_async(self, *, user_id, session_id, new_message):
        self.calls.append(self.phase)
        key = dict(app_name=f'{self.phase.value}_agent', user_id=user_id, session_id=session_id)
        self.sessions.append(key)
        session = await self.session_service.get_session(**key)
        self.contexts.append(deepcopy(session.state))
        self.entered.set()
        if self.block:
            await self.release.wait()
        if self.failure == 'provider':
            raise RuntimeError('private-provider-secret')
        payload = deepcopy(PAYLOADS[self.phase.value])
        if self.phase == Phase.MONITORING:
            payload['kpis'] = {'clicks': None, 'conversions': None}
        if self.failure == 'semantic':
            payload['assets'][0]['status'] = 'published'
        # Even a valid earlier phase-shaped response must not bypass final validation.
        yield Event(author='researcher', content=types.Content(parts=[types.Part(text=json.dumps(payload))]))
        text = 'private-malformed-output' if self.failure == 'malformed' else json.dumps(payload)
        yield Event(author=f'{self.phase.value}_synthesizer', content=types.Content(parts=[types.Part(text=text)]))

    async def assert_clean(self):
        for key in self.sessions:
            assert await self.session_service.get_session(**key) is None


@pytest_asyncio.fixture
async def adk_api(api):
    app, *_ = api
    calls, streams = [], {}
    for phase, adapter in app.state.runners.items():
        stream = Events(phase, calls)
        adapter.runner = stream
        streams[phase] = stream
    with patch('campaign.adk_provider.Client', side_effect=AssertionError('Live provider forbidden')):
        yield api, calls, streams
    for stream in streams.values():
        await stream.assert_clean()


async def create_campaign(client, ws):
    result = await client.post('/api/v1/campaigns', headers=headers(ws), json={
        'brief': BRIEF | {'success_metrics': ['clicks', 'conversions']}})
    assert result.status_code == 201, result.text
    return '/api/v1/campaigns/' + result.json()['campaign_id']


async def test_adk_approval_rejection_retry_and_restart_readback(adk_api, restricted_pools):
    (app, client, db, ws, other, ids, _), calls, streams = adk_api
    login(app, 'approver')
    path = await create_campaign(client, ws)
    assert (await client.get('/health')).json()['runner_mode'] == 'adk'
    waiting = await client.post(path + '/run', headers=headers(ws))
    assert waiting.status_code == 200, waiting.text
    assert waiting.json()['status'] == 'awaiting_approval'
    assert calls == [Phase.PLANNING, Phase.DEVELOPMENT, Phase.EXECUTION]
    assert (await client.post(path + '/phases/monitoring/run', headers=headers(ws))).status_code == 409
    rejected = await client.post(path + '/execution/approval', headers=headers(ws), json={'decision': 'rejected', 'comment': 'Revise'})
    assert rejected.status_code == 200
    assert rejected.json()['status'] == 'failed'
    retry = await client.post(path + '/run', headers=headers(ws))
    assert retry.status_code == 200 and retry.json()['status'] == 'awaiting_approval'
    assert calls == [Phase.PLANNING, Phase.DEVELOPMENT, Phase.EXECUTION, Phase.EXECUTION]
    execution = streams[Phase.EXECUTION]
    assert execution.sessions[0]['session_id'] != execution.sessions[1]['session_id']
    assert execution.contexts[1]['campaign_state']['execution'] is None
    assert 'execution_output' not in execution.contexts[1]
    approved = await client.post(path + '/execution/approval', headers=headers(ws), json={'decision': 'approved'})
    assert approved.status_code == 200
    history = approved.json()['approvals']
    assert [item['decision'] for item in history] == ['rejected', 'approved']
    assert all(item['actor_firebase_uid'] == 'approver' and item['identity_source'] == 'firebase_verified' for item in history)
    assert approved.json()['execution']['activities'][0]['status'] == 'prepared'
    result = await client.post(path + '/run', headers=headers(ws))
    assert result.status_code == 200, result.text
    finished = result.json()
    assert finished['status'] == 'completed'
    assert finished['monitoring']['kpis'] == {'clicks': None, 'conversions': None}
    assert calls[-1] == Phase.MONITORING
    assert await db.fetchval('SELECT count(*) FROM approval_events') == 2

    @asynccontextmanager
    async def pool(_):
        yield restricted_pools['runtime']

    fresh = create_app(database_settings_factory=lambda: None,
        settings_factory=lambda: Settings(campaign_runner_mode='adk', _env_file=None))
    with patch('main.database_pool', pool):
        async with fresh.router.lifespan_context(fresh):
            login(fresh, 'approver')
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fresh), base_url='http://fresh') as reader:
                assert (await reader.get(path, headers=headers(ws))).json() == finished
                assert (await reader.get(path, headers=headers(other))).status_code == 404
    assert finished['created_by_user_id'] == str(ids['approver'])


@pytest.mark.parametrize('failure', ['provider', 'malformed', 'semantic'])
async def test_adk_failure_persists_safe_error_and_retry_preserves_upstream(adk_api, failure):
    (app, client, _, ws, *_), calls, streams = adk_api
    login(app, 'runner')
    path = await create_campaign(client, ws)
    development = streams[Phase.DEVELOPMENT]
    development.failure = failure
    result = await client.post(path + '/run', headers=headers(ws))
    assert result.status_code == 502, result.text
    stored = (await client.get(path, headers=headers(ws))).json()
    assert stored['status'] == 'failed'
    assert stored['phase_runs']['development']['status'] == 'failed'
    assert stored['development'] is None and stored['execution'] is None
    assert 'private-' not in str(stored) + result.text
    assert calls == [Phase.PLANNING, Phase.DEVELOPMENT]
    await development.assert_clean()
    development.failure = None
    retry = await client.post(path + '/run', headers=headers(ws))
    assert retry.status_code == 200 and retry.json()['status'] == 'awaiting_approval'
    assert retry.json()['planning'] == stored['planning']
    assert calls == [Phase.PLANNING, Phase.DEVELOPMENT, Phase.DEVELOPMENT, Phase.EXECUTION]
    assert development.sessions[0]['session_id'] != development.sessions[1]['session_id']


async def test_adk_unauthorized_and_out_of_order_requests_never_invoke_agents(adk_api):
    (app, client, _, ws, other, _, foreign), calls, _ = adk_api
    login(app, 'approver')
    path = await create_campaign(client, ws)
    app.dependency_overrides.pop(require_user)
    assert (await client.post(path + '/run', headers=headers(ws))).status_code == 401
    for role in ('viewer', 'editor'):
        login(app, role)
        assert (await client.post(path + '/run', headers=headers(ws))).status_code == 403
    login(app, 'runner')
    assert (await client.post(path + '/run', headers=headers(other))).status_code == 404
    assert (await client.post(f'/api/v1/campaigns/{foreign}/run', headers=headers(ws))).status_code == 404
    assert (await client.post(path + '/phases/development/run', headers=headers(ws))).status_code == 409
    assert calls == []


@pytest.mark.parametrize('interruption', ['revocation', 'connection_loss'])
async def test_adk_competing_run_and_interrupted_commit_can_retry(adk_api, interruption):
    (app, client, db, ws, _, ids, _), calls, streams = adk_api
    login(app, 'runner')
    path = await create_campaign(client, ws)
    planning = streams[Phase.PLANNING]
    planning.block = True
    first = asyncio.create_task(client.post(path + '/run', headers=headers(ws)))
    try:
        await asyncio.wait_for(planning.entered.wait(), 3)
        assert (await client.post(path + '/run', headers=headers(ws))).status_code == 409
        assert calls == [Phase.PLANNING]
        if interruption == 'revocation':
            await db.execute("UPDATE workspace_members SET status='suspended' WHERE user_id=$1", ids['runner'])
            planning.release.set()
        else:
            pids = await db.fetch("SELECT DISTINCT pid FROM pg_locks WHERE locktype='advisory' AND database=(SELECT oid FROM pg_database WHERE datname=current_database())")
            assert len(pids) == 1
            await db.fetchval('SELECT pg_terminate_backend($1)', pids[0]['pid'])
        result = await asyncio.wait_for(first, 3)
        assert result.status_code == (404 if interruption == 'revocation' else 503)
    finally:
        planning.release.set()
        if not first.done():
            first.cancel()
        await asyncio.gather(first, return_exceptions=True)
    await planning.assert_clean()
    assert await db.fetchval('SELECT count(*) FROM planning_outputs') == 0
    await db.execute("UPDATE workspace_members SET status='active' WHERE user_id=$1", ids['runner'])
    planning.block = False
    retry = await client.post(path + '/run', headers=headers(ws))
    assert retry.status_code == 200 and retry.json()['status'] == 'awaiting_approval'
    assert planning.sessions[0]['session_id'] != planning.sessions[1]['session_id']
