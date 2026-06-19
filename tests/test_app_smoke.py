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


# ── handle_cursor_loop_position (preview-only) ──


def _cursor_loop_state() -> dict:
    return {
        "enabled": True,
        "message_id": None,
        "original_content": "",
        "base_content": "",
        "cursor_pos": None,
        "preview_content": "",
        "status": "idle",
        "stream_key": None,
        "error": None,
    }


def test_handle_cursor_loop_position_does_not_modify_latest_content() -> None:
    """P0-2: preview-only — latest.content is never modified."""
    from app import handle_cursor_loop_position, is_intervenable
    import app as app_module

    assistant = ChatMessage(role="assistant", content="Hello world", status="complete")
    state = {
        "messages": [assistant],
        "is_generating": False,
        "last_error": None,
        "streaming_intervention": None,
        "cursor_loop": _cursor_loop_state(),
        "kw_filter": {"retry_count": 0},
        "validator": {"error": None},
    }
    st = type("st", (), {"session_state": state})()
    _orig_st = app_module.st
    app_module.st = st
    _orig_is_intervenable = app_module.is_intervenable
    app_module.is_intervenable = Mock(return_value=True)

    try:
        original_content = assistant.content
        handle_cursor_loop_position(assistant.id, 6)

        # P0-2: latest.content must not change
        assert assistant.content == original_content
        # Status must not change
        assert assistant.status == "complete"

        # cursor_loop state should be updated
        cl = state["cursor_loop"]
        assert cl["status"] == "streaming"
        assert cl["original_content"] == "Hello world"
        assert cl["base_content"] == "Hello "
        assert cl["preview_content"] == "Hello "
        assert cl["cursor_pos"] == 6

        # streaming_intervention should exist
        assert state["streaming_intervention"] is not None
        assert state["streaming_intervention"]["_cursor_loop"] is True
        assert state["is_generating"] is True
    finally:
        app_module.st = _orig_st
        app_module.is_intervenable = _orig_is_intervenable


def test_handle_cursor_loop_position_stream_key_format() -> None:
    """P0-5: stream_key matches React's thisStreamKey format."""
    from app import handle_cursor_loop_position
    import app as app_module

    assistant = ChatMessage(role="assistant", content="Hello world", status="complete")
    state = {
        "messages": [assistant],
        "is_generating": False,
        "last_error": None,
        "streaming_intervention": None,
        "cursor_loop": _cursor_loop_state(),
        "kw_filter": {"retry_count": 0},
        "validator": {"error": None},
    }
    st = type("st", (), {"session_state": state})()
    _orig_st = app_module.st
    app_module.st = st
    _orig_is_intervenable = app_module.is_intervenable
    app_module.is_intervenable = Mock(return_value=True)

    try:
        handle_cursor_loop_position(assistant.id, 6)

        expected_key = f"{assistant.id}:intervention:6::regenerate_from_here"
        assert state["cursor_loop"]["stream_key"] == expected_key
        assert state["streaming_intervention"]["_stream_key"] == expected_key
    finally:
        app_module.st = _orig_st
        app_module.is_intervenable = _orig_is_intervenable


# ── handle_cursor_loop_preview ──


def test_handle_cursor_loop_preview_stores_content_without_modifying_latest() -> None:
    """P0-2: preview stores content but does NOT touch latest.content."""
    from app import handle_cursor_loop_preview
    import app as app_module

    assistant = ChatMessage(role="assistant", content="Hello world", status="complete")
    state = {
        "messages": [assistant],
        "is_generating": True,
        "last_error": None,
        "streaming_intervention": {"_cursor_loop": True, "_stream_key": "test-key"},
        "cursor_loop": _cursor_loop_state() | {
            "status": "streaming",
            "original_content": "Hello world",
            "base_content": "Hello",
            "stream_key": "test-key",
        },
    }
    st = type("st", (), {"session_state": state})()
    _orig_st = app_module.st
    app_module.st = st

    try:
        handle_cursor_loop_preview("Hello beautiful world", stream_key="test-key")

        # P0-2: latest.content must not change
        assert assistant.content == "Hello world"
        assert assistant.status == "complete"

        # Preview stored separately
        assert state["cursor_loop"]["preview_content"] == "Hello beautiful world"
        assert state["cursor_loop"]["status"] == "complete"
        assert state["is_generating"] is False
    finally:
        app_module.st = _orig_st


