import pytest

from branch_writer.config import LlmSettings
from branch_writer.llm import LlmError, _chat_completions_url, _extract_content


def test_chat_completions_url_adds_v1_path() -> None:
    settings = LlmSettings(base_url="http://localhost:1234", model="model")

    assert _chat_completions_url(settings) == "http://localhost:1234/v1/chat/completions"


def test_chat_completions_url_preserves_existing_v1_path() -> None:
    settings = LlmSettings(base_url="http://localhost:1234/v1", model="model")

    assert _chat_completions_url(settings) == "http://localhost:1234/v1/chat/completions"


def test_extract_content_from_openai_compatible_response() -> None:
    data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "こんにちは。",
                }
            }
        ]
    }

    assert _extract_content(data) == "こんにちは。"


def test_extract_content_from_text_choice_response() -> None:
    data = {"choices": [{"text": "fallback text"}]}

    assert _extract_content(data) == "fallback text"


def test_extract_content_raises_with_raw_response_when_no_choices() -> None:
    with pytest.raises(LlmError, match="LLM returned no choices"):
        _extract_content({"choices": []})


def test_extract_content_raises_with_raw_choice_when_no_content() -> None:
    with pytest.raises(LlmError, match="LLM returned no message content"):
        _extract_content({"choices": [{"message": {"role": "assistant"}}]})
