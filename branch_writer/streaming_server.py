"""SSE streaming server for Branch Writer."""

from __future__ import annotations

import json
import logging
import socket
import threading
from collections.abc import Generator
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from branch_writer.config import LlmSettings
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
_active_streams_lock = threading.Lock()
_server_started = False
_server_lock = threading.Lock()


@app.get("/health")
async def health_endpoint() -> dict[str, str]:
    return {"status": "ok"}


def _is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _sse_event(event: str, data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _register_stream(stream_id: str, event: threading.Event) -> None:
    with _active_streams_lock:
        _active_streams[stream_id] = event


def _unregister_stream(stream_id: str) -> None:
    with _active_streams_lock:
        _active_streams.pop(stream_id, None)


def _get_abort_event(stream_id: str) -> threading.Event | None:
    with _active_streams_lock:
        return _active_streams.get(stream_id)


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
                yield _sse_event("token", {"text": char, "streamId": stream_id})
        logger.info("_stream_normal: done, streamId=%s, %d chars", stream_id, len(full_content))
        yield _sse_event("done", {"streamId": stream_id, "fullContent": full_content})
    except LlmError as exc:
        logger.error("_stream_normal: LlmError streamId=%s: %s", stream_id, exc)
        yield _sse_event("error", {"message": str(exc), "streamId": stream_id})
    except Exception as exc:
        logger.error("_stream_normal: Unexpected error streamId=%s: %s", stream_id, exc)
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
    raw_continuation = ""
    try:
        for chunk in _iter_chat_completion_chunks(
            api_messages=[
                *to_openai_messages(frozen_messages, system_prompt=settings.system_prompt),
                {"role": "assistant", "content": assistant_prefix + insertion},
            ],
            settings=settings,
        ):
            if abort and abort.is_set():
                yield _sse_event("aborted", {"streamId": stream_id})
                return
            raw_continuation += chunk
            clean = strip_continuation_overlap(assistant_prefix, raw_continuation)
            full_content = assistant_prefix + insertion + clean
            for char in clean:
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
        clean = strip_continuation_overlap(assistant_prefix, raw_continuation)
        full_content = assistant_prefix + insertion + clean
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
        logger.error("_stream_intervention: Unexpected error streamId=%s: %s", stream_id, exc)
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

    settings = LlmSettings(**settings_data)
    messages = [ChatMessage(**m) for m in messages_data]

    abort_event = threading.Event()
    _active_streams[stream_id] = abort_event

    if mode == "intervention":
        frozen_data = body.get("frozenMessages", [])
        frozen_messages = [ChatMessage(**m) for m in frozen_data]
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
    """Start the FastAPI server in a background thread (idempotent, once per process)."""
    global _server_started
    import uvicorn

    with _server_lock:
        if _server_started:
            logger.info("start_server: already started, skipping")
            return
        if _is_port_in_use(port):
            # Port already in use by another process — check if it's our server
            try:
                resp = httpx.get(f"http://127.0.0.1:{port}/health", timeout=2)
                if resp.status_code == 200:
                    logger.info("start_server: server already running on port %d, reusing", port)
                    _server_started = True
                    return
            except Exception:
                pass
            logger.error(
                "start_server: Port %d is already in use by another process. "
                "Please free the port or change _STREAMING_PORT in app.py.",
                port,
            )
            raise RuntimeError(
                f"Port {port} is already in use by another process. "
                f"Please free the port or change _STREAMING_PORT in app.py."
            )

        logger.info("start_server: starting on port %d", port)
        _server_started = True

    def run() -> None:
        try:
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")
        except Exception:
            logger.exception("start_server: uvicorn failed to start")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    logger.info("start_server: background thread started")
