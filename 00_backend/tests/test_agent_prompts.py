"""004-R6: deterministic checks of configured prompt boundaries, not model quality."""
import pytest

from campaign.config import RunnerMode, Settings
from campaign.runner_factory import build_phase_runners
from campaign.models import Phase


@pytest.fixture
def runners():
    return build_phase_runners(RunnerMode.ADK, settings=Settings(_env_file=None))


@pytest.mark.parametrize('phase', list(Phase))
def test_all_subagents_use_authoritative_brief_and_preserve_handoffs(runners, phase):
    available = {'campaign_brief', 'campaign_state'}
    available.update(f'{p.value}_output' for p in list(Phase)[:list(Phase).index(phase)])
    import re
    for agent in runners[phase].runner.agent.sub_agents:
        instruction = agent.instruction
        assert '{campaign_brief}' in instruction
        assert 'authoritative for industry, constraints, budget, and preferred channels' in instruction
        assert 'without inventing an industry' in instruction
        assert 'Consumer Packaged Goods' not in instruction
        assert 'approved planning' not in instruction
        assert 'approved strategy' not in instruction
        assert 'approved value proposition' not in instruction
        assert set(re.findall(r'\{(\w+)\}', instruction)) <= available
        available.add(agent.output_key)


def test_development_uses_text_model_and_draft_text_contract(runners):
    root = runners[Phase.DEVELOPMENT].runner.agent
    creative = next(agent for agent in root.sub_agents if agent.name == 'content_design_and_creation')
    assert creative.model.model == 'gemini-2.5-flash'
    for agent in (creative, root.sub_agents[-1]):
        instruction = agent.instruction.lower()
        assert 'draft text' in instruction
        assert 'visual concepts in words only' in instruction
        assert 'claim image files were generated or stored' in instruction
    assert 'completed planning output' in root.sub_agents[-1].instruction
    assert 'status draft' in root.sub_agents[-1].instruction


def test_execution_still_requires_approval_and_no_publication(runners):
    instruction = runners[Phase.EXECUTION].runner.agent.sub_agents[-1].instruction
    assert 'Every activity must remain prepared, not published or sent' in instruction
    assert 'human approval and external integrations are required' in instruction
