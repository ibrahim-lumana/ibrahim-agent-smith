"""Write a diff for a finished investigation. One model call. Does not touch a repo."""

from pydantic import BaseModel, Field

from agentsmith.brains.base import Brain
from agentsmith.models import Incident, InvestigationContext
from agentsmith.settings import load_pipeline


class CodeFix(BaseModel):
    summary: str = Field(min_length=1)
    diff: str = ""


def fix_code(incident: Incident, context: InvestigationContext, brain: Brain) -> CodeFix:
    """Return a unified diff that implements the proposed fix."""
    return brain.complete(
        system=load_pipeline().fix_prompt,
        user=_render(incident, context),
        output_model=CodeFix,
    )


def _render(incident: Incident, context: InvestigationContext) -> str:
    sample = incident.latest_input
    notes = "\n".join(f"- {note}" for note in context.notes) or "(none)"
    return "\n".join(
        [
            f"repo: {context.repo or ''}",
            f"component: {context.component or ''}",
            f"error_message: {sample.error_message}",
            "stack_trace:",
            sample.stack_trace or "",
            f"root_cause: {incident.root_cause}",
            f"proposed_fix: {incident.proposed_fix}",
            "evidence_notes:",
            notes,
            "previous_diff:",
            incident.fix_diff or "(none)",
        ]
    )
