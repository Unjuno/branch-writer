"""Streamlit wrapper for the latest assistant message editor component."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

logger = logging.getLogger("branch_writer.component")

_COMPONENT_NAME = "latest_message_editor"
_COMPONENT_DIR = Path(__file__).parent
_FRONTEND_DIR = _COMPONENT_DIR / "frontend"
_BUILD_DIR = _FRONTEND_DIR / "build"
_BUILD_INDEX = _BUILD_DIR / "index.html"
_DEV_URL = os.environ.get("BRANCH_WRITER_COMPONENT_URL")

if _DEV_URL:
    _component_func = components.declare_component(_COMPONENT_NAME, url=_DEV_URL)
    logger.info("component loaded from dev URL: %s", _DEV_URL)
elif _BUILD_INDEX.exists():
    _component_func = components.declare_component(_COMPONENT_NAME, path=str(_BUILD_DIR))
    logger.info("component loaded from build: %s", _BUILD_DIR)
else:
    _component_func = None
    logger.warning("component not available (no build, no dev URL)")


def component_available() -> bool:
    """Return whether the compiled or dev component is available."""
    return _component_func is not None


def latest_message_editor(
    *,
    message_id: str,
    content: str,
    disabled: bool = False,
    streaming_url: str = "",
    is_streaming: bool = False,
    intervention_data: dict[str, Any] | None = None,
    cursor_loop_enabled: bool = False,
    preview_content: str = "",
    long_mode: bool = False,
    messages_for_stream: list[dict[str, str]] | None = None,
    frozen_messages: list[dict[str, str]] | None = None,
    llm_settings: dict[str, Any] | None = None,
    keyword_filter: dict[str, Any] | None = None,
    key: str | None = None,
) -> dict[str, Any] | None:
    """Render the latest assistant editor and return an intervention event.

    When the frontend has not been built yet, this function returns None. The
    Streamlit app can then display a fallback UI instead of crashing.
    """
    if _component_func is None:
        return None

    logger.debug("latest_message_editor: messageId=%s, disabled=%s, isStreaming=%s",
                 message_id, disabled, is_streaming)
    return _component_func(
        messageId=message_id,
        content=content,
        disabled=disabled,
        streamingUrl=streaming_url,
        isStreaming=is_streaming,
        interventionData=intervention_data,
        cursorLoopEnabled=cursor_loop_enabled,
        previewContent=preview_content,
        messagesForStream=messages_for_stream,
        frozenMessages=frozen_messages,
        longMode=long_mode,
        llmSettings=llm_settings,
        keywordFilter=keyword_filter,
        default=None,
        key=key,
    )