def test_handle_cursor_loop_preview_stale_guard() -> None:
    """P0-5: stale event with mismatched stream_key is ignored."""
    from app import handle_cursor_loop_preview
    import app as app_module

    assistant = ChatMessage(role="assistant", content="Hello world", status="complete")
    state = {
        "messages": [assistant],
        "is_generating": True,
        "last_error": None,
        "streaming_intervention": {"_cursor_loop": True, "_stream_key": "new-key"},
        "cursor_loop": _cursor_loop_state() | {
            "status": "streaming",
            "original_content": "Hello world",
            "base_content": "Hello",
            "stream_key": "new-key",
        },
    }
    st = type("st", (), {"session_state": state})()
    _orig_st = app_module.st
    app_module.st = st

    try:
        # Old event with wrong key
        handle_cursor_loop_preview("stale content", stream_key="old-key")

        # Must not update preview
        assert state["cursor_loop"]["preview_content"] == ""
        assert state["cursor_loop"]["status"] == "streaming"
        assert state["is_generating"] is True
    finally:
        app_module.st = _orig_st


# ── handle_cursor_loop_error ──


def test_handle_cursor_loop_error_sets_error_status() -> None:
    """P0-4: error handler sets status=error, not complete."""
    from app import handle_cursor_loop_error
    import app as app_module

    assistant = ChatMessage(role="assistant", content="Hello world", status="complete")
    state = {
        "messages": [assistant],
        "is_generating": True,
        "last_error": None,
        "streaming_intervention": {"_cursor_loop": True, "_stream_key": "test-key"},
        "cursor_loop": _cursor_loop_state() | {
            "status": "streaming",
            "original_content": "Hello world",
            "base_content": "Hello",
            "preview_content": "Hello",
            "stream_key": "test-key",
        },
    }
    st = type("st", (), {"session_state": state})()
    _orig_st = app_module.st
    app_module.st = st

    try:
        handle_cursor_loop_error("LLM failure", content="Hello part", stream_key="test-key")

        # Must set error, not complete
        assert state["cursor_loop"]["status"] == "error"
        assert state["cursor_loop"]["error"] == "LLM failure"
        assert state["is_generating"] is False
        # preview_content may contain partial content, but status is NOT "complete"
        assert state["cursor_loop"]["status"] != "complete"
    finally:
        app_module.st = _orig_st


def test_handle_cursor_loop_error_does_not_make_preview_complete() -> None:
    """P0-4: error does NOT treat content as complete preview."""
    from app import handle_cursor_loop_error
    import app as app_module

    assistant = ChatMessage(role="assistant", content="Hello world", status="complete")
    state = {
        "messages": [assistant],
        "is_generating": True,
        "last_error": None,
        "streaming_intervention": {"_cursor_loop": True, "_stream_key": "test-key"},
        "cursor_loop": _cursor_loop_state() | {
            "status": "streaming",
            "original_content": "Hello world",
            "base_content": "Hello",
            "preview_content": "",
            "stream_key": "test-key",
        },
    }
    st = type("st", (), {"session_state": state})()
    _orig_st = app_module.st
    app_module.st = st

    try:
        handle_cursor_loop_error("Timeout", content="partial content", stream_key="test-key")

        # Apply button should NOT appear (status is error, not complete)
        assert state["cursor_loop"]["status"] == "error"
        assert state["cursor_loop"]["error"] == "Timeout"
        # is_generating is False so we don't hang
        assert state["is_generating"] is False
        # streaming_intervention is cleared
        assert state["streaming_intervention"] is None
    finally:
        app_module.st = _orig_st


def test_handle_cursor_loop_error_stale_guard() -> None:
    """P0-5: stale error event is ignored."""
    from app import handle_cursor_loop_error
    import app as app_module

    assistant = ChatMessage(role="assistant", content="Hello world", status="complete")
    state = {
        "messages": [assistant],
        "is_generating": True,
        "last_error": None,
        "streaming_intervention": {"_cursor_loop": True, "_stream_key": "new-key"},
        "cursor_loop": _cursor_loop_state() | {
            "status": "streaming",
            "original_content": "Hello world",
            "base_content": "Hello",
            "stream_key": "new-key",
        },
    }
    st = type("st", (), {"session_state": state})()
    _orig_st = app_module.st
    app_module.st = st

    try:
        handle_cursor_loop_error("Old error", content="", stream_key="old-key")

        # Must not change state
        assert state["cursor_loop"]["status"] == "streaming"
        assert state["is_generating"] is True
    finally:
        app_module.st = _orig_st
