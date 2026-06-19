"""Session-state helpers for Branch Writer."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, MutableMapping
from uuid import uuid4

from branch_writer.config import LlmSettings, default_llm_settings
from branch_writer.messages import ChatMessage

logger = logging.getLogger("branch_writer.state")


@dataclass(slots=True)
class UndoSnapshot:
    """A reversible latest-assistant intervention."""

    message_id: str
    before_content: str
    after_content: str
    action: str
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _migrate_llm_settings(state: MutableMapping[str, Any]) -> None:
    """Coerce older session-state LLM settings into the current dataclass shape."""
    current = state.get("llm_settings")
    defaults = default_llm_settings()

    if current is None:
        state["llm_settings"] = defaults
        return

    values: dict[str, Any] = {}
    changed = not isinstance(current, LlmSettings)

    for item in fields(LlmSettings):
        if hasattr(current, item.name):
            values[item.name] = getattr(current, item.name)
        else:
            values[item.name] = getattr(defaults, item.name)
            changed = True

    if changed:
        logger.info("_migrate_llm_settings: migrated session llm_settings to current schema")
        state["llm_settings"] = LlmSettings(**values)


def initialize_state(state: MutableMapping[str, Any]) -> None:
    """Initialize a Streamlit-compatible session state mapping."""
    state.setdefault("messages", [])
    _migrate_llm_settings(state)
    state.setdefault("undo_stack", [])
    state.setdefault("is_generating", False)
    state.setdefault("last_error", None)
    state.setdefault("last_intervention_request_id", None)
    state.setdefault("render_message_limit", 80)
    state.setdefault("available_models", [])
    state.setdefault("insertion_log", [])
    state.setdefault("reuse_insertion", None)
    state.setdefault("streaming_intervention", None)

    state.setdefault("cursor_loop", {
        "enabled": False,
        "message_id": None,
        "original_content": "",
        "cursor_pos": None,
        "preview_content": "",
        "status": "idle",
    })
    cl = state["cursor_loop"]
    cl.setdefault("enabled", False)
    cl.setdefault("message_id", None)
    cl.setdefault("original_content", "")
    cl.setdefault("cursor_pos", None)
    cl.setdefault("preview_content", "")
    cl.setdefault("status", "idle")

    state.setdefault("kw_filter", {
        "enabled": True,
        "words": "",
        "max_retries": 5,
        "retry_count": 0,
    })
    state["kw_filter"].setdefault("enabled", True)
    state["kw_filter"].setdefault("words", "")
    state["kw_filter"].setdefault("max_retries", 5)
    state["kw_filter"].setdefault("retry_count", 0)

    state.setdefault("validator", {
        "enabled": False,
        "prompt": "",
        "results": None,
        "error": None,
    })
    state["validator"].setdefault("enabled", False)
    state["validator"].setdefault("prompt", "")
    state["validator"].setdefault("results", None)
    state["validator"].setdefault("error", None)


def get_messages(state: MutableMapping[str, Any]) -> list[ChatMessage]:
    """Return chat messages from state, initializing them if needed."""
    initialize_state(state)
    return state["messages"]


def get_llm_settings(state: MutableMapping[str, Any]) -> LlmSettings:
    """Return LLM settings from state, initializing them if needed."""
    initialize_state(state)
    return state["llm_settings"]


def push_undo_snapshot(
    state: MutableMapping[str, Any],
    message_id: str,
    before_content: str,
    after_content: str,
    action: str,
) -> UndoSnapshot:
    """Push an undo snapshot and return it."""
    initialize_state(state)
    snapshot = UndoSnapshot(
        message_id=message_id,
        before_content=before_content,
        after_content=after_content,
        action=action,
    )
    state["undo_stack"].append(snapshot)
    return snapshot


def pop_undo_snapshot(state: MutableMapping[str, Any]) -> UndoSnapshot | None:
    """Pop the most recent undo snapshot, if any."""
    initialize_state(state)
    if not state["undo_stack"]:
        return None
    return state["undo_stack"].pop()


def set_error(state: MutableMapping[str, Any], message: str | None) -> None:
    """Set the last error message."""
    initialize_state(state)
    if message:
        logger.warning("set_error: %s", message[:200])
    state["last_error"] = message


def set_generating(state: MutableMapping[str, Any], value: bool) -> None:
    """Set the generation flag."""
    initialize_state(state)
    logger.info("set_generating: %s", value)
    state["is_generating"] = value
