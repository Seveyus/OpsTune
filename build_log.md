# OpsTune Build Log

Last updated: 2026-05-09

OpsTune is our AMD Developer Hackathon project for industrial incident analysis. The product goal is to read messy operator reports and return structured maintenance decisions: severity, category, root causes, evidence, recommended actions, confidence, and a concise final report.

This log reflects the current state of the fine-tuning work. We have prepared the dataset, evaluation pipeline, training scripts, and serving plan. We have not yet fine-tuned the required target model, `Qwen/Qwen2.5-7B-Instruct`.

## Current Fine-Tuning Situation

The project started with a deterministic multi-agent workflow and a working `/analyze/` API. That workflow defines the output contract we want the fine-tuned model to learn:

- `severity`
- `category`
- `likely_root_causes`
- `evidence`
- `recommended_actions`
- `confidence`
- `final_report`

The fine-tuning folder now contains an end-to-end pipeline for turning AI4I predictive-maintenance rows into supervised fine-tuning examples:

```text
AI4I sensor rows
  -> recomputed failure labels
  -> structured maintenance outputs
  -> synthetic operator narratives
  -> train/validation/test split
  -> baseline evaluation
  -> LoRA fine-tuning on AMD MI300X
  -> tuned-model evaluation
  -> vLLM serving
  -> OpsTune API and demo UI
```

The completed local artifacts are:

- `finetuning/ai4i_labeled.jsonl`
- `finetuning/ai4i_finetune.jsonl`
- `finetuning/splits/train.jsonl`
- `finetuning/splits/val.jsonl`
- `finetuning/splits/test.jsonl`
- `finetuning/eval/predictions/baseline.jsonl`
- `finetuning/eval/predictions/baseline.summary.json`
- training scripts under `finetuning/training/`

Dataset status:

- 484 total supervised fine-tuning examples.
- 338 train examples.
- 73 validation examples.
- 73 held-out test examples.
- Failure modes include HDF, PWF, OSF, TWF, RNF, and healthy non-events.

The current committed baseline was produced before the Qwen fine-tuning run. It shows that the baseline model can follow the JSON contract, but it still makes domain-level mistakes:

- JSON valid rate: 100%.
- Schema compliance: 98.6%.
- Severity accuracy: 54.8%.
- Category accuracy: 45.2%.

These metrics are useful as an initial reference, but the next fair comparison should be:

```text
base Qwen/Qwen2.5-7B-Instruct
  vs
fine-tuned Qwen/Qwen2.5-7B-Instruct
```

## Selected Target Model

We selected `Qwen/Qwen2.5-7B-Instruct` as the model we plan to fine-tune for OpsTune.

Why this model fits the project:

- It is open and Hugging Face-native.
- It has an Apache 2.0 license.
- It is small enough for a fast LoRA run on AMD MI300X.
- It is suitable for instruction-following and structured JSON output.
- It is compatible with the planned vLLM serving path.
- It gives the project a relevant Qwen + AMD Developer Cloud story for the hackathon.

Important current-state note:

We have not yet completed a Qwen2.5-7B-Instruct fine-tuning run. The repository currently has scripts prepared for fine-tuning, but the Qwen adapter, Qwen tuned predictions, and tuned Qwen summary have not been generated yet.

## Current Status

Done:

- Agent workflow contract defined.
- Backend `/analyze/` API working.
- Static frontend demo working.
- AI4I labels and structured outputs generated.
- Operator narrative SFT dataset generated.
- Train/val/test split generated.
- Baseline eval summary committed.
- LoRA training scripts written.
- Inference script written.
- vLLM serving script written.

In progress:

- Switch training config from Llama 3.1 8B to Qwen2.5-7B-Instruct.
- Run base Qwen eval for a fair baseline.
- Fine-tune Qwen LoRA on AMD Developer Cloud MI300X.
- Generate tuned predictions and tuned eval summary.
- Wire the live demo to the tuned vLLM endpoint.

Next proof artifacts:

- `finetuning/eval/predictions/qwen_base.summary.json`
- `finetuning/eval/predictions/finetuned.summary.json`
- `finetuning/training/runs/opstune-qwen25-7b-lora-v1/training_log.json`
- Screenshot of `compare_runs.py` showing baseline vs tuned metrics.
- Screenshot or short clip of the frontend calling the tuned model.
- Notes on ROCm setup, vLLM serving, and AMD Developer Cloud experience.

## Planned AMD Developer Cloud Run

Target environment:

- AMD Developer Cloud
- AMD Instinct MI300X
- ROCm
- PyTorch
- Hugging Face Transformers
- PEFT LoRA
- TRL SFTTrainer
- vLLM OpenAI-compatible serving

Planned training commands:

```bash
export OPSTUNE_BASE_MODEL=Qwen/Qwen2.5-7B-Instruct
export OPSTUNE_RUN_NAME=opstune-qwen25-7b-lora-v1

python finetuning/training/train.py --max-steps 5
python finetuning/training/train.py
python finetuning/training/infer.py
python finetuning/training/compare_runs.py
```

Planned serving commands:

```bash
bash finetuning/training/serve_vllm.sh

export OPENAI_BASE_URL=http://<gpu-host>:8000/v1
export OPENAI_API_KEY=dummy
export OPENAI_MODEL=opstune
```

## Planned Evaluation

After the Qwen run, the evidence package should include:

- Base Qwen predictions on the held-out test set.
- Fine-tuned Qwen predictions on the same held-out test set.
- A summary comparing JSON validity, schema compliance, severity accuracy, category accuracy, confidence error, root-cause overlap, and action overlap.
- Per-mode breakdown for HDF, PWF, OSF, TWF, RNF, and healthy cases.
- A short demo showing the backend using the tuned vLLM endpoint.

The main success condition is not just producing valid JSON. The tuned model should improve the domain-specific decisions, especially severity and category classification, while preserving strict schema compliance.

## Submission Story We Are Building Toward

One-line pitch:

OpsTune fine-tunes an open-source LLM into an industrial incident analyst for maintenance teams, converting messy operator reports into structured, actionable maintenance decisions.

Why it matters:

- Downtime is expensive.
- Operator notes are noisy and inconsistent.
- Maintenance teams need fast triage, consistent root-cause hypotheses, and clear next actions.
- A domain-tuned model can improve structure and reliability over a generic chat model.

What judges should see:

- Real fine-tuning pipeline, not just prompting.
- AMD MI300X and ROCm used for the planned training run.
- vLLM serving as an OpenAI-compatible endpoint.
- Before/after eval numbers on a held-out test split.
- A usable frontend and backend demo.
- Clear business value for industrial reliability and predictive maintenance.

## Open Questions

- How much does Qwen2.5-7B improve over its own base eval?
- Does the fine-tuned adapter preserve strict JSON at temperature 0?
- Is merged-weight serving faster or simpler than LoRA adapter serving for the demo?
- Which failure modes still confuse the tuned model after training?
- What ROCm/vLLM setup notes are worth sharing back as AMD developer feedback?
