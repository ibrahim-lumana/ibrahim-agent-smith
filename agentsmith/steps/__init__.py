"""Pipeline stages. Each stage is callable on its own."""

from agentsmith.steps.classify import Classification, classify
from agentsmith.steps.gather_evidence import gather_evidence
from agentsmith.steps.fix import CodeFix, fix_code
from agentsmith.steps.investigate import Investigation, investigate
from agentsmith.steps.judge import Verdict, judge
from agentsmith.steps.open_pr import open_pull_request

__all__ = [
    "Classification",
    "classify",
    "Investigation",
    "gather_evidence",
    "investigate",
    "CodeFix",
    "fix_code",
    "Verdict",
    "judge",
    "open_pull_request",
]
