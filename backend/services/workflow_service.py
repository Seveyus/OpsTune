from ..agent_workflow.workflow import run_workflow

def execute_workflow(incident_report: str, mock_mode: bool) -> dict:
    return run_workflow(incident_report, mock_mode)
