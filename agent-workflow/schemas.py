from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


SeverityLevel = Literal["low", "medium", "high", "critical"]
IncidentCategory = Literal[
    "mechanical",
    "electrical",
    "thermal",
    "sensor",
    "process",
    "quality",
    "safety",
    "unknown",
]
UrgencyLevel = Literal["low", "medium", "high", "immediate"]


class IncidentFacts(BaseModel):
    raw_report: str
    normalized_report: str
    equipment: list[str] = Field(default_factory=list)
    symptoms: list[str] = Field(default_factory=list)
    observed_anomalies: list[str] = Field(default_factory=list)
    operational_impact: list[str] = Field(default_factory=list)
    extracted_signals: list[str] = Field(default_factory=list)


class TriageResult(BaseModel):
    severity: SeverityLevel
    category: IncidentCategory
    urgency: UrgencyLevel
    rationale: str


class RootCauseHypothesis(BaseModel):
    cause: str
    likelihood: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(default_factory=list)


class RootCauseResult(BaseModel):
    likely_root_causes: list[RootCauseHypothesis] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class RecommendedAction(BaseModel):
    priority: Literal["immediate", "next_shift", "planned"]
    action: str
    owner: str
    reason: str


class WorkflowResult(BaseModel):
    severity: SeverityLevel
    category: IncidentCategory
    likely_root_causes: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    final_report: str
