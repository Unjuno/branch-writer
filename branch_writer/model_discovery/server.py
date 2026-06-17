"""MCP server for local LLM model discovery (Ollama / LM Studio)."""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

TOOL_DISCOVER = "discover_models"
TOOL_FETCH_OLLAMA = "fetch_ollama_models"
TOOL_FETCH_LM_STUDIO = "fetch_lm_studio_models"


@dataclass
class ModelInfo:
    id: str
    name: str
    provider: str  # "ollama" | "lm_studio" | "openai_compat"
    size: int | None = None


def _normalize(url: str) -> str:
    return url.strip().rstrip("/")


def _ollama_tags_url(base_url: str) -> str:
    normalized = _normalize(base_url)
    if normalized.endswith("/v1"):
        return normalized[:-3] + "/api/tags"
    return normalized + "/api/tags"


def _openai_models_url(base_url: str) -> str:
    normalized = _normalize(base_url)
    if normalized.endswith("/v1"):
        return normalized + "/models"
    return normalized + "/models"


async def fetch_ollama_models(base_url: str) -> list[ModelInfo]:
    """Fetch models from Ollama's /api/tags endpoint."""
    url = _ollama_tags_url(base_url)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except Exception:
        return []

    models: list[ModelInfo] = []
    for model in data.get("models", []):
        name: str = model.get("name", "")
        if name:
            models.append(ModelInfo(id=name, name=name, provider="ollama", size=model.get("size")))
    return models


async def fetch_openai_models(base_url: str) -> list[ModelInfo]:
    """Fetch models from OpenAI-compatible /v1/models endpoint (LM Studio etc.)."""
    url = _openai_models_url(base_url)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
    except Exception:
        return []

    models: list[ModelInfo] = []
    for model in data.get("data", []):
        model_id: str = model.get("id", "")
        if model_id:
            owned_by = str(model.get("owned_by", "")).lower()
            provider = "lm_studio" if "lm-studio" in owned_by else "openai_compat"
            models.append(ModelInfo(id=model_id, name=model_id, provider=provider))
    return models


async def discover_models(base_url: str) -> list[ModelInfo]:
    """Discover available models from a local LLM endpoint.

    Tries Ollama's /api/tags first, then falls back to OpenAI-compatible /v1/models.
    """
    if not base_url.strip():
        return []

    models = await fetch_ollama_models(base_url)
    if models:
        return models

    return await fetch_openai_models(base_url)


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

server = Server("model-discovery", version="0.1.0")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name=TOOL_DISCOVER,
            description="Discover available local LLM models from Ollama or LM Studio. "
            "Tries Ollama /api/tags first, then falls back to /v1/models.",
            inputSchema={
                "type": "object",
                "properties": {
                    "base_url": {
                        "type": "string",
                        "description": "LLM endpoint base URL (e.g. http://localhost:11434/v1)",
                    },
                },
                "required": ["base_url"],
            },
        ),
        Tool(
            name=TOOL_FETCH_OLLAMA,
            description="Fetch models from Ollama's /api/tags endpoint.",
            inputSchema={
                "type": "object",
                "properties": {
                    "base_url": {
                        "type": "string",
                        "description": "Ollama endpoint base URL",
                    },
                },
                "required": ["base_url"],
            },
        ),
        Tool(
            name=TOOL_FETCH_LM_STUDIO,
            description="Fetch models from LM Studio's /v1/models endpoint.",
            inputSchema={
                "type": "object",
                "properties": {
                    "base_url": {
                        "type": "string",
                        "description": "LM Studio endpoint base URL",
                    },
                },
                "required": ["base_url"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str,
    arguments: dict[str, Any] | None = None,
) -> list[TextContent]:
    args = arguments or {}

    if name == TOOL_DISCOVER:
        models = await discover_models(args.get("base_url", ""))
    elif name == TOOL_FETCH_OLLAMA:
        models = await fetch_ollama_models(args.get("base_url", ""))
    elif name == TOOL_FETCH_LM_STUDIO:
        models = await fetch_openai_models(args.get("base_url", ""))
    else:
        raise ValueError(f"Unknown tool: {name}")

    text = json.dumps([asdict(m) for m in models], ensure_ascii=False)
    return [TextContent(type="text", text=text)]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
