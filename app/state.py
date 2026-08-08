from typing import TypedDict

class IncidentState(TypedDict, total=False):

    input: dict          # raw alert, kept structured

    service: str
    alert_type: str
    severity: str

    logs: str
    metrics: str
    runbook: str

    diagnosis: str
    proposed_action: str
    risk_level: str       # "low" | "high"

    approval: bool
    execution: str
    notification: bool

