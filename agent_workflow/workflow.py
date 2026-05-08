from __future__ import annotations

import json
from pathlib import Path

from .agents.action_planner_agent import ActionPlannerAgent
from .agents.intake_agent import IntakeAgent
from .agents.report_agent import ReportAgent
from .agents.root_cause_agent import RootCauseAgent
from .agents.triage_agent import TriageAgent
from .langchain_backend import LangChainBackend


class OpsTuneWorkflow:
    """Multi-step workflow with deterministic and LangChain-backed execution modes."""

    def __init__(self, llm_backend: LangChainBackend | None = None) -> None:
        self.intake_agent = IntakeAgent()
        self.triage_agent = TriageAgent()
        self.root_cause_agent = RootCauseAgent()
        self.action_planner_agent = ActionPlannerAgent()
        self.report_agent = ReportAgent()
        self.llm_backend = llm_backend

    def run(self, incident_report: str, mock_mode: bool = True) -> dict:
        facts = self.intake_agent.run(
            incident_report=incident_report,
            mock_mode=mock_mode,
            llm_backend=self.llm_backend,
        )
        triage = self.triage_agent.run(facts=facts, mock_mode=mock_mode, llm_backend=self.llm_backend)
        root_cause = self.root_cause_agent.run(
            facts=facts,
            triage=triage,
            mock_mode=mock_mode,
            llm_backend=self.llm_backend,
        )
        actions = self.action_planner_agent.run(
            facts=facts,
            triage=triage,
            root_cause=root_cause,
            mock_mode=mock_mode,
            llm_backend=self.llm_backend,
        )
        result = self.report_agent.run(
            facts=facts,
            triage=triage,
            root_cause=root_cause,
            actions=actions,
            mock_mode=mock_mode,
            llm_backend=self.llm_backend,
        )
        return result.model_dump()


def run_workflow(
    incident_report: str,
    mock_mode: bool = True,
    llm_backend: LangChainBackend | None = None,
) -> dict:
    """Public entrypoint for backend integration."""
    workflow = OpsTuneWorkflow(llm_backend=llm_backend)
    return workflow.run(incident_report=incident_report, mock_mode=mock_mode)


def _load_sample_incident() -> str:
    sample_path = Path(__file__).parent / "examples" / "sample_incidents.jsonl"
    first_line = sample_path.read_text(encoding="utf-8").splitlines()[0]
    payload = json.loads(first_line)
    return payload["incident_report"]


if __name__ == "__main__":
    sample_report = _load_sample_incident()
    output = run_workflow(sample_report, mock_mode=True)
    print(json.dumps(output, indent=2))
