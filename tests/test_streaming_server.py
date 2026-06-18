from branch_writer.config import LlmSettings
from branch_writer.messages import ChatMessage
from branch_writer.streaming_server import _messages_from_payload, _settings_from_payload


def test_settings_from_payload_fills_missing_fields() -> None:
    settings = _settings_from_payload(
        {
            "base_url": "http://localhost:1234/v1",
            "model": "test-model",
            "max_tokens": 1024,
        }
    )

    assert isinstance(settings, LlmSettings)
    assert settings.base_url == "http://localhost:1234/v1"
    assert settings.model == "test-model"
    assert settings.max_tokens == 1024
    assert hasattr(settings, "context_window")
    assert hasattr(settings, "request_timeout_seconds")
    assert hasattr(settings, "system_prompt")


def test_messages_from_payload_accepts_full_message_shape() -> None:
    messages = _messages_from_payload(
        [
            {
                "role": "user",
                "content": "hello",
                "id": "m1",
                "status": "complete",
                "created_at": "now",
            }
        ]
    )

    assert len(messages) == 1
    assert messages[0].id == "m1"
    assert messages[0].content == "hello"


def test_messages_from_payload_accepts_minimal_message_shape() -> None:
    messages = _messages_from_payload([{"role": "assistant", "content": "hi"}])

    assert len(messages) == 1
    assert isinstance(messages[0], ChatMessage)
    assert messages[0].role == "assistant"
    assert messages[0].content == "hi"
