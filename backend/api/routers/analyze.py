from fastapi import APIRouter, Body
from pydantic import BaseModel
from ...agent_workflow.workflow import run_workflow  # Import the workflow
from ...agent_workflow.schemas import IncidentFacts  # Assuming schemas exist

router = APIRouter(prefix="/analyze", tags=["analyze"])


class AnalyzeRequest(BaseModel):
    incident_report: str
    mock_mode: bool = True


class AnalyzeResponse(BaseModel):
    severity: str
    category: str
    likely_root_causes: list[str]
    evidence: list[str]
    recommended_actions: list[dict]  # Simplified; use RecommendedAction if defined
    confidence: float
    final_report: str


@router.post("/", response_model=AnalyzeResponse)
async def analyze_incident(request: AnalyzeRequest = Body(...)):
    # Run the workflow with the provided incident report
    result = run_workflow(request.incident_report, mock_mode=request.mock_mode)

    # Map to response schema (assuming workflow returns a dict matching this)
    return AnalyzeResponse(
        severity=result["severity"],
        category=result["category"],
        likely_root_causes=result["likely_root_causes"],
        evidence=result["evidence"],
        recommended_actions=result["recommended_actions"],
        confidence=result["confidence"],
        final_report=result["final_report"]
    )
