"""Load config/pipeline.toml. Stages read prompts and limits from here."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "config" / "pipeline.toml"


class SettingsError(RuntimeError):
    """config/pipeline.toml is missing a value or has a bad one."""


@dataclass(frozen=True)
class Pipeline:
    provider: str
    model: str
    max_tokens: int
    log_window_minutes: int
    max_iterations: int
    classify_prompt: str
    investigate_prompt: str
    classify_provider: str
    classify_model: str
    investigate_provider: str
    investigate_model: str
    fix_prompt: str
    fix_provider: str
    fix_model: str
    judge_prompt: str
    judge_provider: str
    judge_model: str
    max_revisions: int


def load_pipeline() -> Pipeline:
    try:
        raw = tomllib.loads(_PATH.read_text())
    except OSError as exc:
        raise SettingsError(f"cannot read {_PATH}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise SettingsError(f"invalid {_PATH}: {exc}") from exc

    brain = raw.get("brain") or {}
    evidence = raw.get("evidence") or {}
    classify = raw.get("classify") or {}
    investigate = raw.get("investigate") or {}
    fix = raw.get("fix") or {}
    judge = raw.get("judge") or {}
    return Pipeline(
        provider=_text(brain, "provider"),
        model=_text(brain, "model"),
        max_tokens=_count(brain, "max_tokens"),
        log_window_minutes=_count(evidence, "log_window_minutes", allow_zero=True),
        max_iterations=_count(investigate, "max_iterations"),
        classify_prompt=_text(classify, "prompt"),
        investigate_prompt=_text(investigate, "prompt"),
        classify_provider=_optional(classify, "provider"),
        classify_model=_optional(classify, "model"),
        investigate_provider=_optional(investigate, "provider"),
        investigate_model=_optional(investigate, "model"),
        fix_prompt=_text(fix, "prompt"),
        fix_provider=_optional(fix, "provider"),
        fix_model=_optional(fix, "model"),
        judge_prompt=_text(judge, "prompt"),
        judge_provider=_optional(judge, "provider"),
        judge_model=_optional(judge, "model"),
        max_revisions=_count(judge, "max_revisions", allow_zero=True),
    )


def _text(section: dict, key: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SettingsError(f"config/pipeline.toml needs a non-empty {key}")
    return value.strip()


def _optional(section: dict, key: str) -> str:
    value = section.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SettingsError(f"config/pipeline.toml {key} must be a string")
    return value.strip()


def _count(section: dict, key: str, allow_zero: bool = False) -> int:
    value = section.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SettingsError(f"config/pipeline.toml {key} must be an integer")
    if value < 0 or (value == 0 and not allow_zero):
        raise SettingsError(f"config/pipeline.toml {key} must be positive")
    return value


def _self_check() -> None:
    cfg = load_pipeline()
    assert cfg.provider == "claude"
    assert cfg.model in {"sonnet", "opus"}
    assert cfg.max_tokens >= 1
    assert cfg.log_window_minutes >= 0
    assert cfg.max_iterations >= 1
    assert cfg.max_revisions == 1
    assert "Classify one production error" in cfg.classify_prompt
    assert "judge verdict" in cfg.investigate_prompt
    assert "unified diff" in cfg.fix_prompt
    assert "fixes_bug" in cfg.judge_prompt
    assert cfg.fix_model == ""
    assert cfg.judge_model == ""


if __name__ == "__main__":
    _self_check()
    print("ok")
