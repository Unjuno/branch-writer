"""Configuration models for Branch Writer."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BASE_URL = "http://localhost:11434/v1"
DEFAULT_API_KEY = ""
DEFAULT_MODEL = ""
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 512
MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0
MIN_MAX_TOKENS = 1


@dataclass(slots=True)
class LlmSettings:
    """Settings for an OpenAI-compatible local LLM endpoint."""

    base_url: str = DEFAULT_BASE_URL
    api_key: str = DEFAULT_API_KEY
    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS


def default_llm_settings() -> LlmSettings:
    """Return default local LLM settings."""
    return LlmSettings()


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

    return errors


def is_valid_llm_settings(settings: LlmSettings) -> bool:
    """Return whether LLM settings are valid."""
    return not validate_llm_settings(settings)
