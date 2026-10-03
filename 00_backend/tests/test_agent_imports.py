import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class AgentImportTests(unittest.TestCase):
    def test_canonical_packages_export_root_agents(self) -> None:
        from agents.development_agent import root_agent as development
        from agents.execution_agent import root_agent as execution
        from agents.monitoring_agent import root_agent as monitoring
        from agents.planning_agent import root_agent as planning

        self.assertEqual(planning.name, "root_agent")
        self.assertEqual(development.name, "root_agent")
        self.assertEqual(execution.name, "root_agent")
        self.assertEqual(monitoring.name, "root_agent")

    def test_each_root_agent_finishes_with_structured_synthesizer(self) -> None:
        from agents.development_agent import root_agent as development
        from agents.execution_agent import root_agent as execution
        from agents.monitoring_agent import root_agent as monitoring
        from agents.planning_agent import root_agent as planning

        expected_keys = ["planning", "development", "execution", "monitoring"]
        for agent, output_key in zip(
            [planning, development, execution, monitoring], expected_keys, strict=True
        ):
            synthesizer = agent.sub_agents[-1]
            self.assertEqual(synthesizer.output_key, output_key)
            self.assertIsNotNone(synthesizer.output_schema)

    def test_subagents_reference_explicit_state_handoffs(self) -> None:
        from agents.development_agent import root_agent as development
        from agents.execution_agent import root_agent as execution
        from agents.monitoring_agent import root_agent as monitoring
        from agents.planning_agent import root_agent as planning

        expected_references = [
            (planning, [
                ["campaign_brief"],
                ["campaign_brief", "goals_and_objectives"],
                ["market_and_audience_research"],
                ["position_and_value_prop"],
                ["message_and_channels"],
                ["budget_manager"],
            ]),
            (development, [
                ["campaign_brief", "planning_output"],
                ["channel_selection_and_media_planning"],
                ["message_and_value_prop"],
                ["content_design_and_creation"],
            ]),
            (execution, [
                ["campaign_brief", "development_output"],
                ["social_media_execution"],
                ["email_execution"],
                ["channel_coordination"],
                ["schedule"],
            ]),
            (monitoring, [
                ["campaign_brief", "execution_output"],
                ["kpi_report"],
                ["campaign_analysis"],
                ["strategy_adjustments"],
                ["stakeholder_report"],
            ]),
        ]
        for root_agent, references_by_agent in expected_references:
            self.assertEqual(len(root_agent.sub_agents), len(references_by_agent))
            for subagent, references in zip(
                root_agent.sub_agents, references_by_agent, strict=True
            ):
                instruction = str(subagent.instruction)
                for reference in references:
                    self.assertIn("{" + reference + "}", instruction)


if __name__ == "__main__":
    unittest.main()
