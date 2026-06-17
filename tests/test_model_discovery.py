"""Tests for model discovery — MCP server E2E + unit tests."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from branch_writer.model_discovery.server import (
    _normalize,
    _ollama_tags_url,
    _openai_models_url,
    discover_models,
    fetch_ollama_models,
    fetch_openai_models,
    handle_call_tool,
    handle_list_tools,
)

# ---------------------------------------------------------------------------
# Unit: URL construction
# ---------------------------------------------------------------------------

OLLAMA_V1 = "http://localhost:11434/v1"
OLLAMA_ROOT = "http://localhost:11434"
LM_STUDIO = "http://localhost:1234/v1"
LM_STUDIO_ROOT = "http://localhost:1234"


def test_ollama_tags_url_from_v1() -> None:
    assert _ollama_tags_url(OLLAMA_V1) == "http://localhost:11434/api/tags"


def test_ollama_tags_url_from_root() -> None:
    assert _ollama_tags_url(OLLAMA_ROOT) == "http://localhost:11434/api/tags"


def test_ollama_tags_url_with_trailing_slash() -> None:
    assert _ollama_tags_url("http://localhost:11434/") == "http://localhost:11434/api/tags"


def test_openai_models_url_from_v1() -> None:
    assert _openai_models_url(LM_STUDIO) == "http://localhost:1234/v1/models"


def test_openai_models_url_from_root() -> None:
    assert _openai_models_url(LM_STUDIO_ROOT) == "http://localhost:1234/models"


# ---------------------------------------------------------------------------
# Unit: HTTP fetching with mocked responses
# ---------------------------------------------------------------------------

OLLAMA_RESPONSE = {
    "models": [
        {"name": "llama3.1:8b", "size": 4791825000, "modified_at": "2025-01-01T00:00:00Z"},
        {"name": "qwen2.5:7b", "size": 4284928000, "modified_at": "2025-01-01T00:00:00Z"},
    ],
}

OPENAI_RESPONSE = {
    "data": [
        {"id": "llama-3.1-8b", "object": "model", "owned_by": "lm-studio"},
        {"id": "qwen2.5-7b", "object": "model", "owned_by": "organization"},
    ],
}

OPENAI_EMPTY = {"data": []}


@pytest.mark.asyncio
async def test_fetch_ollama_models_success() -> None:
    mock_get = AsyncMock(return_value=_mock_response(200, OLLAMA_RESPONSE))

    with patch("httpx.AsyncClient.get", mock_get):
        models = await fetch_ollama_models(OLLAMA_V1)

    assert len(models) == 2
    assert models[0].id == "llama3.1:8b"
    assert models[0].provider == "ollama"
    assert models[0].size == 4791825000
    assert models[1].name == "qwen2.5:7b"


@pytest.mark.asyncio
async def test_fetch_ollama_models_unreachable() -> None:
    mock_get = AsyncMock(side_effect=Exception("Connection refused"))

    with patch("httpx.AsyncClient.get", mock_get):
        models = await fetch_ollama_models("http://localhost:1/v1")

    assert models == []


@pytest.mark.asyncio
async def test_fetch_openai_models_success() -> None:
    mock_get = AsyncMock(return_value=_mock_response(200, OPENAI_RESPONSE))

    with patch("httpx.AsyncClient.get", mock_get):
        models = await fetch_openai_models(LM_STUDIO)

    assert len(models) == 2
    assert models[0].id == "llama-3.1-8b"
    assert models[0].provider == "lm_studio"
    assert models[1].provider == "openai_compat"


@pytest.mark.asyncio
async def test_fetch_openai_models_empty() -> None:
    mock_get = AsyncMock(return_value=_mock_response(200, OPENAI_EMPTY))

    with patch("httpx.AsyncClient.get", mock_get):
        models = await fetch_openai_models(LM_STUDIO)

    assert models == []


@pytest.mark.asyncio
async def test_fetch_openai_models_http_error() -> None:
    mock_get = AsyncMock(return_value=_mock_response(404, {"error": "not found"}))

    with patch("httpx.AsyncClient.get", mock_get):
        models = await fetch_openai_models(LM_STUDIO)

    assert models == []


@pytest.mark.asyncio
async def test_discover_models_prefers_ollama() -> None:
    """discover_models should return Ollama results when available."""
    mock_get = AsyncMock(return_value=_mock_response(200, OLLAMA_RESPONSE))

    with patch("httpx.AsyncClient.get", mock_get):
        models = await discover_models(OLLAMA_V1)

    assert len(models) == 2
    assert models[0].provider == "ollama"


@pytest.mark.asyncio
async def test_discover_models_falls_back_to_openai() -> None:
    """When Ollama is unreachable, discover_models should try /v1/models."""
    mock_get = AsyncMock(side_effect=[
        Exception("Ollama unreachable"),          # first call: Ollama fails
        _mock_response(200, OPENAI_RESPONSE),     # second call: OpenAI succeeds
    ])

    with patch("httpx.AsyncClient.get", mock_get):
        models = await discover_models(LM_STUDIO)

    assert len(models) == 2
    assert models[0].provider == "lm_studio"


@pytest.mark.asyncio
async def test_discover_models_empty_base_url() -> None:
    models = await discover_models("")
    assert models == []


@pytest.mark.asyncio
async def test_discover_models_both_fail() -> None:
    """When both endpoints fail, return empty list."""
    mock_get = AsyncMock(side_effect=Exception("All unreachable"))

    with patch("httpx.AsyncClient.get", mock_get):
        models = await discover_models(LM_STUDIO)

    assert models == []


# ---------------------------------------------------------------------------
# MCP Protocol E2E: connect to server subprocess via stdio
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mcp_list_tools() -> None:
    """E2E: Connect to MCP server via stdio and list tools."""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    server_params = StdioServerParameters(
        command="python",
        args=["-m", "branch_writer.model_discovery.server"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

    tool_names = [t.name for t in result.tools]
    assert "discover_models" in tool_names
    assert "fetch_ollama_models" in tool_names
    assert "fetch_lm_studio_models" in tool_names


@pytest.mark.asyncio
async def test_mcp_call_discover_models_empty_base_url() -> None:
    """E2E: Call discover_models with empty base_url should return []."""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    server_params = StdioServerParameters(
        command="python",
        args=["-m", "branch_writer.model_discovery.server"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                name="discover_models",
                arguments={"base_url": ""},
            )

    assert not result.isError
    text = "".join(c.text for c in (result.content or []) if hasattr(c, "text"))
    assert json.loads(text) == []


# ---------------------------------------------------------------------------
# MCP handler unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_list_tools_returns_tools() -> None:
    tools = await handle_list_tools()
    assert len(tools) == 3
    assert tools[0].name == "discover_models"


@pytest.mark.asyncio
async def test_handle_call_tool_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown tool"):
        await handle_call_tool("nonexistent", {})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status: int, data: dict) -> Mock:
    """Create a mock httpx.Response (synchronous methods only)."""
    resp = Mock()
    resp.status_code = status
    resp.json.return_value = data
    if status >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status}", request=None, response=resp,
        )
    return resp
