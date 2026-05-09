# OpsTune fine-tuning dataset

Builds the labeled `(sensors → structured WorkflowResult JSON)` dataset that the
fine-tuning pipeline will consume. Sourced from `ai4i2020.csv` at the repo root.

## Files

| File | Purpose |
|---|---|
| `thresholds.py` | AI4I documented thresholds (TWF window, HDF ΔT/rpm, PWF band, OSF variant limits) and helpers (`power_w`, `delta_t_k`, `osf_limit`). |
| `playbooks.py` | 9 hand-curated playbooks (TWF, HDF, PWF_LOW, PWF_HIGH, OSF, RNF, HDF_PWF, OSF_TWF, NORMAL). Each is `{root_causes, actions}` with `{variant}/{rpm}/...` placeholders. |
| `build_dataset.py` | Reads CSV → recomputes rules → labels rows → samples ~30 % healthy → emits structured outputs. Includes schema validation, CSV-vs-recompute cross-check, and a 3-row spot check. |
| `ai4i_labeled.jsonl` | Generated artifact, ~484 rows. |

## Run

```bash
.venv/bin/python finetuning/build_dataset.py
```

(Project uses a `uv`-managed `.venv`. The only runtime dep beyond stdlib is
`pydantic`, used only for the schema-validation pass — the script gracefully
skips that step if pydantic isn't importable.)

## Output schema

One JSON object per line:

```jsonc
{
  "udi": 4088,
  "product_id": "L51267",
  "product_variant": "L",
  "sensors": { "air_temp_k": ..., "process_temp_k": ..., "rotational_speed_rpm": ...,
               "torque_nm": ..., "tool_wear_min": ... },
  "derived": { "delta_t_k": ..., "power_w": ..., "torque_x_wear_minNm": ... },
  "labels": {
    "machine_failure": 1,
    "primary_mode": "HDF",                   // null for non-failure rows
    "triggered_modes": ["HDF", "PWF"],       // every rule that fired
    "csv_modes":       ["HDF"],              // raw flags from the CSV (kept for cross-check)
    "rule_margins": { "TWF": -3.7, "HDF": 0.003, "PWF": -0.31, "OSF": -0.37, "RNF": -1.0 },
    "pwf_side": "low"                         // "low" / "high" / null
  },
  "structured_output": {                     // matches agent_workflow.schemas.WorkflowResult
    "severity": "high",                       // low / medium / high / critical
    "category": "thermal",                    // mechanical / electrical / thermal / unknown / ...
    "likely_root_causes": [...],
    "evidence": [...],
    "recommended_actions": [...],
    "confidence": 0.78,
    "final_report": "..."
  }
}
```

`structured_output` is exactly the WorkflowResult contract from
`agent_workflow/schemas.py` — it's what the fine-tuned model will be trained
to produce.

## Labeling rules (recomputed, not trusted from CSV)

| Mode | Rule | Notes |
|---|---|---|
| TWF | `200 ≤ tool_wear ≤ 240` | The CSV's TWF flag is the random subset that *actually failed* inside that window — both signals are kept. |
| HDF | `(process_t − air_t) < 8.6 K` AND `rpm < 1380` | |
| PWF | `power = torque · rpm · 2π/60`, fails if `< 3500` or `> 9000` W | `pwf_side` distinguishes under-power (drivetrain slip) from over-power (overload). |
| OSF | `torque · tool_wear > {L: 11000, M: 12000, H: 13000}` minNm | Variant-aware. |
| RNF | Trust the CSV column (untestable from sensors). | |

`rule_margins` are **signed, normalized** distances to the threshold (positive
⇒ rule fired). They drive `confidence` and the spot-check stratification.

When multiple modes fire, the **primary mode** is picked by severity priority
`HDF > PWF > OSF > TWF > RNF`. All triggered modes still appear in
`triggered_modes`, `evidence`, and (for unknown combos) `likely_root_causes`.

## Severity / category / confidence derivation

- **severity** — non-failure → `low`; RNF only → `low`; TWF only → `medium`; OSF
  → `medium` if margin ≤ 0.20 else `high`; HDF or PWF → `high`; ≥ 2 modes →
  `high`, bumped to `critical` if ≥ 3 modes OR any margin > 0.30.
- **category** — HDF→thermal, PWF→electrical, TWF/OSF→mechanical, RNF→unknown,
  multi-mode follows the primary mode, non-failure→unknown.
- **confidence** — single mode: `0.50 + 0.40·margin`; multi-mode: minus
  `0.10·(n_modes−1)` ambiguity penalty; RNF-only: 0.45; non-failure: 0.85–0.95
  scaled by slack to nearest threshold; clipped to [0.30, 0.95].

## Sampling

- Keep all 339 failure rows.
- Add ~145 non-failure rows so the final mix is ~70 / 30. The non-failure
  sample is stratified: 60 % clearly healthy, 40 % within 10 % of any
  threshold — so the model sees the boundary, not just trivial negatives.
- Final: ~484 rows, randomly shuffled.

## Cross-check sanity (last run)

| | count |
|---|---|
| Recomputed `triggered_modes` exact-matches CSV `csv_modes` | 397 |
| Partial overlap (typical: CSV TWF flag missing because it was a "replaced" event, or multi-mode where CSV only flagged one) | 76 |
| Disjoint (pure RNF: CSV says fail, no documented rule fires) | 11 |

## Out of scope (next steps)

- **Operator-style narrative input generation.** The fine-tuning `(x, y)` pair
  needs a messy human-style report as `x`. A separate script will consume
  `ai4i_labeled.jsonl` and template/paraphrase narratives from the labeled
  sensor values + primary mode.
- **Train/val/test split.**
- **Fine-tuning pipeline** (LoRA config, training loop, vLLM serving).
