"""OpenAI-compatible local LLM client for Branch Writer."""

from __future__ import annotations

from openai import OpenAI

from branch_writer.config import LlmSettings, validate_llm_settings
from branch_writer.messages import ChatMessage, to_openai_messages


class LlmError(RuntimeError):
    """Raised when local LLM generation fails."""


def _build_client(settings: LlmSettings) -> OpenAI:
    """Build an OpenAI-compatible client for a local endpoint."""
    return OpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key or "branch-writer-local-key",
    )


def _validate_or_raise(settings: LlmSettings) -> None:
    errors = validate_llm_settings(settings)
    if errors:
        raise LlmError("; ".join(errors))


def generate_chat_response(
    messages: list[ChatMessage],
    settings: LlmSettings,
) -> str:
    """Generate a normal assistant response from chat history."""
    _validate_or_raise(settings)
    client = _build_client(settings)

    try:
        response = client.chat.completions.create(
            model=settings.model,
            messages=to_openai_messages(messages),
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )
    except Exception as exc:  # pragma: no cover - exercised by integration tests later
        raise LlmError(str(exc)) from exc

    if not response.choices:
        raise LlmError("LLM returned no choices")

    content = response.choices[0].message.content
    if content is None:
        raise LlmError("LLM returned an empty message")

    return content


def generate_intervention_continuation(
    frozen_messages: list[ChatMessage],
    assistant_prefix: str,
    insertion: str,
    settings: LlmSettings,
) -> str:
    """Generate only the continuation after an intervention point.

    v0 uses chat completions for compatibility. The discarded suffix is not sent.
    The model is asked to return only the continuation, not the prefix.
    """
    _validate_or_raise(settings)
    client = _build_client(settings)

    continuation_base = assistant_prefix + insertion
    prompt = (
        "Continue the latest assistant response from the following exact text. "
        "Return only the continuation text. Do not repeat the given text.\n\n"
        "Text to continue:\n"
        f"{continuation_base}"
    )

    api_messages = to_openai_messages(frozen_messages)
    api_messages.append({"role": "user", "content": prompt})

    try:
        response = client.chat.completions.create(
            model=settings.model,
            messages=api_messages,
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )
    except Exception as exc:  # pragma: no cover - exercised by integration tests later
        raise LlmError(str(exc)) from exc

    if not response.choices:
        raise LlmError("LLM returned no choices")

    content = response.choices[0].message.content
    if content is None:
        raise LlmError("LLM returned an empty message")

    return content
