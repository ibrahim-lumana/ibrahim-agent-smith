from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from agentsmith.tools import Commit, LogRecord, MachineState

Severity = Literal["critical", "high", "medium", "low"]
Category = Literal[
    "application_bug",
    "infrastructure",
    "network",
    "configuration",
    "dependency",
    "unknown",
]
IncidentStatus = Literal["open", "completed", "failed"]


class IncidentInput(BaseModel):
    """Error payload handed to the orchestrator by a trigger."""

    error_id: str = Field(min_length=1)
    timestamp: datetime
    service: str = Field(min_length=1)
    environment: str = Field(min_length=1)
    error_message: str = Field(min_length=1)
    component: str | None = None
    machine_id: str | None = None
    stack_trace: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Incident(BaseModel):
    """Stored incident. Classification fields are filled after the classify stage succeeds."""

    incident_id: str
    fingerprint: str
    status: IncidentStatus = "open"
    occurrence_count: int = 1
    first_seen: datetime
    last_seen: datetime
    severity: Severity = "medium"
    category: Category = "unknown"
    suspected_component: str = ""
    reasoning_summary: str = ""
    classified: bool = False
    investigated: bool = False
    root_cause: str = ""
    proposed_fix: str = ""
    confidence: float = 0
    observations: list[str] = Field(default_factory=list)
    validation_plan: list[str] = Field(default_factory=list)
    verdict: Literal["", "accept", "revise", "reject"] = ""
    verdict_explanation: str = ""
    fix_summary: str = ""
    fix_diff: str = ""
    pr_number: int | None = None
    pr_url: str = ""
    latest_input: IncidentInput
    samples: list[IncidentInput]


class InvestigationContext(BaseModel):
    """Evidence gathered before the investigation stage asks a model to reason."""

    incident_id: str
    service: str
    repo: str | None = None
    component: str | None = None
    log_start: datetime
    log_end: datetime
    logs: list[LogRecord]
    machine_state: MachineState | None = None
    commits: list[Commit]
    notes: list[str] = Field(default_factory=list)
