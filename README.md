# OpsTune - AI-Powered Industrial Incident Analysis

**AMD AI Hackathon Project** - An end-to-end AI agent workflow that processes industrial incident reports, extracts insights, performs root cause analysis, and generates actionable recommendations.

## 🎯 Project Overview

OpsTune transforms unstructured operator reports into structured, actionable intelligence through a 5-step deterministic agent workflow:

1. **Intake** - Parse and validate incident reports
2. **Triage** - Classify severity and category
3. **Root Cause Analysis** - Identify failure modes using sensor data
4. **Action Planning** - Generate specific remediation steps
5. **Report Generation** - Create comprehensive structured output

The system is designed for industrial predictive maintenance, using the AI4I 2020 Predictive Maintenance Dataset with fine-tuned LLM for enhanced accuracy.

## 🏗️ Architecture

```
┌─────────────────┐
│   Frontend UI   │  Static HTML/CSS/JS demo
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Backend API    │  FastAPI server with /analyze endpoint
│  (port 8000)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Agent Workflow  │  5-step deterministic pipeline
│                 │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  LLM Backend    │  Qwen2.5-3B-Instruct (fine-tuned)
│  (port 8000)    │  OR OpenAI/Groq fallback
└─────────────────┘
```

## 📁 Repository Structure

```
OpsTune/
├── frontend/              # Static HTML demo UI
├── backend/               # FastAPI API server
│   ├── api/routers/      # Endpoint definitions
│   ├── services/         # Business logic
│   └── main.py           # FastAPI app entry
├── agent_workflow/        # Core 5-step workflow engine
│   ├── steps/            # Individual workflow steps
│   ├── schemas.py        # Pydantic data models
│   └── workflow.py       # Orchestration logic
├── finetuning/           # Dataset generation & model training
│   ├── training/         # LoRA fine-tuning scripts
│   │   ├── train.py      # Training runner
│   │   ├── infer.py      # Inference testing
│   │   ├── serve_simple.py  # Lightweight inference server
│   │   └── serve_vllm.sh    # vLLM production server (requires more GPU memory)
│   ├── build_dataset.py  # Generate labeled dataset from AI4I
│   ├── generate_reports.py  # Synthesize operator narratives
│   └── split_dataset.py  # Train/val/test split
├── evaluation/           # Metrics and baseline comparison
└── .env                  # Configuration (API keys, model selection)
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- NVIDIA/AMD GPU with 6GB+ VRAM (for fine-tuned model serving)
- OR OpenAI/Groq API key (for cloud inference)

### 1. Installation

```bash
# Clone repository
git clone <repo-url>
cd OpsTune

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Copy `.env.example` to `.env` and configure:

```bash
# For fine-tuned local model (recommended)
OPENAI_MODEL=opstune
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=dummy  # Any value works for local server

# OR for OpenAI (requires API key)
OPENAI_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
# OPENAI_BASE_URL=  # Comment out for OpenAI

# OR for Groq (free tier)
GROQ_API_KEY=gsk_...
```

### 3. Run the Stack

**Option A: With Fine-tuned Model (Local GPU)**

```bash
# Terminal 1: Start fine-tuned model server
.venv/bin/python finetuning/training/serve_simple.py
# Wait ~30 seconds for model to load

# Terminal 2: Start backend API
cd backend
uvicorn main:app --reload --port 8001

# Terminal 3: Open frontend
# Open frontend/index.html in browser
# Update API endpoint in index.html to http://localhost:8001/analyze if needed
```

**Option B: With OpenAI/Groq (Cloud)**

```bash
# Set API key in .env, then:
cd backend
uvicorn main:app --reload

# Open frontend/index.html in browser
```

### 4. Test the System

**Via Frontend:**
- Open `frontend/index.html` in browser
- Paste an incident report (or use sample)
- Click "Analyze Incident"

**Via API:**
```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "incident_report": "Motor vibrating heavily, temp reading 315K, RPM at 1200. Smell of burning.",
    "mock_mode": false
  }'
```

**Via Python:**
```python
import requests

response = requests.post("http://localhost:8000/analyze", json={
    "incident_report": "Bearing making grinding noise. Vibration sensor shows 45mm/s.",
    "mock_mode": False
})
print(response.json())
```

## 🎓 Fine-Tuning Pipeline

### Dataset Generation

```bash
# Step 1: Generate labeled dataset from AI4I sensor data
python finetuning/build_dataset.py

# Step 2: Generate synthetic operator narratives
export GROQ_API_KEY=gsk_...  # Free tier recommended
python finetuning/generate_reports.py

# Step 3: Split into train/val/test
python finetuning/split_dataset.py
```

This creates:
- `finetuning/ai4i_labeled.jsonl` - 484 labeled rows (339 failures + 145 healthy)
- `finetuning/ai4i_finetune.jsonl` - Chat-format SFT pairs
- `finetuning/splits/train.jsonl` - 338 training examples
- `finetuning/splits/val.jsonl` - 73 validation examples
- `finetuning/splits/test.jsonl` - 73 test examples

### Model Training

