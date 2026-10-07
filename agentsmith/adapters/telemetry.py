"""Fixture machine telemetry. Reads fixtures/machines.json."""

from datetime import datetime

from pydantic import TypeAdapter

from agentsmith.adapters.fixture_io import as_utc, load_fixture
from agentsmith.tools import MachineState, ToolError

_STATES = TypeAdapter(list[MachineState])


class FixtureTelemetry:
    def __init__(self) -> None:
        self._states = _STATES.validate_python(load_fixture("machines.json"))

    def get_machine_state(self, *, machine_id: str, timestamp: datetime) -> MachineState:
        matches = [state for state in self._states if state.machine_id == machine_id]
        if not matches:
            raise ToolError(f"no machine state for {machine_id}")
        moment = as_utc(timestamp)
        return min(
            matches,
            key=lambda state: abs((as_utc(state.timestamp) - moment).total_seconds()),
        )
