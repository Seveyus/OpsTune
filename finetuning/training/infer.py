"""Run the fine-tuned model on the held-out test split.

Loads `BASE_MODEL_ID` + the LoRA adapter from `runs/<RUN_NAME>/adapter/`,
generates a structured-output prediction per test narrative, and writes
the cache file `finetuning/eval/predictions/finetuned.jsonl` in the exact
schema `baseline_eval.ipynb` expects ({udi, primary_mode, raw}). After this,
re-running the notebook with `RUN_NAME=finetuned` does pure analysis.

Run:
    python finetuning/training/infer.py
    python finetuning/training/infer.py --merged    # use merged weights instead of base+adapter
    python finetuning/training/infer.py --limit 5   # smoke test
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from finetuning.training import config as cfg  # noqa: E402
from finetuning.generate_reports import SYSTEM_PROMPT  # noqa: E402


def _already_cached(path: Path) -> set[int]:
    if not path.exists():
        return set()
    seen: set[int] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            seen.add(int(json.loads(line)["udi"]))
        except Exception:  # noqa: BLE001
            continue
    return seen


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged", action="store_true",
                        help="Load runs/<RUN_NAME>/merged/ instead of base+adapter.")
    parser.add_argument("--limit", type=int, default=None,
                        help="Only run on the first N test rows (smoke test).")
    parser.add_argument("--out", type=Path, default=cfg.PREDICTIONS_PATH,
                        help="Output JSONL path (default: finetuning/eval/predictions/finetuned.jsonl).")
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"[infer] base model: {cfg.BASE_MODEL_ID}")
    print(f"[infer] adapter:    {cfg.ADAPTER_DIR}")
    print(f"[infer] out:        {args.out}")

    # --- load model --------------------------------------------------------
    if args.merged:
        load_path = str(cfg.MERGED_DIR)
        print(f"[infer] loading merged weights from {load_path}")
        tokenizer = AutoTokenizer.from_pretrained(load_path, use_fast=True)
        model = AutoModelForCausalLM.from_pretrained(
            load_path, torch_dtype=torch.bfloat16, device_map="auto",
        )
    else:
        from peft import PeftModel
        tokenizer = AutoTokenizer.from_pretrained(str(cfg.ADAPTER_DIR), use_fast=True)
        base = AutoModelForCausalLM.from_pretrained(
            cfg.BASE_MODEL_ID, torch_dtype=torch.bfloat16, device_map="auto",
        )
        model = PeftModel.from_pretrained(base, str(cfg.ADAPTER_DIR))

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model.eval()

    # --- load test set -----------------------------------------------------
    rows = [json.loads(l) for l in cfg.TEST_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    cached = _already_cached(args.out)
    pending = [r for r in rows if r["metadata"]["udi"] not in cached]
    if args.limit is not None:
        pending = pending[: args.limit]
    print(f"[infer] test rows: {len(rows)}, cached: {len(cached)}, to run: {len(pending)}")

    if not pending:
        print("[infer] nothing to do.")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    out_f = args.out.open("a", encoding="utf-8")

    t0 = time.time()
    for i, row in enumerate(pending, 1):
        narrative = row["messages"][1]["content"]
        chat = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": narrative},
        ]
        inputs = tokenizer.apply_chat_template(
            chat, add_generation_prompt=True, return_tensors="pt"
        ).to(model.device)

        with torch.inference_mode():
            output_ids = model.generate(
                inputs,
                max_new_tokens=cfg.INFER["max_new_tokens"],
                do_sample=cfg.INFER["do_sample"],
                temperature=cfg.INFER["temperature"] if cfg.INFER["do_sample"] else None,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )

        gen_ids = output_ids[0, inputs.shape[1]:]
        raw = tokenizer.decode(gen_ids, skip_special_tokens=True).strip()

        out_f.write(json.dumps({
            "udi": row["metadata"]["udi"],
            "primary_mode": row["metadata"]["primary_mode"],
            "raw": raw,
        }, ensure_ascii=False) + "\n")
        out_f.flush()

        if i % 10 == 0 or i == len(pending):
            rate = i / max(1e-6, time.time() - t0)
            print(f"[infer] {i}/{len(pending)}  ({rate:.2f} rows/s)")

    out_f.close()
    print(f"[infer] predictions → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
