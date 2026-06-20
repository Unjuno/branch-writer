"""SSE streaming server for Branch Writer."""

from __future__ import annotations

import json
import logging
import socket
import threading
import time
from collections.abc import Generator
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from branch_writer.config import LlmSettings
from branch_writer.intervention import strip_continuation_overlap
from branch_writer.llm import LlmError, _iter_chat_completion_chunks, prefill_cache
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


@app.post("/api/warmup")
async def warmup_endpoint(request: Request) -> dict[str, str]:
    body = await request.json()
    raw_messages = body.get("messages", [])
    raw_settings = body.get("settings")
    if not raw_messages or not raw_settings:
        return {"status": "skip", "reason": "missing messages or settings"}
    settings = LlmSettings(**raw_settings)
    messages = [ChatMessage(role=m.get("role", "user"), content=m.get("content", "")) for m in raw_messages]
    threading.Thread(target=prefill_cache, args=(messages, settings), daemon=True).start()
    return {"status": "warming"}


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
    stream_epoch: int,
    ttft: dict[str, Any] | None = None,
) -> Generator[str, None, None]:
    """Stream a normal assistant response character by character."""
    logger.info("_stream_normal: streamId=%s, %d messages, model=%s", stream_id, len(messages), settings.model)
    abort = _get_abort_event(stream_id)
    full_content = ""
    emitted_ttft_debug = False
    try:
        if ttft is not None:
            ttft["t3"] = time.monotonic()
        for chunk in _iter_chat_completion_chunks(
            api_messages=to_openai_messages(messages, system_prompt=settings.system_prompt),
            settings=settings,
            ttft=ttft,
        ):
            if abort and abort.is_set():
                yield _sse_event("aborted", {"streamId": stream_id, "epoch": stream_epoch})
                return
            if ttft is not None and not emitted_ttft_debug:
                payload = dict(ttft)
                payload["streamId"] = stream_id
                payload["epoch"] = stream_epoch
                yield _sse_event("debug:ttft", payload)
                emitted_ttft_debug = True
            full_content += chunk
            if abort and abort.is_set():
                yield _sse_event("aborted", {"streamId": stream_id, "epoch": stream_epoch})
                return
            yield _sse_event("token", {"fullContent": full_content, "streamId": stream_id, "epoch": stream_epoch})
        logger.info("_stream_normal: done, streamId=%s, %d chars", stream_id, len(full_content))
        yield _sse_event("done", {"streamId": stream_id, "epoch": stream_epoch, "fullContent": full_content})
    except LlmError as exc:
        logger.error("_stream_normal: LlmError streamId=%s: %s", stream_id, exc)
        yield _sse_event("error", {"message": str(exc), "streamId": stream_id, "epoch": stream_epoch})
    except Exception as exc:
        logger.error("_stream_normal: Unexpected error streamId=%s: %s", stream_id, exc)
        yield _sse_event("error", {"message": f"Unexpected error: {exc}", "streamId": stream_id, "epoch": stream_epoch})
    finally:
        _unregister_stream(stream_id)


def _stream_intervention(
    frozen_messages: list[ChatMessage],
    assistant_prefix: str,
    generation_prefix: str,
    insertion: str,
    before_content: str,
    selection_start: int,
    action: str,
    settings: LlmSettings,
    stream_id: str,
    stream_epoch: int,
    ttft: dict[str, Any] | None = None,
) -> Generator[str, None, None]:
    """Stream an intervention continuation character by character."""
    base_content = assistant_prefix + insertion
    prompt_prefix = generation_prefix if generation_prefix else base_content
    logger.info("_stream_intervention: streamId=%s, action=%s, selectionStart=%d, base=%d chars",
                stream_id, action, selection_start, len(base_content))
    abort = _get_abort_event(stream_id)
    raw_continuation = ""
    last_clean_len = 0
    emitted_ttft_debug = False
    try:
        if ttft is not None:
            ttft["t3"] = time.monotonic()
        for chunk in _iter_chat_completion_chunks(
            api_messages=[
                *to_openai_messages(frozen_messages, system_prompt=settings.system_prompt),
                {"role": "assistant", "content": prompt_prefix},
            ],
            settings=settings,
            ttft=ttft,
        ):
            if abort and abort.is_set():
                yield _sse_event("aborted", {"streamId": stream_id, "epoch": stream_epoch, "streamKey": stream_id})
                return
            if ttft is not None and not emitted_ttft_debug:
                payload = dict(ttft)
                payload["streamId"] = stream_id
                payload["epoch"] = stream_epoch
                yield _sse_event("debug:ttft", payload)
                emitted_ttft_debug = True
            raw_continuation += chunk
            clean = strip_continuation_overlap(base_content, raw_continuation)
            full_content = base_content + clean
            new_chars = clean[last_clean_len:]
            if not new_chars:
                continue
            last_clean_len = len(clean)
            yield _sse_event(
                "token",
                {
                    "fullContent": full_content,
                    "streamId": stream_id,
                    "epoch": stream_epoch,
                    "streamKey": stream_id,
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
                "epoch": stream_epoch,
                "streamKey": stream_id,
                "fullContent": full_content,
                "action": action,
                "selectionStart": selection_start,
                "insertion": insertion,
            },
        )
    except LlmError as exc:
        logger.error("_stream_intervention: LlmError streamId=%s: %s", stream_id, exc)
        yield _sse_event("error", {"message": str(exc), "streamId": stream_id, "epoch": stream_epoch, "streamKey": stream_id})
    except Exception as exc:
        logger.error("_stream_intervention: Unexpected error streamId=%s: %s", stream_id, exc)
        yield _sse_event("error", {"message": f"Unexpected error: {exc}", "streamId": stream_id, "epoch": stream_epoch, "streamKey": stream_id})
    finally:
        _unregister_stream(stream_id)


