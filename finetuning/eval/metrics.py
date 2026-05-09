"""Evaluation metrics for OpsTune predictions vs ground truth.

Pure functions, no LLM calls — the notebook handles inference + caching.
Inputs are dicts with the WorkflowResult shape; predictions may be raw
strings (un-parsed model output) which `parse_prediction` will try to
extract JSON from.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

SEVERITIES = ["low", "medium", "high", "critical"]
CATEGORIES = [
    "mechanical", "electrical", "thermal", "sensor",
    "process", "quality", "safety", "unknown",
]
REQUIRED_FIELDS = {
    "severity", "category", "likely_root_causes", "evidence",
    "recommended_actions", "confidence", "final_report",
}


# ---------- parsing ---------------------------------------------------------


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def parse_prediction(raw: str) -> tuple[dict | None, str]:
    """Try to extract a JSON object from a model's raw output.

    Returns (parsed_dict_or_none, error_message). Strips markdown fences,
    finds the first balanced { ... } block, and json.loads it.
    """
    if not raw or not raw.strip():
        return None, "empty"
    text = raw.strip()
    # Strip ```json ... ``` fences if present.
    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()
    # Quick path: try the whole thing.
    try:
        return json.loads(text), ""
    except json.JSONDecodeError:
        pass
    # Fall back: find the first balanced { ... } block.
    start = text.find("{")
    if start == -1:
        return None, "no opening brace"
    depth = 0
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate), ""
                except json.JSONDecodeError as exc:
                    return None, f"json decode failed at offset {i}: {exc.msg}"
    return None, "unbalanced braces"


def schema_compliant(obj: dict) -> tuple[bool, list[str]]:
    """Check the parsed object has all required fields with the right types/values."""
    if not isinstance(obj, dict):
        return False, ["not a dict"]
    issues: list[str] = []
    for f in REQUIRED_FIELDS:
        if f not in obj:
            issues.append(f"missing field '{f}'")
    if "severity" in obj and obj["severity"] not in SEVERITIES:
        issues.append(f"severity '{obj['severity']}' not in {SEVERITIES}")
    if "category" in obj and obj["category"] not in CATEGORIES:
        issues.append(f"category '{obj['category']}' not in {CATEGORIES}")
    for list_field in ("likely_root_causes", "evidence", "recommended_actions"):
        if list_field in obj and not isinstance(obj[list_field], list):
            issues.append(f"{list_field} is not a list")
    if "confidence" in obj:
        try:
            c = float(obj["confidence"])
            if not 0.0 <= c <= 1.0:
                issues.append(f"confidence {c} out of [0,1]")
        except (TypeError, ValueError):
            issues.append("confidence not numeric")
    if "final_report" in obj and not isinstance(obj["final_report"], str):
        issues.append("final_report is not a string")
    return len(issues) == 0, issues


# ---------- per-field comparators ------------------------------------------


def severity_distance(pred: str | None, truth: str) -> int | None:
    """0 if equal, otherwise positive ordinal distance on the severity ladder."""
    if pred not in SEVERITIES or truth not in SEVERITIES:
        return None
    return abs(SEVERITIES.index(pred) - SEVERITIES.index(truth))


def confidence_error(pred, truth: float) -> float | None:
    try:
        return abs(float(pred) - float(truth))
    except (TypeError, ValueError):
        return None


_TOKEN_RE = re.compile(r"[A-Za-z]{3,}")
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "have", "has", "are",
    "was", "were", "but", "not", "any", "all", "may", "can", "use", "using",
    "due", "out", "into", "over", "under", "between", "above", "below",
    "operator", "report", "line", "cell", "machine", "tool", "shift",
    "noticed", "saw", "showed", "called", "stopped", "running", "running",
}


def _tokens(s: str) -> set[str]:
    return {w.lower() for w in _TOKEN_RE.findall(s) if w.lower() not in _STOPWORDS}


def list_jaccard(pred_list: list[str] | None, truth_list: list[str]) -> float | None:
    """Jaccard over the union of (cleaned) word tokens across each list."""
    if not isinstance(pred_list, list):
        return None
    pred_toks: set[str] = set()
    for s in pred_list:
        if isinstance(s, str):
            pred_toks |= _tokens(s)
    truth_toks: set[str] = set()
    for s in truth_list:
        if isinstance(s, str):
            truth_toks |= _tokens(s)
    if not pred_toks and not truth_toks:
        return 1.0
    if not pred_toks or not truth_toks:
        return 0.0
    return len(pred_toks & truth_toks) / len(pred_toks | truth_toks)


# ---------- aggregation ----------------------------------------------------


def score_one(pred_raw: str, truth: dict) -> dict[str, Any]:
    parsed, parse_err = parse_prediction(pred_raw)
    out: dict[str, Any] = {
        "json_valid": parsed is not None,
        "parse_error": parse_err,
        "schema_ok": False,
        "schema_issues": [],
        "severity_match": None,
        "severity_distance": None,
        "category_match": None,
        "confidence_mae": None,
        "causes_jaccard": None,
        "actions_jaccard": None,
        "predicted": parsed,
    }
    if parsed is None:
        return out
    ok, issues = schema_compliant(parsed)
    out["schema_ok"] = ok
    out["schema_issues"] = issues
    out["severity_match"] = parsed.get("severity") == truth["severity"]
    out["severity_distance"] = severity_distance(parsed.get("severity"), truth["severity"])
    out["category_match"] = parsed.get("category") == truth["category"]
    out["confidence_mae"] = confidence_error(parsed.get("confidence"), truth["confidence"])
    out["causes_jaccard"] = list_jaccard(parsed.get("likely_root_causes"), truth["likely_root_causes"])
    out["actions_jaccard"] = list_jaccard(parsed.get("recommended_actions"), truth["recommended_actions"])
    return out


def aggregate(scored: list[dict]) -> dict[str, float | int]:
    n = len(scored)

    def _frac(key):
        vals = [s[key] for s in scored if isinstance(s[key], bool)]
        return sum(vals) / len(vals) if vals else 0.0

    def _mean(key):
        vals = [s[key] for s in scored if isinstance(s[key], (int, float))]
        return sum(vals) / len(vals) if vals else float("nan")

    return {
        "n": n,
        "json_valid_rate": _frac("json_valid"),
        "schema_ok_rate": _frac("schema_ok"),
        "severity_accuracy": _frac("severity_match"),
        "severity_mean_dist": _mean("severity_distance"),
        "category_accuracy": _frac("category_match"),
        "confidence_mae": _mean("confidence_mae"),
        "causes_jaccard_mean": _mean("causes_jaccard"),
        "actions_jaccard_mean": _mean("actions_jaccard"),
    }


def confusion(scored: list[dict], truths: list[dict], field: str, labels: list[str]) -> list[list[int]]:
    """Return a confusion matrix [truth][pred] for the given field."""
    idx = {l: i for i, l in enumerate(labels)}
    mat = [[0] * len(labels) for _ in labels]
    for s, t in zip(scored, truths):
        truth_label = t[field]
        pred = (s.get("predicted") or {}).get(field) if s.get("predicted") else None
        if truth_label not in idx:
            continue
        if pred not in idx:
            # Count off-vocab predictions in a synthetic last column? Skip for now.
            continue
        mat[idx[truth_label]][idx[pred]] += 1
    return mat


def label_distribution(scored: list[dict], field: str) -> Counter:
    return Counter(
        (s.get("predicted") or {}).get(field) if s.get("predicted") else "<no_json>"
        for s in scored
    )
