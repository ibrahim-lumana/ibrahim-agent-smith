import hashlib
import re
from pathlib import Path

from agentsmith.models import Incident, IncidentInput
from agentsmith.queue import IncidentQueue

_UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
)
_HEX_ID = re.compile(r"\b[0-9a-f]{8,}\b")
_LONG_NUMBER = re.compile(r"\b\d{3,}\b")
_WHITESPACE = re.compile(r"\s+")
_STACK_FRAME = re.compile(r'File "([^"]+)", line \d+, in (\S+)')

_FRAME_LIMIT = 3
DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "incidents.sqlite"


def normalize_message(message: str) -> str:
    """Lowercase, collapse whitespace, and drop ids so repeat samples match."""
    text = message.lower()
    text = _UUID.sub(" ", text)
    text = _HEX_ID.sub(" ", text)
    text = _LONG_NUMBER.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def relevant_stack_frames(stack_trace: str | None, limit: int = _FRAME_LIMIT) -> list[str]:
    """Return file:function for the frames closest to the exception, ignoring line numbers."""
    if not stack_trace:
        return []
    frames = [
        f"{Path(path).name}:{function}"
        for path, function in _STACK_FRAME.findall(stack_trace)
    ]
    return frames[-limit:]


def fingerprint_incident(incident: IncidentInput) -> str:
    frames = relevant_stack_frames(incident.stack_trace)
    payload = "\n".join(
        [incident.service.strip().lower(), normalize_message(incident.error_message), *frames]
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def accept(incident: IncidentInput, queue: IncidentQueue | None = None) -> Incident:
    """Store a new open incident, or count another sample of an open one."""
    store = queue if queue is not None else IncidentQueue(DEFAULT_DB_PATH)
    fingerprint = fingerprint_incident(incident)
    existing = store.find_open_by_fingerprint(fingerprint)
    if existing is not None:
        return store.increment(existing.incident_id, incident)
    return store.add(
        Incident(
            incident_id=store.next_incident_id(),
            fingerprint=fingerprint,
            first_seen=incident.timestamp,
            last_seen=incident.timestamp,
            latest_input=incident,
            samples=[incident],
        )
    )
