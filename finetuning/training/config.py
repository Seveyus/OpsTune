"""Single source of truth for the OpsTune fine-tuning run.

Every script in `finetuning/training/` imports from here so a config change
only happens in one place. Values can be overridden via env vars where
noted (lets you swap models or run names without editing the file).
"""

from __future__ import annotations

import os
from pathlib import Path

# --- paths -----------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent.parent
SPLITS_DIR = ROOT / "finetuning" / "splits"
TRAIN_PATH = SPLITS_DIR / "train.jsonl"
VAL_PATH = SPLITS_DIR / "val.jsonl"
TEST_PATH = SPLITS_DIR / "test.jsonl"
PRED_DIR = ROOT / "finetuning" / "eval" / "predictions"
RUNS_DIR = ROOT / "finetuning" / "training" / "runs"

# --- model -----------------------------------------------------------------
BASE_MODEL_ID = os.getenv("OPSTUNE_BASE_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
RUN_NAME = os.getenv("OPSTUNE_RUN_NAME", "opstune-llama31-8b-lora-v1")
RUN_DIR = RUNS_DIR / RUN_NAME
ADAPTER_DIR = RUN_DIR / "adapter"
MERGED_DIR = RUN_DIR / "merged"
TRAIN_LOG_PATH = RUN_DIR / "training_log.json"

# Output cache for inference (matches the format baseline_eval.ipynb expects)
PREDICTIONS_PATH = PRED_DIR / "finetuned.jsonl"

# --- LoRA ------------------------------------------------------------------
# Cover every linear layer for max representational coverage on a small dataset.
LORA = dict(
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    bias="none",
    task_type="CAUSAL_LM",
)

# --- training --------------------------------------------------------------
# Small dataset (338 train rows) → few epochs, conservative LR.
TRAIN = dict(
    output_dir=str(RUN_DIR),
    num_train_epochs=3,
    per_device_train_batch_size=4,
    per_device_eval_batch_size=4,
    gradient_accumulation_steps=4,         # effective batch = 16
    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    warmup_ratio=0.03,
    weight_decay=0.0,
    bf16=True,                             # MI300X native; A100/H100 also fine
    logging_steps=5,
    eval_strategy="epoch",
    save_strategy="epoch",
    save_total_limit=2,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    greater_is_better=False,
    report_to="none",                       # no wandb dependency by default
    seed=17,
)

# SFTConfig-specific knobs (passed via SFTConfig, not TrainingArguments)
SFT = dict(
    max_seq_length=1536,
    packing=False,                          # variable-length structured outputs — packing would cross-contaminate
    dataset_kwargs=dict(add_special_tokens=False, append_concat_token=False),
)

# --- inference -------------------------------------------------------------
INFER = dict(
    max_new_tokens=700,
    temperature=0.0,
    do_sample=False,
)
