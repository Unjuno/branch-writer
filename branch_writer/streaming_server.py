"""SSE streaming server for Branch Writer."""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Generator
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from branch_writer.config import LlmSettings, default_llm_settings
from branch_writer.intervention import strip_continuation_overlap
from branch_writer.llm import LlmError, _iter_chat_completion_chunks
from branch_writer.messages import ChatMessage, to_openai_messages

logger = logging.getLogger("branch_writer.streaming_server")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_active_streams: dict[str, threading.Event] = {}
_server_lock = threading.Lock()
_server_started = False
_server_port: int | None = None


def _sse_event(event: str, data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _settings_from_payload(settings_data: dict[str, Any]) -> LlmSettings:
    defaults = default_llm_settings()
    values: dict[str, Any] = {}
    for name in LlmSettings.__dataclass_fields__:
        values[name] = settings_data.get(name, getattr(defaults, name))
    return LlmSettings(**values)


def _messages_from_payload(messages_data: list[dict[str, Any]]) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for item in messages_data:
        try:
            messages.append(ChatMessage(**item))
        except TypeError:
            role = item.get("role")
            content = item.get("content", "")
            if role in {"user", "assistant"}:
                messages.append(ChatMessage(role=role, content=content))
    return messages


def _stream_normal(
    messages: list[ChatMessage],
    settings: LlmSettings,
    stream_id: str,
) -> Generator[str, None, None]:
    """Stream a normal assistant response character by character."""
    logger.info("_stream_normal: streamId=%s, %d messages, model=%s", stream_id, len(messages), settings.model)
    abort = _active_streams.get(stream_id)
    full_content = ""
    try:
        for chunk in _iter_chat_completion_chunks(
            api_messages=to_openai_messages(messages, system_prompt=settings.system_prompt),
            settings=settings,
        ):
            if abort and abort.is_set():
                yield _sse_event("aborted", {"streamId": stream_id})
                return
            for char in chunk:
                if abort and abort.is_set():
                    yield _sse_event("aborted", {"streamId": stream_id})
                    return
                full_content += char
                yield _sse_event("token", {"text": char, "streamId": stream_id, "fullContent": full_content})
        logger.info("_stream_normal: done, streamId=%s, %d chars", stream_id, len(full_content))
        yield _sse_event("done", {"streamId": stream_id, "fullContent": full_content})
    except LlmError as exc:
        logger.error("_stream_normal: LlmError streamId=%s: %s", stream_id, exc)
        yield _sse_event("error", {"message": str(exc), "streamId": stream_id})
    except Exception as exc:
        logger.exception("_stream_normal: Unexpected error streamId=%s", stream_id)
        yield _sse_event("error", {"message": f"Unexpected error: {exc}", "streamId": stream_id})
    finally:
        _active_streams.pop(stream_id, None)


def _stream_intervention(
    frozen_messages: list[ChatMessage],
    assistant_prefix: str,
    insertion: str,
    before_content: str,
    selection_start: int,
    action: str,
    settings: LlmSettings,
    stream_id: str,
) -> Generator[str, None, None]:
    """Stream an intervention continuation character by character."""
    logger.info("_stream_intervention: streamId=%s, action=%s, selectionStart=%d, prefix=%d chars",
                stream_id, action, selection_start, len(assistant_prefix))
    abort = _active_streams.get(stream_id)
    base_content = assistant_prefix + insertion
    raw_continuation = ""
    previous_full_content = base_content
    try:
        for chunk in _iter_chat_completion_chunks(
            api_messages=[
                *to_openai_messages(frozen_messages, system_prompt=settings.system_prompt),
                {"role": "assistant", "content": base_content},
            ],
            settings=settings,
        ):
            if abort and abort.is_set():
                yield _sse_event("aborted", {"streamId": stream_id})
                return
            raw_continuation += chunk
            clean = strip_continuation_overlap(base_content, raw_continuation)
            full_content = base_content + clean
            delta = full_content[len(previous_full_content):]
            previous_full_content = full_content
            if not delta:
                continue
            for char in delta:
                if abort and abort.is_set():
                    yield _sse_event("aborted", {"streamId": stream_id})
                    return
                yield _sse_event(
                    "token",
                    {
                        "text": char,
                        "streamId": stream_id,
                        "fullContent": full_content,
                        "action": action,
                        "selectionStart": selection_start,
                        "insertion": insertion,
                    },
                )
        clean = strip_continuation_overlap(base_content, raw_continuation)
        full_content = base_content + clean
        logger.info("_stream_intervention: done, streamId=%s, %d chars", stream_id, len(full_content))
        yield _sse_event(
            "done",
            {
                "streamId": stream_id,
                "fullContent": full_content,
                "action": action,
                "selectionStart": selection_start,
                "insertion": insertion,
            },
        )
    except LlmError as exc:
        logger.error("_stream_intervention: LlmError streamId=%s: %s", stream_id, exc)
        yield _sse_event("error", {"message": str(exc), "streamId": stream_id})
    except Exception as exc:
        logger.exception("_stream_intervention: Unexpected error streamId=%s", stream_id)
        yield _sse_event("error", {"message": f"Unexpected error: {exc}", "streamId": stream_id})
    finally:
        _active_streams.pop(stream_id, None)


@app.post("/api/stream")
async def stream_endpoint(request: Request) -> StreamingResponse:
    body = await request.json()

    stream_id = body.get("streamId", "")
    mode = body.get("mode", "normal")
    settings_data = body.get("settings", {})
    messages_data = body.get("messages", [])

    logger.info("stream_endpoint: streamId=%s, mode=%s, model=%s", stream_id, mode, settings_data.get("model"))

    settings = _settings_from_payload(settings_data)
    messages = _messages_from_payload(messages_data)

    abort_event = threading.Event()
    if stream_id:
        previous = _active_streams.get(stream_id)
        if previous:
            previous.set()
        _active_streams[stream_id] = abort_event

    if mode == "intervention":
        frozen_data = body.get("frozenMessages", [])
        frozen_messages = _messages_from_payload(frozen_data)
        generator = _stream_intervention(
            frozen_messages=frozen_messages,
            assistant_prefix=body.get("assistantPrefix", ""),
            insertion=body.get("insertion", ""),
            before_content=body.get("beforeContent", ""),
            selection_start=body.get("selectionStart", 0),
            action=body.get("action", "regenerate_from_here"),
            settings=settings,
            stream_id=stream_id,
        )
    else:
        generator = _stream_normal(
            messages=messages,
            settings=settings,
            stream_id=stream_id,
        )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/abort")
async def abort_endpoint(request: Request) -> dict[str, str]:
    body = await request.json()
    stream_id = body.get("streamId", "")
    logger.info("abort_endpoint: streamId=%s", stream_id)
    abort_event = _active_streams.get(stream_id)
    if abort_event:
        abort_event.set()
        return {"status": "aborted", "streamId": stream_id}
    return {"status": "not_found", "streamId": stream_id}


def start_server(port: int = 8765) -> None:
    """Start the FastAPI server once per Python process."""
    import uvicorn

    global _server_started, _server_port
    with _server_lock:
        if _server_started:
            logger.info("start_server: already started on port %s", _server_port)
            return
        _server_started = True
        _server_port = port

    logger.info("start_server: starting on port %d", port)

    def run() -> None:
        try:
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")
        except Exception:
            logger.exception("start_server: uvicorn stopped unexpectedly")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info("start_server: background thread started")
