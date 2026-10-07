"""Anthropic brain. Choose sonnet or opus; the API model id stays inside this class."""

import os
from typing import TypeVar

from anthropic import APIError, Anthropic
from pydantic import BaseModel, ValidationError

from agentsmith.brains.base import Brain, BrainError, load_project_env, require_prompts
from agentsmith.brains.debug import record_brain_call

T = TypeVar("T", bound=BaseModel)

CLAUDE_MODELS = {
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
}

def _usage(usage: object) -> dict | None:
    if usage is None:
        return None
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
    }


class ClaudeBrain(Brain):
    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        max_tokens: int | None = None,
        task: str = "",
    ) -> None:
        load_project_env()
        if max_tokens is None:
            from agentsmith.settings import load_pipeline

            max_tokens = load_pipeline().max_tokens
        choice = (model or os.environ.get("CLAUDE_MODEL") or "sonnet").strip().lower()
        if choice not in CLAUDE_MODELS:
            known = ", ".join(CLAUDE_MODELS)
            raise BrainError(f"Claude model must be one of: {known}")
        self.model_name = choice
        self.model = CLAUDE_MODELS[choice]
        self.max_tokens = max_tokens
        self.task = task

        explicit_key = (api_key or "").strip()
        if explicit_key:
            self._client = Anthropic(api_key=explicit_key)
            return
        if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
            raise BrainError("ANTHROPIC_API_KEY is not set")
        self._client = Anthropic()

    def complete(self, *, system: str, user: str, output_model: type[T]) -> T:
        require_prompts(system, user)
        try:
            message = self._client.messages.parse(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=output_model,
            )
        except (APIError, ValidationError) as exc:
            self._debug(system, user, output_model, error=str(exc))
            raise BrainError(str(exc)) from exc
        parsed = message.parsed_output
        if not isinstance(parsed, output_model):
            self._debug(system, user, output_model, stop_reason=message.stop_reason, usage=message.usage)
            raise BrainError(
                f"Claude returned no structured output (stop_reason={message.stop_reason})"
            )
        self._debug(
            system,
            user,
            output_model,
            response=parsed.model_dump(mode="json"),
            stop_reason=message.stop_reason,
            usage=message.usage,
        )
        return parsed

    def _debug(self, system: str, user: str, output_model: type[BaseModel], **extra: object) -> None:
        usage = extra.pop("usage", None)
        record_brain_call(
            {
                "task": self.task,
                "model": self.model,
                "system": system,
                "user": user,
                "output_model": output_model.__name__,
                "output_schema": output_model.model_json_schema(),
                "usage": _usage(usage),
                **extra,
            }
        )
