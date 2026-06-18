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


def generate_text(prompt: str, settings: LlmSettings) -> str:
    """Generate a one-shot text response without mutating conversation state."""
    msg = ChatMessage(role="user", content=prompt)
    return "".join(iter_chat_response([msg], settings))


def iter_chat_response(
    messages: list[ChatMessage],
    settings: LlmSettings,
) -> Iterator[str]:
    """Yield a normal assistant response as streaming chunks."""
    _validate_or_raise(settings)
    yield from _iter_chat_completion_chunks(
        api_messages=to_openai_messages(messages, system_prompt=settings.system_prompt),
        settings=settings,
    )


def _intervention_messages(
    frozen_messages: list[ChatMessage],
    assistant_prefix: str,
    insertion: str,
    system_prompt: str = "",
) -> list[dict[str, str]]:
    continuation_base = assistant_prefix + insertion
    api_messages = to_openai_messages(frozen_messages, system_prompt=system_prompt)
    api_messages.append({"role": "assistant", "content": continuation_base})
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
        api_messages=_intervention_messages(
            frozen_messages, assistant_prefix, insertion,
            system_prompt=settings.system_prompt,
        ),
        settings=settings,
    )



