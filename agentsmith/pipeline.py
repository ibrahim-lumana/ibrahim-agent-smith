"""Sequence the stages. A duplicate error does not call the brain again."""

from agentsmith.brains import Brain, brain_for
from agentsmith.manager import DEFAULT_DB_PATH, accept
from agentsmith.models import Incident, IncidentInput, InvestigationContext
from agentsmith.queue import IncidentQueue
from agentsmith.settings import load_pipeline
from agentsmith.steps.classify import classify
from agentsmith.steps.fix import fix_code
from agentsmith.steps.gather_evidence import gather_evidence
from agentsmith.steps.investigate import Investigation, investigate
from agentsmith.steps.judge import Verdict, judge
from agentsmith.steps.open_pr import open_pull_request
from agentsmith.tools import Toolset, load_tools


def receive(
    incident: IncidentInput,
    queue: IncidentQueue | None = None,
    brain: Brain | None = None,
) -> Incident:
    """Store the error, and classify it when this incident has not been classified yet."""
    store = queue if queue is not None else IncidentQueue(DEFAULT_DB_PATH)
    stored = accept(incident, store)
    if stored.classified:
        return stored

    model = brain if brain is not None else brain_for("classify")
    classification = classify(stored.latest_input, model)
    return store.save_classification(
        stored.model_copy(
            update={
                "category": classification.category,
                "severity": classification.severity,
                "suspected_component": classification.suspected_component,
                "reasoning_summary": classification.reasoning_summary,
                "classified": True,
            }
        )
    )


def collect_evidence(incident: Incident, tools: Toolset | None = None) -> InvestigationContext:
    """Gather logs, telemetry, and commits for one stored incident."""
    return gather_evidence(incident, tools if tools is not None else load_tools())


def process_next(
    queue: IncidentQueue | None = None,
    brain: Brain | None = None,
    tools: Toolset | None = None,
) -> tuple[Incident, InvestigationContext] | None:
    """Pull the highest-severity waiting incident, then gather evidence and investigate it."""
    store = queue if queue is not None else IncidentQueue(DEFAULT_DB_PATH)
    incident = store.next_uninvestigated()
    if incident is None:
        return None
    toolset = tools if tools is not None else load_tools()
    context = gather_evidence(incident, toolset)
    updated, _result = solve(incident, context, brain=brain, tools=toolset, queue=store)
    return updated, context


def solve(
    incident: Incident,
    context: InvestigationContext,
    brain: Brain | None = None,
    tools: Toolset | None = None,
    queue: IncidentQueue | None = None,
    judge_brain: Brain | None = None,
    fix_brain: Brain | None = None,
) -> tuple[Incident, Investigation | None]:
    """Investigate, write a diff, then judge that diff. One failed verdict is sent back once."""
    if incident.investigated:
        return incident, None
    investigator = brain if brain is not None else brain_for("investigate")
    fixer = fix_brain if fix_brain is not None else brain_for("fix")
    reviewer = judge_brain if judge_brain is not None else brain_for("judge")
    toolset = tools if tools is not None else load_tools()
    max_revisions = load_pipeline().max_revisions
    revisions = 0
    current = incident
    phase = "investigate"
    result: Investigation | None = None
    while True:
        if phase == "investigate":
            result = investigate(current, context, investigator, toolset)
            if result.stopped_reason != "concluded":
                return _with_conclusion(current, result, investigated=False), result
            current = _with_conclusion(current, result, investigated=False)
            phase = "fix"
            continue
        if phase == "fix":
            fix = fix_code(current, context, fixer)
            current = current.model_copy(update={"fix_summary": fix.summary, "fix_diff": fix.diff})
            phase = "judge"
            continue
        verdict = judge(current, context, reviewer)
        route = _route(verdict)
        done = route == "accept" or revisions >= max_revisions
        current = current.model_copy(
            update={
                "investigated": done,
                "verdict": "accept" if route == "accept" else verdict.decision,
                "verdict_explanation": verdict.explanation,
            }
        )
        if done:
            if route == "accept":
                opened = open_pull_request(current, context, toolset)
                current = current.model_copy(
                    update={"pr_number": opened.number, "pr_url": opened.html_url}
                )
            store = queue if queue is not None else IncidentQueue(DEFAULT_DB_PATH)
            return store.save_investigation(current), result
        revisions += 1
        context.notes.append(_objection(verdict, route))
        phase = "investigate" if route == "investigate" else "fix"


def _route(verdict: Verdict) -> str:
    passed = verdict.code_ok and verdict.implements_recommendation and verdict.fixes_bug
    if verdict.decision == "accept" and passed:
        return "accept"
    if not verdict.fixes_bug:
        return "investigate"
    return "fix"


def _objection(verdict: Verdict, route: str) -> str:
    if route == "investigate":
        return (
            f"Judge verdict: reject. {verdict.explanation} "
            "The change does not fix the bug. Investigate again."
        )
    return (
        f"Judge verdict: revise. {verdict.explanation} "
        "The diff is wrong. Write a new diff."
    )


