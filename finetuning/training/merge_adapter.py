"""Merge the LoRA adapter into the base weights for vLLM full-weight serving.

vLLM can serve LoRA adapters directly (`--enable-lora`), but inference is
faster and simpler with merged weights. Use this for the demo deployment.

Run:
    python finetuning/training/merge_adapter.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from finetuning.training import config as cfg  # noqa: E402


def main() -> int:
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not cfg.ADAPTER_DIR.exists():
        print(f"[merge] adapter not found at {cfg.ADAPTER_DIR} — train first.")
        return 1

    print(f"[merge] base:    {cfg.BASE_MODEL_ID}")
    print(f"[merge] adapter: {cfg.ADAPTER_DIR}")
    print(f"[merge] target:  {cfg.MERGED_DIR}")

    base = AutoModelForCausalLM.from_pretrained(
        cfg.BASE_MODEL_ID, torch_dtype=torch.bfloat16, device_map="auto",
    )
    model = PeftModel.from_pretrained(base, str(cfg.ADAPTER_DIR))
    merged = model.merge_and_unload()

    cfg.MERGED_DIR.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(str(cfg.MERGED_DIR), safe_serialization=True)

    tokenizer = AutoTokenizer.from_pretrained(str(cfg.ADAPTER_DIR), use_fast=True)
    tokenizer.save_pretrained(str(cfg.MERGED_DIR))

    print(f"[merge] merged weights → {cfg.MERGED_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
