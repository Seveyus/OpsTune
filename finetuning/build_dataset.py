"""Build the OpsTune fine-tuning dataset from AI4I 2020.

Step 1: recompute the documented TWF/HDF/PWF/OSF rules for every row and
        record which conditions fire (multi-mode is preserved).
Step 2: emit a deterministic structured output per row that matches the
        backend's WorkflowResult contract.

Run:
    python finetuning/build_dataset.py
"""

from __future__ import annotations

import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from agent_workflow.schemas import WorkflowResult  # noqa: E402
except ModuleNotFoundError:
    WorkflowResult = None  # validation step will be skipped with a notice

from finetuning.playbooks import PLAYBOOKS, select_playbook_key  # noqa: E402
from finetuning.thresholds import (  # noqa: E402
    HDF_DELTA_T_MAX_K,
    HDF_RPM_MAX,
    PWF_POWER_MAX,
    PWF_POWER_MIN,
    TWF_WEAR_MAX,
    TWF_WEAR_MIN,
    osf_limit,
    power_w,
)

CSV_PATH = ROOT / "ai4i2020.csv"
OUT_PATH = ROOT / "finetuning" / "ai4i_labeled.jsonl"
RANDOM_SEED = 17
NONFAILURE_FRACTION = 0.30          # of final dataset
NEAR_THRESHOLD_FRACTION = 0.40      # of the non-failure sample

# Severity priority — used to pick the primary mode when multiple fire.
MODE_PRIORITY = ["HDF", "PWF", "OSF", "TWF", "RNF"]
MODE_TO_CATEGORY = {
    "HDF": "thermal",
    "PWF": "electrical",
    "OSF": "mechanical",
    "TWF": "mechanical",
    "RNF": "unknown",
}
MODE_HUMAN = {
    "HDF": "heat dissipation failure",
    "PWF": "power failure",
    "OSF": "overstrain failure",
    "TWF": "tool wear failure",
    "RNF": "random / unexplained failure",
}


# ---------- Step 1 helpers --------------------------------------------------


def parse_row(row: dict) -> dict:
    air = float(row["Air temperature [K]"])
    proc = float(row["Process temperature [K]"])
    rpm = float(row["Rotational speed [rpm]"])
    tq = float(row["Torque [Nm]"])
    tw = float(row["Tool wear [min]"])
    variant = row["Type"]
    return {
        "udi": int(row["UDI"]),
        "product_id": row["Product ID"],
        "variant": variant,
        "air_t": air,
        "proc_t": proc,
        "rpm": rpm,
        "torque": tq,
        "tool_wear": tw,
        "delta_t": proc - air,
        "power_w": power_w(tq, rpm),
        "torque_x_wear": tq * tw,
        "csv_machine_failure": int(row["Machine failure"]),
        "csv_modes": [m for m in ("TWF", "HDF", "PWF", "OSF", "RNF") if int(row[m]) == 1],
    }


