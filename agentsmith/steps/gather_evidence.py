"""Gather the obvious evidence for one incident. This stage does not call a model."""

import json
from datetime import datetime, timedelta
from pathlib import Path

from agentsmith.models import Incident, InvestigationContext
from agentsmith.settings import load_pipeline
from agentsmith.tools import MachineState, ToolError, Toolset

_SERVICE_MAP = Path(__file__).resolve().parent.parent.parent / "config" / "service_map.json"


def gather_evidence(incident: Incident, tools: Toolset) -> InvestigationContext:
    """Read logs, a telemetry snapshot, and recent commits through the toolset."""
    sample = incident.latest_input
    window = timedelta(minutes=load_pipeline().log_window_minutes)
    start = sample.timestamp - window
    end = sample.timestamp + window
    component = _component(incident)
    repo = _repo_for(sample.service)
    commits = tools.get_recent_changes(repo=repo, component=component) if repo else []
    return InvestigationContext(
        incident_id=incident.incident_id,
        service=sample.service,
        repo=repo,
        component=component,
        log_start=start,
        log_end=end,
        logs=tools.get_logs(
            machine_id=sample.machine_id,
            start_time=start,
            end_time=end,
            service=sample.service,
        ),
        machine_state=_machine_state(tools, sample.machine_id, sample.timestamp),
        commits=commits,
    )


def _component(incident: Incident) -> str | None:
    suspected = incident.suspected_component.strip()
    if suspected:
        return suspected
    return incident.latest_input.component


def _repo_for(service: str) -> str | None:
    mapping = json.loads(_SERVICE_MAP.read_text())
    repo = mapping.get(service)
    if repo is None:
        return None
    return str(repo)


def _machine_state(tools: Toolset, machine_id: str | None, timestamp: datetime) -> MachineState | None:
    if not machine_id:
        return None
    try:
        return tools.get_machine_state(machine_id=machine_id, timestamp=timestamp)
    except ToolError:
        return None
