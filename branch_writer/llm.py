"""OpenAI-compatible local LLM client for Branch Writer."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx

from branch_writer.config import (
    LlmSettings,
    normalize_openai_base_url,
    validate_llm_settings,
)
from branch_writer.messages import ChatMessage, to_openai_messages


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


def _chat_payload(
    *,
    api_messages: list[dict[str, str]],
    settings: LlmSettings,
    stream: bool,
) -> dict[str, Any]:
    return {
        "model": settings.model,
        "messages": api_messages,
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
        "stream": stream,
    }


def _post_chat_completion(
    *,
    api_messages: list[dict[str, str]],
    settings: LlmSettings,
) -> dict[str, Any]:
    payload = _chat_payload(api_messages=api_messages, settings=settings, stream=False)
    url = _chat_completions_url(settings)
    timeout_seconds = settings.request_timeout_seconds

    try:
        response = httpx.post(
            url,
            headers=_headers(settings),
            json=payload,
            timeout=timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise LlmError(f"LLM request timed out after {timeout_seconds:.0f}s: {url}") from exc
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


def _iter_chat_completion_chunks(
    *,
    api_messages: list[dict[str, str]],
    settings: LlmSettings,
) -> Iterator[str]:
    payload = _chat_payload(api_messages=api_messages, settings=settings, stream=True)
    url = _chat_completions_url(settings)
    timeout_seconds = settings.request_timeout_seconds

    try:
        with httpx.stream(
            "POST",
            url,
            headers=_headers(settings),
            json=payload,
            timeout=timeout_seconds,
        ) as response:
            if response.status_code >= 400:
                body = response.read().decode("utf-8", errors="replace")[:2000]
                raise LlmError(f"LLM HTTP {response.status_code}: {body}")

            for line in response.iter_lines():
                if not line:
                    continue

                if line.startswith("data:"):
                    line = line.removeprefix("data:").strip()

                if line == "[DONE]":
                    break

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                chunk = _extract_delta_content(data)
                if chunk:
                    yield chunk
    except LlmError:
        raise
    except httpx.TimeoutException as exc:
        raise LlmError(f"LLM stream timed out after {timeout_seconds:.0f}s: {url}") from exc
    except httpx.RequestError as exc:
        raise LlmError(f"LLM stream failed: {exc}") from exc


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


def _extract_delta_content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    first = choices[0]
    if not isinstance(first, dict):
        return ""

    delta = first.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            return content

    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content

    text = first.get("text")
    if isinstance(text, str):
        return text

    return ""


def iter_chat_response(
    messages: list[ChatMessage],
    settings: LlmSettings,
) -> Iterator[str]:
    """Yield a normal assistant response as streaming chunks."""
    _validate_or_raise(settings)
    yield from _iter_chat_completion_chunks(
        api_messages=to_openai_messages(messages),
        settings=settings,
    )


def generate_chat_response(
    messages: list[ChatMessage],
    settings: LlmSettings,
) -> str:
    """Generate a normal assistant response from chat history."""
    return "".join(iter_chat_response(messages, settings))


def _intervention_messages(
    frozen_messages: list[ChatMessage],
    assistant_prefix: str,
    insertion: str,
) -> list[dict[str, str]]:
    continuation_base = assistant_prefix + insertion
    prompt = (
        "Continue the latest assistant response from the following exact text. "
        "Return only the continuation text. Do not repeat the given text.\n\n"
        "Text to continue:\n"
        f"{continuation_base}"
    )

    api_messages = to_openai_messages(frozen_messages)
    api_messages.append({"role": "user", "content": prompt})
    return api_messages


def iter_intervention_continuation(
    frozen_messages: list[ChatMessage],
    assistant_prefix: str,
    insertion: str,
    settings: LlmSettings,
) -> Iterator[str]:
    """Yield an intervention continuation as streaming chunks."""
    _validate_or_raise(settings)
    yield from _iter_chat_completion_chunks(
        api_messages=_intervention_messages(frozen_messages, assistant_prefix, insertion),
        settings=settings,
    )


def generate_intervention_continuation(
    frozen_messages: list[ChatMessage],
    assistant_prefix: str,
    insertion: str,
    settings: LlmSettings,
) -> str:
    """Generate only the continuation after an intervention point."""
    return "".join(
        iter_intervention_continuation(
            frozen_messages=frozen_messages,
            assistant_prefix=assistant_prefix,
            insertion=insertion,
            settings=settings,
        )
    )
