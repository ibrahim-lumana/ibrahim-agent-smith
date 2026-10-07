"""Append brain calls to data/brain-debug.json when BRAIN_DEBUG is on."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from agentsmith.brains.base import load_project_env

_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "brain-debug.json"
_ON = {"1", "true", "yes", "on"}


def brain_debug_enabled() -> bool:
    load_project_env()
    return (os.environ.get("BRAIN_DEBUG") or "").strip().lower() in _ON


def record_brain_call(entry: dict, path: Path | None = None) -> None:
    """Append one call. No-op unless BRAIN_DEBUG is on."""
    if not brain_debug_enabled():
        return
    destination = path or _PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    calls: list = []
    if destination.exists():
        try:
            calls = json.loads(destination.read_text()).get("calls", [])
        except json.JSONDecodeError:
            calls = []
    calls.append({"at": datetime.now(timezone.utc).isoformat(), **entry})
    destination.write_text(json.dumps({"calls": calls}, indent=2) + "\n")


def _self_check() -> None:
    import tempfile

    os.environ["BRAIN_DEBUG"] = "1"
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "brain-debug.json"
        record_brain_call({"task": "classify", "response": {"severity": "medium"}}, path)
        record_brain_call({"task": "investigate", "response": {"action": "conclude"}}, path)
        saved = json.loads(path.read_text())
        assert [call["task"] for call in saved["calls"]] == ["classify", "investigate"]
        assert saved["calls"][0]["response"]["severity"] == "medium"
    os.environ["BRAIN_DEBUG"] = ""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "brain-debug.json"
        record_brain_call({"task": "classify"}, path)
        assert not path.exists()


if __name__ == "__main__":
    _self_check()
    print("ok")
