"""004-R2: model context excludes stale results and isolates each attempt."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from google.adk.sessions import InMemorySessionService

from campaign.adk_runner import AdkRunnerAdapter, AdkRunnerError
from campaign.models import (
    PHASE_ORDER, CampaignBrief, CampaignState, Phase, PhaseStatus,
    PlanningOutput, DevelopmentOutput, ExecutionOutput, MonitoringOutput,
)

OUTPUTS = {
    Phase.PLANNING: PlanningOutput(goals=['planning-marker'], measurable_objectives=[],
        audience_segments=[], positioning_statement='', value_proposition='',
        key_messages=[], recommended_channels=[], budget_by_channel={}),
    Phase.DEVELOPMENT: DevelopmentOutput(creative_direction='development-marker', assets=[], media_plan={}),
    Phase.EXECUTION: ExecutionOutput(activities=[], publication_summary='execution-marker'),
    Phase.MONITORING: MonitoringOutput(kpis={}, analysis=[], recommendations=[], stakeholder_summary='monitoring-marker'),
}


def campaign():
    result = CampaignState(brief=CampaignBrief(brand='Brand', campaign_goal='Grow',
        target_audience=['People'], duration_weeks=4, budget=100))
    for phase, output in OUTPUTS.items():
        setattr(result, phase.value, output.model_copy(deep=True))
        result.phase_runs[phase].status = PhaseStatus.COMPLETED
    return result


class RecordingRunner:
    """Real ADK session storage, fake event stream; never invokes a model."""
    def __init__(self, phase, concurrent=False, fail_first=False):
        self.session_service = InMemorySessionService()
        self.phase = phase
        self.calls = []
        self.concurrent = concurrent
        self.fail_first = fail_first
        self.both_started = asyncio.Event()

    async def run_async(self, *, user_id, session_id, new_message):
        session = await self.session_service.get_session(
            app_name=f'{self.phase.value}_agent', user_id=user_id, session_id=session_id)
        initial = json.loads(json.dumps(session.state))
        self.calls.append((user_id, session_id, initial, new_message.parts[0].text))
        # Mimic intermediate output_key writes to actual ADK session storage.
        from google.adk.events import Event, EventActions
        await self.session_service.append_event(session, Event(
            author='intermediate', actions=EventActions(state_delta={'intermediate': user_id})))
        if self.concurrent:
            if len(self.calls) == 2:
                self.both_started.set()
            await asyncio.wait_for(self.both_started.wait(), timeout=2)
            saved = await self.session_service.get_session(
                app_name=f'{self.phase.value}_agent', user_id=user_id, session_id=session_id)
            assert saved.state['intermediate'] == user_id
        text = 'invalid' if self.fail_first and len(self.calls) == 1 else OUTPUTS[self.phase].model_dump_json()
        yield SimpleNamespace(author=f"{self.phase.value}_synthesizer", is_final_response=lambda: True,
            content=SimpleNamespace(parts=[SimpleNamespace(text=text)]))


def adapter(phase, runner):
    return AdkRunnerAdapter(app_name=f'{phase.value}_agent', phase=phase,
        output_model=type(OUTPUTS[phase]), runner=runner)


@pytest.mark.asyncio
@pytest.mark.parametrize('phase', PHASE_ORDER)
@pytest.mark.parametrize('upstream_status', list(PhaseStatus))
async def test_only_completed_upstream_results_reach_both_context_surfaces(phase, upstream_status):
    state = campaign()
    for run in state.phase_runs.values():
        run.status = upstream_status
    before = state.model_dump_json()
    runner = RecordingRunner(phase)
    await adapter(phase, runner).run(state)
    _, _, session, prompt = runner.calls[0]
    prompt_state = json.loads(prompt.split('CampaignState:\n', 1)[1])
    for candidate in PHASE_ORDER:
        included = PHASE_ORDER.index(candidate) < PHASE_ORDER.index(phase) and upstream_status == PhaseStatus.COMPLETED
        assert (f'{candidate.value}_output' in session) == included
        assert (session['campaign_state'][candidate.value] is not None) == included
        assert (candidate.value in prompt_state) == included
        if included:
            assert session[f'{candidate.value}_output'] == OUTPUTS[candidate].model_dump(mode='json')
    assert state.model_dump_json() == before
    assert session['campaign_brief'] == state.brief.model_dump(mode='json')


@pytest.mark.asyncio
@pytest.mark.parametrize('fail_first', [False, True])
async def test_execution_retry_has_fresh_session_and_no_stale_package(fail_first):
    state = campaign()
    state.phase_runs[Phase.EXECUTION].status = PhaseStatus.FAILED
    before = state.model_dump_json()
    runner = RecordingRunner(Phase.EXECUTION, fail_first=fail_first)
    phase_adapter = adapter(Phase.EXECUTION, runner)
    if fail_first:
        with pytest.raises(AdkRunnerError):
            await phase_adapter.run(state)
    else:
        await phase_adapter.run(state)
    await phase_adapter.run(state)
    assert runner.calls[0][1] != runner.calls[1][1]
    for _, _, session, prompt in runner.calls:
        assert 'intermediate' not in session
        assert 'execution_output' not in session
        assert 'execution-marker' not in prompt
        assert session['campaign_state']['execution'] is None
        assert 'planning_output' in session and 'development_output' in session
    assert state.model_dump_json() == before


@pytest.mark.asyncio
async def test_concurrent_campaigns_do_not_share_session_writes():
    first, second = campaign(), campaign()
    first.brief.brand, second.brief.brand = 'First', 'Second'
    runner = RecordingRunner(Phase.DEVELOPMENT, concurrent=True)
    phase_adapter = adapter(Phase.DEVELOPMENT, runner)
    await asyncio.gather(phase_adapter.run(first), phase_adapter.run(second))
    assert len({call[1] for call in runner.calls}) == 2
    by_user = {call[0]: call[2] for call in runner.calls}
    assert by_user[str(first.campaign_id)]['campaign_brief']['brand'] == 'First'
    assert by_user[str(second.campaign_id)]['campaign_brief']['brand'] == 'Second'
    assert all('intermediate' not in call[2] for call in runner.calls)
