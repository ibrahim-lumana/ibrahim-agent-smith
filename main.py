import json
import sys
from pathlib import Path

from pydantic import ValidationError

from agentsmith.brains import BrainError
from agentsmith.manager import DEFAULT_DB_PATH
from agentsmith.models import IncidentInput
from agentsmith.pipeline import process_next, receive
from agentsmith.queue import IncidentQueue
from agentsmith.tools import ToolError


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python main.py <incident.json>", file=sys.stderr)
        return 2

    path = Path(args[0])
    try:
        payload = json.loads(path.read_text())
        incoming = IncidentInput.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"failed to load {path}: {exc}", file=sys.stderr)
        return 1

    store = IncidentQueue(DEFAULT_DB_PATH)
    try:
        accepted = receive(incoming, store)
    except BrainError as exc:
        print(f"classification failed: {exc}", file=sys.stderr)
        return 1

    action = "created" if accepted.occurrence_count == 1 else "deduplicated"
    print(action)
    print(f"incident_id={accepted.incident_id}")
    print(f"fingerprint={accepted.fingerprint}")
    print(f"occurrence_count={accepted.occurrence_count}")
    print(f"category={accepted.category}")
    print(f"severity={accepted.severity}")
    print(f"suspected_component={accepted.suspected_component}")
    print(f"reasoning_summary={accepted.reasoning_summary}")

    try:
        pulled = process_next(store)
    except (BrainError, ToolError) as exc:
        print(f"investigation failed: {exc}", file=sys.stderr)
        return 1
    if pulled is None:
        print("queue=empty")
        return 0

    incident, evidence = pulled
    commit_ids = ",".join(commit.sha for commit in evidence.commits) or "none"
    print(f"pulled={incident.incident_id}")
    print(f"pulled_severity={incident.severity}")
    print(f"repo={evidence.repo or 'none'}")
    print(f"log_lines={len(evidence.logs)}")
    if evidence.machine_state is None:
        print("machine=none")
    else:
        state = evidence.machine_state
        print(f"machine={state.machine_id} version={state.software_version}")
    print(f"commits={commit_ids}")
    print(f"root_cause={incident.root_cause}")
    print(f"confidence={incident.confidence:.2f}")
    print(f"proposed_fix={incident.proposed_fix}")
    print(f"fix_summary={incident.fix_summary}")
    print(f"fix_diff={incident.fix_diff}")
    print(f"verdict={incident.verdict or 'none'}")
    print(f"pr_url={incident.pr_url or 'none'}")
    print(f"verdict_explanation={incident.verdict_explanation}")
    for step in incident.validation_plan:
        print(f"validation={step}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
