from __future__ import annotations

from langchain_backend import LangChainBackend
from prompts.action_planner import ACTION_PLANNER_PROMPT
from schemas import ActionPlanResult, IncidentFacts, RecommendedAction, RootCauseResult, TriageResult


class ActionPlannerAgent:
    """Recommend simple operational and maintenance actions."""

    def run(
        self,
        facts: IncidentFacts,
        triage: TriageResult,
        root_cause: RootCauseResult,
        mock_mode: bool = True,
        llm_backend: LangChainBackend | None = None,
    ) -> list[RecommendedAction]:
        if not mock_mode:
            return self._run_langchain(
                facts=facts,
                triage=triage,
                root_cause=root_cause,
                llm_backend=llm_backend,
            )

        actions: list[RecommendedAction] = []

        if triage.urgency == "immediate":
            actions.append(
                RecommendedAction(
                    priority="immediate",
                    action="Stabilize the asset and confirm safe operating state before restart.",
                    owner="operations",
                    reason="Incident suggests immediate production or safety impact.",
                )
            )

        if triage.category in {"mechanical", "thermal"}:
            actions.append(
                RecommendedAction(
                    priority="next_shift",
                    action="Inspect bearings, alignment, and lubrication condition on the affected equipment.",
                    owner="maintenance",
                    reason="Mechanical and thermal symptoms often correlate with wear or lubrication issues.",
                )
            )

        if triage.category == "sensor":
            actions.append(
                RecommendedAction(
                    priority="next_shift",
                    action="Validate sensor readings against manual checks and inspect connectors or wiring.",
                    owner="maintenance",
                    reason="Reported evidence may reflect instrumentation faults rather than asset damage.",
                )
            )

        actions.append(
            RecommendedAction(
                priority="planned",
                action="Log this case for trend review and compare with prior incidents on the same asset class.",
                owner="reliability",
                reason="Recurring incident signatures improve future predictive maintenance rules.",
            )
        )

        if mock_mode and not facts.operational_impact:
            actions.append(
                RecommendedAction(
                    priority="planned",
                    action="Capture missing runtime, downtime, and operator observations in the next report revision.",
                    owner="operations",
                    reason="Mock mode preserves a deterministic recommendation for incomplete narratives.",
                )
            )

        return actions

    def _run_langchain(
        self,
        *,
        facts: IncidentFacts,
        triage: TriageResult,
        root_cause: RootCauseResult,
        llm_backend: LangChainBackend | None,
    ) -> list[RecommendedAction]:
        backend = llm_backend or LangChainBackend()
        result = backend.invoke_structured(
            system_prompt=ACTION_PLANNER_PROMPT,
            user_payload={
                "facts": facts.model_dump(),
                "triage": triage.model_dump(),
                "root_cause": root_cause.model_dump(),
            },
            schema=ActionPlanResult,
        )
        return result.actions
