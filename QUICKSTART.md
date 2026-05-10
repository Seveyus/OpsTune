# OpsTune - Quick Start Guide

Get OpsTune up and running in 5 minutes with the fine-tuned model.

## Prerequisites

- Python 3.10+
- NVIDIA/AMD GPU with 6GB+ VRAM
- OR OpenAI/Groq API key

## 1. Clone & Install (2 min)

```bash
git clone <repo-url>
cd OpsTune

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt
```

## 2. Configure (1 min)

Edit `.env` file:

**For Local Fine-tuned Model:**
```bash
# Model config
OPSTUNE_BASE_MODEL=Qwen/Qwen2.5-3B-Instruct
OPSTUNE_RUN_NAME=opstune-qwen25-3b-lora-v1
HF_TOKEN=hf_...  # Get from https://huggingface.co/settings/tokens

# LLM backend
OPENAI_MODEL=opstune
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_API_KEY=dummy
```

**OR For OpenAI (Cloud):**
```bash
OPENAI_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-proj-...
# Comment out OPENAI_BASE_URL
```

## 3. Run (2 min)

### Option A: With Fine-tuned Model

**Terminal 1 - Start Model Server:**
```bash
.venv/bin/python finetuning/training/serve_simple.py
# Wait ~30 seconds for model to load
# You'll see: "Model loaded successfully!"
```

**Terminal 2 - Start Backend API:**
```bash
cd backend
uvicorn main:app --reload --port 8001
```

**Terminal 3 - Open Frontend:**
```bash
# Open frontend/index.html directly in browser (recommended)
# File path: /home/piotrek/OpsTune/frontend/index.html
# Or just double-click the file
```

### Option B: With OpenAI/Groq (Cloud)

```bash
# Just start backend
cd backend
uvicorn main:app --reload

# Open frontend/index.html in browser
```

## 4. Test

### Via Frontend:
1. Open `frontend/index.html` in browser
2. Paste incident report:
   ```
   Motor bearing making grinding noise. Vibration sensor reading 45mm/s.
   Temperature at 318K. RPM showing 1200.
   ```
3. Click "Analyze Incident"
4. See structured analysis with severity, root causes, and recommended actions

### Via API:
```bash
curl -X POST http://localhost:8001/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "incident_report": "Pump overheating, temp gauge shows 325K. Unusual noise from motor.",
    "mock_mode": false
  }'
```

### Via Python:
```python
import requests

response = requests.post("http://localhost:8001/analyze", json={
    "incident_report": "Tool wear indicator showing 230 minutes. Vibration increasing.",
    "mock_mode": False
})

result = response.json()
print(f"Severity: {result['severity']}")
print(f"Category: {result['category']}")
print(f"Root Causes: {result['likely_root_causes']}")
print(f"Actions: {result['recommended_actions']}")
```

## Expected Output

```json
{
  "severity": "high",
  "category": "mechanical",
  "likely_root_causes": [
    "Tool wear approaching failure threshold",
    "Bearing degradation causing excessive vibration"
  ],
  "evidence": [
    "Tool wear at 230 minutes (within critical 200-240 range)",
    "Vibration levels elevated above normal"
  ],
  "recommended_actions": [
    {
      "action": "Replace cutting tool immediately",
      "priority": "high",
      "timeline": "Within current shift"
    },
    {
      "action": "Inspect motor bearings for damage",
      "priority": "high",
      "timeline": "Before next production run"
    }
  ],
  "confidence": 0.82,
  "final_report": "OpsTune classified this incident as HIGH severity mechanical failure..."
}
```

## Troubleshooting

### Model server won't start
```bash
# Check GPU memory
nvidia-smi  # or rocm-smi for AMD

# Try reducing memory limit in serve_simple.py:
# Line 85: max_memory={0: "3.5GiB", "cpu": "12GiB"}

# Or use cloud API instead
```

### Backend returns 500 error
```bash
# Check model server is running
curl http://localhost:8000/health

# If not, restart:
.venv/bin/python finetuning/training/serve_simple.py
```

### Frontend shows CORS error
```bash
# Make sure backend is running on correct port
# Check browser console for actual endpoint being called
# Update API_ENDPOINT in frontend/index.html if needed
```

### Model downloads slowly
```bash
# First run downloads ~6GB model
# Be patient, or use Hugging Face mirror
# Model is cached for future runs
```

## What's Next?

✅ **Train Your Own Model:**
```bash
# Generate dataset
python finetuning/build_dataset.py
python finetuning/generate_reports.py
python finetuning/split_dataset.py

# Train
cd finetuning/training
python train.py
```

✅ **Customize Workflow:**
- Edit `agent_workflow/steps/` to modify analysis logic
- Adjust severity thresholds in `finetuning/thresholds.py`
- Add new failure modes to `finetuning/playbooks.py`

✅ **Deploy to Production:**
- See `README.md` for Docker containerization
- Add authentication & monitoring
- Scale with load balancer + multiple replicas

## Need Help?

- **Full Documentation:** See `README.md`
- **Training Guide:** See `finetuning/training/README.md`
- **API Docs:** http://localhost:8001/docs (when backend is running)
- **Issues:** Report at GitHub issues page

## Quick Reference

| Component | Command | Port |
|-----------|---------|------|
| Model Server | `python finetuning/training/serve_simple.py` | 8000 |
| Backend API | `cd backend && uvicorn main:app --reload --port 8001` | 8001 |
| Frontend | Open `frontend/index.html` in browser | - |
| API Docs | Visit `/docs` when backend running | 8001 |

## Test Data

Sample incident reports to try:

1. **Thermal Failure:**
   > "Temperature sensor showing 320K, much higher than usual. RPM at 1100. Process temp barely above ambient."

2. **Power Failure:**
   > "Motor drawing unusually high current. Torque reading 55Nm at 2000 RPM. Breaker keeps tripping."

3. **Tool Wear:**
   > "Tool has been in use for 225 minutes. Surface finish degrading. Slight vibration increase."

4. **Healthy System:**
   > "Routine check - all sensors nominal. Temperature 300K, RPM 1500, torque 35Nm. No issues."

---

**You're ready to go! 🚀**
