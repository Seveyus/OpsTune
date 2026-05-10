# OpsTune fine-tuning pipeline

LoRA fine-tunes Qwen2.5-3B-Instruct (or 7B) on the OpsTune SFT splits, evaluates
the result against the un-fine-tuned baseline using the same eval notebook,
and serves the adapter with a lightweight inference server or vLLM.

**Successfully trained on:** RTX 3060 Laptop (6GB VRAM) using Qwen2.5-3B-Instruct
with 4-bit quantization. Scripts also work on AMD MI300X (ROCm 6.x) and other
NVIDIA CUDA GPUs.

## Files

| File | Purpose |
|---|---|
| `requirements.txt` | Pip deps. PyTorch + transformers + PEFT + TRL + bitsandbytes. |
| `config.py` | Single source of truth: model id, LoRA hyperparams, training hyperparams, paths. Override via env vars. |
| `train.py` | TRL `SFTTrainer` + PEFT LoRA. Reads `splits/{train,val}.jsonl`, saves adapter to `runs/<RUN_NAME>/adapter/`. |
| `infer.py` | Loads base + adapter (or merged), runs on `splits/test.jsonl`, writes `eval/predictions/finetuned.jsonl` in the schema the eval notebook expects. |
| `merge_adapter.py` | Merges LoRA into base for vLLM full-weight serving. Optional. |
| `compare_runs.py` | Diffs `baseline.summary.json` vs `finetuned.summary.json` — the demo screenshot. |
| `serve_simple.py` | Lightweight OpenAI-compatible server using transformers. Works on 6GB GPUs. |
| `serve_vllm.sh` | Production vLLM server. Requires 8GB+ GPU. Defaults to LoRA mode; `--merged` flag uses merged weights. |
| `runs/` | Gitignored. Per-run output: checkpoints, adapter, merged weights, training logs. |

## End-to-end training (6GB+ GPU)

```bash
# 1. Clone + venv
git clone <repo>
cd OpsTune
python -m venv .venv && source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure model (defaults to Qwen2.5-3B-Instruct for 6GB GPUs)
# Edit .env or export:
export OPSTUNE_BASE_MODEL=Qwen/Qwen2.5-3B-Instruct
export OPSTUNE_RUN_NAME=opstune-qwen25-3b-lora-v1
export HF_TOKEN=hf_...  # From https://huggingface.co/settings/tokens

# 4. (Optional) Smoke test — 5 steps, no checkpoint
python finetuning/training/train.py --max-steps 5

# 5. Full training run (~22 min on RTX 3060 Laptop, 3 epochs)
python finetuning/training/train.py
# → runs/opstune-qwen25-3b-lora-v1/adapter/
# → runs/opstune-qwen25-3b-lora-v1/training_log.json

# 6. Generate predictions on the held-out test split
python finetuning/training/infer.py
# → finetuning/eval/predictions/finetuned.jsonl

# 7. Serve the fine-tuned model
python finetuning/training/serve_simple.py
# OpenAI-compatible server on http://localhost:8000
```

## Training configuration

**Model: Qwen2.5-3B-Instruct** (default for 6GB GPUs)
- Quantization: 4-bit NF4 with double quantization
- GPU memory: ~4.5GB during training
- Training time: ~22 minutes (3 epochs, RTX 3060 Laptop)

**LoRA configuration:**
```python
LORA = dict(
    r=8,                    # LoRA rank
    lora_alpha=16,         # Scaling factor
    lora_dropout=0.05,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj"
    ],
    bias="none",
    task_type="CAUSAL_LM"
)
```

**Training hyperparameters:**
```python
TRAIN = dict(
    num_train_epochs=3,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=8,  # Effective batch size: 8
    learning_rate=2e-4,
    lr_scheduler_type="cosine",
    warmup_ratio=0.03,
    weight_decay=0.0,
    bf16=True,
    optim="paged_adamw_8bit",
    max_seq_length=128
)
```

**Dataset:**
- Training: 338 examples
- Validation: 73 examples
- Test: 73 examples

## Inference serving

### Option 1: Lightweight server (6GB GPU, recommended)