def evaluate_rules(r: dict) -> dict:
    """Return per-mode {triggered: bool, margin: float, side: str|None}.

    Margin is signed and normalized to the threshold so magnitudes are
    comparable across modes. Positive ⇒ rule fires.
    """
    osf_lim = osf_limit(r["variant"])

    # TWF: in window ⇒ "triggered" (CSV will tell us if it actually failed
    # vs being a planned replacement). Margin: distance from window center
    # normalized by half-width — positive when inside the window.
    twf_center = (TWF_WEAR_MIN + TWF_WEAR_MAX) / 2
    twf_half = (TWF_WEAR_MAX - TWF_WEAR_MIN) / 2
    twf_margin = (twf_half - abs(r["tool_wear"] - twf_center)) / twf_half
    twf_trig = TWF_WEAR_MIN <= r["tool_wear"] <= TWF_WEAR_MAX

    # HDF: both conditions must hold. Margin = min of the two normalized slacks.
    hdf_dt_margin = (HDF_DELTA_T_MAX_K - r["delta_t"]) / HDF_DELTA_T_MAX_K
    hdf_rpm_margin = (HDF_RPM_MAX - r["rpm"]) / HDF_RPM_MAX
    hdf_margin = min(hdf_dt_margin, hdf_rpm_margin)
    hdf_trig = r["delta_t"] < HDF_DELTA_T_MAX_K and r["rpm"] < HDF_RPM_MAX

    # PWF: out-of-band on either side. Track which side.
    if r["power_w"] < PWF_POWER_MIN:
        pwf_margin = (PWF_POWER_MIN - r["power_w"]) / PWF_POWER_MIN
        pwf_trig = True
        pwf_side: str | None = "low"
    elif r["power_w"] > PWF_POWER_MAX:
        pwf_margin = (r["power_w"] - PWF_POWER_MAX) / PWF_POWER_MAX
        pwf_trig = True
        pwf_side = "high"
    else:
        # Distance to nearest edge, negative since not triggered.
        slack = min(r["power_w"] - PWF_POWER_MIN, PWF_POWER_MAX - r["power_w"])
        pwf_margin = -slack / PWF_POWER_MIN
        pwf_trig = False
        pwf_side = None

    # OSF
    osf_margin = (r["torque_x_wear"] - osf_lim) / osf_lim
    osf_trig = r["torque_x_wear"] > osf_lim

    # RNF: untestable from sensors — trust the CSV column.
    rnf_trig = "RNF" in r["csv_modes"]
    rnf_margin = 1.0 if rnf_trig else -1.0

    return {
        "TWF": {"triggered": twf_trig, "margin": twf_margin, "side": None},
        "HDF": {"triggered": hdf_trig, "margin": hdf_margin, "side": None},
        "PWF": {"triggered": pwf_trig, "margin": pwf_margin, "side": pwf_side},
        "OSF": {"triggered": osf_trig, "margin": osf_margin, "side": None},
        "RNF": {"triggered": rnf_trig, "margin": rnf_margin, "side": None},
    }


def pick_primary_mode(triggered: list[str]) -> str | None:
    for m in MODE_PRIORITY:
        if m in triggered:
            return m
    return None


# ---------- Step 2 helpers --------------------------------------------------


def build_evidence(r: dict, rules: dict) -> list[str]:
    """One observation per sensor / derived quantity, signal and non-signal."""
    ev: list[str] = []

    # Tool wear
    if rules["TWF"]["triggered"]:
        ev.append(f"Tool wear: {r['tool_wear']:.0f} min (within 200–240 min TWF window)")
    else:
        ev.append(f"Tool wear: {r['tool_wear']:.0f} min (outside TWF window)")

    # Thermal
    dt_note = "below" if r["delta_t"] < HDF_DELTA_T_MAX_K else "above"
    ev.append(
        f"ΔT process−air: {r['delta_t']:.1f} K ({dt_note} {HDF_DELTA_T_MAX_K} K HDF threshold)"
    )

    # RPM
    rpm_note = "below" if r["rpm"] < HDF_RPM_MAX else "above"
    ev.append(
        f"Rotational speed: {r['rpm']:.0f} rpm ({rpm_note} {HDF_RPM_MAX} rpm HDF threshold)"
    )

    # Torque
    ev.append(f"Torque: {r['torque']:.1f} Nm")

    # Power
    if r["power_w"] < PWF_POWER_MIN:
        ev.append(
            f"Power: {r['power_w']:.0f} W (below {PWF_POWER_MIN} W PWF lower limit)"
        )
    elif r["power_w"] > PWF_POWER_MAX:
        ev.append(
            f"Power: {r['power_w']:.0f} W (above {PWF_POWER_MAX} W PWF upper limit)"
        )
    else:
        ev.append(
            f"Power: {r['power_w']:.0f} W (within {PWF_POWER_MIN}–{PWF_POWER_MAX} W safe band)"
        )

    # Torque x wear
    osf_lim = osf_limit(r["variant"])
    if rules["OSF"]["triggered"]:
        ev.append(
            f"Torque × wear: {r['torque_x_wear']:.0f} minNm "
            f"(exceeds {osf_lim} minNm OSF limit for variant {r['variant']})"
        )
    else:
        ev.append(
            f"Torque × wear: {r['torque_x_wear']:.0f} minNm "
            f"(within {osf_lim} minNm OSF limit for variant {r['variant']})"
        )

    if rules["RNF"]["triggered"]:
        ev.append("Random failure flag set in source data with no documented sensor breach")

    return ev


def fill_template(s: str, r: dict) -> str:
    return s.format(
        variant=r["variant"],
        rpm=f"{r['rpm']:.0f}",
        torque=f"{r['torque']:.1f}",
        tool_wear=f"{r['tool_wear']:.0f}",
        power_w=f"{r['power_w']:.0f}",
        air_t=f"{r['air_t']:.1f}",
        proc_t=f"{r['proc_t']:.1f}",
        delta_t=f"{r['delta_t']:.1f}",
        torque_x_wear=f"{r['torque_x_wear']:.0f}",
        osf_limit=osf_limit(r["variant"]),
    )


