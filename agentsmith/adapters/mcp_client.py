"""One streamable-HTTP call to an MCP tool server."""

import asyncio

from agentsmith.tools import ToolError


def call_tool(url: str, name: str, arguments: dict, *, server: str) -> str:
    try:
        return asyncio.run(_call_tool_async(url, name, arguments, server))
    except ToolError:
        raise
    except Exception as exc:
        raise ToolError(f"{server} MCP {name} failed: {exc}") from exc


async def _call_tool_async(url: str, name: str, arguments: dict, server: str) -> str:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(url) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
    if getattr(result, "is_error", False):
        raise ToolError(_result_text(result) or f"{server} MCP {name} returned an error")
    text = _result_text(result)
    if not text:
        raise ToolError(f"{server} MCP {name} returned no text")
    return text


def _result_text(result: object) -> str:
    parts = []
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)
