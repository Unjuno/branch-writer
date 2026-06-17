"""OpenAI-compatible local LLM client for Branch Writer."""

from __future__ import annotations

from typing import Any

import httpx

from branch_writer.config import (
    LlmSettings,
    normalize_openai_base_url,
    validate_llm_settings,
)
from branch_writer.messages import ChatMessage, to_openai_messages

REQUEST_TIMEOUT_SECONDS = 600.0


class LlmError(RuntimeError):
    """Raised when local LLM generation fails."""


def _validate_or_raise(settings: LlmSettings) -> None:
    errors = validate_llm_settings(settings)
    if errors:
        raise LlmError("; ".join(errors))


def _chat_completions_url(settings: LlmSettings) -> str:
    return f"{normalize_openai_base_url(settings.base_url)}/chat/completions"


def _headers(settings: LlmSettings) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"
    return headers


def _post_chat_completion(
    *,
    api_messages: list[dict[str, str]],
    settings: LlmSettings,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": settings.model,
        "messages": api_messages,
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
        "stream": False,
    }

    url = _chat_completions_url(settings)

    try:
        response = httpx.post(
            url,
            headers=_headers(settings),
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except httpx.TimeoutException as exc:
        raise LlmError(f"LLM request timed out after {REQUEST_TIMEOUT_SECONDS:.0f}s: {url}") from exc
    except httpx.RequestError as exc:
        raise LlmError(f"LLM request failed: {exc}") from exc

    if response.status_code >= 400:
        body = response.text[:2000]
        raise LlmError(f"LLM HTTP {response.status_code}: {body}")

    try:
        data = response.json()
    except ValueError as exc:
        raise LlmError(f"LLM returned non-JSON response: {response.text[:2000]}") from exc

    if not isinstance(data, dict):
        raise LlmError(f"LLM returned unexpected response type: {type(data).__name__}")

    return data


def _extract_content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LlmError(f"LLM returned no choices. Raw response: {str(data)[:2000]}")

    first = choices[0]
    if not isinstance(first, dict):
        raise LlmError(f"LLM returned invalid choice: {str(first)[:2000]}")

    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content:
            return content

    text = first.get("text")
    if isinstance(text, str) and text:
        return text

    delta = first.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str) and content:
            return content

    raise LlmError(f"LLM returned no message content. Raw choice: {str(first)[:2000]}")


def generate_chat_response(
    messages: list[ChatMessage],
    settings: LlmSettings,
) -> str:
    """Generate a normal assistant response from chat history."""
    _validate_or_raise(settings)
    data = _post_chat_completion(
        api_messages=to_openai_messages(messages),
        settings=settings,
    )
    return _extract_content(data)


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

    continuation_base = assistant_prefix + insertion
    prompt = (
        "Continue the latest assistant response from the following exact text. "
        "Return only the continuation text. Do not repeat the given text.\n\n"
        "Text to continue:\n"
        f"{continuation_base}"
    )

    api_messages = to_openai_messages(frozen_messages)
    api_messages.append({"role": "user", "content": prompt})

    data = _post_chat_completion(
        api_messages=api_messages,
        settings=settings,
    )
    return _extract_content(data)
