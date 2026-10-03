"""004-R3/R5: select and validate only the designated synthesizer result."""
import json

import pytest
from google.adk.events import Event
from google.genai import types

from campaign.adk_runner import AdkRunnerError
from campaign.models import PHASE_ORDER, Phase
from tests.test_adk_context import OUTPUTS, adapter, campaign
from tests.test_adk_runner import FakeRunner


def event(author, text, *, partial=False):
    return Event(author=author, partial=partial,
        content=types.Content(role='model', parts=[] if text is None else [types.Part(text=text)]))


@pytest.mark.asyncio
@pytest.mark.parametrize('phase', PHASE_ORDER)
@pytest.mark.parametrize('fenced', [False, True])
async def test_only_expected_synthesizer_can_supply_output(phase, fenced):
    payload = OUTPUTS[phase].model_dump_json()
    text = f'```json\n{payload}\n```' if fenced else payload
    runner = FakeRunner([
        event('researcher', 'earlier final'),
        event(f'{phase.value}_synthesizer', 'partial', partial=True),
        event(f'{phase.value}_synthesizer', text),
        event('other_synthesizer', 'later final'),
    ])
    state = campaign()
    before = state.model_dump_json()
    assert await adapter(phase, runner).run(state) == OUTPUTS[phase]
    assert state.model_dump_json() == before
    assert runner.session_service.deleted_with['session_id'] == 'session-1'


@pytest.mark.asyncio
@pytest.mark.parametrize('phase', PHASE_ORDER)
@pytest.mark.parametrize('bad', ['missing', 'empty', 'partial', 'malformed', 'prose', 'array', 'wrong_phase', 'last_empty', 'last_invalid'])
async def test_invalid_or_missing_final_never_falls_back(phase, bad):
    payload = OUTPUTS[phase].model_dump_json()
    name = f'{phase.value}_synthesizer'
    events = [event('researcher', payload)]
    if bad.startswith('last_'):
        events.append(event(name, payload))
    alternatives = {
        'empty': '', 'malformed': 'private invalid output', 'prose': f'Result: {payload}',
        'array': f'[{payload}]',
        'wrong_phase': OUTPUTS[PHASE_ORDER[(PHASE_ORDER.index(phase)+1)%4]].model_dump_json(),
        'last_empty': '', 'last_invalid': 'private invalid output',
    }
    if bad == 'partial':
        events.append(event(name, payload, partial=True))
    elif bad != 'missing':
        events.append(event(name, alternatives[bad]))
    runner = FakeRunner(events)
    state = campaign()
    before = state.model_dump_json()
    with pytest.raises(AdkRunnerError) as error:
        await adapter(phase, runner).run(state)
    assert 'private' not in str(error.value)
    assert state.model_dump_json() == before
    assert runner.session_service.deleted_with['session_id'] == 'session-1'


@pytest.mark.asyncio
@pytest.mark.parametrize('phase,change', [
    (Phase.PLANNING, {'budget_by_channel': {'email': 'private invalid number'}}),
    (Phase.DEVELOPMENT, {'assets': [{'asset_id': 'private invalid uuid', 'channel': 'email', 'format': 'text', 'headline': 'Hi', 'body': 'Body'}]}),
    (Phase.EXECUTION, {'activities': [{'channel': 'email', 'action': 'prepare', 'scheduled_for': 'private invalid date'}]}),
    (Phase.MONITORING, {'kpis': {'clicks': {'private': 'invalid nested object'}}}),
])
async def test_invalid_nested_contracts_are_rejected_without_raw_details(phase, change):
    payload = OUTPUTS[phase].model_dump(mode='json') | change
    runner = FakeRunner([event(f'{phase.value}_synthesizer', json.dumps(payload))])
    with pytest.raises(AdkRunnerError) as error:
        await adapter(phase, runner).run(campaign())
    assert str(error.value) == f'{phase.value} agent returned an invalid {type(OUTPUTS[phase]).__name__}'
    assert runner.session_service.deleted_with


@pytest.mark.asyncio
async def test_explicit_synthesizer_identity_overrides_phase_default():
    runner = FakeRunner([event('custom_final', OUTPUTS[Phase.PLANNING].model_dump_json())])
    instance = adapter(Phase.PLANNING, runner)
    instance.synthesizer_name = 'custom_final'
    assert await instance.run(campaign()) == OUTPUTS[Phase.PLANNING]
