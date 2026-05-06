from __future__ import annotations

from langchain_backend import LangChainBackend
from prompts.root_cause import ROOT_CAUSE_PROMPT
from schemas import IncidentFacts, RootCauseHypothesis, RootCauseResult, TriageResult


class RootCauseAgent:
    """Propose likely root cause hypotheses from facts and triage context."""

    def run(
        self,
        facts: IncidentFacts,
        triage: TriageResult,
        mock_mode: bool = True,
        llm_backend: LangChainBackend | None = None,
    ) -> RootCauseResult:
        if not mock_mode:
            return self._run_langchain(facts=facts, triage=triage, llm_backend=llm_backend)

        report = facts.normalized_report.lower()
        hypotheses: list[RootCauseHypothesis] = []
        evidence: list[str] = []

        if any(term in report for term in ("bearing", "vibration", "noise")):
            items = ["Abnormal vibration or noise noted in report"]
            evidence.extend(items)
            hypotheses.append(
                RootCauseHypothesis(
                    cause="Bearing wear or mechanical misalignment",
                    likelihood=0.81,
                    evidence=items,
                )
            )

        if any(term in report for term in ("overheat", "temperature", "hot")):
            items = ["Temperature rise or overheating mentioned"]
            evidence.extend(items)
            hypotheses.append(
                RootCauseHypothesis(
                    cause="Insufficient lubrication or cooling constraint",
                    likelihood=0.76,
                    evidence=items,
                )
            )

        if any(term in report for term in ("sensor", "error", "fault code")):
            items = ["Sensor or error-code language present"]
            evidence.extend(items)
            hypotheses.append(
                RootCauseHypothesis(
                    cause="Sensor drift, wiring issue, or false positive alert",
                    likelihood=0.64,
                    evidence=items,
                )
            )

        if not hypotheses:
            default_evidence = [
                f"General incident pattern classified as {triage.category}",
                "Report lacks precise failure indicators",
            ]
            evidence.extend(default_evidence)
            hypotheses.append(
                RootCauseHypothesis(
                    cause="General process instability requiring inspection",
                    likelihood=0.55 if mock_mode else 0.4,
                    evidence=default_evidence,
                )
            )

        deduped_evidence = list(dict.fromkeys(evidence))
        return RootCauseResult(likely_root_causes=hypotheses, evidence=deduped_evidence)

    def _run_langchain(
        self,
        *,
        facts: IncidentFacts,
        triage: TriageResult,
        llm_backend: LangChainBackend | None,
    ) -> RootCauseResult:
        backend = llm_backend or LangChainBackend()
        return backend.invoke_structured(
            system_prompt=ROOT_CAUSE_PROMPT,
            user_payload={
                "facts": facts.model_dump(),
                "triage": triage.model_dump(),
            },
            schema=RootCauseResult,
        )
