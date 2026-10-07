"""Judge a finished investigation. One model call, no tools."""

from typing import Literal

from pydantic import BaseModel, Field

from agentsmith.brains.base import Brain
from agentsmith.models import Incident, InvestigationContext
from agentsmith.settings import load_pipeline


class Verdict(BaseModel):
    decision: Literal["accept", "revise", "reject"]
    code_ok: bool
    implements_recommendation: bool
    fixes_bug: bool
    explanation: str = Field(min_length=1)


def judge(incident: Incident, context: InvestigationContext, brain: Brain) -> Verdict:
    """Decide whether the proposed fix is good enough to continue."""
    return brain.complete(
        system=load_pipeline().judge_prompt,
        user=_render(incident, context),
        output_model=Verdict,
    )


def _render(incident: Incident, context: InvestigationContext) -> str:
    sample = incident.latest_input
    commits = "\n".join(
        f"- {commit.sha} pr={commit.pr_number or ''} {commit.message} files={', '.join(commit.files)}"
        for commit in context.commits
    ) or "(none)"
    notes = "\n".join(f"- {note}" for note in context.notes) or "(none)"
    observations = "\n".join(f"- {item}" for item in incident.observations) or "(none)"
    plan = "\n".join(f"- {item}" for item in incident.validation_plan) or "(none)"
    return "\n".join(
        [
            f"repo: {context.repo or ''}",
            f"component: {context.component or ''}",
            f"error_message: {sample.error_message}",
            "stack_trace:",
            sample.stack_trace or "",
            "commits:",
            commits,
            "evidence_notes:",
            notes,
            f"root_cause: {incident.root_cause}",
            f"confidence: {incident.confidence}",
            f"proposed_fix: {incident.proposed_fix}",
            f"fix_summary: {incident.fix_summary}",
            "diff:",
            incident.fix_diff or "(none)",
            "observations:",
            observations,
            "validation_plan:",
            plan,
        ]
    )
