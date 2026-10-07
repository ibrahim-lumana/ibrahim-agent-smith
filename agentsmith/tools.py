"""Tool dispatcher. Stages call a Toolset and do not import adapters."""

import os
from datetime import datetime

from pydantic import BaseModel, Field

from agentsmith.brains.base import load_project_env


class ToolError(RuntimeError):
    """A tool could not complete a request."""


class LogRecord(BaseModel):
    timestamp: datetime
    machine_id: str
    service: str
    severity: str
    message: str


class MachineState(BaseModel):
    machine_id: str
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    gpu_percent: float
    software_version: str
    architecture: str
    restart_count: int = 0


class Commit(BaseModel):
    repo: str
    sha: str
    timestamp: datetime
    author: str
    message: str
    component: str | None = None
    files: list[str] = Field(default_factory=list)
    pr_number: int | None = None


class PullRequest(BaseModel):
    repo: str
    number: int
    title: str
    html_url: str


class Toolset:
    """The functions an investigation stage is allowed to call."""

    def __init__(self, logs: object, telemetry: object, git: object, github: object) -> None:
        self._logs = logs
        self._telemetry = telemetry
        self._git = git
        self._github = github

    def get_logs(
        self,
        *,
        machine_id: str | None,
        start_time: datetime,
        end_time: datetime,
        service: str | None = None,
    ) -> list[LogRecord]:
        if start_time > end_time:
            raise ToolError("log start_time is after end_time")
        return self._logs.get_logs(
            machine_id=machine_id,
            start_time=start_time,
            end_time=end_time,
            service=service,
        )

    def get_machine_state(self, *, machine_id: str, timestamp: datetime) -> MachineState:
        return self._telemetry.get_machine_state(machine_id=machine_id, timestamp=timestamp)

    def get_recent_changes(self, *, repo: str, component: str | None = None) -> list[Commit]:
        return self._git.get_recent_changes(repo=repo, component=component)

    def get_file(self, *, repo: str, path: str, ref: str = "") -> str:
        return self._github.get_file(repo=repo, path=path, ref=ref)

    def get_pull_request_diff(self, *, repo: str, number: int) -> str:
        return self._github.get_pull_request_diff(repo=repo, number=number)

    def open_pull_request(self, *, repo: str, title: str, body: str, diff: str) -> PullRequest:
        if not diff.strip():
            raise ToolError("pull request diff is empty")
        return self._github.open_pull_request(repo=repo, title=title, body=body, diff=diff)


def load_tools() -> Toolset:
    """Build the toolset. GITHUB_ADAPTER=mcp calls the GitHub MCP server; fixture is the default."""
    load_project_env()
    from agentsmith.adapters.git import FixtureGit
    from agentsmith.adapters.github import FixtureGitHub, McpGitHub
    from agentsmith.adapters.logs import FixtureLogs
    from agentsmith.adapters.telemetry import FixtureTelemetry

    return Toolset(
        logs=_select("LOGS_ADAPTER", {"fixture": FixtureLogs}),
        telemetry=_select("TELEMETRY_ADAPTER", {"fixture": FixtureTelemetry}),
        git=_select("GIT_ADAPTER", {"fixture": FixtureGit}),
        github=_select("GITHUB_ADAPTER", {"fixture": FixtureGitHub, "mcp": McpGitHub}),
    )


def _select(env_name: str, options: dict[str, type]) -> object:
    name = (os.environ.get(env_name) or "fixture").strip().lower() or "fixture"
    try:
        return options[name]()
    except KeyError:
        known = ", ".join(sorted(options))
        raise ToolError(f"{env_name} must be one of: {known}") from None
