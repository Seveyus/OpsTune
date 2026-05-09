# OpsTune fine-tuning pipeline

LoRA fine-tunes Llama 3.1 8B Instruct on the OpsTune SFT splits, evaluates
the result against the un-fine-tuned baseline using the same eval notebook,
and serves the adapter (or merged weights) with vLLM.

**Compute target: AMD Developer Cloud MI300X (ROCm 6.x).** Scripts also
work unchanged on NVIDIA CUDA boxes; only the torch wheel is installed
from a different index. The local laptop has no usable GPU — everything
in this directory runs on the GPU box; the laptop only consumes the
predictions/summaries that get committed back.

## Files

| File | Purpose |
|---|---|
| `requirements.txt` | Pip deps. Install torch first from the right index (ROCm or CUDA). |
| `config.py` | Single source of truth: model id, LoRA hyperparams, training hyperparams, paths. Override via env vars. |
| `train.py` | TRL `SFTTrainer` + PEFT LoRA. Reads `splits/{train,val}.jsonl`, saves adapter to `runs/<RUN_NAME>/adapter/`. |
| `infer.py` | Loads base + adapter (or merged), runs on `splits/test.jsonl`, writes `eval/predictions/finetuned.jsonl` in the schema the eval notebook expects. |
| `merge_adapter.py` | Merges LoRA into base for vLLM full-weight serving. Optional. |
| `compare_runs.py` | Diffs `baseline.summary.json` vs `finetuned.summary.json` — the demo screenshot. |
| `serve_vllm.sh` | OpenAI-compatible vLLM server. Defaults to LoRA mode; `--merged` flag uses merged weights. |
| `runs/` | Gitignored. Per-run output: checkpoints, adapter, merged weights, training logs. |

## End-to-end on MI300X

```bash
# 0. Provision an MI300X instance on AMD Developer Cloud.
# 1. Clone + venv
git clone <repo>
cd OpsTune
python -m venv .venv && source .venv/bin/activate

# 2. Install torch for ROCm 6.2, then everything else
pip install --pre torch --index-url https://download.pytorch.org/whl/rocm6.2
pip install -r finetuning/training/requirements.txt

# 3. HuggingFace auth (Llama 3.1 license must be accepted on your account)
export HF_TOKEN=...
huggingface-cli login --token "$HF_TOKEN"

# 4. (Optional) Smoke test — 5 steps, no checkpoint
python finetuning/training/train.py --max-steps 5

# 5. Full training run (~10–15 min on a single MI300X)
python finetuning/training/train.py
# → runs/opstune-llama31-8b-lora-v1/adapter/
# → runs/opstune-llama31-8b-lora-v1/training_log.json

# 6. Generate predictions on the held-out test split
python finetuning/training/infer.py
# → finetuning/eval/predictions/finetuned.jsonl

# 7. Re-run the eval notebook against the finetuned predictions.
#    The notebook caches by RUN_NAME, so it sees all 73 predictions cached
#    and just runs the analysis cells.
RUN_NAME=finetuned BASELINE_MODEL=meta-llama/Llama-3.1-8B-Instruct \
  jupyter nbconvert --to notebook --execute --inplace \
    --ExecutePreprocessor.kernel_name=opstune-venv \
    finetuning/eval/baseline_eval.ipynb
# → finetuning/eval/predictions/finetuned.summary.json

# 8. Print the before/after delta table
python finetuning/training/compare_runs.py
```

## Serving

```bash
# Optional: merge LoRA into base for faster inference
python finetuning/training/merge_adapter.py
# → runs/opstune-llama31-8b-lora-v1/merged/

# Serve (LoRA-mode default; --merged uses the merged weights)
bash finetuning/training/serve_vllm.sh           # base + adapter on :8000
bash finetuning/training/serve_vllm.sh --merged  # merged weights

# Sanity check
curl http://localhost:8000/v1/models
curl http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "opstune",
    "messages": [
      {"role":"system","content":"You are OpsTune..."},
      {"role":"user","content":"Line 3 stopped, vibration was heavy and torque pegged at 65 Nm..."}
    ]
  }'
```

Wire the existing backend at it via env vars (no code changes needed —
`agent_workflow/langchain_backend.py` already honors these):

```bash
export OPENAI_BASE_URL=http://<gpu-host>:8000/v1
export OPENAI_API_KEY=dummy
export OPENAI_MODEL=opstune
```

## Config knobs

Everything central lives in `config.py`. Common overrides via env:

| Env | Effect |
|---|---|
| `OPSTUNE_BASE_MODEL` | Swap the base (e.g. `Qwen/Qwen2.5-7B-Instruct` if Llama license is blocked). |
| `OPSTUNE_RUN_NAME`   | Name the output directory under `runs/`. |
| `HF_HOME`            | Where to cache HF model downloads (set to a big disk on cloud images). |

If you change LoRA rank/targets or training hyperparams, edit `config.py`
directly — every script re-reads from there.

## Notes on the AMD path

- vLLM ROCm wheel is not always on PyPI; if `pip install vllm` fails on
  the AMD image, follow https://docs.vllm.ai/en/latest/getting_started/amd-installation.html
  (typically a `pip install` from the AMD vLLM fork branch, or a Docker
  image they publish).
- bitsandbytes 4-bit is **not** used (incomplete ROCm support, and the
  MI300X has 192 GB so we don't need it). All training is bf16.
- Flash-attention is not required — `attn_implementation="sdpa"` works
  on both ROCm and CUDA out of the box.

## Why these choices

- **TRL `SFTTrainer` + PEFT** — least abstraction over HF transformers, easiest to debug at hackathon pace. Works identically on ROCm + CUDA.
- **LoRA r=16 over every linear** — covers attention + MLP for max representational coverage on a small (338-row) dataset; adapter is ~50 MB.
- **3 epochs, cosine LR 2e-4, effective batch 16** — standard small-dataset LoRA recipe; `load_best_model_at_end` pulls the best eval-loss checkpoint.
- **`packing=False`** — variable-length structured outputs would cross-contaminate if packed.
- **bf16 throughout** — MI300X native; no quantization complexity.