_CONTINUE_TRUNCATE = 4000


def _stream_continue(
    frozen_messages: list[ChatMessage],
    base_content: str,
    settings: LlmSettings,
    stream_id: str,
    stream_epoch: int,
    ttft: dict[str, Any] | None = None,
) -> Generator[str, None, None]:
    """Continue generating from the end of base_content."""
    truncated = base_content[-_CONTINUE_TRUNCATE:] if len(base_content) > _CONTINUE_TRUNCATE else base_content
    logger.info("_stream_continue: streamId=%s, base=%d chars, truncated=%d",
                stream_id, len(base_content), len(truncated))
    abort = _get_abort_event(stream_id)
    full_content = base_content
    emitted_ttft_debug = False
    try:
        if ttft is not None:
            ttft["t3"] = time.monotonic()
        for chunk in _iter_chat_completion_chunks(
            api_messages=[
                *to_openai_messages(frozen_messages, system_prompt=settings.system_prompt),
                {"role": "assistant", "content": truncated},
            ],
            settings=settings,
            ttft=ttft,
        ):
            if abort and abort.is_set():
                yield _sse_event("aborted", {"streamId": stream_id, "epoch": stream_epoch})
                return
            if ttft is not None and not emitted_ttft_debug:
                payload = dict(ttft)
                payload["streamId"] = stream_id
                payload["epoch"] = stream_epoch
                yield _sse_event("debug:ttft", payload)
                emitted_ttft_debug = True
            full_content += chunk
            if abort and abort.is_set():
                yield _sse_event("aborted", {"streamId": stream_id, "epoch": stream_epoch})
                return
            yield _sse_event("token", {"fullContent": full_content, "streamId": stream_id, "epoch": stream_epoch})
        logger.info("_stream_continue: done, streamId=%s, %d chars", stream_id, len(full_content))
        yield _sse_event("done", {"streamId": stream_id, "epoch": stream_epoch, "fullContent": full_content})
    except LlmError as exc:
        logger.error("_stream_continue: LlmError streamId=%s: %s", stream_id, exc)
        yield _sse_event("error", {"message": str(exc), "streamId": stream_id, "epoch": stream_epoch})
    except Exception as exc:
        logger.error("_stream_continue: Unexpected error streamId=%s: %s", stream_id, exc)
        yield _sse_event("error", {"message": f"Unexpected error: {exc}", "streamId": stream_id, "epoch": stream_epoch})
    finally:
        _unregister_stream(stream_id)


@app.post("/api/stream")
async def stream_endpoint(request: Request) -> Response:
    body = await request.json()

    stream_id = body.get("streamId", "")
    stream_epoch = int(body.get("epoch", 0) or 0)
    mode = body.get("mode", "normal")
    settings_data = body.get("settings", {})
    messages_data = body.get("messages", [])

    logger.info("stream_endpoint: streamId=%s, mode=%s, model=%s", stream_id, mode, settings_data.get("model"))

    ttft: dict[str, Any] = {}
    client_ts = body.get("clientTimestamps")
    if isinstance(client_ts, dict):
        ttft["t0"] = client_ts.get("t0")
        ttft["t1"] = client_ts.get("t1")
    ttft["t2"] = time.monotonic()

    try:
        settings = LlmSettings(**settings_data)
        messages = [ChatMessage(**m) for m in messages_data]
    except (TypeError, KeyError, ValueError) as exc:
        logger.error("stream_endpoint: invalid request data: %s", exc)
        return JSONResponse(status_code=400, content={"error": f"Invalid request data: {exc}"})

    abort_event = threading.Event()
    _register_stream(stream_id, abort_event)

    if mode == "continue":
        frozen_data = body.get("frozenMessages", [])
        try:
            frozen_messages = [ChatMessage(**m) for m in frozen_data]
        except (TypeError, KeyError, ValueError) as exc:
            _unregister_stream(stream_id)
            return JSONResponse(status_code=400, content={"error": f"Invalid frozen messages: {exc}"})
        base = body.get("baseContent", "")
        generator = _stream_continue(
            frozen_messages=frozen_messages,
            base_content=base,
            settings=settings,
            stream_id=stream_id,
            stream_epoch=stream_epoch,
            ttft=ttft,
        )
    elif mode in ("intervention", "cursor_loop"):
        frozen_data = body.get("frozenMessages", [])
        try:
            frozen_messages = [ChatMessage(**m) for m in frozen_data]
        except (TypeError, KeyError, ValueError) as exc:
            _unregister_stream(stream_id)
            return JSONResponse(status_code=400, content={"error": f"Invalid frozen messages: {exc}"})
        generator = _stream_intervention(
            frozen_messages=frozen_messages,
            assistant_prefix=body.get("assistantPrefix", ""),
            generation_prefix=body.get("generationPrefix", ""),
            insertion=body.get("insertion", ""),
            before_content=body.get("beforeContent", ""),
            selection_start=body.get("selectionStart", 0),
            action=body.get("action", "regenerate_from_here"),
            settings=settings,
            stream_id=stream_id,
            stream_epoch=stream_epoch,
            ttft=ttft,
        )
    else:
        generator = _stream_normal(
            messages=messages,
            settings=settings,
            stream_id=stream_id,
            stream_epoch=stream_epoch,
            ttft=ttft,
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
    abort_event = _get_abort_event(stream_id)
    if abort_event:
        abort_event.set()
        return {"status": "aborted", "streamId": stream_id}
    return {"status": "not_found", "streamId": stream_id}


def start_server(port: int = 8765) -> None:
    """Start the FastAPI server in a background thread (idempotent, once per process)."""
    global _server_started

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
