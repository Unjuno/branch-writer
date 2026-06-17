"""Configuration models for Branch Writer."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

DEFAULT_BASE_URL = "http://localhost:11434/v1"
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


@dataclass(slots=True)
class LlmSettings:
    """Settings for an OpenAI-compatible local LLM endpoint."""

    base_url: str = DEFAULT_BASE_URL
    api_key: str = DEFAULT_API_KEY
    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    context_window: int = DEFAULT_CONTEXT_WINDOW
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS


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

    parsed = urlparse(stripped)
    if parsed.path in {"", "/"}:
        return f"{stripped}/v1"

    return stripped


def validate_llm_settings(settings: LlmSettings) -> list[str]:
    """Return validation errors for LLM settings.

    An empty list means the settings are valid enough to attempt generation.
    """
    errors: list[str] = []

    if not settings.base_url.strip():
        errors.append("API Base URL is required")

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

    if not MIN_REQUEST_TIMEOUT_SECONDS <= settings.request_timeout_seconds <= MAX_REQUEST_TIMEOUT_SECONDS:
        errors.append(
            "Request Timeout must be between "
            f"{MIN_REQUEST_TIMEOUT_SECONDS:.0f} and {MAX_REQUEST_TIMEOUT_SECONDS:.0f} seconds"
        )

    return errors


def is_valid_llm_settings(settings: LlmSettings) -> bool:
    """Return whether LLM settings are valid."""
    return not validate_llm_settings(settings)
