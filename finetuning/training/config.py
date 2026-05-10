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
BASE_MODEL_ID = os.getenv("OPSTUNE_BASE_MODEL", "Qwen/Qwen2.5-7B-Instruct")
RUN_NAME = os.getenv("OPSTUNE_RUN_NAME", "opstune-qwen25-7b-lora-v1")
RUN_DIR = RUNS_DIR / RUN_NAME
ADAPTER_DIR = RUN_DIR / "adapter"
MERGED_DIR = RUN_DIR / "merged"
TRAIN_LOG_PATH = RUN_DIR / "training_log.json"

# Output cache for inference (matches the format baseline_eval.ipynb expects)
PREDICTIONS_PATH = PRED_DIR / "finetuned.jsonl"

# --- Quantization ----------------------------------------------------------
QUANT = dict(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype="bfloat16",
    bnb_4bit_use_double_quant=True,
)

# --- LoRA ------------------------------------------------------------------
# Cover every linear layer for max representational coverage on a small dataset.
LORA = dict(
    r=8,
    lora_alpha=16,
    lora_dropout=0.05,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
    ],
    bias="none",
    task_type="CAUSAL_LM",
)

# --- training --------------------------------------------------------------
# Small dataset (338 train rows) → few epochs, conservative LR.
TRAIN = dict(
    output_dir=str(RUN_DIR),
    num_train_epochs=3,
    per_device_train_batch_size=1,
    per_device_eval_batch_size=1,
    gradient_accumulation_steps=8,
    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    warmup_ratio=0.03,
    weight_decay=0.0,
    bf16=True,
    logging_steps=5,
    eval_strategy="epoch",
    save_strategy="epoch",
    save_total_limit=2,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    greater_is_better=False,
    report_to="none",
    seed=17,
    max_grad_norm=0.3,
    optim="paged_adamw_8bit",
)

MAX_SEQ_LENGTH = 128
