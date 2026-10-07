"""Logs. fixture reads fixtures/logs.json. mcp calls query_logs on the GCP MCP server."""

import json
import os
from datetime import datetime, timedelta

from pydantic import TypeAdapter

from agentsmith.adapters.fixture_io import as_utc, load_fixture
from agentsmith.adapters.mcp_client import call_tool
from agentsmith.tools import LogRecord, ToolError

_DEFAULT_MCP_URL = "http://127.0.0.1:8000/mcp"
_PAGE = 50  # ponytail: one query_logs page; follow next_cursor if a window needs more than 50 lines

_LOGS = TypeAdapter(list[LogRecord])


class FixtureLogs:
    def __init__(self) -> None:
        self._logs = _LOGS.validate_python(load_fixture("logs.json"))

    def get_logs(
        self,
        *,
        machine_id: str | None,
        start_time: datetime,
        end_time: datetime,
        service: str | None = None,
    ) -> list[LogRecord]:
        start = as_utc(start_time)
        end = as_utc(end_time)
        matched = [
            record
            for record in self._logs
            if start <= as_utc(record.timestamp) <= end
            and (machine_id is None or record.machine_id == machine_id)
            and (service is None or record.service == service)
        ]
        return sorted(matched, key=lambda record: as_utc(record.timestamp))


class McpLogs:
    """Calls query_logs on mcp-gcp. The SSH tunnel must already be open."""

    def __init__(self, url: str | None = None) -> None:
        self.url = (url or os.environ.get("LOGS_MCP_URL") or _DEFAULT_MCP_URL).strip()

    def get_logs(
        self,
        *,
        machine_id: str | None,
        start_time: datetime,
        end_time: datetime,
        service: str | None = None,
    ) -> list[LogRecord]:
        start = as_utc(start_time)
        end = as_utc(end_time)
        hours = max((end - start).total_seconds() / 3600, 0.01)
        raw = call_tool(
            self.url,
            "query_logs",
            {
                "filter": _service_filter(service),
                "hours": hours,
                "end": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "limit": _PAGE,
            },
            server="GCP logs",
        )
        try:
            payload = json.loads(raw)
            entries = payload["entries"]
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ToolError("query_logs must return JSON with entries") from exc
        records = []
        for entry in entries:
            record = _record(entry, machine_id=machine_id, service=service)
            if record is not None and start <= as_utc(record.timestamp) <= end:
                records.append(record)
        return records


def _service_filter(service: str | None) -> str:
    if not service:
        return ""
    safe = service.replace("\\", "\\\\").replace('"', '\\"')
    return (
        f'(jsonPayload.app="{safe}" OR resource.labels.container_name="{safe}" '
        f'OR resource.labels.pod_name:"{safe}" OR textPayload:"{safe}")'
    )


def _record(entry: object, *, machine_id: str | None, service: str | None) -> LogRecord | None:
    if not isinstance(entry, dict) or not entry.get("time"):
        return None
    labels = entry.get("labels") if isinstance(entry.get("labels"), dict) else {}
    payload = entry.get("payload")
    message = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    return LogRecord(
        timestamp=entry["time"],
        machine_id=machine_id or str(labels.get("pod_name") or labels.get("cluster_name") or "gcp"),
        service=service or str(labels.get("container_name") or entry.get("log") or "gcp"),
        severity=str(entry.get("severity") or "DEFAULT"),
        message=message,
    )


def _self_check() -> None:
    end = datetime.fromisoformat("2026-10-07T12:25:18+00:00")
    start = end - timedelta(minutes=2)
    assert _service_filter("analyzer_reader").startswith("(jsonPayload.app=")
    assert _service_filter(None) == ""
    record = _record(
        {
            "time": "2026-10-07T12:25:18.651763567Z",
            "severity": "ERROR",
            "log": "stdout",
            "labels": {"pod_name": "livekit"},
            "payload": {"message": "Failed to delete room"},
        },
        machine_id=None,
        service=None,
    )
    assert record is not None
    assert record.machine_id == "livekit"
    assert "Failed to delete room" in record.message
    assert as_utc(record.timestamp) > start
    assert isinstance(FixtureLogs(), FixtureLogs)


if __name__ == "__main__":
    _self_check()
    print("ok")
