from __future__ import annotations

from schemas import IncidentFacts, TriageResult


class TriageAgent:
    """Assign severity, category, and urgency using simple deterministic rules."""

    def run(self, facts: IncidentFacts, mock_mode: bool = True) -> TriageResult:
        report = facts.normalized_report.lower()

        severity = "low"
        urgency = "low"
        category = "unknown"

        if any(term in report for term in ("safety", "smoke", "fire")):
            category = "safety"
            severity = "critical"
            urgency = "immediate"
        elif any(term in report for term in ("overheat", "temperature", "hot")):
            category = "thermal"
            severity = "high"
            urgency = "high"
        elif any(term in report for term in ("sensor", "fault code", "error code")):
            category = "sensor"
            severity = "medium"
            urgency = "medium"
        elif any(term in report for term in ("bearing", "vibration", "noise", "motor", "pump")):
            category = "mechanical"
            severity = "high" if any(term in report for term in ("shutdown", "trip", "stopped")) else "medium"
            urgency = "high" if severity == "high" else "medium"
        elif any(term in report for term in ("current", "amp", "voltage", "electrical")):
            category = "electrical"
            severity = "high"
            urgency = "high"

        if any(term in report for term in ("line down", "downtime", "production loss", "stopped")):
            severity = "critical" if severity == "high" else "high"
            urgency = "immediate" if severity == "critical" else "high"

        if mock_mode and category == "unknown":
            category = "process"
            severity = "medium"
            urgency = "medium"

        rationale = (
            f"Category={category} based on extracted symptoms {facts.symptoms or ['generic anomaly']}; "
            f"severity escalated by operational impact {facts.operational_impact or ['not explicitly stated']}."
        )

        return TriageResult(
            severity=severity,
            category=category,
            urgency=urgency,
            rationale=rationale,
        )
