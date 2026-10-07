"""Investigate one incident. The brain may request a tool, then must conclude."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from agentsmith.brains.base import Brain
from agentsmith.models import Incident, InvestigationContext
from agentsmith.settings import load_pipeline
from agentsmith.tools import ToolError, Toolset


class ToolRequest(BaseModel):
    name: Literal[
        "get_logs",
        "get_machine_state",
        "get_recent_changes",
        "get_file",
        "get_pull_request_diff",
    ]
    machine_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    service: str | None = None
    timestamp: datetime | None = None
    repo: str | None = None
    component: str | None = None
    path: str | None = None
    ref: str | None = None
    number: int | None = None


class InvestigationTurn(BaseModel):
    action: Literal["request_tool", "conclude"]
    tool: ToolRequest | None = None
    observations: list[str] = Field(default_factory=list)
    root_cause: str = ""
    confidence: float = Field(default=0, ge=0, le=1)
    proposed_fix: str = ""
    validation_plan: list[str] = Field(default_factory=list)


class Investigation(BaseModel):
    observations: list[str]
    root_cause: str
    confidence: float
    proposed_fix: str
    validation_plan: list[str]
    tool_calls: int
    stopped_reason: Literal["concluded", "iteration_cap"]


def investigate(
    incident: Incident,
    context: InvestigationContext,
    brain: Brain,
    tools: Toolset,
    max_iterations: int | None = None,
) -> Investigation:
    """Run the brain until it concludes or the iteration cap is reached."""
    cfg = load_pipeline()
    if max_iterations is None:
        max_iterations = cfg.max_iterations
    tool_calls = 0
    last_observations: list[str] = []
    for _ in range(max_iterations):
        turn = brain.complete(
            system=cfg.investigate_prompt,
            user=_render(incident, context),
            output_model=InvestigationTurn,
        )
        last_observations = turn.observations
        if turn.action == "conclude" and turn.root_cause.strip() and turn.proposed_fix.strip():
            return Investigation(
                observations=turn.observations,
                root_cause=turn.root_cause.strip(),
                confidence=turn.confidence,
                proposed_fix=turn.proposed_fix.strip(),
                validation_plan=turn.validation_plan,
                tool_calls=tool_calls,
                stopped_reason="concluded",
            )
        if turn.action == "request_tool" and turn.tool is not None:
            tool_calls += 1
            context.notes.append(_run_tool(context, tools, turn.tool))
            continue
        context.notes.append("The last decision had no usable tool request or conclusion.")
    return Investigation(
        observations=last_observations,
        root_cause="Investigation stopped before a conclusion.",
        confidence=0,
        proposed_fix="",
        validation_plan=[],
        tool_calls=tool_calls,
        stopped_reason="iteration_cap",
    )


def _render(incident: Incident, context: InvestigationContext) -> str:
    sample = incident.latest_input
    logs = "\n".join(
        f"- {record.timestamp.isoformat()} {record.severity} {record.message}"
        for record in context.logs
    ) or "(none)"
    if context.machine_state is None:
        machine = "(none)"
    else:
        state = context.machine_state
        machine = (
            f"{state.machine_id} version {state.software_version}, "
            f"cpu {state.cpu_percent}%, memory {state.memory_percent}%, "
            f"restarts {state.restart_count}"
        )
    commits = "\n".join(
        f"- {commit.sha} pr={commit.pr_number or ''} {commit.message} files={', '.join(commit.files)}"
        for commit in context.commits
    ) or "(none)"
    notes = "\n".join(f"- {note}" for note in context.notes) or "(none)"
    return "\n".join(
        [
            f"service: {sample.service}",
            f"environment: {sample.environment}",
            f"component: {context.component or ''}",
            f"category: {incident.category}",
            f"severity: {incident.severity}",
            f"repo: {context.repo or ''}",
            f"error_message: {sample.error_message}",
            "stack_trace:",
            sample.stack_trace or "",
            "logs:",
            logs,
            f"machine_state: {machine}",
            "commits:",
            commits,
            "tool_notes:",
            notes,
        ]
    )


def _run_tool(context: InvestigationContext, tools: Toolset, request: ToolRequest) -> str:
    try:
        if request.name == "get_logs":
            return _logs(context, tools, request)
        if request.name == "get_machine_state":
            return _machine(context, tools, request)
        if request.name == "get_recent_changes":
            return _commits(context, tools, request)
        if request.name == "get_file":
            return _file(context, tools, request)
        if request.name == "get_pull_request_diff":
            return _diff(context, tools, request)
        return f"unknown tool {request.name}"
    except ToolError as exc:
        return f"{request.name} failed: {exc}"


def _logs(context: InvestigationContext, tools: Toolset, request: ToolRequest) -> str:
    if request.start_time is None or request.end_time is None:
        return "get_logs needs start_time and end_time"
    records = tools.get_logs(
        machine_id=request.machine_id,
        start_time=request.start_time,
        end_time=request.end_time,
        service=request.service,
    )
    known = {(record.timestamp, record.machine_id, record.message) for record in context.logs}
    added = [
        record
        for record in records
        if (record.timestamp, record.machine_id, record.message) not in known
    ]
    context.logs.extend(added)
    return f"get_logs returned {len(records)} lines, {len(added)} new"


def _machine(context: InvestigationContext, tools: Toolset, request: ToolRequest) -> str:
    if not request.machine_id or request.timestamp is None:
        return "get_machine_state needs machine_id and timestamp"
    state = tools.get_machine_state(machine_id=request.machine_id, timestamp=request.timestamp)
    context.machine_state = state
    return f"get_machine_state returned {state.machine_id} version {state.software_version}"


def _commits(context: InvestigationContext, tools: Toolset, request: ToolRequest) -> str:
    if not request.repo:
        return "get_recent_changes needs repo"
    commits = tools.get_recent_changes(repo=request.repo, component=request.component)
    known = {commit.sha for commit in context.commits}
    added = [commit for commit in commits if commit.sha not in known]
    context.commits.extend(added)
    return f"get_recent_changes returned {len(commits)} commits, {len(added)} new"


def _file(context: InvestigationContext, tools: Toolset, request: ToolRequest) -> str:
    del context
    if not request.repo or not request.path:
        return "get_file needs repo and path"
    content = tools.get_file(repo=request.repo, path=request.path, ref=request.ref or "")
    return f"get_file {request.repo}:{request.path}\n{content[:12000]}"


def _diff(context: InvestigationContext, tools: Toolset, request: ToolRequest) -> str:
    del context
    if not request.repo or request.number is None:
        return "get_pull_request_diff needs repo and number"
    diff = tools.get_pull_request_diff(repo=request.repo, number=request.number)
    return f"get_pull_request_diff {request.repo}#{request.number}\n{diff[:12000]}"
