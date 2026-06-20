"""OpenAI-compatible local LLM client for Branch Writer."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from typing import Any

import httpx

logger = logging.getLogger("branch_writer.llm")

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
    ttft: dict[str, Any] | None = None,
) -> Iterator[str]:
    payload = _chat_payload(api_messages=api_messages, settings=settings, stream=True)
    url = _chat_completions_url(settings)
    timeout_seconds = settings.request_timeout_seconds
    timeout_label = "disabled" if timeout_seconds is None else f"{timeout_seconds:.0f}s"
    logger.info("_iter_chat_completion_chunks: POST %s (model=%s, msgs=%d, timeout=%s)",
                url, settings.model, len(api_messages), timeout_label)

    try:
        timeout = (
            httpx.Timeout(None)
            if timeout_seconds is None
            else httpx.Timeout(timeout_seconds, connect=min(10.0, timeout_seconds), read=None)
        )
        with httpx.stream(
            "POST",
            url,
            headers=_headers(settings),
            json=payload,
            timeout=timeout,
        ) as response:
            if response.status_code >= 400:
                body = response.read().decode("utf-8", errors="replace")[:2000]
                logger.error("_iter_chat_completion_chunks: HTTP %d — %s", response.status_code, body[:200])
                raise LlmError(f"LLM HTTP {response.status_code}: {body}")

            chunk_count = 0
            last_data: dict[str, Any] | None = None
            saw_done = False
            for line in response.iter_lines():
                if not line:
                    continue

                if line.startswith("data:"):
                    line = line.removeprefix("data:").strip()

                if line == "[DONE]":
                    logger.debug("_iter_chat_completion_chunks: [DONE] received after %d chunks", chunk_count)
                    saw_done = True
                    break

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if isinstance(data, dict):
                    last_data = data
                chunk = _extract_delta_content(data)
                if chunk:
                    if ttft is not None and "t4" not in ttft:
                        ttft["t4"] = time.monotonic()
                    chunk_count += 1
                    yield chunk

            if ttft is not None:
                try:
                    usage = last_data.get("usage") if last_data else None
                    if usage:
                        times = ttft.setdefault("times", {})
                        if isinstance(times, dict):
                            times["usage"] = usage
                except Exception:
                    pass
            if chunk_count and not saw_done:
                logger.warning(
                    "_iter_chat_completion_chunks: stream closed before [DONE] (chunks=%d, url=%s)",
                    chunk_count,
                    url,
                )
    except LlmError:
        raise
    except httpx.TimeoutException as exc:
        logger.error("_iter_chat_completion_chunks: timeout after %s: %s", timeout_label, url)
        raise LlmError(f"LLM request timed out after {timeout_label}: {url}") from exc
    except httpx.RequestError as exc:
        logger.error("_iter_chat_completion_chunks: request error: %s", exc)
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
    logger.info("generate_text: prompt=%d chars", len(prompt))
    msg = ChatMessage(role="user", content=prompt)
    return "".join(iter_chat_response([msg], settings))


def _batch_chars(text: str, batch_size: int = 3) -> Iterator[str]:
    """Yield text in fixed-size character batches."""
    for i in range(0, len(text), batch_size):
        yield text[i:i + batch_size]


def iter_chat_response(
    messages: list[ChatMessage],
    settings: LlmSettings,
) -> Iterator[str]:
    """Yield a normal assistant response in small character batches."""
    logger.info("iter_chat_response: %d messages, model=%s", len(messages), settings.model)
    _validate_or_raise(settings)
    for chunk in _iter_chat_completion_chunks(
        api_messages=to_openai_messages(messages, system_prompt=settings.system_prompt),
        settings=settings,
    ):
        yield from _batch_chars(chunk)


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
    """Yield an intervention continuation in small character batches."""
    logger.info("iter_intervention_continuation: prefix=%d chars, insertion=%d chars, model=%s",
                len(assistant_prefix), len(insertion), settings.model)
    _validate_or_raise(settings)
    for chunk in _iter_chat_completion_chunks(
        api_messages=_intervention_messages(
            frozen_messages, assistant_prefix, insertion,
            system_prompt=settings.system_prompt,
        ),
        settings=settings,
    ):
        yield from _batch_chars(chunk)
