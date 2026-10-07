"""Open a pull request for an accepted diff. The submit tool does the write."""

from agentsmith.models import Incident, InvestigationContext
from agentsmith.tools import PullRequest, ToolError, Toolset


def open_pull_request(
    incident: Incident,
    context: InvestigationContext,
    tools: Toolset,
) -> PullRequest:
    """Submit the accepted diff. Refuses any verdict other than accept."""
    if incident.verdict != "accept":
        raise ToolError("a pull request requires an accepted verdict")
    if not incident.fix_diff.strip():
        raise ToolError("a pull request requires a diff")
    if not context.repo:
        raise ToolError("a pull request requires a repo")
    title = _title(incident)
    return tools.open_pull_request(
        repo=context.repo,
        title=title,
        body=_body(incident),
        diff=incident.fix_diff,
    )


def _title(incident: Incident) -> str:
    text = (incident.fix_summary or incident.proposed_fix or "Fix incident").strip()
    return text.split("\n", 1)[0][:120]


def _body(incident: Incident) -> str:
    checks = "\n".join(f"- {step}" for step in incident.validation_plan) or "- (none)"
    return "\n".join(
        [
            "## Root cause",
            incident.root_cause,
            "",
            "## Proposed fix",
            incident.proposed_fix,
            "",
            "## Summary",
            incident.fix_summary,
            "",
            "## Diff",
            "```diff",
            incident.fix_diff,
            "```",
            "",
            "## Validation",
            checks,
        ]
    )
