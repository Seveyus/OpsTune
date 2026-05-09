# OpsTune Backend API

This directory contains the backend API for OpsTune, built with FastAPI. It provides RESTful endpoints to analyze industrial incident reports using the agent workflow, compare results with a mock database, and perform evaluations. The API integrates with the `agent-workflow` module to process incidents through five deterministic steps: Intake, Triage, Root Cause, Action Planner, and Report.

## What it does

The backend exposes a FastAPI application with the following endpoints:
- `/health`: Health check endpoint.
- `/analyze`: Analyzes an incident report and returns structured results.
- `/compare`: Compares analysis results with a mock database and provides a tuned output.

All operations are mock-based for V1, ensuring deterministic responses without requiring live LLM APIs.

## File layout

```
backend/
├── api/
│   ├── routers/
│   │   ├── analyze.py       # /analyze endpoint
│   │   ├── compare.py       # /compare endpoint
│   │   ├── health.py        # /health endpoint
│   │   └── workflow.py      # Placeholder for workflow-related endpoints
│   └── schemas/             # Pydantic models for API requests/responses
├── evaluation/
│   └── mock_db.json         # Mock database for comparisons
├── services/
│   ├── workflow_service.py  # Service wrapper for workflow execution
│   └── ...                  # Other services (e.g., evalutation_service.py)
├── config.py                # Configuration settings
├── dependencies.py          # Dependency injection functions
├── main.py                  # Main FastAPI app entry point
└── README.md                # This file
```


## Install

Ensure you have Python 3.8+ installed. From the project root:

```shell script
pip install -r requirements.txt
```


## Run the API

From the `backend/` directory:

```shell script
uvicorn main:app --reload
```


This starts the server on `http://localhost:8000`. Access the interactive API docs at `http://localhost:8000/docs`.

## Endpoints

### Health Check
- **GET** `/health`
- Returns: `{"status": "healthy", "version": "v1"}`

### Analyze Incident
- **POST** `/analyze`
- Request body:
```json
{
    "incident_report": "Operator reported rising vibration...",
    "mock_mode": true
  }
```

- Response: Structured analysis result including severity, category, root causes, etc.
- Example response:
```json
{
    "severity": "high",
    "category": "mechanical",
    "likely_root_causes": ["Bearing wear"],
    "evidence": ["Vibration detected"],
    "recommended_actions": [{"action": "Inspect bearings"}],
    "confidence": 0.79,
    "final_report": "OpsTune classified this incident..."
  }
```


### Compare Analysis
- **POST** `/compare`
- Request body:
```json
{
    "analysis_result": {...},  // Output from /analyze
    "incident_id": "incident_001"
  }
```

- Response: Comparison score, differences, and tuned result.
- Example response:
```json
{
    "match_score": 0.8,
    "differences": {"severity": false},
    "tuned_result": {...}
  }
```


## Use from Python

```python
import requests

# Analyze an incident
response = requests.post("http://localhost:8000/analyze", json={
    "incident_report": "Pump motor vibrating heavily.",
    "mock_mode": True
})
print(response.json())

# Compare result
analysis = response.json()
compare_resp = requests.post("http://localhost:8000/compare", json={
    "analysis_result": analysis,
    "incident_id": "incident_001"
})
print(compare_resp.json())
```


## Test

Run tests (assuming pytest is configured):

```shell script
pytest
```


## Notes for later integration

- The API uses mock data for V1 to keep it deterministic and easy to test.
- Schemas in `api/schemas/` are defined with Pydantic for validation.
- Workflow integration pulls from `agent-workflow` via `run_workflow`.
- Frontend team member @Fashzd added a small backend CORS update in `main.py` so the static frontend demo can call `POST /analyze/` from the browser. This fixes local browser preflight requests (`OPTIONS /analyze/`) that were returning 405 when `frontend/index.html` was opened directly from `file://`.
- TODO: Add authentication, database integration, and expand services for production use.
- For full project README, see the root `README.md`.
