"""GitHub access. fixture reads local samples; mcp calls the GitHub MCP server."""

import asyncio
import json
import os
from pathlib import Path

from agentsmith.tools import PullRequest, ToolError

_FIXTURE = Path(__file__).resolve().parent.parent.parent / "fixtures" / "github.json"
_DEFAULT_MCP_URL = "http://127.0.0.1:8000/mcp"


class FixtureGitHub:
    def __init__(self) -> None:
        payload = json.loads(_FIXTURE.read_text())
        self._files = payload["files"]
        self._diffs = payload["diffs"]

    def get_file(self, *, repo: str, path: str, ref: str = "") -> str:
        exact = [
            item
            for item in self._files
            if item["repo"] == repo and item["path"] == path and item.get("ref", "") == ref
        ]
        if not exact and not ref:
            exact = [
                item
                for item in self._files
                if item["repo"] == repo and (item["path"] == path or item["path"].endswith("/" + path))
            ]
        if not exact:
            raise ToolError(f"no file {repo}:{path}")
        return exact[0]["content"]

    def get_pull_request_diff(self, *, repo: str, number: int) -> str:
        matches = [item for item in self._diffs if item["repo"] == repo and item["number"] == number]
        if not matches:
            raise ToolError(f"no pull request diff {repo}#{number}")
        return matches[0]["diff"]

    def open_pull_request(self, *, repo: str, title: str, body: str, diff: str) -> PullRequest:
        del body, diff
        return PullRequest(
            repo=repo,
            number=9001,
            title=title,
            html_url=f"fixture://{repo}/pull/9001",
        )


class McpGitHub:
    """Calls tools/mcp-servers/github over streamable HTTP. The server must already be running."""

    def __init__(self, url: str | None = None) -> None:
        self.url = (url or os.environ.get("GITHUB_MCP_URL") or _DEFAULT_MCP_URL).strip()

    def get_file(self, *, repo: str, path: str, ref: str = "") -> str:
        arguments = {"repo": repo, "path": path}
        if ref:
            arguments["ref"] = ref
        return _call_tool(self.url, "get_file", arguments)

    def get_pull_request_diff(self, *, repo: str, number: int) -> str:
        return _call_tool(self.url, "get_pull_request_diff", {"repo": repo, "number": number})

    def open_pull_request(self, *, repo: str, title: str, body: str, diff: str) -> PullRequest:
        raw = _call_tool(
            self.url,
            "open_pull_request",
            {"repo": repo, "title": title, "body": body, "diff": diff},
        )
        try:
            data = json.loads(raw)
            number = int(data["number"])
            url = str(data["html_url"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ToolError("open_pull_request must return JSON with number and html_url") from exc
        return PullRequest(repo=repo, number=number, title=str(data.get("title") or title), html_url=url)


def _call_tool(url: str, name: str, arguments: dict) -> str:
    try:
        return asyncio.run(_call_tool_async(url, name, arguments))
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"GitHub MCP {name} failed: {exc}") from exc


async def _call_tool_async(url: str, name: str, arguments: dict) -> str:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
    if getattr(result, "is_error", False):
        raise ToolError(_result_text(result) or f"GitHub MCP {name} returned an error")
    text = _result_text(result)
    if not text:
        raise ToolError(f"GitHub MCP {name} returned no text")
    return text


def _result_text(result: object) -> str:
    parts = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)
