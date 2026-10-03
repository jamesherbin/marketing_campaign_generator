"""004-R7: run via stdin inside the root-context backend image, without networking."""
import importlib
import os
from pathlib import Path
from unittest.mock import patch

from campaign.adk_provider import ConfiguredGemini
from campaign.adk_runner import AdkRunnerAdapter
from campaign.config import RunnerMode, Settings
from campaign.models import PHASE_ORDER
from campaign.runner_factory import build_phase_runners
from main import app

assert os.getuid() == 10001, 'Image must use its unprivileged runtime user'
assert app.title == 'Marketing Campaign Orchestrator API'
assert not Path('/app/00_backend/.env').exists()
assert not any(key in os.environ for key in (
    'GOOGLE_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_APPLICATION_CREDENTIALS', 'DATABASE_URL',
)), 'Smoke check must run without injected credentials'

with patch('campaign.adk_provider.Client', side_effect=AssertionError('Provider call forbidden')):
    settings = Settings(_env_file=None)
    assert settings.runner_mode == RunnerMode.DETERMINISTIC
    for mode in RunnerMode:
        runners = build_phase_runners(mode, settings=settings)
        assert list(runners) == PHASE_ORDER
        if mode == RunnerMode.ADK:
            for phase, runner in runners.items():
                assert isinstance(runner, AdkRunnerAdapter)
                package = importlib.import_module(f'agents.{phase.value}_agent')
                assert Path(package.__file__).is_relative_to('/app/agents')
                assert runner.runner.agent is not package.root_agent
                assert runner.synthesizer_name == runner.runner.agent.sub_agents[-1].name
                assert runner.runner.agent.sub_agents[-1].output_key == phase.value
                for agent in runner.runner.agent.sub_agents:
                    assert isinstance(agent.model, ConfiguredGemini)
        print(f'PASS: {mode.value} constructs all four phase runners')
print('PASS: API import, packaged agents, and unprivileged credential-free construction')