def _self_check() -> None:
    import tempfile
    from datetime import datetime, timezone
    from pathlib import Path

    from agentsmith.models import IncidentInput

    class Scripted:
        def __init__(self, turns: list[dict], fixes: list[dict], verdicts: list[dict]) -> None:
            self.names: list[str] = []
            self.turns = turns
            self.fixes = fixes
            self.verdicts = verdicts

        def complete(self, *, system: str, user: str, output_model: type) -> object:
            del system, user
            name = output_model.__name__
            self.names.append(name)
            if name == "Verdict":
                payload = self.verdicts.pop(0)
            elif name == "CodeFix":
                payload = self.fixes.pop(0)
            else:
                payload = self.turns.pop(0)
            return output_model.model_validate(payload)

    now = datetime.now(timezone.utc)
    incoming = IncidentInput(
        error_id="e",
        timestamp=now,
        service="video-indexer",
        environment="production",
        error_message="StreamContext destroyed",
    )

    def incident_for(fingerprint: str) -> Incident:
        return Incident(
            incident_id="INC-fix",
            fingerprint=fingerprint,
            first_seen=now,
            last_seen=now,
            category="application_bug",
            severity="medium",
            classified=True,
            latest_input=incoming,
            samples=[incoming],
        )

    class RecordingTools:
        def __init__(self) -> None:
            self.opened = None

        def open_pull_request(self, **kwargs):
            from agentsmith.tools import PullRequest

            self.opened = kwargs
            return PullRequest(
                repo=kwargs["repo"],
                number=9001,
                title=kwargs["title"],
                html_url=f"fixture://{kwargs['repo']}/pull/9001",
            )

    def context_for() -> InvestigationContext:
        return InvestigationContext(
            incident_id="INC-fix",
            service="video-indexer",
            repo="lumana/video-indexer",
            component="stream_manager",
            log_start=now,
            log_end=now,
            logs=[],
            commits=[],
            notes=["get_file stream_manager.py\nself._context.callback()"],
        )

    passed = {
        "decision": "accept",
        "code_ok": True,
        "implements_recommendation": True,
        "fixes_bug": True,
        "explanation": "the diff restores the hold",
    }
    patch = Scripted(
        [{"action": "conclude", "observations": ["once"], "root_cause": "cause", "confidence": 0.6, "proposed_fix": "restore hold", "validation_plan": ["test"]}],
        [{"summary": "bad edit", "diff": "- callback\n+ nope"}, {"summary": "restore hold", "diff": "- callback\n+ hold"}],
        [
            {"decision": "revise", "code_ok": False, "implements_recommendation": True, "fixes_bug": True, "explanation": "unrelated edit"},
            passed,
        ],
    )
    opened = RecordingTools()
    with tempfile.TemporaryDirectory() as directory:
        store = IncidentQueue(Path(directory) / "incidents.sqlite")
        store.add(incident_for("patch"))
        updated, _result = solve(
            incident_for("patch"), context_for(), brain=patch, fix_brain=patch, judge_brain=patch,
            tools=opened, queue=store,
        )
        assert updated.verdict == "accept" and updated.fix_diff.endswith("+ hold")
        assert updated.pr_url == "fixture://lumana/video-indexer/pull/9001"
        assert opened.opened["diff"].endswith("+ hold")
        assert patch.names.count("InvestigationTurn") == 1
        assert patch.names.count("CodeFix") == 2

    diagnosis = Scripted(
        [
            {"action": "conclude", "observations": ["once"], "root_cause": "wrong", "confidence": 0.2, "proposed_fix": "fix", "validation_plan": ["look"]},
            {"action": "conclude", "observations": ["twice"], "root_cause": "still wrong", "confidence": 0.3, "proposed_fix": "other", "validation_plan": ["look"]},
        ],
        [{"summary": "a", "diff": "+ a"}, {"summary": "b", "diff": "+ b"}],
        [
            {"decision": "reject", "code_ok": True, "implements_recommendation": True, "fixes_bug": False, "explanation": "does not fix the crash"},
            {"decision": "reject", "code_ok": True, "implements_recommendation": True, "fixes_bug": False, "explanation": "still does not fix the crash"},
        ],
    )
    skipped = RecordingTools()
    with tempfile.TemporaryDirectory() as directory:
        store = IncidentQueue(Path(directory) / "incidents.sqlite")
        store.add(incident_for("diagnosis"))
        updated, _result = solve(
            incident_for("diagnosis"), context_for(), brain=diagnosis, fix_brain=diagnosis,
            judge_brain=diagnosis, tools=skipped, queue=store,
        )
        assert updated.verdict == "reject" and updated.investigated
        assert updated.pr_url == "" and skipped.opened is None
        assert updated.root_cause == "still wrong"
        assert diagnosis.names.count("InvestigationTurn") == 2
        assert store.next_uninvestigated() is None


def _with_conclusion(incident: Incident, result: Investigation, investigated: bool) -> Incident:
    return incident.model_copy(
        update={
            "investigated": investigated,
            "root_cause": result.root_cause,
            "proposed_fix": result.proposed_fix,
            "confidence": result.confidence,
            "observations": result.observations,
            "validation_plan": result.validation_plan,
        }
    )


if __name__ == "__main__":
    _self_check()
    print("ok")
