import unittest

from campaign.adk_runner import AdkRunnerAdapter
from campaign.config import RunnerMode
from campaign.models import PHASE_ORDER, Phase
from campaign.orchestrator import PlanningRunner
from campaign.runner_factory import (
    RunnerConfigurationError,
    build_phase_runners,
    parse_runner_mode,
)


class RunnerFactoryTests(unittest.TestCase):
    def test_rejects_unknown_mode(self) -> None:
        with self.assertRaisesRegex(RunnerConfigurationError, "expected one of"):
            parse_runner_mode("unknown")

    def test_builds_all_deterministic_phase_runners(self) -> None:
        runners = build_phase_runners(RunnerMode.DETERMINISTIC)
        self.assertEqual(list(runners), PHASE_ORDER)
        self.assertIsInstance(runners[Phase.PLANNING], PlanningRunner)

    def test_builds_all_adk_phase_runners_without_calling_models(self) -> None:
        runners = build_phase_runners(RunnerMode.ADK)
        self.assertEqual(list(runners), PHASE_ORDER)
        for phase, runner in runners.items():
            self.assertIsInstance(runner, AdkRunnerAdapter)
            self.assertEqual(runner.phase, phase)
            self.assertEqual(runner.app_name, f"{phase.value}_agent")


if __name__ == "__main__":
    unittest.main()


def test_factory_rejects_invalid_mode_without_constructing_adk():
    from unittest.mock import patch
    import pytest

    with patch('campaign.runner_factory._build_adk_runners') as adk:
        with pytest.raises(RunnerConfigurationError):
            build_phase_runners('unknown')
        adk.assert_not_called()


def test_every_phase_maps_to_its_canonical_agent_and_output():
    import os
    from unittest.mock import patch
    from campaign.config import Settings
    from campaign.models import PlanningOutput, DevelopmentOutput, ExecutionOutput, MonitoringOutput
    from campaign.orchestrator import DevelopmentRunner, ExecutionRunner, MonitoringRunner
    from agents.planning_agent import root_agent as planning
    from agents.development_agent import root_agent as development
    from agents.execution_agent import root_agent as execution
    from agents.monitoring_agent import root_agent as monitoring

    with patch.dict(os.environ, {}, clear=True), patch('campaign.adk_provider.Client') as client:
        settings = Settings(_env_file=None)
        deterministic = build_phase_runners(settings.runner_mode, settings=settings)
        adk = build_phase_runners(RunnerMode.ADK, settings=settings)
        expected = zip(PHASE_ORDER,
                       [PlanningRunner, DevelopmentRunner, ExecutionRunner, MonitoringRunner],
                       [planning, development, execution, monitoring],
                       [PlanningOutput, DevelopmentOutput, ExecutionOutput, MonitoringOutput], strict=True)
        for phase, runner_type, source, output_type in expected:
            assert type(deterministic[phase]) is runner_type
            adapter = adk[phase]
            assert adapter.phase == phase
            assert adapter.app_name == f'{phase.value}_agent'
            assert adapter.output_model is output_type
            clone = adapter.runner.agent
            assert clone is not source
            assert [a.name for a in clone.sub_agents] == [a.name for a in source.sub_agents]
            assert clone.sub_agents[-1].output_key == phase.value
        client.assert_not_called()
