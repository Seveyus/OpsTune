"""Print a side-by-side baseline vs fine-tuned eval comparison.

Reads `predictions/baseline.summary.json` and `predictions/finetuned.summary.json`
(both produced by `baseline_eval.ipynb` with different RUN_NAME values) and
prints a delta table — the demo screenshot.

Run:
    python finetuning/training/compare_runs.py
    python finetuning/training/compare_runs.py --baseline X.summary.json --finetuned Y.summary.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

DEFAULT_BASELINE = ROOT / "finetuning" / "eval" / "predictions" / "baseline.summary.json"
DEFAULT_FINETUNED = ROOT / "finetuning" / "eval" / "predictions" / "finetuned.summary.json"

# Metrics where higher = better (use ↑ delta marker); others (confidence_mae) get ↓.
HIGHER_IS_BETTER = {
    "json_valid_rate", "schema_ok_rate", "severity_accuracy",
    "category_accuracy", "causes_jaccard_mean", "actions_jaccard_mean",
}
LOWER_IS_BETTER = {"confidence_mae", "severity_mean_dist"}


def _arrow(delta: float, metric: str) -> str:
    if metric in HIGHER_IS_BETTER:
        return "▲" if delta > 0 else ("▼" if delta < 0 else "·")
    if metric in LOWER_IS_BETTER:
        return "▲" if delta < 0 else ("▼" if delta > 0 else "·")
    return " "


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def print_delta(baseline: dict, finetuned: dict) -> None:
    bag = baseline["aggregate"]
    fag = finetuned["aggregate"]
    keys = [k for k in bag if k != "n"]
    width = max(len(k) for k in keys) + 2

    print(f"\nBaseline: {baseline['model']!r:<35} (n={bag['n']})")
    print(f"Tuned:    {finetuned['model']!r:<35} (n={fag['n']})")
    print()
    print(f"  {'Metric'.ljust(width)} {'Baseline':>10} {'Finetuned':>11} {'Δ':>9}")
    print(f"  {'-' * width} {'-'*10:>10} {'-'*11:>11} {'-'*9:>9}")
    for k in keys:
        b = bag.get(k)
        f = fag.get(k)
        if not isinstance(b, (int, float)) or not isinstance(f, (int, float)):
            print(f"  {k.ljust(width)} {_fmt(b):>10} {_fmt(f):>11} {'-':>9}")
            continue
        delta = f - b
        arrow = _arrow(delta, k)
        print(f"  {k.ljust(width)} {_fmt(b):>10} {_fmt(f):>11} {delta:+.3f} {arrow}")


def print_per_mode(baseline: dict, finetuned: dict) -> None:
    bm = {row["primary_mode"]: row for row in baseline["by_mode"]}
    fm = {row["primary_mode"]: row for row in finetuned["by_mode"]}
    modes = sorted(set(bm) | set(fm))

    fields = ("severity_acc", "category_acc", "conf_mae", "causes_jaccard", "actions_jaccard")
    print("\nPer-mode breakdown:")
    print(f"  {'mode':<10} {'n':>4}  " + "  ".join(f"{f:>22}" for f in fields))
    for m in modes:
        b = bm.get(m, {})
        f = fm.get(m, {})
        n = f.get("n", b.get("n", "-"))
        cells = []
        for fld in fields:
            bv = b.get(fld)
            fv = f.get(fld)
            if isinstance(bv, (int, float)) and isinstance(fv, (int, float)):
                delta = fv - bv
                arrow = _arrow(delta, "severity_accuracy" if fld in ("severity_acc", "category_acc", "causes_jaccard", "actions_jaccard") else "confidence_mae")
                cells.append(f"{bv:.2f}→{fv:.2f} {arrow}")
            else:
                cells.append(f"{_fmt(bv)}→{_fmt(fv)}")
        print(f"  {m:<10} {n:>4}  " + "  ".join(f"{c:>22}" for c in cells))


def print_distributions(baseline: dict, finetuned: dict) -> None:
    print("\nPredicted-severity distribution:")
    print(f"  baseline:  {baseline.get('predicted_severity_distribution', {})}")
    print(f"  finetuned: {finetuned.get('predicted_severity_distribution', {})}")
    print("\nPredicted-category distribution:")
    print(f"  baseline:  {baseline.get('predicted_category_distribution', {})}")
    print(f"  finetuned: {finetuned.get('predicted_category_distribution', {})}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--finetuned", type=Path, default=DEFAULT_FINETUNED)
    args = parser.parse_args()

    if not args.baseline.exists():
        print(f"[compare] missing {args.baseline}")
        return 1
    if not args.finetuned.exists():
        print(f"[compare] missing {args.finetuned} — run inference + the eval notebook with RUN_NAME=finetuned first.")
        return 1

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    finetuned = json.loads(args.finetuned.read_text(encoding="utf-8"))

    print_delta(baseline, finetuned)
    print_per_mode(baseline, finetuned)
    print_distributions(baseline, finetuned)
    return 0


if __name__ == "__main__":
    sys.exit(main())
