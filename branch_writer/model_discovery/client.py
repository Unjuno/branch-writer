"""MCP client wrapper for the model-discovery server.

Spawns the server as a subprocess and communicates via the stdio MCP transport.
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def discover_models_sync(base_url: str) -> list[dict[str, Any]]:
    """Call the model-discovery MCP server and return available models.

    Returns a list of dicts with keys: id, name, provider[, size].
    """
    return asyncio.run(_call_discover_models(base_url))


async def _call_discover_models(base_url: str) -> list[dict[str, Any]]:
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "branch_writer.model_discovery.server"],
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                name="discover_models",
                arguments={"base_url": base_url},
            )

            if result.isError:
                return []

            text = "".join(
                c.text for c in (result.content or []) if hasattr(c, "text")
            )
            if text:
                return json.loads(text)
            return []
