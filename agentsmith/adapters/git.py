"""Fixture git history. Reads fixtures/commits.json."""

from pydantic import TypeAdapter

from agentsmith.adapters.fixture_io import load_fixture
from agentsmith.tools import Commit

_COMMITS = TypeAdapter(list[Commit])


class FixtureGit:
    def __init__(self) -> None:
        self._commits = _COMMITS.validate_python(load_fixture("commits.json"))

    def get_recent_changes(self, *, repo: str, component: str | None = None) -> list[Commit]:
        matched = [
            commit
            for commit in self._commits
            if commit.repo == repo and (component is None or commit.component == component)
        ]
        return sorted(matched, key=lambda commit: commit.timestamp, reverse=True)
