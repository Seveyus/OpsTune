"""Generate operator-style narrative inputs for each labeled row.

Reads:  finetuning/ai4i_labeled.jsonl
Writes: finetuning/ai4i_finetune.jsonl   (chat-format SFT pairs)

Each output line is:
    {
      "messages": [
        {"role": "system",    "content": SYSTEM_PROMPT},
        {"role": "user",      "content": <synthetic operator narrative>},
        {"role": "assistant", "content": <structured_output JSON string>}
      ],
      "metadata": {"udi": ..., "primary_mode": ...}
    }

Default backend is Groq (free tier, OpenAI-compatible) but any
OpenAI-compatible endpoint works via env vars:

    GROQ_API_KEY=...                                # default path
    OPENAI_API_KEY=... OPENAI_BASE_URL=...          # for OpenAI / proxies
    LLM_MODEL=llama-3.1-8b-instant                  # override model

Resumable: if the output file already exists, UDIs already present are
skipped — safe to re-run after a crash or rate-limit.

Run:
    .venv/bin/python finetuning/generate_reports.py
    .venv/bin/python finetuning/generate_reports.py --limit 5    # smoke test
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IN_PATH = ROOT / "finetuning" / "ai4i_labeled.jsonl"
OUT_PATH = ROOT / "finetuning" / "ai4i_finetune.jsonl"

DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.1-8b-instant"
MAX_WORKERS = 3
MAX_RETRIES = 8
BASE_BACKOFF_S = 4.0
MAX_BACKOFF_S = 75.0  # Groq free tier TPM resets per minute

SYSTEM_PROMPT = (
    "You are OpsTune, an industrial operations incident analyst. "
    "Read the operator's incident report and produce a JSON object with these fields: "
    "severity (low|medium|high|critical), "
    "category (mechanical|electrical|thermal|sensor|process|quality|safety|unknown), "
    "likely_root_causes (list of strings, most likely first), "
    "evidence (list of short observation strings drawn from the report), "
    "recommended_actions (list of strings, highest priority first), "
    "confidence (number between 0 and 1), "
    "and final_report (a short summary paragraph). "
    "Return JSON only — no markdown fences, no commentary."
)

# Stylistic recipes the LLM picks from to vary the operator voice. The recipe
# is included in the prompt so the LLM produces varied narratives instead of
# a single template repeated 484 times.
STYLE_RECIPES = [
    "terse shift-end note from a senior operator, mostly observations and what they did",
    "verbose maintenance ticket with timestamps and a bit of unrelated context",
    "frustrated mid-shift note — operator was annoyed and rushed",
    "calm hand-off message to the next shift, lists symptoms in order they appeared",
    "short Slack-style message to the maintenance lead, slightly informal",
    "structured incident form filled in by a junior operator, slightly repetitive",
]

NARRATIVE_INSTRUCTIONS_FAILURE = """\
Write ONE first-person operator report — no alternatives, no numbered list,
no headings, no preamble. Hard cap: 2 to 4 sentences, single paragraph.

The report should sound like a real plant operator, NOT a sensor dump:
- Lead with what was NOTICED (sound, smell, vibration, smoke, alarm, what
  the part looked like, what the line did).
- You may naturally quote at most 2 sensor readings, but ONLY values that
  appear in the snapshot above. Quote them verbatim. NEVER invent or guess
  a value the snapshot does not contain (no "power dropped to zero" if
  power is not in the snapshot like that).
- NEVER label a number as "high", "low", "normal", "abnormal", "off",
  "way off", "above the operating range", etc. Just say what was seen
  ("torque was reading 54 Nm", not "torque was way too high"). Operators
  on the floor often quote raw numbers without judgment.
- Mention briefly what the operator did in response (stopped the line, called
  maintenance, swapped tool, paged supervisor) when it fits.
- DO NOT name the failure mode or its acronym (no "TWF/HDF/PWF/OSF/RNF",
  no "tool wear failure", "heat dissipation failure", "power failure",
  "overstrain", "random failure"). The model has to infer it.
