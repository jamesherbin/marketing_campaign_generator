from __future__ import annotations

import sys
from pathlib import Path

from .adk_runner import AdkRunnerAdapter
from .config import RunnerMode, Settings
from .adk_provider import configured_agent
from .models import (
    DevelopmentOutput,
    ExecutionOutput,
    MonitoringOutput,
    Phase,
    PlanningOutput,
)
from .orchestrator import (
    DevelopmentRunner,
    ExecutionRunner,
    MonitoringRunner,
    PhaseRunner,
    PlanningRunner,
)


class RunnerConfigurationError(RuntimeError):
    pass


def parse_runner_mode(value: str) -> RunnerMode:
    try:
        return RunnerMode(value.lower())
    except ValueError as exc:
        choices = ", ".join(mode.value for mode in RunnerMode)
        raise RunnerConfigurationError(
            f"Invalid runner mode {value!r}; expected one of: {choices}"
        ) from exc


def build_phase_runners(mode: RunnerMode, *, settings: Settings | None = None) -> dict[Phase, PhaseRunner]:
    if mode == RunnerMode.DETERMINISTIC:
        return {
            Phase.PLANNING: PlanningRunner(),
            Phase.DEVELOPMENT: DevelopmentRunner(),
            Phase.EXECUTION: ExecutionRunner(),
            Phase.MONITORING: MonitoringRunner(),
        }
    if mode == RunnerMode.ADK:
        return _build_adk_runners(settings or Settings())
    raise RunnerConfigurationError("Invalid runner mode; expected deterministic or adk")


def _build_adk_runners(settings: Settings) -> dict[Phase, PhaseRunner]:
    # The API and agents are sibling source packages in this repository. Keep the
    # checkout runnable without requiring a repository-level packaging migration.
    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from agents.development_agent import root_agent as development_agent
        from agents.execution_agent import root_agent as execution_agent
        from agents.monitoring_agent import root_agent as monitoring_agent
        from agents.planning_agent import root_agent as planning_agent
    except ImportError as exc:
        raise RunnerConfigurationError(f"Unable to import campaign agents: {exc}") from exc

    return {
        Phase.PLANNING: AdkRunnerAdapter(
            app_name="planning_agent",
            phase=Phase.PLANNING,
            output_model=PlanningOutput,
            agent=configured_agent(planning_agent, settings),
        ),
        Phase.DEVELOPMENT: AdkRunnerAdapter(
            app_name="development_agent",
            phase=Phase.DEVELOPMENT,
            output_model=DevelopmentOutput,
            agent=configured_agent(development_agent, settings),
        ),
        Phase.EXECUTION: AdkRunnerAdapter(
            app_name="execution_agent",
            phase=Phase.EXECUTION,
            output_model=ExecutionOutput,
            agent=configured_agent(execution_agent, settings),
        ),
        Phase.MONITORING: AdkRunnerAdapter(
            app_name="monitoring_agent",
            phase=Phase.MONITORING,
            output_model=MonitoringOutput,
            agent=configured_agent(monitoring_agent, settings),
        ),
    }
