"""Classify a new error into a category and severity."""

from pydantic import BaseModel, Field

from agentsmith.brains.base import Brain
from agentsmith.models import Category, IncidentInput, Severity
from agentsmith.settings import load_pipeline


class Classification(BaseModel):
    category: Category
    severity: Severity
    suspected_component: str = Field(min_length=1)
    reasoning_summary: str = Field(min_length=1)


def classify(incident: IncidentInput, brain: Brain) -> Classification:
    return brain.complete(
        system=load_pipeline().classify_prompt,
        user=_render(incident),
        output_model=Classification,
    )


def _render(incident: IncidentInput) -> str:
    lines = [
        f"service: {incident.service}",
        f"environment: {incident.environment}",
        f"component: {incident.component or ''}",
        f"error_message: {incident.error_message}",
        "stack_trace:",
        incident.stack_trace or "",
    ]
    return "\n".join(lines)
