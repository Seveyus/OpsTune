# OpsTune Agent Workflow

This folder contains the V1 agent/workflow layer for OpsTune. It converts a messy industrial incident report into a structured maintenance-oriented JSON response without requiring a live LLM API.

## What it does

The workflow runs five simple steps:

1. Intake: extract useful facts from the raw narrative
2. Triage: classify severity, category, and urgency
3. Root cause: propose likely failure hypotheses with evidence
4. Action planner: recommend operational next steps
5. Report: assemble the final JSON and human-readable summary

For V1, all steps are implemented with deterministic Python rules and Pydantic schemas. This keeps the workflow easy to test locally and leaves clear integration points for future LangChain or CrewAI work.

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
- Prompt files under `prompts/` are placeholders for future LLM-backed agents.
- `workflow.py` exposes `run_workflow(...)` so the backend can import it later.
- TODO comments mark where LangChain or CrewAI integration can be added.