- DO NOT mention severity, category, root causes, recommended actions,
  or confidence. Those are the model's job.
- Vary phrasing across reports. About half the time include a minor
  irrelevant aside (shift, weather, neighboring line).
"""

NARRATIVE_INSTRUCTIONS_HEALTHY = """\
Write ONE first-person operator note — no alternatives, no numbered list,
no headings, no preamble. Hard cap: 2 to 4 sentences, single paragraph.

The line is HEALTHY this run. Natural framings:
- end-of-shift handover saying the line ran clean
- routine inspection or QC walk-around with no findings
- a brief log entry confirming numbers stayed in band
- a "false alarm" follow-up where the operator went to check and found nothing

Rules:
- Do NOT invent a failure or symptom.
- You may mention at most 1 nominal reading if natural; mostly qualitative.
- Vary phrasing across reports.
"""


def make_user_payload(row: dict) -> str:
    """Build the prompt content sent to the LLM (the inputs the operator
    would have access to on the floor)."""
    sensors = row["sensors"]
    derived = row["derived"]
    labels = row["labels"]
    primary = labels["primary_mode"]
    triggered = labels["triggered_modes"]

    facts = (
        f"Product ID: {row['product_id']}  (variant {row['product_variant']})\n"
        f"Air temperature: {sensors['air_temp_k']} K\n"
        f"Process temperature: {sensors['process_temp_k']} K\n"
        f"ΔT (process − air): {derived['delta_t_k']} K\n"
        f"Rotational speed: {sensors['rotational_speed_rpm']} rpm\n"
        f"Torque: {sensors['torque_nm']} Nm\n"
        f"Tool wear: {sensors['tool_wear_min']} min\n"
        f"Computed power: {derived['power_w']} W\n"
        f"Torque × wear: {derived['torque_x_wear_minNm']} minNm\n"
    )

    if primary is None:
        framing = (
            "GROUND TRUTH: this row is HEALTHY — no failure occurred. "
            "Generate a realistic non-event operator note.\n\n"
            f"Sensor snapshot (for your reference, do not list mechanically):\n{facts}\n"
            f"{NARRATIVE_INSTRUCTIONS_HEALTHY}\n"
            f"Style for this report: {random.choice(STYLE_RECIPES)}\n\n"
            "Return ONLY the operator note — no preamble, no quotes, no JSON."
        )
    else:
        framing = (
            f"GROUND TRUTH (do NOT mention in the report): the underlying "
            f"failure mode is {primary}"
            + (f" (with co-triggered modes {triggered})" if len(triggered) > 1 else "")
            + ".\n\n"
            f"Sensor readings on the cell HMI when the event occurred:\n{facts}\n"
            f"{NARRATIVE_INSTRUCTIONS_FAILURE}\n"
            f"Style for this report: {random.choice(STYLE_RECIPES)}\n\n"
            "Return ONLY the operator narrative — no preamble, no quotes, no JSON."
        )
    return framing


def make_client():
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit(
            "openai package missing — run: uv pip install openai"
        ) from exc

    groq_key = os.getenv("GROQ_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    if groq_key and not openai_key:
        return OpenAI(api_key=groq_key, base_url=DEFAULT_GROQ_BASE_URL), os.getenv(
            "LLM_MODEL", DEFAULT_MODEL
        )
    if openai_key:
        base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_API_BASE")
        model = os.getenv("LLM_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        return OpenAI(api_key=openai_key, base_url=base_url), model

    raise SystemExit(
        "No API key found. Set GROQ_API_KEY (recommended, free) "
        "or OPENAI_API_KEY (with optional OPENAI_BASE_URL for other providers)."
    )


_NUMBERED_LIST_RE = __import__("re").compile(r"(?m)^\s*(?:\d+[.)]|[-*])\s+")
_PREAMBLE_RE = __import__("re").compile(
    r"^(?:here(?:'s| is| are)|sure[,!]|of course|certainly[,!]?|below|the following).*?\n+",
    __import__("re").IGNORECASE | __import__("re").DOTALL,
)


def _sanitize_narrative(text: str) -> str:
    """Trim quotes, strip preambles, and collapse multi-option outputs to the first."""
    text = text.strip()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1].strip()
    # Drop a "Here are 3 reports..." preamble if present.
    text = _PREAMBLE_RE.sub("", text, count=1).strip()
    # If the model returned a numbered list, keep only the first item.
    parts = _NUMBERED_LIST_RE.split(text)
    if len(parts) > 2:
        first = parts[1].strip()
        # Cut at the next list marker if it sneaked through.
        for i in range(2, len(parts)):
            pass
        text = first
    # Collapse to a single paragraph (the spec asks for one paragraph).
    text = " ".join(line.strip() for line in text.splitlines() if line.strip())
    return text


def call_llm(client, model: str, prompt: str) -> str:
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=0.7,
                max_tokens=260,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You generate ONE realistic synthetic operator incident "
                            "report per request. Output only the report itself — no "
                            "alternatives, no numbered options, no headings, no JSON."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            text = (resp.choices[0].message.content or "").strip()
            text = _sanitize_narrative(text)
            if text:
                return text
            raise RuntimeError("empty completion")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            wait = min(MAX_BACKOFF_S, BASE_BACKOFF_S * (2 ** attempt)) + random.random()
            # Honor "Please try again in Xs" hint from Groq's 429 body when present.
            msg = str(exc)
            m = __import__("re").search(r"try again in ([\d.]+)s", msg)
            if m:
                try:
                    wait = max(wait, float(m.group(1)) + 1.0)
                except ValueError:
                    pass
            time.sleep(wait)
    raise RuntimeError(f"LLM call failed after {MAX_RETRIES} attempts: {last_err}")


def already_done(path: Path) -> set[int]:
    if not path.exists():
        return set()
    seen: set[int] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
                seen.add(int(obj["metadata"]["udi"]))
            except Exception:  # noqa: BLE001
                continue
    return seen


def process_row(client, model: str, row: dict) -> dict:
    prompt = make_user_payload(row)
    narrative = call_llm(client, model, prompt)
    structured_json = json.dumps(row["structured_output"], ensure_ascii=False)
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": narrative},
            {"role": "assistant", "content": structured_json},
        ],
        "metadata": {
            "udi": row["udi"],
            "product_id": row["product_id"],
            "primary_mode": row["labels"]["primary_mode"],
            "triggered_modes": row["labels"]["triggered_modes"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N pending rows (smoke test)")
    parser.add_argument("--workers", type=int, default=MAX_WORKERS)
    args = parser.parse_args()

    random.seed(17)
    client, model = make_client()
    print(f"[gen] backend model: {model}")

    rows = [json.loads(line) for line in IN_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    done = already_done(OUT_PATH)
    pending = [r for r in rows if r["udi"] not in done]
    if args.limit is not None:
        pending = pending[: args.limit]
    print(f"[gen] {len(rows)} total, {len(done)} already done, {len(pending)} to process")

    if not pending:
        print("[gen] nothing to do.")
        return 0

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_f = OUT_PATH.open("a", encoding="utf-8")

    completed = 0
    failed: list[tuple[int, str]] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(process_row, client, model, r): r for r in pending}
        for fut in as_completed(futures):
            row = futures[fut]
            try:
                obj = fut.result()
            except Exception as exc:  # noqa: BLE001
                failed.append((row["udi"], str(exc)))
                continue
            out_f.write(json.dumps(obj, ensure_ascii=False) + "\n")
            out_f.flush()
            completed += 1
            if completed % 25 == 0 or completed == len(pending):
                rate = completed / max(1e-6, time.time() - t0)
                print(f"[gen] {completed}/{len(pending)}  ({rate:.1f} rows/s)")

    out_f.close()
    print(f"[gen] done: {completed} written, {len(failed)} failed")
    if failed:
        print("[gen] failed UDIs (first 5):", failed[:5])
        return 1
    print(f"[gen] output: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
