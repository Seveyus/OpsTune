# OpsTune Agent Workflow

This folder contains the V1 agent/workflow layer for OpsTune. It converts a messy industrial incident report into a structured maintenance-oriented JSON response and now supports both deterministic and LangChain-backed execution.

## What it does

The workflow runs five simple steps:

1. Intake: extract useful facts from the raw narrative
2. Triage: classify severity, category, and urgency
3. Root cause: propose likely failure hypotheses with evidence
4. Action planner: recommend operational next steps
5. Report: assemble the final JSON and human-readable summary

The workflow has two modes:

- `mock_mode=True`: deterministic Python rules and Pydantic schemas for local testing
- `mock_mode=False`: LangChain structured-output calls backed by an OpenAI chat model

This keeps the workflow easy to test locally while enabling an LLM-backed multi-agent path.

## File layout

```text
agent-workflow/
├── README.md
├── requirements.txt
├── schemas.py
├── workflow.py
├── agents/
├── prompts/
├── examples/
└── tests/
```

## Install

From this folder:

```bash
pip install -r requirements.txt
```

## Run the sample workflow

From this folder:

```bash
python workflow.py
```

This loads the sample incident from `examples/sample_incidents.jsonl` and prints the structured JSON result.

## Run with LangChain

Set your API key and disable mock mode:

```bash
export OPENAI_API_KEY=your_key_here
export OPENAI_MODEL=gpt-4o-mini
python -c "from workflow import run_workflow; print(run_workflow('Pump motor temperature rose, alarm triggered, line stopped.', mock_mode=False))"
```

## Run with Fireworks

Fireworks exposes an OpenAI-compatible API, so the same LangChain path can use it by changing the base URL, API key, and model name.

```bash
export FIREWORKS_API_KEY=your_fireworks_key_here
export OPENAI_API_BASE=https://api.fireworks.ai/inference/v1
export OPENAI_MODEL=accounts/fireworks/models/llama-v3p1-8b-instruct
python -c "from workflow import run_workflow; print(run_workflow('Pump motor temperature rose, alarm triggered, line stopped.', mock_mode=False))"
```

## Use from Python

```python
from workflow import run_workflow

incident_report = "Operator reported rising vibration and heat from the pump motor before stopping the line."
result = run_workflow(incident_report, mock_mode=True)
print(result)
```

Main entrypoint:

```python
run_workflow(incident_report: str, mock_mode: bool = True) -> dict
```

## Example output shape

```json
{
  "severity": "high",
  "category": "mechanical",
  "likely_root_causes": [
    "Bearing wear or mechanical misalignment"
  ],
  "evidence": [
    "Abnormal vibration or noise noted in report"
  ],
  "recommended_actions": [
    "Inspect bearings, alignment, and lubrication condition on the affected equipment."
  ],
  "confidence": 0.79,
  "final_report": "OpsTune classified this incident as high severity..."
}
```

## Test

```bash
pytest
```

## Notes for later integration

- `mock_mode=True` keeps outputs deterministic and API-free for hackathon development.
- `mock_mode=False` uses `langchain-openai` structured outputs.
- For OpenAI, set `OPENAI_API_KEY`.
- For Fireworks, set `FIREWORKS_API_KEY` and `OPENAI_API_BASE=https://api.fireworks.ai/inference/v1`.
- Prompt files under `prompts/` define the LangChain agent roles.
- `workflow.py` exposes `run_workflow(...)` so the backend can import it later.
