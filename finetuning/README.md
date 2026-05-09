# OpsTune fine-tuning dataset

Builds the labeled `(sensors → structured WorkflowResult JSON)` dataset that the
fine-tuning pipeline will consume. Sourced from `ai4i2020.csv` at the repo root.

## Files

| File | Purpose |
|---|---|
| `thresholds.py` | AI4I documented thresholds (TWF window, HDF ΔT/rpm, PWF band, OSF variant limits) and helpers (`power_w`, `delta_t_k`, `osf_limit`). |
| `playbooks.py` | 9 hand-curated playbooks (TWF, HDF, PWF_LOW, PWF_HIGH, OSF, RNF, HDF_PWF, OSF_TWF, NORMAL). Each is `{root_causes, actions}` with `{variant}/{rpm}/...` placeholders. |
| `build_dataset.py` | Reads CSV → recomputes rules → labels rows → samples ~30 % healthy → emits structured outputs. Includes schema validation, CSV-vs-recompute cross-check, and a 3-row spot check. |
| `ai4i_labeled.jsonl` | Generated artifact, ~484 rows. The labels-and-target dataset. |
| `generate_reports.py` | Step 2 of dataset construction. For each labeled row, calls a cheap LLM (Groq Llama 3.1 8B by default) to synthesize a realistic operator-style narrative. Writes SFT chat-format pairs. Resumable, concurrent, retry-aware for free-tier rate limits. |
| `ai4i_finetune.jsonl` | Generated SFT-ready artifact: `{messages: [system, user=narrative, assistant=structured_output]}` per row. The actual fine-tuning training file. |

## Run

End-to-end (both stages):

```bash
# Stage 1 — labels & deterministic structured outputs (no LLM, no API key)
.venv/bin/python finetuning/build_dataset.py

# Stage 2 — synthesize operator narratives (needs an LLM API key)
export GROQ_API_KEY=...                # free, recommended
.venv/bin/python finetuning/generate_reports.py
# or smoke-test first:
.venv/bin/python finetuning/generate_reports.py --limit 8
```

Project uses a `uv`-managed `.venv`. Runtime deps beyond stdlib: `pydantic`
(schema validation; gracefully skipped if missing) and `openai` (Groq /
OpenAI-compatible client; only needed for stage 2).

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

## Stage 2 — operator-narrative synthesis (`generate_reports.py`)

Each labeled row is paired with one synthetic operator-style narrative
generated by a cheap LLM, producing the `(x, y)` pairs the model is trained on.

### Backend selection

Provider is chosen by env vars (no flag wiring needed):

| Env var | Effect |
|---|---|
| `GROQ_API_KEY` (default) | Routes to `https://api.groq.com/openai/v1` with `llama-3.1-8b-instant`. Free tier; rate-limited. |
| `OPENAI_API_KEY` | Routes to OpenAI (or anywhere via `OPENAI_BASE_URL`) with `gpt-4o-mini`. ~$0.10 for 484 rows. |
| `LLM_MODEL` | Override the model name on whichever backend is active. |

### Prompt design

The LLM is given the failure mode + sensor values for each row and asked
to write **one** 2–4 sentence first-person operator note that:
- Leads with what was *noticed* (sound, smell, vibration, smoke, alarm)
- Quotes at most 2 sensor readings verbatim
- Never names the failure mode (no "TWF/HDF/PWF/OSF/RNF")
- Never labels a number "high/low/normal" — just states what was seen
- Mentions the operator's response (stopped line, called maintenance) when natural
- Picks one of six rotating style recipes (terse / verbose / frustrated /
  hand-off / Slack DM / junior-form) for variety

For healthy rows the prompt switches to a non-event framing
(end-of-shift handover, false alarm, routine walk-around).

### Resumability and rate-limit handling

- Each completed row is appended to `ai4i_finetune.jsonl` and flushed
  immediately, so a crash or rate-limit kill loses no work.
- Re-running the script reads the output file, builds the set of UDIs
  already done, and processes only the missing ones.
- 429 responses from the provider are retried with exponential backoff;
  Groq's "Please try again in Xs" hint is parsed and honored, with the
  cap raised above 60 s so token-per-minute resets are absorbed.
- Concurrency is `MAX_WORKERS = 3` to stay under Groq's free-tier TPM.

### Output format

Chat-format SFT JSONL (one example per line):

```jsonc
{
  "messages": [
    {"role": "system",    "content": "You are OpsTune, an industrial..."},
    {"role": "user",      "content": "<synthetic operator narrative>"},
    {"role": "assistant", "content": "<structured_output as JSON string>"}
  ],
  "metadata": {"udi": 4088, "product_id": "L51267", "primary_mode": "HDF",
               "triggered_modes": ["HDF"]}
}
```

The `assistant` content is the same `structured_output` produced by stage 1,
serialized as JSON. The system prompt is identical for every row so the
fine-tuned model learns a stable contract.

## Out of scope (next steps)

- **Train/val/test split.**
- **Fine-tuning pipeline** (LoRA config, training loop, vLLM serving).
