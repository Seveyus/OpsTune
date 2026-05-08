from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, ConfigDict
import json
from pathlib import Path

from config import config
from dependencies import get_config

router = APIRouter(prefix="/compare", tags=["compare"])


class CompareRequest(BaseModel):
    analysis_result: dict
    incident_id: str


class CompareResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    match_score: float
    differences: dict
    tuned_result: dict


@router.post("/", response_model=CompareResponse)
async def compare_analysis(
    request: CompareRequest = Body(...),
    cfg=Depends(get_config),
):
    # mock database path
    db_path = getattr(cfg, "MOCK_DB_PATH", None) or Path("evaluation/mock_db.json")

    try:
        with open(db_path, "r", encoding="utf-8") as f:
            mock_db = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        mock_db = {}

    # Fallback if no entry in the database
    ground_truth = mock_db.get(
        request.incident_id,
        {
            "severity": "high",
            "category": "mechanical",
            "likely_root_causes": ["Bearing failure"],
            "evidence": ["Vibration detected"],
            "recommended_actions": [{"action": "Replace bearing"}],
            "confidence": 0.85,
            "final_report": "Tuned report summary",
        },
    )

    analysis = request.analysis_result

    differences = {
        "severity": analysis.get("severity") != ground_truth.get("severity"),
        "category": analysis.get("category") != ground_truth.get("category"),
        "root_causes_match": set(analysis.get("likely_root_causes", []))
        == set(ground_truth.get("likely_root_causes", [])),
    }

    tuned = ground_truth.copy()
    if "confidence" in analysis:
        tuned["confidence"] = round(
            (analysis["confidence"] + ground_truth.get("confidence", 0.8)) / 2, 2
        )

    match_score = round(
        1.0 - (sum(differences.values()) / len(differences)), 2
    )

    return CompareResponse(
        match_score=match_score,
        differences=differences,
        tuned_result=tuned,
    )