```bash
python finetuning/training/serve_simple.py --port 8000

# Test
curl http://localhost:8000/health
curl http://localhost:8000/v1/models

curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "opstune",
    "messages": [{"role": "user", "content": "Motor vibrating, temp 315K"}],
    "max_tokens": 512,
    "temperature": 0.7
  }'
```

**Features:**
- Uses `transformers` + `PEFT` for inference
- 4-bit quantized like training
- Works on 6GB GPUs
- OpenAI-compatible API
- Single request at a time (no batching)

### Option 2: vLLM server (8GB+ GPU, production)

```bash
bash finetuning/training/serve_vllm.sh

# Or with custom port
bash finetuning/training/serve_vllm.sh --port 8001

# Use merged weights (faster, but requires more GPU memory)
bash finetuning/training/serve_vllm.sh --merged
```

**Features:**
- High throughput with continuous batching
- CUDA graphs for faster inference
- LoRA adapter swapping
- Requires 8GB+ GPU memory

**If vLLM fails with OOM:**
1. Close other GPU applications
2. Use `serve_simple.py` instead
3. Switch to Qwen2.5-3B if using 7B

## Environment variables

```bash
# Model selection (in .env or export)
OPSTUNE_BASE_MODEL=Qwen/Qwen2.5-3B-Instruct  # or Qwen/Qwen2.5-7B-Instruct
OPSTUNE_RUN_NAME=opstune-qwen25-3b-lora-v1

# HuggingFace token
HF_TOKEN=hf_...

# LLM backend for agent workflow
OPENAI_MODEL=opstune                      # Use fine-tuned model
OPENAI_BASE_URL=http://localhost:8000/v1  # Local server
OPENAI_API_KEY=dummy                      # Any value works

# OR use OpenAI/Groq for comparison
OPENAI_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-proj-...
GROQ_API_KEY=gsk_...
```

## Evaluation

```bash
# Run inference on test set
python finetuning/training/infer.py
# → finetuning/eval/predictions/finetuned.jsonl

# Compare with baseline
python finetuning/training/compare_runs.py

# Or use the notebook
jupyter notebook finetuning/eval/baseline_eval.ipynb
```

## Troubleshooting

**GPU Out of Memory during training:**
- Switch to Qwen2.5-3B: `export OPSTUNE_BASE_MODEL=Qwen/Qwen2.5-3B-Instruct`
- Close other GPU apps (Discord, PyCharm, browser)
- Reduce `max_memory` in `train.py` (line 73)

**vLLM won't start:**
- Use `serve_simple.py` instead (works on 6GB)
- Check `nvidia-smi` for available memory
- Kill any running model servers

**Model loading slow:**
- First run downloads ~6GB model from HuggingFace
- Set `HF_HOME` to fast storage (not network drive)
- Use HuggingFace mirror if in restricted region

**Inference returns gibberish:**
- Check adapter path matches `config.py`
- Verify same base model used for train & serve
- Try lowering temperature (0.3-0.5)

## Performance benchmarks

**RTX 3060 Laptop (6GB VRAM):**
- Training: 22 min (3 epochs, 338 examples)
- Inference: ~2-3 seconds per request (serve_simple.py)
- GPU memory: 4.5GB training, 4.0GB serving

**Expected improvements on larger GPUs:**
- RTX 4090 (24GB): ~8 min training, <1s inference
- AMD MI300X (192GB): ~5 min training, <0.5s inference with vLLM

## Next steps

1. **Merge adapter** for faster inference:
   ```bash
   python finetuning/training/merge_adapter.py
   bash finetuning/training/serve_vllm.sh --merged
   ```

2. **Evaluate metrics:**
   - Exact match accuracy
   - Per-field F1 scores
   - Confidence calibration
   - Inference latency

3. **Deploy:**
   - Containerize with Docker
   - Add authentication
   - Set up monitoring (Prometheus + Grafana)
   - Load balancing for multiple replicas

4. **Iterate:**
   - Collect user feedback
   - Fine-tune on production data
   - Experiment with larger models (7B, 14B)
   - Try different LoRA ranks (r=16, r=32)
