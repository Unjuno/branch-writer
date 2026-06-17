"""Branch Writer Streamlit app."""

from __future__ import annotations

import streamlit as st

from branch_writer.config import LlmSettings, validate_llm_settings
from branch_writer.llm import LlmError, generate_chat_response
from branch_writer.messages import (
    ChatMessage,
    append_assistant_message,
    append_user_message,
    is_intervenable,
)
from branch_writer.state import initialize_state, set_error, set_generating


def render_sidebar() -> None:
    """Render local LLM settings."""
    settings: LlmSettings = st.session_state["llm_settings"]

    st.sidebar.header("LLM Settings")
    settings.base_url = st.sidebar.text_input("API Base URL", value=settings.base_url)
    settings.api_key = st.sidebar.text_input("API Key", value=settings.api_key, type="password")
    settings.model = st.sidebar.text_input("Model", value=settings.model)
    settings.temperature = st.sidebar.slider(
        "Temperature",
        min_value=0.0,
        max_value=2.0,
        value=float(settings.temperature),
        step=0.1,
    )
    settings.max_tokens = st.sidebar.number_input(
        "Max Tokens",
        min_value=1,
        max_value=8192,
        value=int(settings.max_tokens),
        step=1,
    )

    errors = validate_llm_settings(settings)
    if errors:
        st.sidebar.warning("\n".join(errors))


def render_frozen_message(message: ChatMessage) -> None:
    """Render a non-intervenable message with standard Streamlit chat UI."""
    with st.chat_message(message.role):
        st.markdown(message.content)


def render_latest_assistant_message(message: ChatMessage) -> None:
    """Render the latest assistant message.

    This function is intentionally separated so it can be replaced with the
    React/TypeScript custom component in a later milestone.
    """
    with st.chat_message("assistant"):
        st.markdown(message.content)
        st.caption("Latest assistant message — intervention UI will appear here.")


def render_messages() -> None:
    """Render chat history."""
    messages: list[ChatMessage] = st.session_state["messages"]

    for index, message in enumerate(messages):
        is_latest = index == len(messages) - 1
        if is_latest and is_intervenable(messages, message.id):
            render_latest_assistant_message(message)
        else:
            render_frozen_message(message)


def handle_user_prompt(prompt: str) -> None:
    """Append a user prompt and generate an assistant response."""
    messages: list[ChatMessage] = st.session_state["messages"]
    settings: LlmSettings = st.session_state["llm_settings"]

    append_user_message(messages, prompt)
    set_error(st.session_state, None)
    set_generating(st.session_state, True)

    try:
        response = generate_chat_response(messages, settings)
    except LlmError as exc:
        set_error(st.session_state, str(exc))
        append_assistant_message(
            messages,
            "ローカルLLMへの接続または生成に失敗しました。サイドバーの設定を確認してください。",
            status="error",
        )
    else:
        append_assistant_message(messages, response)
    finally:
        set_generating(st.session_state, False)


def main() -> None:
    st.set_page_config(page_title="Branch Writer", page_icon="✍️", layout="centered")
    initialize_state(st.session_state)

    st.title("Branch Writer")
    st.caption("普通のチャットUI。ただし、AIの最新出力だけは途中から曲げられる。")

    render_sidebar()

    last_error = st.session_state.get("last_error")
    if last_error:
        st.error(last_error)

    render_messages()

    prompt = st.chat_input("メッセージを入力")
    if prompt:
        handle_user_prompt(prompt)
        st.rerun()


if __name__ == "__main__":
    main()
