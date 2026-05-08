from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel
import json
from config import config
from dependencies import get_config

router = APIRouter(prefix="/compare", tags=["compare"])

class CompareRequest(BaseModel):
    analysis_result: dict  # The output from /analyze
    incident_id: str  # ID to look up in fictional DB

class CompareResponse(BaseModel):
    match_score: float
    differences: dict
    tuned_result: dict  # Fictional "tuned" version

@router.post("/", response_model=CompareResponse)
async def compare_analysis(
    request: CompareRequest = Body(...),
    cfg=Depends(get_config)  # Using dependency for config
):
    # Load fictional DB (mock JSON file)
    try:
        with open(cfg.MOCK_DB_PATH, "r") as f:
            mock_db = json.load(f)
    except FileNotFoundError:
        mock_db = {}  # Fallback if no file

    # Fictional ground truth from "DB"
    ground_truth = mock_db.get(request.incident_id, {
        "severity": "high",
        "category": "mechanical",
        "likely_root_causes": ["Bearing failure"],
        "evidence": ["Vibration detected"],
        "recommended_actions": [{"action": "Replace bearing"}],
        "confidence": 0.85,
        "final_report": "Tuned report summary"
    })

    # Simple fictional comparison logic
    match_score = 0.8  # Mock score
    differences = {
        "severity": request.analysis_result.get("severity") != ground_truth["severity"],
        "category": request.analysis_result.get("category") != ground_truth["category"]
        # Add more fields as needed
    }

    # Fictional "tuned" result: average confidence or something simple
    tuned_result = ground_truth.copy()
    tuned_result["confidence"] = (request.analysis_result.get("confidence", 0) + ground_truth["confidence"]) / 2

    return CompareResponse(
        match_score=match_score,
        differences=differences,
        tuned_result=tuned_result
    )
