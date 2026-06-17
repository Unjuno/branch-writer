from branch_writer.messages import (
    append_assistant_message,
    append_user_message,
    is_intervenable,
)


def test_latest_assistant_is_intervenable() -> None:
    messages = []
    assistant = append_assistant_message(messages, "hello")

    assert is_intervenable(messages, assistant.id) is True


def test_past_assistant_is_not_intervenable() -> None:
    messages = []
    assistant = append_assistant_message(messages, "first")
    append_user_message(messages, "next")

    assert is_intervenable(messages, assistant.id) is False


def test_user_message_is_not_intervenable() -> None:
    messages = []
    user = append_user_message(messages, "hello")

    assert is_intervenable(messages, user.id) is False


def test_empty_history_is_not_intervenable() -> None:
    assert is_intervenable([], "missing") is False


def test_error_assistant_is_not_intervenable() -> None:
    messages = []
    assistant = append_assistant_message(messages, "failed", status="error")

    assert is_intervenable(messages, assistant.id) is False


def test_streaming_assistant_is_intervenable() -> None:
    messages = []
    assistant = append_assistant_message(messages, "streaming", status="streaming")

    assert is_intervenable(messages, assistant.id) is True
