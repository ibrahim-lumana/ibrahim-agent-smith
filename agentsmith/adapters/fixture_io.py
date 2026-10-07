"""Load JSON fixtures from the repository fixtures/ directory."""

import json
from datetime import datetime, timezone
from pathlib import Path

_FIXTURES = Path(__file__).resolve().parent.parent.parent / "fixtures"


def load_fixture(name: str) -> list[dict]:
    path = _FIXTURES / name
    if not path.is_file():
        raise FileNotFoundError(f"fixture not found: {name}")
    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise ValueError(f"fixture {name} must be a list")
    return payload


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
