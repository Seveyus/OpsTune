from __future__ import annotations

from schemas import IncidentFacts, RecommendedAction, RootCauseResult, TriageResult, WorkflowResult


class ReportAgent:
    """Assemble the final workflow response."""

    def run(
        self,
        facts: IncidentFacts,
        triage: TriageResult,
        root_cause: RootCauseResult,
        actions: list[RecommendedAction],
        mock_mode: bool = True,
    ) -> WorkflowResult:
        likely_root_causes = [item.cause for item in root_cause.likely_root_causes]
        recommended_actions = [item.action for item in actions]
        confidence = self._calculate_confidence(facts, triage, root_cause, mock_mode=mock_mode)

        final_report = (
            f"OpsTune classified this incident as {triage.severity} severity in the {triage.category} category. "
            f"Observed signals include {', '.join(facts.symptoms or ['general anomaly'])}. "
            f"Top hypothesis: {likely_root_causes[0]}. "
            f"Recommended next step: {recommended_actions[0]}"
        )

        return WorkflowResult(
            severity=triage.severity,
            category=triage.category,
            likely_root_causes=likely_root_causes,
            evidence=root_cause.evidence,
            recommended_actions=recommended_actions,
            confidence=confidence,
            final_report=final_report,
        )

    def _calculate_confidence(
        self,
        facts: IncidentFacts,
        triage: TriageResult,
        root_cause: RootCauseResult,
        mock_mode: bool,
    ) -> float:
        score = 0.45
        score += min(len(facts.symptoms), 3) * 0.08
        score += min(len(root_cause.evidence), 3) * 0.06
        if triage.category != "unknown":
            score += 0.1
        if mock_mode:
            score += 0.05
        return round(min(score, 0.95), 2)
