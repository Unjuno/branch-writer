from branch_writer.config import (
    DEFAULT_BASE_URL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    LlmSettings,
    default_llm_settings,
    normalize_openai_base_url,
    validate_llm_settings,
)


def test_default_llm_settings() -> None:
    settings = default_llm_settings()

    assert settings.base_url == DEFAULT_BASE_URL
    assert settings.temperature == DEFAULT_TEMPERATURE
    assert settings.max_tokens == DEFAULT_MAX_TOKENS
    assert settings.max_tokens == 4096


def test_empty_base_url_is_invalid() -> None:
    settings = LlmSettings(base_url="", model="model")

    assert "API Base URL is required" in validate_llm_settings(settings)


def test_empty_model_is_invalid() -> None:
    settings = LlmSettings(model="")

    assert "Model is required" in validate_llm_settings(settings)


def test_temperature_too_low_is_invalid() -> None:
    settings = LlmSettings(model="model", temperature=-0.1)

    assert any("Temperature must be between" in error for error in validate_llm_settings(settings))


def test_temperature_too_high_is_invalid() -> None:
    settings = LlmSettings(model="model", temperature=2.1)

    assert any("Temperature must be between" in error for error in validate_llm_settings(settings))


def test_max_tokens_less_than_one_is_invalid() -> None:
    settings = LlmSettings(model="model", max_tokens=0)

    assert "Max Tokens must be greater than or equal to 1" in validate_llm_settings(settings)


def test_valid_settings_have_no_errors() -> None:
    settings = LlmSettings(
        base_url="http://localhost:11434/v1",
        api_key="",
        model="local-model",
        temperature=0.7,
        max_tokens=4096,
    )

    assert validate_llm_settings(settings) == []


def test_normalize_openai_base_url_adds_v1_for_server_root() -> None:
    assert normalize_openai_base_url("http://localhost:1234") == "http://localhost:1234/v1"


def test_normalize_openai_base_url_preserves_existing_v1_path() -> None:
    assert normalize_openai_base_url("http://localhost:1234/v1") == "http://localhost:1234/v1"


def test_normalize_openai_base_url_trims_trailing_slash() -> None:
    assert normalize_openai_base_url("http://localhost:1234/") == "http://localhost:1234/v1"


def test_normalize_openai_base_url_preserves_custom_path() -> None:
    assert normalize_openai_base_url("http://localhost:1234/api") == "http://localhost:1234/api"
