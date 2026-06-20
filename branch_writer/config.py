"""Configuration models for Branch Writer."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger("branch_writer.config")

DEFAULT_BASE_URL = ""
DEFAULT_API_KEY = ""
DEFAULT_MODEL = ""
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 4096
DEFAULT_CONTEXT_WINDOW = 8192
DEFAULT_REQUEST_TIMEOUT_SECONDS = 180.0
MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0
MIN_MAX_TOKENS = 1
MIN_CONTEXT_WINDOW = 512
MAX_CONTEXT_WINDOW = 1048576
MIN_REQUEST_TIMEOUT_SECONDS = 5.0
MAX_REQUEST_TIMEOUT_SECONDS = 900.0

MODEL_CAPABILITIES: dict[str, tuple[int, int]] = {
    "llama3.2": (128000, 8192),
    "llama3.1": (128000, 8192),
    "llama3": (8192, 4096),
    "llama2": (4096, 2048),
    "qwen2.5": (32768, 8192),
    "qwen2": (32768, 8192),
    "qwen": (32768, 8192),
    "mistral": (32768, 8192),
    "mixtral": (32768, 8192),
    "phi3": (128000, 8192),
    "phi-3": (128000, 8192),
    "phi4": (16384, 8192),
    "gemma2": (8192, 4096),
    "gemma": (8192, 4096),
    "codellama": (16384, 4096),
    "deepseek-coder": (16384, 4096),
    "deepseek-r1": (131072, 8192),
    "deepseek-v2": (131072, 8192),
    "deepseek-v3": (131072, 8192),
    "nemotron": (131072, 8192),
    "command-r": (131072, 4096),
    "command-r-plus": (131072, 4096),
    "aya": (131072, 4096),
    "dbrx": (32768, 4096),
    "starcoder2": (16384, 4096),
    "stable-code": (16384, 4096),
    "falcon": (8192, 4096),
    "solar": (4096, 2048),
    "yi": (4096, 2048),
    "codegeex4": (131072, 8192),
}


def lookup_model_capabilities(model_name: str) -> tuple[int, int]:
    """Return (context_window, max_tokens) guessed from model name."""
    name_lower = model_name.lower().strip()
    if name_lower.endswith(":latest"):
        name_lower = name_lower[:-len(":latest")]
    # Exact match first (e.g. "llama3.2:3b" -> "llama3.2")
    for prefix, (ctx, out) in MODEL_CAPABILITIES.items():
        if name_lower.startswith(prefix):
            return ctx, out
    return DEFAULT_CONTEXT_WINDOW, DEFAULT_MAX_TOKENS


@dataclass(slots=True)
class LlmSettings:
    """Settings for an OpenAI-compatible local LLM endpoint."""

    base_url: str = DEFAULT_BASE_URL
    api_key: str = DEFAULT_API_KEY
    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    context_window: int = DEFAULT_CONTEXT_WINDOW
    request_timeout_seconds: float | None = DEFAULT_REQUEST_TIMEOUT_SECONDS
    system_prompt: str = ""


def default_llm_settings() -> LlmSettings:
    """Return default local LLM settings."""
    return LlmSettings()


def normalize_openai_base_url(base_url: str) -> str:
    """Normalize a local server URL to an OpenAI-compatible base URL.

    LM Studio and similar local servers often display the server root, such as
    ``http://localhost:1234``. The OpenAI SDK expects the API base path, usually
    ``/v1``. If the user already supplies a path, it is preserved unless it is
    the root path.
    """
    stripped = base_url.strip().rstrip("/")
    if not stripped:
        return stripped

    # /v1/chat/completions が直接入力された場合の誤二重付与を防止
    for suffix in ("/chat/completions", "/v1"):
        if stripped.rstrip("/").endswith(suffix):
            stripped = stripped.rstrip("/")[:-len(suffix)]

    parsed = urlparse(stripped)
    if parsed.path in {"", "/"}:
        return f"{stripped}/v1"

    return stripped


def validate_llm_settings(settings: LlmSettings) -> list[str]:
    """Return validation errors for LLM settings.

    An empty list means the settings are valid enough to attempt generation.
    """
    errors: list[str] = []

    # base_url is optional — empty means auto-detect

    if not settings.model.strip():
        errors.append("Model is required")

    if not MIN_TEMPERATURE <= settings.temperature <= MAX_TEMPERATURE:
        errors.append(
            f"Temperature must be between {MIN_TEMPERATURE} and {MAX_TEMPERATURE}"
        )

    if settings.max_tokens < MIN_MAX_TOKENS:
        errors.append("Max Tokens must be greater than or equal to 1")

    if not MIN_CONTEXT_WINDOW <= settings.context_window <= MAX_CONTEXT_WINDOW:
        errors.append(
            f"Context Window must be between {MIN_CONTEXT_WINDOW:,} and {MAX_CONTEXT_WINDOW:,}"
        )

    if settings.max_tokens > settings.context_window:
        errors.append(
            f"Max Tokens ({settings.max_tokens}) cannot exceed Context Window ({settings.context_window})"
        )

    if settings.request_timeout_seconds is not None:
        if not MIN_REQUEST_TIMEOUT_SECONDS <= settings.request_timeout_seconds <= MAX_REQUEST_TIMEOUT_SECONDS:
            errors.append(
                "Request Timeout must be between "
                f"{MIN_REQUEST_TIMEOUT_SECONDS:.0f} and {MAX_REQUEST_TIMEOUT_SECONDS:.0f} seconds"
            )

    return errors


def is_valid_llm_settings(settings: LlmSettings) -> bool:
    """Return whether LLM settings are valid."""
    return not validate_llm_settings(settings)
