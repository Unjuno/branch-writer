"""Tests for model discovery — direct HTTP functions."""
from __future__ import annotations

from unittest.mock import Mock, patch

import httpx

from branch_writer.model_discovery.client import (
    _ollama_tags_url,
    _openai_models_url,
    _try_ollama,
    _try_openai,
    discover_models_sync,
)

# ---------------------------------------------------------------------------
# URL construction
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
# HTTP fetching with mocked responses
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


def _mock_response(status: int, data: dict) -> Mock:
    resp = Mock()
    resp.status_code = status
    resp.json.return_value = data
    if status >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status}", request=None, response=resp,
        )
    return resp


def test_try_ollama_success() -> None:
    mock_get = Mock(return_value=_mock_response(200, OLLAMA_RESPONSE))
    with patch("httpx.get", mock_get):
        models = _try_ollama(OLLAMA_V1)

    assert len(models) == 2
    assert models[0]["id"] == "llama3.1:8b"
    assert models[0]["provider"] == "ollama"
    assert models[0]["size"] == 4791825000
    assert models[1]["name"] == "qwen2.5:7b"


def test_try_ollama_unreachable() -> None:
    mock_get = Mock(side_effect=Exception("Connection refused"))
    with patch("httpx.get", mock_get):
        models = _try_ollama("http://localhost:1/v1")

    assert models == []


def test_try_openai_success() -> None:
    mock_get = Mock(return_value=_mock_response(200, OPENAI_RESPONSE))
    with patch("httpx.get", mock_get):
        models = _try_openai(LM_STUDIO)

    assert len(models) == 2
    assert models[0]["id"] == "llama-3.1-8b"
    assert models[0]["provider"] == "lm_studio"
    assert models[1]["provider"] == "openai_compat"


def test_try_openai_empty() -> None:
    mock_get = Mock(return_value=_mock_response(200, OPENAI_EMPTY))
    with patch("httpx.get", mock_get):
        models = _try_openai(LM_STUDIO)

    assert models == []


def test_try_openai_http_error() -> None:
    mock_get = Mock(return_value=_mock_response(404, {"error": "not found"}))
    with patch("httpx.get", mock_get):
        models = _try_openai(LM_STUDIO)

    assert models == []


# ---------------------------------------------------------------------------
# discover_models_sync (integration-style)
# ---------------------------------------------------------------------------


def test_discover_models_prefers_ollama() -> None:
    mock_get = Mock(return_value=_mock_response(200, OLLAMA_RESPONSE))
    with patch("httpx.get", mock_get):
        models = discover_models_sync(OLLAMA_V1)

    assert len(models) == 2
    assert models[0]["provider"] == "ollama"


def test_discover_models_falls_back_to_openai() -> None:
    mock_get = Mock(side_effect=[
        Exception("Ollama unreachable"),
        _mock_response(200, OPENAI_RESPONSE),
    ])
    with patch("httpx.get", mock_get):
        models = discover_models_sync(LM_STUDIO)

    assert len(models) == 2
    assert models[0]["provider"] == "lm_studio"


def test_discover_models_empty_base_url() -> None:
    assert discover_models_sync("") == []


def test_discover_models_both_fail() -> None:
    mock_get = Mock(side_effect=Exception("All unreachable"))
    with patch("httpx.get", mock_get):
        models = discover_models_sync(LM_STUDIO)

    assert models == []
