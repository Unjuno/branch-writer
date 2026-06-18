"""Direct HTTP model discovery (no MCP)."""

from __future__ import annotations

from typing import Any

import httpx


def discover_models_sync(base_url: str) -> list[dict[str, Any]]:
    """Discover available models from Ollama (preferred) or OpenAI-compatible endpoint.

    Returns a list of dicts with keys: id, name, provider[, size].
    """
    stripped = base_url.strip()
    if not stripped:
        return []

    models = _try_ollama(stripped)
    if models:
        return models

    return _try_openai(stripped)


def _try_ollama(base_url: str) -> list[dict[str, Any]]:
    """Fetch models from Ollama's /api/tags endpoint."""
    url = _ollama_tags_url(base_url)
    try:
        resp = httpx.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    models: list[dict[str, Any]] = []
    for model in data.get("models", []):
        name: str = model.get("name", "")
        if name:
            models.append({
                "id": name,
                "name": name,
                "provider": "ollama",
                "size": model.get("size"),
            })
    return models


def _try_openai(base_url: str) -> list[dict[str, Any]]:
    """Fetch models from OpenAI-compatible /v1/models endpoint (LM Studio etc.)."""
    url = _openai_models_url(base_url)
    try:
        resp = httpx.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    models: list[dict[str, Any]] = []
    for model in data.get("data", []):
        model_id: str = model.get("id", "")
        if model_id:
            owned_by = str(model.get("owned_by", "")).lower()
            provider = "lm_studio" if "lm-studio" in owned_by else "openai_compat"
            models.append({
                "id": model_id,
                "name": model_id,
                "provider": provider,
            })
    return models


def _ollama_tags_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return normalized + "/api/tags"


def _openai_models_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/v1"):
        return normalized + "/models"
    return normalized + "/models"
