from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from workflow import run_workflow


def test_run_workflow_returns_expected_fields() -> None:
    report = (
        "Operator noticed heavy vibration and heat from the pump motor. "
        "The line was stopped after an alarm to prevent further damage."
    )

    result = run_workflow(report, mock_mode=True)

    expected_keys = {
        "severity",
        "category",
        "likely_root_causes",
        "evidence",
        "recommended_actions",
        "confidence",
        "final_report",
    }

    assert expected_keys.issubset(result.keys())
    assert result["severity"] in {"low", "medium", "high", "critical"}
    assert isinstance(result["likely_root_causes"], list) and result["likely_root_causes"]
    assert isinstance(result["recommended_actions"], list) and result["recommended_actions"]
    assert 0.0 <= result["confidence"] <= 1.0
