from __future__ import annotations

import re

from langchain_backend import LangChainBackend
from prompts.intake import INTAKE_PROMPT
from schemas import IncidentFacts


class IntakeAgent:
    """Extract basic operational facts from a raw incident report."""

    KEYWORD_PATTERNS = {
        "equipment": [
            r"\bpump\b",
            r"\bmotor\b",
            r"\bbearing\b",
            r"\bconveyor\b",
            r"\bcompressor\b",
            r"\bspindle\b",
            r"\bhydraulic\b",
        ],
        "symptoms": [
            r"\bvibration\b",
            r"\boverheat(?:ing)?\b",
            r"\bleak(?:ing)?\b",
            r"\bsmell\b",
            r"\bnoise\b",
            r"\balarm\b",
            r"\bshutdown\b",
            r"\btrip(?:ped)?\b",
            r"\bstall(?:ed)?\b",
        ],
        "impact": [
            r"\bdowntime\b",
            r"\bstopped\b",
            r"\bline down\b",
            r"\bproduction loss\b",
            r"\bscrap\b",
            r"\bslow(?:ed)?\b",
        ],
        "signals": [
            r"\btemperature\b",
            r"\bpressure\b",
            r"\bcurrent\b",
            r"\bamp(?:s)?\b",
            r"\bsensor\b",
            r"\bcode\b",
            r"\berror\b",
        ],
    }

    def run(
        self,
        incident_report: str,
        mock_mode: bool = True,
        llm_backend: LangChainBackend | None = None,
    ) -> IncidentFacts:
        if not mock_mode:
            return self._run_langchain(incident_report=incident_report, llm_backend=llm_backend)

        normalized = " ".join(incident_report.strip().split())
        lower_report = normalized.lower()

        equipment = self._extract_matches(lower_report, "equipment")
        symptoms = self._extract_matches(lower_report, "symptoms")
        impact = self._extract_matches(lower_report, "impact")
        signals = self._extract_matches(lower_report, "signals")

        anomalies = []
        if "vibration" in symptoms:
            anomalies.append("Abnormal vibration reported")
        if any(term in lower_report for term in ("overheat", "temperature", "hot")):
            anomalies.append("Thermal anomaly mentioned")
        if any(term in lower_report for term in ("alarm", "trip", "shutdown", "stopped")):
            anomalies.append("Operational interruption observed")

        if mock_mode and not equipment:
            equipment = ["machine"]

        return IncidentFacts(
            raw_report=incident_report,
            normalized_report=normalized,
            equipment=equipment,
            symptoms=symptoms,
            observed_anomalies=anomalies,
            operational_impact=impact,
            extracted_signals=signals,
        )

    def _run_langchain(
        self,
        *,
        incident_report: str,
        llm_backend: LangChainBackend | None,
    ) -> IncidentFacts:
        backend = llm_backend or LangChainBackend()
        return backend.invoke_structured(
            system_prompt=INTAKE_PROMPT,
            user_payload={"incident_report": incident_report},
            schema=IncidentFacts,
        )

    def _extract_matches(self, text: str, section: str) -> list[str]:
        matches: list[str] = []
        for pattern in self.KEYWORD_PATTERNS[section]:
            found = re.findall(pattern, text)
            for item in found:
                normalized = item if isinstance(item, str) and item else re.sub(r"\\b", "", pattern)
                if normalized not in matches:
                    matches.append(normalized)
        return matches
