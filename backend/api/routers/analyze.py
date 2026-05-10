from fastapi import APIRouter, Body
from pydantic import BaseModel, ConfigDict
import sys
from pathlib import Path

# Add parent directory to path to import agent_workflow
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from agent_workflow.workflow import run_workflow
from agent_workflow.hf_backend import HuggingFaceBackend

router = APIRouter(prefix="/analyze", tags=["analyze"])


class AnalyzeRequest(BaseModel):
    incident_report: str
    mock_mode: bool = True
    use_llm: bool = False


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    severity: str
    category: str
    likely_root_causes: list[str]
    evidence: list[str]
    recommended_actions: list[str]
    confidence: float
    final_report: str


@router.post("/", response_model=AnalyzeResponse)
async def analyze_incident(request: AnalyzeRequest = Body(...)):
    llm_backend = None

    if request.use_llm and not request.mock_mode:
        llm_backend = HuggingFaceBackend()

    result = run_workflow(
        incident_report=request.incident_report,
        mock_mode=request.mock_mode,
        llm_backend=llm_backend
    )

    return AnalyzeResponse(**result)
