"""LoRA SFT on Qwen2.5-7B Instruct.

Run from terminal (zalecane):
    python finetuning/training/train.py
    python finetuning/training/train.py --max-steps 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
from transformers import AutoTokenizer, BitsAndBytesConfig, AutoModelForCausalLM

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from finetuning.training import config as cfg


def _load_chat_dataset(path: Path):
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
    parser.add_argument("--max-steps", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    import torch
    from peft import LoraConfig
    from trl import SFTConfig, SFTTrainer

    cfg.RUN_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[train] base model: {cfg.BASE_MODEL_ID}")
    print(f"[train] run dir:    {cfg.RUN_DIR}")
    print(f"[train] torch:      {torch.__version__} (cuda={torch.cuda.is_available()})")

    tokenizer = AutoTokenizer.from_pretrained(cfg.BASE_MODEL_ID, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        llm_int8_enable_fp32_cpu_offload=True,
    )

    model = AutoModelForCausalLM.from_pretrained(
        cfg.BASE_MODEL_ID,
        quantization_config=bnb_config,
        device_map="auto",
        low_cpu_mem_usage=True,
        trust_remote_code=True,
        max_memory={0: "4.5GiB", "cpu": "12GiB"},
    )

    model.config.use_cache = False
    model.gradient_checkpointing_enable()

    lora_config = LoraConfig(**cfg.LORA)

    train_ds = _load_chat_dataset(cfg.TRAIN_PATH)
    val_ds = _load_chat_dataset(cfg.VAL_PATH)
    print(f"[train] train rows: {len(train_ds)}, val rows: {len(val_ds)}")

    train_args = dict(cfg.TRAIN)
    if args.max_steps is not None:
        train_args["max_steps"] = args.max_steps
        train_args["num_train_epochs"] = 1
        train_args["save_strategy"] = "no"
        train_args["eval_strategy"] = "no"
        train_args["load_best_model_at_end"] = False

    sft_args = SFTConfig(**train_args)

    trainer = SFTTrainer(
        model=model,
        args=sft_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        peft_config=lora_config,
        processing_class=tokenizer,
    )

    trainer.train(resume_from_checkpoint=args.resume or None)

    cfg.ADAPTER_DIR.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(cfg.ADAPTER_DIR))
    tokenizer.save_pretrained(str(cfg.ADAPTER_DIR))

    print(f"[train] adapter saved to {cfg.ADAPTER_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
