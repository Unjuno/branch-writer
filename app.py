"""Branch Writer Streamlit app."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import streamlit as st

from branch_writer.config import LlmSettings, validate_llm_settings
from branch_writer.model_discovery import discover_models_sync
from branch_writer.intervention import (
    insert_and_continue,
    regenerate_from_here,
    strip_continuation_overlap,
    validate_selection_start,
)
from branch_writer.llm import (
    LlmError,
    iter_chat_response,
    iter_intervention_continuation,
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
CURSOR = "▌"

_CURSOR_CSS_INJECTED = False
_CHARS_PER_TOKEN_ESTIMATE = 4


def _inject_cursor_css() -> None:
    """Inject CSS for the streaming cursor once."""
    global _CURSOR_CSS_INJECTED
    if _CURSOR_CSS_INJECTED:
        return
    _CURSOR_CSS_INJECTED = True
    st.markdown(
        """<style>
.bw-cursor {
    animation: bw-blink 0.9s step-end infinite;
    color: var(--primary-color);
    font-weight: bold;
}
@keyframes bw-blink {
    50% { opacity: 0; }
}
</style>""",
        unsafe_allow_html=True,
    )


def _cursor_span() -> str:
    """Return an HTML span for the streaming cursor."""
    return '<span class="bw-cursor">▌</span>'


def reset_chat_state() -> None:
    """Clear chat-related state without changing LLM settings."""
    st.session_state["messages"] = []
    st.session_state["undo_stack"] = []
    st.session_state["last_error"] = None
    st.session_state["is_generating"] = False
    st.session_state["last_intervention_request_id"] = None
    st.session_state["pending_intervention"] = None
    st.session_state["insertion_log"] = []
    st.session_state["reuse_insertion"] = None
    st.session_state["streaming_generator"] = None


def estimate_tokens(text: str) -> int:
    return max(len(text) // _CHARS_PER_TOKEN_ESTIMATE, 0)


def render_context_usage() -> None:
    """Display context usage with warnings, breakdown, and per-message sizes."""
    messages: list[ChatMessage] = st.session_state["messages"]
    settings: LlmSettings = st.session_state["llm_settings"]
    ctx = settings.context_window
    max_out = settings.max_tokens

    total_chars = sum(len(m.content) for m in messages)
    input_tokens = estimate_tokens(total_chars)
    output_headroom = max_out
    total_usage = input_tokens + output_headroom
    used_ratio = total_usage / ctx if ctx > 0 else 0

    st.sidebar.divider()
    st.sidebar.caption("Model Context")

    col1, col2, col3 = st.sidebar.columns(3)
    col1.metric("Input~", f"{input_tokens:,}")
    col2.metric("Output", f"{output_headroom:,}")
    col3.metric("Limit", f"{ctx:,}")

    bar_color = "default"
    warn = ""
    if used_ratio >= 0.90:
        bar_color = "🔥"
        warn = "DANGER: Context nearly full!"
    elif used_ratio >= 0.70:
        bar_color = "⚠️"
        warn = "Warning: Context running low"

    progress_val = min(used_ratio, 1.0)
    pct = int(progress_val * 100)

    st.sidebar.progress(
        progress_val,
        text=f"{bar_color} {input_tokens:,} in + {output_headroom:,} out = {total_usage:,} / {ctx:,} ({pct}%)",
    )

    if warn:
        if "DANGER" in warn:
            st.sidebar.error(warn)
        else:
            st.sidebar.warning(warn)

    if used_ratio >= 0.70:
        st.sidebar.caption("💡 Clear chat or reduce `Max Tokens` to free up space.")


def render_sidebar() -> None:
    """Render local LLM settings."""
    settings: LlmSettings = st.session_state["llm_settings"]
    is_generating = bool(st.session_state["is_generating"])

    st.sidebar.header("LLM Settings")
    settings.base_url = st.sidebar.text_input("API Base URL", value=settings.base_url, disabled=is_generating)
    settings.api_key = st.sidebar.text_input("API Key", value=settings.api_key, type="password", disabled=is_generating)

    if settings.base_url.strip() and not is_generating and st.session_state.get("_discovered_at_url") is None:
        st.session_state["_discovered_at_url"] = settings.base_url
        with st.spinner("モデル一覧を取得中..."):
            models = discover_models_sync(settings.base_url)
            st.session_state["available_models"] = models
        st.rerun()

    if st.sidebar.button("🔄 モデル一覧を再取得", disabled=is_generating, key="discover_models_btn"):
        with st.spinner("モデル一覧を取得中..."):
            models = discover_models_sync(settings.base_url)
            st.session_state["available_models"] = models
            st.session_state["_discovered_at_url"] = settings.base_url
        st.rerun()

    available = st.session_state.get("available_models", [])
    if available:
        model_names = [m["name"] for m in available]
        current = settings.model if settings.model in model_names else model_names[0]
        selected = st.sidebar.selectbox(
            "Model",
            options=model_names,
            index=model_names.index(current),
            disabled=is_generating,
        )
        settings.model = selected
    else:
        settings.model = st.sidebar.text_input("Model", value=settings.model, disabled=is_generating)
    settings.temperature = st.sidebar.slider("Temperature", min_value=0.0, max_value=2.0, value=float(settings.temperature), step=0.1, disabled=is_generating)
    settings.max_tokens = st.sidebar.number_input("Max Tokens (output)", min_value=1, max_value=32768, value=int(settings.max_tokens), step=1, disabled=is_generating)
    settings.context_window = st.sidebar.number_input("Context Window (model limit)", min_value=512, max_value=1048576, value=int(settings.context_window), step=512, disabled=is_generating)
    settings.request_timeout_seconds = st.sidebar.number_input("Request Timeout Seconds", min_value=5, max_value=900, value=int(settings.request_timeout_seconds), step=5, disabled=is_generating)

    render_context_usage()

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
    if st.sidebar.button("Undo last intervention", disabled=is_generating or not st.session_state["undo_stack"]):
        undo_last_intervention()
        st.rerun()

    if st.sidebar.button("Clear chat", disabled=is_generating):
        reset_chat_state()
        st.rerun()

    insertion_log: list[dict[str, str]] = st.session_state.get("insertion_log", [])
    if insertion_log:
        st.sidebar.divider()
        st.sidebar.caption("Insertion Log")
        for i, entry in enumerate(insertion_log):
            text = entry["text"]
            label = text[:30] + "..." if len(text) > 30 else text
            cols = st.sidebar.columns([4, 1])
            cols[0].text(f"{i+1}. {label}")
            if cols[1].button("使用", key=f"reuse-insertion-{i}"):
                st.session_state["reuse_insertion"] = text
                st.rerun()


def render_frozen_message(message: ChatMessage) -> None:
    """Render a non-intervenable message with standard Streamlit chat UI."""
    with st.chat_message(message.role):
        content = message.content
        if message.status == "streaming" and content:
            content = content + _cursor_span()
        st.markdown(content, unsafe_allow_html=True)
        if message.status != "streaming" and content:
            tokens = estimate_tokens(content)
            st.caption(f"~{tokens:,} tokens | {len(content):,} chars")


def render_latest_assistant_message(message: ChatMessage) -> dict[str, Any] | None:
    """Render the latest assistant message and return an intervention event."""
    with st.chat_message("assistant"):
        if component_available():
            return latest_message_editor(
                message_id=message.id,
                content=message.content,
                disabled=False,
                key="latest-message-editor",
            )

        st.markdown(message.content)
        st.info(
            "Custom component is not built yet. Using manual selectionStart fallback. "
            "Build the component or set BRANCH_WRITER_COMPONENT_URL to use the React UI."
        )
        return render_manual_intervention_fallback(message)


def render_manual_intervention_fallback(message: ChatMessage) -> dict[str, Any] | None:
    """Fallback UI for intervention before the React component is built."""
    disabled = False  # Allow intervention even during generation
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

    reuse = st.session_state.pop("reuse_insertion", None)
    default_insertion = reuse if reuse else ""
    insertion = st.text_area("挿入する文", value=default_insertion, key=f"manual-insertion-{message.id}", disabled=disabled)

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


def continue_streaming() -> None:
    """Pull the next chunk from an in-progress streaming generator."""
    generator = st.session_state.get("streaming_generator")
    if generator is None:
        return

    messages: list[ChatMessage] = st.session_state["messages"]
    if not messages or messages[-1].status != "streaming":
        st.session_state["streaming_generator"] = None
        set_generating(st.session_state, False)
        return

    assistant = messages[-1]
    try:
        chunk = next(generator)
        assistant.content += chunk
    except StopIteration:
        assistant.status = "complete"
        st.session_state["streaming_generator"] = None
        set_generating(st.session_state, False)
    except LlmError as exc:
        set_error(st.session_state, str(exc))
        assistant.content = "ローカルLLMへの接続または生成に失敗しました。サイドバーの設定を確認してください。"
        assistant.status = "error"
        st.session_state["streaming_generator"] = None
        set_generating(st.session_state, False)
    except Exception as exc:
        set_error(st.session_state, f"Unexpected generation error: {type(exc).__name__}: {exc}")
        assistant.content = "予期しないエラーで生成に失敗しました。エラー表示を確認してください。"
        assistant.status = "error"
        st.session_state["streaming_generator"] = None
        set_generating(st.session_state, False)


def handle_user_prompt(prompt: str) -> None:
    """Append a user prompt and start streaming an assistant response."""
    messages: list[ChatMessage] = st.session_state["messages"]
    settings: LlmSettings = st.session_state["llm_settings"]

    append_user_message(messages, prompt)
    set_error(st.session_state, None)
    set_generating(st.session_state, True)

    append_assistant_message(messages, "", status="streaming")

    generator = iter_chat_response(messages[:-1], settings)
    st.session_state["streaming_generator"] = generator


def _event_fingerprint(event: dict[str, Any]) -> str:
    return repr((event.get("action"), event.get("messageId"), event.get("selectionStart"), event.get("selectionEnd"), event.get("insertion") or ""))


def _event_request_id(event: dict[str, Any]) -> str:
    request_id = event.get("requestId")
    if isinstance(request_id, str) and request_id:
        return request_id
    return _event_fingerprint(event)


def handle_intervention_event(event: dict[str, Any]) -> bool:
    """Apply an intervention event emitted by the latest-message editor."""
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

    # Cancel any ongoing streaming
    st.session_state["streaming_generator"] = None

    set_error(st.session_state, None)
    set_generating(st.session_state, True)

    try:
        prefix = before_content[:selection_start]
        effective_insertion = insertion if action == "insert_and_continue" else ""
        base_content = prefix + effective_insertion
        latest.content = base_content
        latest.status = "streaming"

        with st.chat_message("assistant"):
            st.caption("Streaming revised continuation")
            placeholder = st.empty()
            placeholder.markdown(base_content + _cursor_span(), unsafe_allow_html=True)
            chunks = iter_intervention_continuation(
                frozen_messages=frozen_messages_before_latest(messages),
                assistant_prefix=prefix,
                insertion=effective_insertion,
                settings=settings,
            )
            raw_continuation = ""
            clean_continuation = ""
            for chunk in chunks:
                raw_continuation += chunk
                clean_continuation = strip_continuation_overlap(base_content, raw_continuation)
                latest.content = base_content + clean_continuation
                placeholder.markdown(latest.content + _cursor_span(), unsafe_allow_html=True)
            placeholder.markdown(latest.content)

        if action == "regenerate_from_here":
            result = regenerate_from_here(before_content, selection_start, clean_continuation)
        else:
            result = insert_and_continue(before_content, selection_start, insertion, clean_continuation)

        latest.content = result.next_content
        latest.status = "complete"
        push_undo_snapshot(
            st.session_state,
            message_id=latest.id,
            before_content=before_content,
            after_content=latest.content,
            action=str(action),
        )

        if action == "insert_and_continue" and insertion:
            from datetime import datetime, timezone
            log: list[dict[str, str]] = st.session_state.setdefault("insertion_log", [])
            log.append({"text": insertion, "timestamp": datetime.now(timezone.utc).isoformat()})
    except (LlmError, TypeError, ValueError) as exc:
        latest.content = before_content
        latest.status = "complete"
        set_error(st.session_state, str(exc))
    except Exception as exc:
        latest.content = before_content
        latest.status = "complete"
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
    messages[-1].status = "complete"
    st.session_state["last_intervention_request_id"] = None
    set_error(st.session_state, None)


def main() -> None:
    st.set_page_config(page_title="Branch Writer", page_icon="✍️", layout="centered")
    initialize_state(st.session_state)
    _inject_cursor_css()

    st.title("Branch Writer")
    st.caption("チャットして、AIの返答の途中に割り込んで、書き換えて、続きを紡ぐ。")

    # Continue streaming before rendering so context usage is up-to-date
    if st.session_state["is_generating"] and st.session_state.get("streaming_generator"):
        continue_streaming()
        st.rerun()

    render_sidebar()

    last_error = st.session_state.get("last_error")
    if last_error:
        st.error(last_error)

    event = render_messages()
    if event:
        st.session_state["pending_intervention"] = event
        st.rerun()

    pending = st.session_state.pop("pending_intervention", None)
    if pending:
        handled = handle_intervention_event(pending)
        if handled:
            st.rerun()

    prompt = st.chat_input("メッセージを入力", disabled=bool(st.session_state["is_generating"]))
    if prompt:
        handle_user_prompt(prompt)
        st.rerun()


if __name__ == "__main__":
    main()
