"""Branch Writer Streamlit app."""

from __future__ import annotations

from typing import Any

import streamlit as st

from branch_writer.config import LlmSettings, validate_llm_settings
from branch_writer.intervention import insert_and_continue, regenerate_from_here
from branch_writer.llm import (
    LlmError,
    generate_chat_response,
    generate_intervention_continuation,
)
from branch_writer.messages import (
    ChatMessage,
    append_assistant_message,
    append_user_message,
    frozen_messages_before_latest,
    is_intervenable,
)
from branch_writer.state import (
    initialize_state,
    pop_undo_snapshot,
    push_undo_snapshot,
    set_error,
    set_generating,
)
from components.latest_message_editor import component_available, latest_message_editor


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

    if st.sidebar.button("Undo last intervention", disabled=not st.session_state["undo_stack"]):
        undo_last_intervention()
        st.rerun()


def render_frozen_message(message: ChatMessage) -> None:
    """Render a non-intervenable message with standard Streamlit chat UI."""
    with st.chat_message(message.role):
        st.markdown(message.content)


def render_latest_assistant_message(message: ChatMessage) -> dict[str, Any] | None:
    """Render the latest assistant message and return an intervention event."""
    with st.chat_message("assistant"):
        if component_available():
            event = latest_message_editor(
                message_id=message.id,
                content=message.content,
                disabled=st.session_state["is_generating"],
                key=f"latest-message-editor-{message.id}",
            )
            return event

        st.markdown(message.content)
        st.info(
            "Custom component is not built yet. Using manual selectionStart fallback. "
            "Build the component or set BRANCH_WRITER_COMPONENT_URL to use the React UI."
        )
        return render_manual_intervention_fallback(message)


def render_manual_intervention_fallback(message: ChatMessage) -> dict[str, Any] | None:
    """Fallback UI for intervention before the React component is built."""
    max_index = len(message.content)
    selection_start = st.number_input(
        "selectionStart",
        min_value=0,
        max_value=max_index,
        value=max_index,
        step=1,
        key=f"manual-selection-{message.id}",
    )
    insertion = st.text_area(
        "挿入する文",
        value="",
        key=f"manual-insertion-{message.id}",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("ここから再生成", key=f"manual-regenerate-{message.id}"):
            return {
                "action": "regenerate_from_here",
                "messageId": message.id,
                "selectionStart": int(selection_start),
                "selectionEnd": int(selection_start),
            }
    with col2:
        if st.button("入力して続ける", key=f"manual-insert-{message.id}"):
            return {
                "action": "insert_and_continue",
                "messageId": message.id,
                "selectionStart": int(selection_start),
                "selectionEnd": int(selection_start),
                "insertion": insertion,
            }

    return None


def render_messages() -> dict[str, Any] | None:
    """Render chat history and return the latest intervention event if any."""
    messages: list[ChatMessage] = st.session_state["messages"]
    event = None

    for index, message in enumerate(messages):
        is_latest = index == len(messages) - 1
        if is_latest and is_intervenable(messages, message.id):
            event = render_latest_assistant_message(message)
        else:
            render_frozen_message(message)

    return event


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


def handle_intervention_event(event: dict[str, Any]) -> None:
    """Apply an intervention event emitted by the latest-message editor."""
    messages: list[ChatMessage] = st.session_state["messages"]
    settings: LlmSettings = st.session_state["llm_settings"]

    if not messages:
        return

    latest = messages[-1]
    message_id = event.get("messageId")
    if not isinstance(message_id, str) or not is_intervenable(messages, message_id):
        set_error(st.session_state, "このメッセージは既に凍結されているため、介入できません。")
        return

    if latest.id != message_id:
        set_error(st.session_state, "介入対象が最新Assistantメッセージではありません。")
        return

    action = event.get("action")
    selection_start = event.get("selectionStart")
    if not isinstance(selection_start, int):
        set_error(st.session_state, "selectionStart が不正です。")
        return

    insertion = event.get("insertion") or ""
    before_content = latest.content
    set_error(st.session_state, None)
    set_generating(st.session_state, True)

    try:
        prefix = before_content[:selection_start]
        continuation = generate_intervention_continuation(
            frozen_messages=frozen_messages_before_latest(messages),
            assistant_prefix=prefix,
            insertion=insertion if action == "insert_and_continue" else "",
            settings=settings,
        )

        if action == "regenerate_from_here":
            result = regenerate_from_here(before_content, selection_start, continuation)
        elif action == "insert_and_continue":
            result = insert_and_continue(before_content, selection_start, insertion, continuation)
        else:
            set_error(st.session_state, f"未知の介入操作です: {action}")
            return

        latest.content = result.next_content
        push_undo_snapshot(
            st.session_state,
            message_id=latest.id,
            before_content=before_content,
            after_content=latest.content,
            action=str(action),
        )
    except (LlmError, TypeError, ValueError) as exc:
        set_error(st.session_state, str(exc))
    finally:
        set_generating(st.session_state, False)


def undo_last_intervention() -> None:
    """Undo the most recent latest-assistant intervention."""
    messages: list[ChatMessage] = st.session_state["messages"]
    snapshot = pop_undo_snapshot(st.session_state)

    if snapshot is None:
        return

    if not messages or messages[-1].id != snapshot.message_id:
        set_error(st.session_state, "Undo対象のメッセージが最新Assistantではありません。")
        return

    messages[-1].content = snapshot.before_content
    set_error(st.session_state, None)


def main() -> None:
    st.set_page_config(page_title="Branch Writer", page_icon="✍️", layout="centered")
    initialize_state(st.session_state)

    st.title("Branch Writer")
    st.caption("普通のチャットUI。ただし、AIの最新出力だけは途中から曲げられる。")

    render_sidebar()

    last_error = st.session_state.get("last_error")
    if last_error:
        st.error(last_error)

    event = render_messages()
    if event:
        handle_intervention_event(event)
        st.rerun()

    prompt = st.chat_input("メッセージを入力")
    if prompt:
        handle_user_prompt(prompt)
        st.rerun()


if __name__ == "__main__":
    main()