def build_causes_and_actions(
    r: dict,
    rules: dict,
    primary: str | None,
    triggered: list[str],
) -> tuple[list[str], list[str]]:
    if primary is None:
        pb = PLAYBOOKS["NORMAL"]
        return (
            [fill_template(c, r) for c in pb["root_causes"]],
            [fill_template(a, r) for a in pb["actions"]],
        )

    pwf_side = rules["PWF"]["side"]
    key = select_playbook_key(primary, triggered, pwf_side)
    base = PLAYBOOKS[key]
    causes = [fill_template(c, r) for c in base["root_causes"]]
    actions = [fill_template(a, r) for a in base["actions"]]

    # If multi-mode but no curated combo applies, splice in one cause from
    # each secondary mode so the ambiguity is reflected.
    if key not in {"HDF_PWF", "OSF_TWF"} and len(triggered) > 1:
        for sec in triggered:
            if sec == primary:
                continue
            sec_key = sec
            if sec == "PWF":
                sec_key = "PWF_LOW" if pwf_side == "low" else "PWF_HIGH"
            sec_pb = PLAYBOOKS.get(sec_key)
            if not sec_pb:
                continue
            extra = fill_template(sec_pb["root_causes"][0], r)
            if extra not in causes:
                causes.append(extra)

    return causes, actions


def derive_severity(
    primary: str | None,
    triggered: list[str],
    rules: dict,
) -> str:
    if primary is None:
        return "low"
    if triggered == ["RNF"]:
        return "low"
    n = len(triggered)
    if n >= 2:
        max_margin = max(
            rules[m]["margin"] for m in triggered if m != "RNF"
        ) if any(m != "RNF" for m in triggered) else 0.0
        if n >= 3 or max_margin > 0.30:
            return "critical"
        return "high"
    # single mode
    if primary == "TWF":
        return "medium"
    if primary == "OSF":
        return "high" if rules["OSF"]["margin"] > 0.20 else "medium"
    if primary in ("HDF", "PWF"):
        return "high"
    return "medium"


def derive_category(primary: str | None) -> str:
    if primary is None:
        return "unknown"
    return MODE_TO_CATEGORY.get(primary, "unknown")


def derive_confidence(
    primary: str | None,
    triggered: list[str],
    rules: dict,
) -> float:
    if primary is None:
        # Healthier (further from any threshold) ⇒ more confident.
        worst = max(
            rules[m]["margin"] for m in ("HDF", "PWF", "OSF", "TWF")
        )  # ≤ 0 when nothing is firing
        slack = max(0.0, -worst)  # how far we are from triggering
        score = 0.85 + 0.10 * min(1.0, slack)
    elif triggered == ["RNF"]:
        score = 0.45
    else:
        margins = [rules[m]["margin"] for m in triggered if m != "RNF"]
        base = max(margins) if margins else 0.0
        base = max(0.0, min(1.0, base))
        score = 0.50 + 0.40 * base
        if len(triggered) > 1:
            score -= 0.10 * (len(triggered) - 1)
    return round(max(0.30, min(0.95, score)), 2)


def build_final_report(
    r: dict,
    primary: str | None,
    severity: str,
    category: str,
    causes: list[str],
    actions: list[str],
) -> str:
    if primary is None:
        return (
            f"Healthy operation on product {r['product_id']} (variant {r['variant']}). "
            f"All sensor values within safe operating bands; continue routine monitoring."
        )
    summary = (
        f"Air {r['air_t']:.1f} K / process {r['proc_t']:.1f} K (ΔT {r['delta_t']:.1f} K), "
        f"spindle {r['rpm']:.0f} rpm, torque {r['torque']:.1f} Nm, "
        f"tool wear {r['tool_wear']:.0f} min, power {r['power_w']:.0f} W."
    )
    top_cause = causes[0].rstrip(".")
    top_action = actions[0].rstrip(".")
    return (
        f"{severity.capitalize()}-severity {category} event on product {r['product_id']} "
        f"(variant {r['variant']}). Primary mode: {MODE_HUMAN[primary]}. "
        f"{summary} Likely cause: {top_cause}. Immediate action: {top_action}."
    )


