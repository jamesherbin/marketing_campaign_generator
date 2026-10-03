"""004-R6: generation-only safeguards preserve historical runtime contracts."""
import json
from copy import deepcopy

import pytest

from campaign.adk_runner import AdkRunnerError
from campaign.models import Phase, CampaignState
from tests.test_adk_context import OUTPUTS, adapter, campaign
from tests.test_adk_runner import FakeRunner
from tests.test_adk_synthesizer import event


async def invoke(phase, payload, metrics=()):
    state = campaign()
    state.brief.success_metrics = list(metrics)
    state.metadata = {'analytics': {'clicks': 99}, 'analytics_connected': True}
    before = state.model_dump_json()
    runner = FakeRunner([event(f'{phase.value}_synthesizer', json.dumps(payload))])
    try:
        return await adapter(phase, runner).run(state)
    finally:
        assert state.model_dump_json() == before
        assert runner.session_service.deleted_with['session_id'] == 'session-1'


@pytest.mark.asyncio
@pytest.mark.parametrize('phase,field,item,expected', [
    (Phase.DEVELOPMENT, 'assets', dict(channel='email', format='text', headline='Hi', body='Body'), 'draft'),
    (Phase.EXECUTION, 'activities', dict(channel='email', action='Prepare'), 'prepared'),
])
@pytest.mark.parametrize('status', [None, 'expected', 'published', 'sent', 'approved', 'DRAFT', 'private-secret'])
async def test_generation_statuses_are_exact_and_defaults_are_accepted(phase, field, item, expected, status):
    payload = OUTPUTS[phase].model_dump(mode='json')
    value = deepcopy(item)
    if status is not None:
        value['status'] = expected if status == 'expected' else status
    # Include a valid first item to ensure every item is checked.
    payload[field] = [item, value]
    if status in (None, 'expected'):
        result = await invoke(phase, payload)
        assert all(entry.status == expected for entry in getattr(result, field))
    else:
        with pytest.raises(AdkRunnerError) as error:
            await invoke(phase, payload)
        assert 'private-secret' not in str(error.value)
        # The same historic value remains readable through the canonical state model.
        historical = campaign().model_dump(mode='json')
        historical[phase.value] = payload
        assert getattr(CampaignState.model_validate(historical), phase.value)


@pytest.mark.asyncio
@pytest.mark.parametrize('metrics,kpis,valid', [
    ([], {}, True),
    ([], {'extra': None}, True),
    (['clicks', 'conversions'], {'clicks': None, 'conversions': None}, True),
    (['clicks', 'clicks'], {'clicks': None, 'extra': None}, True),
    (['clicks'], {}, False),
    (['clicks'], {'Clicks': None}, False),
    (['clicks'], {'clicks': 0}, False),
    (['clicks'], {'clicks': 2.5}, False),
    (['clicks'], {'clicks': 'unavailable'}, False),
    (['clicks'], {'clicks': None, 'extra': 0}, False),
    ([], {'extra': 'private-secret'}, False),
])
async def test_monitoring_requires_exact_requested_keys_and_only_null_values(metrics, kpis, valid):
    payload = OUTPUTS[Phase.MONITORING].model_dump(mode='json') | {'kpis': kpis}
    if valid:
        assert (await invoke(Phase.MONITORING, payload, metrics)).kpis == kpis
    else:
        with pytest.raises(AdkRunnerError) as error:
            await invoke(Phase.MONITORING, payload, metrics)
        assert 'private-secret' not in str(error.value)
        historical = campaign().model_dump(mode='json')
        historical['monitoring'] = payload
        assert CampaignState.model_validate(historical).monitoring.kpis == kpis
