from branch_writer.config import LlmSettings
from branch_writer.llm import (
    _chat_completions_url,
    _extract_delta_content,
)


def test_chat_completions_url_adds_v1_path() -> None:
    settings = LlmSettings(base_url="http://localhost:1234", model="model")

    assert _chat_completions_url(settings) == "http://localhost:1234/v1/chat/completions"


def test_chat_completions_url_preserves_existing_v1_path() -> None:
    settings = LlmSettings(base_url="http://localhost:1234/v1", model="model")

    assert _chat_completions_url(settings) == "http://localhost:1234/v1/chat/completions"


def test_extract_delta_content_from_streaming_delta() -> None:
    data = {"choices": [{"delta": {"content": "こ"}}]}

    assert _extract_delta_content(data) == "こ"


def test_extract_delta_content_from_empty_streaming_delta() -> None:
    data = {"choices": [{"delta": {}}]}

    assert _extract_delta_content(data) == ""



