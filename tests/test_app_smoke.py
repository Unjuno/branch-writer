"""Tests for app.py — importable functions."""
from __future__ import annotations

from unittest.mock import Mock

from branch_writer.messages import ChatMessage


def test_app_imports_without_running_streamlit_main() -> None:
    import app

    assert hasattr(app, "main")
    assert hasattr(app, "handle_intervention_event")


def test_estimate_tokens() -> None:
    from app import estimate_tokens

    assert estimate_tokens("Hello, world!") == 3
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 100) == 25


# ── handle_streaming_error ──


def _make_state(*, messages: list | None = None) -> Mock:
    state = Mock()
    state.get = Mock(side_effect=lambda key, default=None: {
        "messages": messages or [],
        "is_generating": True,
        "streaming_intervention": None,
    }.get(key, default))
    state.__setitem__ = Mock()
    state.__getitem__ = Mock(side_effect=lambda key: {
        "messages": messages or [],
        "is_generating": True,
        "streaming_intervention": None,
    }.get(key, ""))
    state.setdefault = Mock()
    return state


def test_handle_streaming_error_sets_latest_to_error_status() -> None:
    from app import handle_streaming_error
    import app as app_module

    assistant = ChatMessage(role="assistant", content="Hello", status="streaming")
    state = {
        "messages": [assistant],
        "is_generating": True,
        "last_error": None,
        "streaming_intervention": None,
    }
    st = type("st", (), {"session_state": state})()
    _orig_st = app_module.st
    app_module.st = st

    try:
        event = {
            "type": "streaming_error",
            "message": "Connection lost",
            "content": "Hel",
            "messageId": assistant.id,
        }
        handle_streaming_error(event)

        assert state["messages"][-1].status == "error"
        assert state["messages"][-1].content == "Hel"
        assert state["last_error"] == "Streaming error: Connection lost"
        assert state["is_generating"] is False
    finally:
        app_module.st = _orig_st


def test_handle_streaming_error_skips_stale_event() -> None:
    from app import handle_streaming_error
    import app as app_module

    assistant = ChatMessage(role="assistant", content="Hello", status="complete")
    state = {
        "messages": [assistant],
        "is_generating": False,
        "last_error": None,
        "streaming_intervention": None,
    }
    st = type("st", (), {"session_state": state})()
    _orig_st = app_module.st
    app_module.st = st

    try:
        event = {
            "type": "streaming_error",
            "message": "Late error",
            "content": "",
            "messageId": assistant.id,
        }
        handle_streaming_error(event)

        # Should not change anything
        assert assistant.status == "complete"
        assert assistant.content == "Hello"
    finally:
        app_module.st = _orig_st


def test_handle_streaming_error_falls_back_to_before_content() -> None:
    from app import handle_streaming_error
    import app as app_module

    assistant = ChatMessage(role="assistant", content="partial", status="streaming")
    state = {
        "messages": [assistant],
        "is_generating": True,
        "last_error": None,
        "streaming_intervention": {
            "before_content": "original full content",
        },
    }
    st = type("st", (), {"session_state": state})()
    _orig_st = app_module.st
    app_module.st = st

    try:
        event = {
            "type": "streaming_error",
            "message": "Timeout",
            "content": "",
            "messageId": assistant.id,
        }
        handle_streaming_error(event)

        # Falls back to before_content since error content is empty
        assert assistant.content == "original full content"
        assert assistant.status == "error"
        assert state["is_generating"] is False
    finally:
        app_module.st = _orig_st


def test_handle_streaming_error_empty_messages() -> None:
    from app import handle_streaming_error
    import app as app_module

    state = {
        "messages": [],
        "is_generating": True,
        "last_error": None,
        "streaming_intervention": None,
    }
    st = type("st", (), {"session_state": state})()
    _orig_st = app_module.st
    app_module.st = st

    try:
        event = {
            "type": "streaming_error",
            "message": "Error with no messages",
            "content": "",
            "messageId": "nonexistent",
        }
        handle_streaming_error(event)

        assert state["last_error"] == "Streaming error: Error with no messages"
        assert state["is_generating"] is False
    finally:
        app_module.st = _orig_st
