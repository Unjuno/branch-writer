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


class LegacySettings:
    def __init__(self) -> None:
        self.base_url = "http://localhost:1234/v1"
        self.api_key = ""
        self.model = "legacy-model"
        self.temperature = 0.4
        self.max_tokens = 1024


def test_initialize_state_sets_defaults() -> None:
    state = {}

    initialize_state(state)

    assert state["messages"] == []
    assert isinstance(state["llm_settings"], LlmSettings)
    assert state["undo_stack"] == []
    assert state["is_generating"] is False
    assert state["last_error"] is None
    assert state["last_intervention_request_id"] is None
    assert state["render_message_limit"] == 80
    assert state["available_models"] == []
    assert state["insertion_log"] == []
    assert state["reuse_insertion"] is None
    assert state["streaming_intervention"] is None
    assert state["kw_filter"]["enabled"] is True
    assert state["validator"]["enabled"] is False


def test_initialize_state_migrates_legacy_llm_settings() -> None:
    state = {"llm_settings": LegacySettings()}

    initialize_state(state)

    settings = state["llm_settings"]
    assert isinstance(settings, LlmSettings)
    assert settings.base_url == "http://localhost:1234/v1"
    assert settings.model == "legacy-model"
    assert settings.temperature == 0.4
    assert settings.max_tokens == 1024
    assert hasattr(settings, "context_window")
    assert hasattr(settings, "request_timeout_seconds")
    assert hasattr(settings, "system_prompt")


def test_initialize_state_preserves_existing_values() -> None:
    message = ChatMessage(role="user", content="hello")
    settings = LlmSettings(model="model")
    state = {
        "messages": [message],
        "llm_settings": settings,
        "undo_stack": ["existing"],
        "is_generating": True,
        "last_error": "error",
        "last_intervention_request_id": "request-1",
        "render_message_limit": 120,
    }

    initialize_state(state)

    assert state["messages"] == [message]
    assert state["llm_settings"] is settings
    assert state["undo_stack"] == ["existing"]
    assert state["is_generating"] is True
    assert state["last_error"] == "error"
    assert state["last_intervention_request_id"] == "request-1"
    assert state["render_message_limit"] == 120


def test_initialize_state_repairs_partial_nested_dicts() -> None:
    state = {
        "kw_filter": {"enabled": False},
        "validator": {"prompt": "check {text}"},
    }

    initialize_state(state)

    assert state["kw_filter"]["enabled"] is False
    assert state["kw_filter"]["words"] == ""
    assert state["kw_filter"]["max_retries"] == 5
    assert state["kw_filter"]["retry_count"] == 0
    assert state["validator"]["prompt"] == "check {text}"
    assert state["validator"]["enabled"] is False
    assert state["validator"]["results"] is None
    assert state["validator"]["error"] is None


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
