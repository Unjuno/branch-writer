"""Branch Writer Streamlit app."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import streamlit as st

from branch_writer.config import LlmSettings, validate_llm_settings
from branch_writer.intervention import (
    insert_and_continue,
    regenerate_from_here,
    validate_selection_start,
)
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

VALID_INTERVENTION_ACTIONS = {"regenerate_from_here", "insert_and_continue"}
DEFAULT_RENDER_MESSAGE_LIMIT = 80
MIN_RENDER_MESSAGE_LIMIT = 10
MAX_RENDER_MESSAGE_LIMIT = 500


def reset_chat_state() -> None:
    """Clear chat-related state without changing LLM settings."""
    st.session_state["messages"] = []
    st.session_state["undo_stack"] = []
    st.session_state["last_error"] = None
    st.session_state["is_generating"] = False
    st.session_state["last_intervention_request_id"] = None


def render_sidebar() -> None:
    """Render local LLM settings."""
    settings: LlmSettings = st.session_state["llm_settings"]
    is_generating = bool(st.session_state["is_generating"])

    st.sidebar.header("LLM Settings")
    settings.base_url = st.sidebar.text_input(
        "API Base URL",
        value=settings.base_url,
        disabled=is_generating,
    )
    settings.api_key = st.sidebar.text_input(
        "API Key",
        value=settings.api_key,
        type="password",
        disabled=is_generating,
    )
    settings.model = st.sidebar.text_input(
        "Model",
        value=settings.model,
        disabled=is_generating,
    )
    settings.temperature = st.sidebar.slider(
        "Temperature",
        min_value=0.0,
        max_value=2.0,
        value=float(settings.temperature),
        step=0.1,
        disabled=is_generating,
    )
    settings.max_tokens = st.sidebar.number_input(
        "Max Tokens",
        min_value=1,
        max_value=32768,
        value=int(settings.max_tokens),
        step=1,
        disabled=is_generating,
    )
    settings.request_timeout_seconds = st.sidebar.number_input(
        "Request Timeout Seconds",
        min_value=5,
        max_value=900,
        value=int(settings.request_timeout_seconds),
        step=5,
        disabled=is_generating,
    )

    st.sidebar.divider()
    st.session_state["render_message_limit"] = st.sidebar.number_input(
        "Rendered message limit",
        min_value=MIN_RENDER_MESSAGE_LIMIT,
        max_value=MAX_RENDER_MESSAGE_LIMIT,
        value=int(st.session_state.get("render_message_limit", DEFAULT_RENDER_MESSAGE_LIMIT)),
        step=10,
        disabled=is_generating,
    )

    errors = validate_llm_settings(settings)
    if errors:
        st.sidebar.warning("\n".join(errors))

    st.sidebar.divider()
    if st.sidebar.button(
        "Undo last intervention",
        disabled=is_generating or not st.session_state["undo_stack"],
    ):
        undo_last_intervention()
        st.rerun()

    if st.sidebar.button("Clear chat", disabled=is_generating):
        reset_chat_state()
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
    disabled = bool(st.session_state["is_generating"])
    max_index = len(message.content)
    selection_start = st.number_input(
        "selectionStart",
        min_value=0,
        max_value=max_index,
        value=max_index,
        step=1,
        key=f"manual-selection-{message.id}",
        disabled=disabled,
    )
    insertion = st.text_area(
        "挿入する文",
        value="",
        key=f"manual-insertion-{message.id}",
        disabled=disabled,
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("ここから再生成", key=f"manual-regenerate-{message.id}", disabled=disabled):
            return {
                "requestId": str(uuid4()),
                "action": "regenerate_from_here",
                "messageId": message.id,
                "selectionStart": int(selection_start),
                "selectionEnd": int(selection_start),
            }
    with col2:
        if st.button("入力して続ける", key=f"manual-insert-{message.id}", disabled=disabled):
            return {
                "requestId": str(uuid4()),
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
    limit = int(st.session_state.get("render_message_limit", DEFAULT_RENDER_MESSAGE_LIMIT))
    hidden_count = max(0, len(messages) - limit)
    visible_messages = messages[-limit:]

    if hidden_count:
        st.caption(f"Older messages hidden for performance: {hidden_count}")

    for index, message in enumerate(visible_messages):
        original_index = hidden_count + index
        is_latest = original_index == len(messages) - 1
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
    except Exception as exc:  # pragma: no cover - defensive Streamlit guard
        set_error(st.session_state, f"Unexpected generation error: {type(exc).__name__}: {exc}")
        append_assistant_message(
            messages,
            "予期しないエラーで生成に失敗しました。エラー表示を確認してください。",
            status="error",
        )
    else:
        append_assistant_message(messages, response)
    finally:
        set_generating(st.session_state, False)


def _event_fingerprint(event: dict[str, Any]) -> str:
    return repr(
        (
            event.get("action"),
            event.get("messageId"),
            event.get("selectionStart"),
            event.get("selectionEnd"),
            event.get("insertion") or "",
        )
    )


def _event_request_id(event: dict[str, Any]) -> str:
    request_id = event.get("requestId")
    if isinstance(request_id, str) and request_id:
        return request_id
    return _event_fingerprint(event)


def handle_intervention_event(event: dict[str, Any]) -> bool:
    """Apply an intervention event emitted by the latest-message editor.

    Returns True only when a new event was actually processed. Streamlit
    components keep returning their last value across reruns, so duplicate
    events must be ignored without triggering another rerun.
    """
    if st.session_state["is_generating"]:
        return False

    request_id = _event_request_id(event)
    if st.session_state.get("last_intervention_request_id") == request_id:
        return False

    st.session_state["last_intervention_request_id"] = request_id

    messages: list[ChatMessage] = st.session_state["messages"]
    settings: LlmSettings = st.session_state["llm_settings"]

    if not messages:
        return False

    latest = messages[-1]
    message_id = event.get("messageId")
    if not isinstance(message_id, str) or not is_intervenable(messages, message_id):
        set_error(st.session_state, "このメッセージは既に凍結されているため、介入できません。")
        return True

    if latest.id != message_id:
        set_error(st.session_state, "介入対象が最新Assistantメッセージではありません。")
        return True

    action = event.get("action")
    if action not in VALID_INTERVENTION_ACTIONS:
        set_error(st.session_state, f"未知の介入操作です: {action}")
        return True

    selection_start = event.get("selectionStart")
    if not isinstance(selection_start, int):
        set_error(st.session_state, "selectionStart が不正です。")
        return True

    insertion = event.get("insertion") or ""
    before_content = latest.content

    try:
        validate_selection_start(before_content, selection_start)
    except (TypeError, ValueError) as exc:
        set_error(st.session_state, str(exc))
        return True

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
        else:
            result = insert_and_continue(before_content, selection_start, insertion, continuation)

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
    except Exception as exc:  # pragma: no cover - defensive Streamlit guard
        set_error(st.session_state, f"Unexpected intervention error: {type(exc).__name__}: {exc}")
    finally:
        set_generating(st.session_state, False)

    return True


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
    st.session_state["last_intervention_request_id"] = None
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
        processed = handle_intervention_event(event)
        if processed:
            st.rerun()

    prompt = st.chat_input("メッセージを入力", disabled=bool(st.session_state["is_generating"]))
    if prompt:
        with st.spinner("Generating..."):
            handle_user_prompt(prompt)
        st.rerun()


if __name__ == "__main__":
    main()
