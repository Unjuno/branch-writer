"""Streamlit wrapper for the latest assistant message editor component."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

_COMPONENT_NAME = "latest_message_editor"
_COMPONENT_DIR = Path(__file__).parent
_FRONTEND_DIR = _COMPONENT_DIR / "frontend"
_BUILD_DIR = _FRONTEND_DIR / "build"
_BUILD_INDEX = _BUILD_DIR / "index.html"
_DEV_URL = os.environ.get("BRANCH_WRITER_COMPONENT_URL")

if _DEV_URL:
    _component_func = components.declare_component(_COMPONENT_NAME, url=_DEV_URL)
elif _BUILD_INDEX.exists():
    _component_func = components.declare_component(_COMPONENT_NAME, path=str(_BUILD_DIR))
else:
    _component_func = None


def component_available() -> bool:
    """Return whether the compiled or dev component is available."""
    return _component_func is not None


def latest_message_editor(
    *,
    message_id: str,
    content: str,
    disabled: bool = False,
    key: str | None = None,
) -> dict[str, Any] | None:
    """Render the latest assistant editor and return an intervention event.

    When the frontend has not been built yet, this function returns None. The
    Streamlit app can then display a fallback UI instead of crashing.
    """
    if _component_func is None:
        return None

    return _component_func(
        messageId=message_id,
        content=content,
        disabled=disabled,
        default=None,
        key=key,
    )
