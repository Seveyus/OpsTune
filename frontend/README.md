# OpsTune Frontend Demo

This is a plain HTML/CSS/JavaScript demo UI for the OpsTune `/analyze/` endpoint.

## Open Directly

Open `frontend/index.html` in a browser. The page can be used without a backend; if the API is unavailable, it shows fallback demo output.

## Use With FastAPI

Start the FastAPI backend, then open the frontend in a browser. The page sends:

```json
{
  "incident_report": "...",
  "mock_mode": true
}
```

to `/analyze/` when served from the same origin. When opened directly from the filesystem, it also tries `http://127.0.0.1:8000/analyze/`.

## Fallback Mode

If the API request fails, the UI automatically switches to fallback demo mode with hardcoded sample analysis data. The demo does not call `/compare` and does not depend on evaluation or fine-tuning.
