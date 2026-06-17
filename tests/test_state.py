from branch_writer.config import LlmSettings
from branch_writer.messages import ChatMessage
from branch_writer.state import (
    get_llm_settings,
    get_messages,
    initialize_state,
    pop_undo_snapshot,
    push_undo_snapshot,
    set_error,
    set_generating,
)


def test_initialize_state_sets_defaults() -> None:
    state = {}

    initialize_state(state)

    assert state["messages"] == []
    assert isinstance(state["llm_settings"], LlmSettings)
    assert state["undo_stack"] == []
    assert state["is_generating"] is False
    assert state["last_error"] is None


def test_initialize_state_preserves_existing_values() -> None:
    message = ChatMessage(role="user", content="hello")
    settings = LlmSettings(model="model")
    state = {
        "messages": [message],
        "llm_settings": settings,
        "undo_stack": ["existing"],
        "is_generating": True,
        "last_error": "error",
    }

    initialize_state(state)

    assert state["messages"] == [message]
    assert state["llm_settings"] is settings
    assert state["undo_stack"] == ["existing"]
    assert state["is_generating"] is True
    assert state["last_error"] == "error"


def test_get_messages_initializes_state() -> None:
    state = {}

    messages = get_messages(state)

    assert messages == []
    assert state["messages"] is messages


def test_get_llm_settings_initializes_state() -> None:
    state = {}

    settings = get_llm_settings(state)

    assert isinstance(settings, LlmSettings)
    assert state["llm_settings"] is settings


def test_push_and_pop_undo_snapshot() -> None:
    state = {}

    snapshot = push_undo_snapshot(
        state,
        message_id="message-1",
        before_content="before",
        after_content="after",
        action="regenerate_from_here",
    )

    assert state["undo_stack"] == [snapshot]
    assert snapshot.message_id == "message-1"
    assert snapshot.before_content == "before"
    assert snapshot.after_content == "after"
    assert snapshot.action == "regenerate_from_here"

    popped = pop_undo_snapshot(state)

    assert popped == snapshot
    assert state["undo_stack"] == []


def test_pop_empty_undo_stack_returns_none() -> None:
    state = {}

    assert pop_undo_snapshot(state) is None


def test_set_error() -> None:
    state = {}

    set_error(state, "failed")

    assert state["last_error"] == "failed"


def test_set_generating() -> None:
    state = {}

    set_generating(state, True)

    assert state["is_generating"] is True
