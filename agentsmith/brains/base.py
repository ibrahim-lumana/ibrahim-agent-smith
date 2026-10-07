"""Brain contract shared by every model provider."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


class BrainError(RuntimeError):
    """A brain could not return a validated structured response."""


class Brain(ABC):
    """A reasoning provider. Stages call complete() and do not import a vendor SDK."""

    @abstractmethod
    def complete(self, *, system: str, user: str, output_model: type[T]) -> T:
        """Send one prompt and return a validated instance of output_model."""


def load_project_env() -> None:
    load_dotenv(_ENV_PATH)


def require_prompts(system: str, user: str) -> None:
    if not system.strip():
        raise BrainError("system prompt is empty")
    if not user.strip():
        raise BrainError("user prompt is empty")
