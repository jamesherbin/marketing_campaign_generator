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
