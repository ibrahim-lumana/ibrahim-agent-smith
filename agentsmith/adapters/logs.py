"""Fixture logs. Reads fixtures/logs.json and filters by machine, service, and time."""

from datetime import datetime

from pydantic import TypeAdapter

from agentsmith.adapters.fixture_io import as_utc, load_fixture
from agentsmith.tools import LogRecord

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