def build_structured_output(r: dict, rules: dict, machine_failure: int) -> dict:
    triggered = [m for m in MODE_PRIORITY if rules[m]["triggered"]]

    # Honor the dataset's machine_failure label when it disagrees with rule recompute:
    # - If CSV says failure but no rule fires, treat as RNF (random / latent).
    # - If CSV says non-failure, drop any "fired" modes (TWF window without actual failure).
    if machine_failure == 1 and not triggered:
        triggered = ["RNF"]
        rules["RNF"]["triggered"] = True
        rules["RNF"]["margin"] = 1.0
    if machine_failure == 0:
        triggered = []
        for m in rules:
            rules[m]["triggered"] = False

    primary = pick_primary_mode(triggered)
    severity = derive_severity(primary, triggered, rules)
    category = derive_category(primary)
    causes, actions = build_causes_and_actions(r, rules, primary, triggered)
    evidence = build_evidence(r, rules)
    confidence = derive_confidence(primary, triggered, rules)
    final_report = build_final_report(r, primary, severity, category, causes, actions)

    return {
        "primary_mode": primary,
        "triggered_modes": triggered,
        "structured_output": {
            "severity": severity,
            "category": category,
            "likely_root_causes": causes,
            "evidence": evidence,
            "recommended_actions": actions,
            "confidence": confidence,
            "final_report": final_report,
        },
    }


# ---------- Sampling --------------------------------------------------------


def sample_nonfailures(
    healthy_rows: list[tuple[dict, dict]],
    n_target: int,
    rng: random.Random,
) -> list[tuple[dict, dict]]:
    """Stratified sample: 60% clearly healthy, 40% near-threshold."""
    near, clearly = [], []
    for r, rules in healthy_rows:
        worst = max(rules[m]["margin"] for m in ("HDF", "PWF", "OSF", "TWF"))
        # margin in (-0.10, 0] ⇒ within 10% of triggering ⇒ near-threshold
        if -0.10 < worst <= 0:
            near.append((r, rules))
        else:
            clearly.append((r, rules))

    n_near = min(int(n_target * NEAR_THRESHOLD_FRACTION), len(near))
    n_clearly = min(n_target - n_near, len(clearly))
    rng.shuffle(near)
    rng.shuffle(clearly)
    return near[:n_near] + clearly[:n_clearly]


# ---------- Main ------------------------------------------------------------


def main() -> int:
    rng = random.Random(RANDOM_SEED)

    failure_records: list[tuple[dict, dict]] = []
    healthy_records: list[tuple[dict, dict]] = []

    with CSV_PATH.open(newline="", encoding="utf-8-sig") as f:
        for raw in csv.DictReader(f):
            r = parse_row(raw)
            rules = evaluate_rules(r)
            if r["csv_machine_failure"] == 1:
                failure_records.append((r, rules))
            else:
                healthy_records.append((r, rules))

    n_fail = len(failure_records)
    n_nonfail = round(n_fail * NONFAILURE_FRACTION / (1 - NONFAILURE_FRACTION))
    healthy_sample = sample_nonfailures(healthy_records, n_nonfail, rng)

    output_records = []
    for (r, rules) in failure_records:
        labelinfo = build_structured_output(r, rules, machine_failure=1)
        output_records.append((r, rules, labelinfo))
    for (r, rules) in healthy_sample:
        labelinfo = build_structured_output(r, rules, machine_failure=0)
        output_records.append((r, rules, labelinfo))

    rng.shuffle(output_records)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as out:
        for r, rules, labelinfo in output_records:
            obj = {
                "udi": r["udi"],
                "product_id": r["product_id"],
                "product_variant": r["variant"],
                "sensors": {
                    "air_temp_k": round(r["air_t"], 2),
                    "process_temp_k": round(r["proc_t"], 2),
                    "rotational_speed_rpm": round(r["rpm"], 1),
                    "torque_nm": round(r["torque"], 2),
                    "tool_wear_min": round(r["tool_wear"], 1),
                },
                "derived": {
                    "delta_t_k": round(r["delta_t"], 2),
                    "power_w": round(r["power_w"], 1),
                    "torque_x_wear_minNm": round(r["torque_x_wear"], 1),
                },
                "labels": {
                    "machine_failure": r["csv_machine_failure"],
                    "primary_mode": labelinfo["primary_mode"],
                    "triggered_modes": labelinfo["triggered_modes"],
                    "csv_modes": r["csv_modes"],
                    "rule_margins": {
                        m: round(rules[m]["margin"], 3)
                        for m in ("TWF", "HDF", "PWF", "OSF", "RNF")
                    },
                    "pwf_side": rules["PWF"]["side"],
                },
                "structured_output": labelinfo["structured_output"],
            }
            out.write(json.dumps(obj, ensure_ascii=False) + "\n")

    _print_summary(output_records, n_fail, len(healthy_sample))
    _validate_schema(OUT_PATH)
    _spot_check(OUT_PATH)
    return 0


