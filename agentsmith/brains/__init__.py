"""Brain implementations. brain_for(task) picks the provider for one pipeline stage."""

import os

from agentsmith.brains.base import Brain, BrainError, load_project_env
from agentsmith.brains.claude import ClaudeBrain
from agentsmith.settings import load_pipeline

__all__ = ["Brain", "BrainError", "ClaudeBrain", "brain_for"]


def brain_for(task: str) -> Brain:
    """Build the brain for a stage. CLASSIFY_BRAIN overrides BRAIN, and the same for the model."""
    load_project_env()
    task_key = task.strip().upper()
    if not task_key:
        raise BrainError("task name is empty")

    cfg = load_pipeline()
    stage = task.strip().lower()
    stage_provider = ""
    stage_model = ""
    if stage == "classify":
        stage_provider, stage_model = cfg.classify_provider, cfg.classify_model
    elif stage == "investigate":
        stage_provider, stage_model = cfg.investigate_provider, cfg.investigate_model
    elif stage == "fix":
        stage_provider, stage_model = cfg.fix_provider, cfg.fix_model
    elif stage == "judge":
        stage_provider, stage_model = cfg.judge_provider, cfg.judge_model
    provider = _setting(f"{task_key}_BRAIN", "BRAIN", default=stage_provider or cfg.provider)
    if provider == "claude":
        model = _setting(f"{task_key}_CLAUDE_MODEL", "CLAUDE_MODEL", default=stage_model or cfg.model)
        return ClaudeBrain(model=model, task=stage, max_tokens=cfg.max_tokens)
    raise BrainError(f"unknown brain: {provider}")


def _setting(*names: str, default: str) -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return default