```bash
cd finetuning/training

# Train LoRA adapter (requires 6GB+ GPU)
python train.py

# Quick test (5 steps, sanity check)
python train.py --max-steps 5

# Results saved to: runs/opstune-qwen25-3b-lora-v1/
```

**Training Configuration:**
- Base model: `Qwen/Qwen2.5-3B-Instruct`
- Method: LoRA (r=8, alpha=16)
- Quantization: 4-bit NF4
- Epochs: 3
- Batch size: 1 (gradient accumulation: 8)
- GPU memory: ~4.5GB

### Inference & Serving

```bash
# Option 1: Lightweight server (transformers-based, 6GB GPU)
python finetuning/training/serve_simple.py

# Option 2: Production vLLM server (requires 8GB+ GPU, faster)
bash finetuning/training/serve_vllm.sh

# Test inference
python finetuning/training/infer.py
```

## 🧪 Evaluation

```bash
# Run baseline evaluation
jupyter notebook finetuning/eval/baseline_eval.ipynb

# Compare baseline vs fine-tuned
python finetuning/training/compare_runs.py
```

Metrics tracked:
- Exact match accuracy (full JSON)
- Field-level F1 scores (severity, category, root causes, actions)
- Confidence calibration
- Inference latency

## 📊 Dataset Details

**AI4I 2020 Predictive Maintenance Dataset:**
- 10,000 sensor readings from CNC milling machines
- 339 machine failures across 5 failure modes
- Recomputed labels using documented thresholds

**Failure Modes:**
| Mode | Description | Rule |
|------|-------------|------|
| TWF | Tool Wear Failure | Tool wear 200-240 min |
| HDF | Heat Dissipation Failure | ΔT < 8.6K AND RPM < 1380 |
| PWF | Power Failure | Power < 3500W OR > 9000W |
| OSF | Overstrain Failure | Torque × Wear > variant limit |
| RNF | Random Failure | Untestable from sensors |

**Generated Narratives:**
- 484 synthetic operator reports
- 6 style variations (terse, verbose, frustrated, handoff, Slack DM, junior)
- 2-4 sentences, first-person, realistic shop floor language
- Generated via Groq Llama 3.1 8B Instant

## 🔧 Configuration

**Environment Variables (.env):**

```bash
# Hugging Face (for model downloads)
HF_TOKEN=hf_...

# Fine-tuning model selection
OPSTUNE_BASE_MODEL=Qwen/Qwen2.5-3B-Instruct  # or Qwen/Qwen2.5-7B-Instruct
OPSTUNE_RUN_NAME=opstune-qwen25-3b-lora-v1

# LLM Backend (choose one)
OPENAI_MODEL=opstune                      # Fine-tuned model
OPENAI_BASE_URL=http://localhost:8000/v1  # Local inference server
OPENAI_API_KEY=dummy

# OR
OPENAI_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-proj-...

# OR
GROQ_API_KEY=gsk_...

# Backend
ENVIRONMENT=development
```

## 🐛 Troubleshooting

**GPU Out of Memory:**
- Use Qwen2.5-3B instead of 7B: `OPSTUNE_BASE_MODEL=Qwen/Qwen2.5-3B-Instruct`
- Close other GPU applications (Discord, PyCharm)
- Use `serve_simple.py` instead of vLLM

**Model Server Won't Start:**
- Check GPU memory: `nvidia-smi` or `rocm-smi`
- Verify .env configuration matches model size
- Try reducing `max_memory` in `serve_simple.py`

**API Returns 405 CORS Error:**
- Backend includes CORS middleware for frontend
- Ensure frontend calls correct endpoint (check browser console)

**Rate Limits (Groq/OpenAI):**
- `generate_reports.py` auto-retries with exponential backoff
- Use `--limit` flag for testing: `python generate_reports.py --limit 10`

## 🏆 Key Features

✅ **Deterministic Workflow** - 5-step agent pipeline with structured schemas
✅ **Fine-tuned Model** - Domain-specific Qwen2.5-3B trained on industrial data
✅ **Multi-backend Support** - Local GPU, OpenAI, or Groq
✅ **Resumable Dataset Generation** - Handles rate limits gracefully
✅ **Production-ready API** - FastAPI with OpenAPI docs
✅ **Interactive Demo** - Static frontend with fallback mode

## 📝 Development

**Run Tests:**
```bash
pytest
```

**Code Quality:**
```bash
black .
flake8 .
mypy .
```

**API Documentation:**
- Start backend: `uvicorn backend.main:app --reload`
- Visit: http://localhost:8000/docs

## 🤝 Contributing

Team roles:
- **Document Processing** - Input parsing & validation
- **Backend/API** - FastAPI server & evaluation metrics
- **Agent Workflow** - Multi-step reasoning pipeline
- **Frontend/Demo** - UI & presentation

## 📄 License

MIT License - See LICENSE file

## 🙏 Acknowledgments

- AMD AI Hackathon organizers
- AI4I 2020 Predictive Maintenance Dataset authors
- Qwen team for open-source models
- HuggingFace for transformers & PEFT libraries

---

**Built with ❤️ for AMD AI Hackathon**