# ---------- Reporting / verification ---------------------------------------


def _print_summary(records, n_fail, n_nonfail):
    n_total = len(records)
    primary_counts = Counter(li["primary_mode"] for _, _, li in records)
    triggered_counts = Counter()
    multi = 0
    severity_counts = Counter()
    category_counts = Counter()
    confidences = []
    csv_vs_recomp = Counter()

    for r, _rules, li in records:
        for m in li["triggered_modes"]:
            triggered_counts[m] += 1
        if len(li["triggered_modes"]) > 1:
            multi += 1
        severity_counts[li["structured_output"]["severity"]] += 1
        category_counts[li["structured_output"]["category"]] += 1
        confidences.append(li["structured_output"]["confidence"])
        csv = set(r["csv_modes"])
        rec = set(li["triggered_modes"])
        if csv == rec:
            csv_vs_recomp["exact_match"] += 1
        elif csv & rec:
            csv_vs_recomp["partial_overlap"] += 1
        else:
            csv_vs_recomp["disjoint"] += 1

    print("=" * 60)
    print(f"Wrote {n_total} rows to {OUT_PATH}")
    print(f"  failures:     {n_fail}")
    print(f"  non-failures: {n_nonfail} ({n_nonfail/n_total:.0%} of total)")
    print(f"  multi-mode failures: {multi}")
    print(f"\nPrimary mode distribution: {dict(primary_counts)}")
    print(f"Triggered mode counts:     {dict(triggered_counts)}")
    print(f"Severity distribution:     {dict(severity_counts)}")
    print(f"Category distribution:     {dict(category_counts)}")
    print(f"Confidence — mean: {sum(confidences)/len(confidences):.2f}, "
          f"min: {min(confidences):.2f}, max: {max(confidences):.2f}")
    print(f"\nCSV modes vs recomputed triggered set: {dict(csv_vs_recomp)}")


def _validate_schema(path: Path) -> None:
    if WorkflowResult is None:
        print("\n[schema] pydantic / agent_workflow not importable — skipping validation")
        return
    n_ok = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            WorkflowResult(**obj["structured_output"])
            n_ok += 1
    print(f"\n[schema] All {n_ok} structured_output entries validate against WorkflowResult")


def _spot_check(path: Path) -> None:
    """Print one clean single-mode HDF, one multi-mode, one near-threshold healthy."""
    targets = {"hdf_only": None, "multi": None, "near_healthy": None}
    with path.open(encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            tm = obj["labels"]["triggered_modes"]
            if targets["hdf_only"] is None and tm == ["HDF"]:
                targets["hdf_only"] = obj
            if targets["multi"] is None and len(tm) >= 2:
                targets["multi"] = obj
            if targets["near_healthy"] is None and obj["labels"]["machine_failure"] == 0:
                worst = max(obj["labels"]["rule_margins"][m] for m in ("HDF", "PWF", "OSF", "TWF"))
                if -0.10 < worst <= 0:
                    targets["near_healthy"] = obj
            if all(targets.values()):
                break

    print("\n" + "=" * 60)
    print("Spot-check samples:")
    for label, obj in targets.items():
        if obj is None:
            print(f"\n[{label}] (none found)")
            continue
        print(f"\n[{label}] UDI={obj['udi']} product={obj['product_id']} "
              f"primary={obj['labels']['primary_mode']} triggered={obj['labels']['triggered_modes']}")
        so = obj["structured_output"]
        print(f"  severity={so['severity']} category={so['category']} confidence={so['confidence']}")
        print(f"  evidence: {so['evidence']}")
        print(f"  causes:   {so['likely_root_causes']}")
        print(f"  actions:  {so['recommended_actions']}")
        print(f"  report:   {so['final_report']}")


if __name__ == "__main__":
    raise SystemExit(main())
