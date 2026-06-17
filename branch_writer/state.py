"""Session-state helpers for Branch Writer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, MutableMapping
from uuid import uuid4

from branch_writer.config import LlmSettings, default_llm_settings
from branch_writer.messages import ChatMessage


@dataclass(slots=True)
class UndoSnapshot:
    """A reversible latest-assistant intervention."""

    message_id: str
    before_content: str
    after_content: str
    action: str
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def initialize_state(state: MutableMapping[str, Any]) -> None:
    """Initialize a Streamlit-compatible session state mapping."""
    state.setdefault("messages", [])
    state.setdefault("llm_settings", default_llm_settings())
    state.setdefault("undo_stack", [])
    state.setdefault("is_generating", False)
    state.setdefault("last_error", None)
    state.setdefault("last_intervention_request_id", None)
    state.setdefault("render_message_limit", 80)
    state.setdefault("available_models", [])
    state.setdefault("insertion_log", [])
    state.setdefault("reuse_insertion", None)
    state.setdefault("streaming_generator", None)


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
    state["last_error"] = message


def set_generating(state: MutableMapping[str, Any], value: bool) -> None:
    """Set the generation flag."""
    initialize_state(state)
    state["is_generating"] = value
