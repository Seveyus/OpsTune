"""LoRA SFT on Llama 3.1 8B Instruct (target: AMD MI300X / ROCm).

Reads `finetuning/splits/{train,val}.jsonl` (chat-format SFT pairs already
produced by `generate_reports.py`) and trains a LoRA adapter on top of the
base model, saving to `finetuning/training/runs/<RUN_NAME>/adapter/`.

Run:
    python finetuning/training/train.py
    python finetuning/training/train.py --max-steps 5    # smoke test

Env:
    HF_TOKEN              HuggingFace token (Llama 3.1 license must be accepted)
    OPSTUNE_BASE_MODEL    override BASE_MODEL_ID
    OPSTUNE_RUN_NAME      override RUN_NAME (output dir)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from finetuning.training import config as cfg  # noqa: E402


def _load_chat_dataset(path: Path):
    """Load a chat-format JSONL file as a HF Dataset of {messages: [...]} rows."""
    from datasets import Dataset

    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        rows.append({"messages": obj["messages"]})
    return Dataset.from_list(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-steps", type=int, default=None,
                        help="Cap training at N steps (smoke test).")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from latest checkpoint in RUN_DIR.")
    args = parser.parse_args()

    import torch
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    cfg.RUN_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[train] base model: {cfg.BASE_MODEL_ID}")
    print(f"[train] run dir:    {cfg.RUN_DIR}")
    print(f"[train] torch:      {torch.__version__} (cuda={torch.cuda.is_available()})")

    # --- tokenizer ---------------------------------------------------------
    tokenizer = AutoTokenizer.from_pretrained(cfg.BASE_MODEL_ID, use_fast=True)
    if tokenizer.pad_token is None:
        # Llama tokenizers ship without a pad — reuse EOS, but add a dedicated id
        # so the loss mask doesn't accidentally hide EOS predictions.
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # --- model -------------------------------------------------------------
    model = AutoModelForCausalLM.from_pretrained(
        cfg.BASE_MODEL_ID,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        attn_implementation="sdpa",   # safe default on ROCm + CUDA
    )
    model.config.use_cache = False    # required for gradient checkpointing
    model.gradient_checkpointing_enable()

    lora_config = LoraConfig(**cfg.LORA)

    # --- data --------------------------------------------------------------
    train_ds = _load_chat_dataset(cfg.TRAIN_PATH)
    val_ds = _load_chat_dataset(cfg.VAL_PATH)
    print(f"[train] train rows: {len(train_ds)}, val rows: {len(val_ds)}")

    # --- training args -----------------------------------------------------
    train_args = dict(cfg.TRAIN)
    if args.max_steps is not None:
        train_args["max_steps"] = args.max_steps
        train_args["num_train_epochs"] = 1  # honored when max_steps < 0
        train_args["save_strategy"] = "no"
        train_args["eval_strategy"] = "no"
        train_args["load_best_model_at_end"] = False

    sft_args = SFTConfig(**train_args, **cfg.SFT)

    trainer = SFTTrainer(
        model=model,
        args=sft_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        peft_config=lora_config,
        tokenizer=tokenizer,
    )

    trainer.train(resume_from_checkpoint=args.resume or None)

    # --- save adapter ------------------------------------------------------
    cfg.ADAPTER_DIR.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(cfg.ADAPTER_DIR))
    tokenizer.save_pretrained(str(cfg.ADAPTER_DIR))

    # --- log ---------------------------------------------------------------
    log = {
        "base_model": cfg.BASE_MODEL_ID,
        "run_name": cfg.RUN_NAME,
        "lora": cfg.LORA,
        "train_args": train_args,
        "sft_args": cfg.SFT,
        "metrics_history": trainer.state.log_history,
    }
    cfg.TRAIN_LOG_PATH.write_text(json.dumps(log, indent=2, default=str))
    print(f"[train] adapter saved to {cfg.ADAPTER_DIR}")
    print(f"[train] training log:    {cfg.TRAIN_LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
