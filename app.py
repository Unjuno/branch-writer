"""Branch Writer の Streamlit アプリ。"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Any
from uuid import uuid4

import streamlit as st

from branch_writer.config import (
    LlmSettings,
    lookup_model_capabilities,
    validate_llm_settings,
)
from branch_writer.intervention import (
    validate_selection_start,
)
from branch_writer.llm import (
    generate_text,
)
from branch_writer.messages import (
    ChatMessage,
    append_assistant_message,
    append_user_message,
    frozen_messages_before_latest,
    is_intervenable,
)
from branch_writer.model_discovery import discover_models_sync
from branch_writer.state import (
    initialize_state,
    pop_undo_snapshot,
    push_undo_snapshot,
    set_error,
    set_generating,
)
from branch_writer.streaming_server import start_server
from components.latest_message_editor import component_available, latest_message_editor

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)

# RotatingFileHandler で branch_writer.log の肥大化を防止（最大5MB, 3世代）
# 読み取り専用環境では失敗しても無視する。rerunによる重複追加も防止する。
if not any(isinstance(h, RotatingFileHandler) for h in logging.getLogger().handlers):
    try:
        _file_handler = RotatingFileHandler("branch_writer.log", encoding="utf-8", maxBytes=5 * 1024 * 1024, backupCount=3)
        _file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        logging.getLogger().addHandler(_file_handler)
    except (OSError, PermissionError):
        pass

logger = logging.getLogger("branch_writer.app")

_STREAMING_PORT = 8765
_STREAMING_URL = f"http://127.0.0.1:{_STREAMING_PORT}"

VALID_INTERVENTION_ACTIONS = {"regenerate_from_here", "insert_and_continue"}
DEFAULT_RENDER_MESSAGE_LIMIT = 80
MIN_RENDER_MESSAGE_LIMIT = 10
MAX_RENDER_MESSAGE_LIMIT = 500

_CHARS_PER_TOKEN_ESTIMATE = 4

_DEFAULT_ENDPOINTS = [
    "http://localhost:11434/v1",   # Ollama
    "http://localhost:1234/v1",    # LM Studio
]


def _inject_custom_css() -> None:
    if st.session_state.get("_custom_css_injected"):
        return
    st.session_state["_custom_css_injected"] = True
    st.markdown(
        """<style>
@keyframes bw-blink {
    50% { opacity: 0; }
}

.bw-thinking {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 4px 14px;
    border-radius: 20px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    font-size: 0.9rem;
    font-weight: 600;
    box-shadow: 0 2px 8px rgba(102,126,234,0.4);
}
.bw-thinking::after {
    content: "";
    width: 8px;
    height: 8px;
    margin-left: 4px;
    border-radius: 50%;
    background: white;
    animation: bw-dot 1.2s ease-in-out infinite;
}
@keyframes bw-dot {
    0%, 100% { opacity: 0.3; transform: scale(0.8); }
    50% { opacity: 1; transform: scale(1.2); }
}

.bw-cursor {
    animation: bw-blink 0.9s step-end infinite;
    color: var(--primary-color);
    font-weight: bold;
    font-size: 1.1em;
}

[data-testid="stSidebar"] {
    min-width: 480px !important;
    max-width: 720px !important;
}
</style>""",
        unsafe_allow_html=True,
    )


def _cursor_span() -> str:
    return '<span class="bw-cursor">▌</span>'


def _probe_base_url(url: str) -> str:
    if url.strip():
        logger.debug("_probe_base_url: already set, returning %s", url)
        return url
    import httpx
    for candidate in _DEFAULT_ENDPOINTS:
        try:
            resp = httpx.get(f"{candidate.removesuffix('/v1')}/api/tags", timeout=2)
            if resp.status_code < 500:
                logger.info("_probe_base_url: found Ollama at %s", candidate)
                return candidate
        except Exception:
            try:
                resp = httpx.get(f"{candidate}/models", timeout=2)
                if resp.status_code < 500:
                    logger.info("_probe_base_url: found OpenAI-compat at %s", candidate)
                    return candidate
            except Exception:
                continue
    logger.warning("_probe_base_url: no endpoint found")
    return url


def estimate_tokens(text: str | int) -> int:
    char_count = len(text) if isinstance(text, str) else text
    return max(char_count // _CHARS_PER_TOKEN_ESTIMATE, 0)


def render_context_usage() -> None:
    messages: list[ChatMessage] = st.session_state["messages"]
    settings: LlmSettings = st.session_state["llm_settings"]
    ctx = settings.context_window
    max_out = settings.max_tokens

    if not messages:
        return

    total_chars = sum(len(m.content) for m in messages)
    input_tokens = estimate_tokens(total_chars)
    output_headroom = max_out
    total_usage = input_tokens + output_headroom
    used_ratio = total_usage / ctx if ctx > 0 else 0

    st.sidebar.divider()
    st.sidebar.caption("モデルコンテキスト")

    col1, col2, col3 = st.sidebar.columns(3)
    col1.metric("入力~", f"{input_tokens:,}")
    col2.metric("出力枠", f"{output_headroom:,}")
    col3.metric("上限", f"{ctx:,}")

    bar_color = ""
    warn = ""
    if used_ratio >= 0.90:
        bar_color = "🔥 "
        warn = "危険: コンテキストがほぼ一杯です！"
    elif used_ratio >= 0.70:
        bar_color = "⚠️ "
        warn = "警告: コンテキスト残りわずか"

    progress_val = min(used_ratio, 1.0)
    pct = int(progress_val * 100)

    st.sidebar.progress(
        progress_val,
        text=f"{bar_color}{input_tokens:,} in + {output_headroom:,} out = {total_usage:,} / {ctx:,} ({pct}%)",
    )

    if warn:
        if "危険" in warn:
            st.sidebar.error(warn)
        else:
            st.sidebar.warning(warn)

    if used_ratio >= 0.70:
        st.sidebar.caption("💡 チャットをクリアするか、Max Tokens を減らして空きを確保してください。")


def render_sidebar() -> None:
    settings: LlmSettings = st.session_state["llm_settings"]
    is_generating = bool(st.session_state["is_generating"])

    st.sidebar.header("LLM 設定")
    placeholder = "自動 (Ollama / LM Studio)"
    settings.base_url = st.sidebar.text_input(
        "API ベースURL",
        value=settings.base_url,
        placeholder=placeholder,
        disabled=is_generating,
    )
    settings.api_key = st.sidebar.text_input(
        "API キー", value=settings.api_key, type="password", disabled=is_generating
    )

    settings.system_prompt = st.sidebar.text_area(
        "システムプロンプト",
        value=settings.system_prompt,
        placeholder="創作のテーマや作風を指定（例: 三人称、現代日本を舞台にした探偵小説）",
        disabled=is_generating,
        key="system_prompt_input",
    )

    if st.sidebar.button("🔄 モデル一覧を再取得", disabled=is_generating, key="discover_models_btn"):
        with st.spinner("モデル一覧を取得中..."):
            resolved = _probe_base_url(settings.base_url)
            if resolved and resolved != settings.base_url:
                settings.base_url = resolved
            models = discover_models_sync(settings.base_url)
            st.session_state["available_models"] = models
        st.rerun()

    available = st.session_state.get("available_models", [])
    if available:
        model_names = [m["name"] for m in available]
        current = settings.model if settings.model in model_names else model_names[0]
        selected = st.sidebar.selectbox(
            "モデル",
            options=model_names,
            index=model_names.index(current),
            disabled=is_generating,
        )
        if selected != settings.model:
            settings.model = selected
            ctx, out = lookup_model_capabilities(selected)
            settings.context_window = ctx
            settings.max_tokens = out
        else:
            settings.model = selected
    else:
        prev = settings.model
        settings.model = st.sidebar.text_input("モデル名", value=settings.model, disabled=is_generating)
        if settings.model != prev:
            ctx, out = lookup_model_capabilities(settings.model)
            settings.context_window = ctx
            settings.max_tokens = out
    settings.temperature = st.sidebar.slider(
        "温度 (Temperature)", min_value=0.0, max_value=2.0,
        value=float(settings.temperature), step=0.1, disabled=is_generating,
    )

    # context_window のみ表示し、max_tokens は自動計算する
    settings.context_window = st.sidebar.number_input(
        "コンテキストウィンドウ",
        min_value=512,
        max_value=1048576,
        value=int(settings.context_window),
        step=512,
        disabled=is_generating,
    )
    derived = min(int(settings.context_window * 0.5), 16384)
    if settings.max_tokens != derived:
        settings.max_tokens = derived
    st.sidebar.caption(f"出力トークン上限: {settings.max_tokens:,}（コンテキストの約50%）")
    settings.request_timeout_seconds = st.sidebar.number_input(
        "リクエストタイムアウト（秒）",
        min_value=5,
        max_value=900,
        value=int(settings.request_timeout_seconds),
        step=5,
        disabled=is_generating,
    )

    render_context_usage()

    st.sidebar.divider()
    st.session_state["render_message_limit"] = st.sidebar.number_input(
        "表示メッセージ数",
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
    if st.sidebar.button("直前の介入を取り消す", disabled=is_generating or not st.session_state["undo_stack"]):
        undo_last_intervention()
        st.rerun()

    if st.sidebar.button("チャットをクリア", disabled=is_generating):
        reset_chat_state()
        st.rerun()

    insertion_log: list[dict[str, str]] = st.session_state.get("insertion_log", [])
    if insertion_log:
        st.sidebar.divider()
        st.sidebar.caption("挿入履歴")
        for i, entry in enumerate(insertion_log):
            text = entry["text"]
            label = text[:30] + "..." if len(text) > 30 else text
            cols = st.sidebar.columns([4, 1])
            cols[0].text(f"{i+1}. {label}")
            if cols[1].button("再利用", key=f"reuse-insertion-{i}"):
                st.session_state["reuse_insertion"] = text
                st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown("---")
    render_validator_panel()


def reset_chat_state() -> None:
    logger.info("reset_chat_state: clearing all session state")
    st.session_state["messages"] = []
    st.session_state["undo_stack"] = []
    st.session_state["last_error"] = None
    st.session_state["is_generating"] = False
    st.session_state["last_intervention_request_id"] = None
    st.session_state["insertion_log"] = []
    st.session_state["reuse_insertion"] = None
    st.session_state["streaming_intervention"] = None
    st.session_state["cursor_loop"] = {
        "enabled": False,
        "message_id": None,
        "original_content": "",
        "base_content": "",
        "cursor_pos": None,
        "preview_content": "",
        "status": "idle",
        "stream_key": None,
        "error": None,
    }
    st.session_state["available_models"] = []
    st.session_state["kw_filter"]["retry_count"] = 0
    st.session_state["validator"]["error"] = None
    st.session_state["kw_filter"]["enabled"] = True
    st.session_state["kw_filter"]["words"] = ""
    st.session_state["kw_filter"]["max_retries"] = 5
    st.session_state["validator"]["results"] = None


def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_frozen_message(message: ChatMessage) -> None:
    with st.chat_message(message.role):
        st.markdown(_escape_html(message.content), unsafe_allow_html=False)
        if message.content:
            tokens = estimate_tokens(message.content)
            st.caption(f"~{tokens:,} tokens | {len(message.content):,} chars")


def render_intervention_panel() -> dict[str, Any] | None:
    messages: list[ChatMessage] = st.session_state["messages"]
    if not messages:
        return None
    latest = messages[-1]
    if not is_intervenable(messages, latest.id):
        return None

    st.divider()
    st.caption("✂️ 介入 — スライダーで位置を選んで書き換え")

    max_index = len(latest.content)
    selection_start = st.slider(
        "介入位置",
        min_value=0,
        max_value=max_index,
        value=max_index,
        key=f"intervention-slider-{latest.id}",
    )

    suffix = latest.content[selection_start:]
    if suffix:
        short = suffix[:120].replace("\n", "↵")
        st.caption(f"削除される部分（{len(suffix)}字）: {short}{'...' if len(suffix) > 120 else ''}")

    reuse = st.session_state.pop("reuse_insertion", None)
    default_insertion = reuse if reuse else ""
    insertion = st.text_area("挿入する文", value=default_insertion, key=f"intervention-insertion-{latest.id}")

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        if st.button("ここから再生成", key=f"intervention-regenerate-{latest.id}"):
            return {
                "requestId": str(uuid4()),
                "action": "regenerate_from_here",
                "messageId": latest.id,
                "selectionStart": int(selection_start),
                "selectionEnd": int(selection_start),
            }
    with btn_col2:
        if st.button("入力して続ける", key=f"intervention-insert-{latest.id}"):
            return {
                "requestId": str(uuid4()),
                "action": "insert_and_continue",
                "messageId": latest.id,
                "selectionStart": int(selection_start),
                "selectionEnd": int(selection_start),
                "insertion": insertion,
            }

    return None


def render_messages() -> None:
    messages: list[ChatMessage] = st.session_state["messages"]
    limit = int(st.session_state.get("render_message_limit", DEFAULT_RENDER_MESSAGE_LIMIT))
    hidden_count = max(0, len(messages) - limit)
    visible_messages = messages[-limit:]

    if hidden_count:
        st.caption(f"パフォーマンスのため古いメッセージ{hidden_count}件を非表示")

    # Prepare messages for streaming (exclude the last assistant message being generated)
    settings: LlmSettings = st.session_state["llm_settings"]
    messages_for_stream = []
    if messages and messages[-1].role == "assistant" and messages[-1].status == "streaming":
        # During generation, send all messages except the streaming one
        messages_for_stream = [
            {"role": m.role, "content": m.content, "id": m.id}
            for m in messages[:-1]
        ]
    else:
        messages_for_stream = [
            {"role": m.role, "content": m.content, "id": m.id}
            for m in messages
        ]

    llm_settings_dict = {
        "base_url": settings.base_url,
        "api_key": settings.api_key,
        "model": settings.model,
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
        "system_prompt": settings.system_prompt,
        "request_timeout_seconds": settings.request_timeout_seconds,
        "context_window": settings.context_window,
    }

    for index, message in enumerate(visible_messages):
        is_latest_intervenable = is_intervenable(messages, message.id)

        if is_latest_intervenable and component_available():
            in_intervention = st.session_state.get("streaming_intervention") is not None
            generating = bool(st.session_state["is_generating"])

            intervention_data = None
            if in_intervention:
                intervention_state = st.session_state.get("streaming_intervention", {})
                if intervention_state:
                    frozen = intervention_state.get("frozen_messages", [])
                    intervention_data = {
                        "frozenMessages": [
                            {"role": m.role, "content": m.content, "id": m.id}
                            for m in frozen
                        ],
                        "baseContent": intervention_state.get("base_content", ""),
                        "assistantPrefix": intervention_state.get("assistant_prefix", ""),
                        "insertion": intervention_state.get("insertion", ""),
                        "action": intervention_state.get("action", "regenerate_from_here"),
                        "beforeContent": intervention_state.get("before_content", ""),
                        "selectionStart": intervention_state.get("selection_start", 0),
                        "streamKey": intervention_state.get("stream_key", ""),
                    }

            # Componentは常に描画
            with st.chat_message("assistant"):
                logger.info("render_messages: editor msg=%s, streaming=%s, has_intervention=%s",
                            message.id, generating, intervention_data is not None)
                event = latest_message_editor(
                    message_id=message.id,
                    content=message.content,
                    disabled=False,
                    streaming_url=_STREAMING_URL,
                    is_streaming=generating,
                    intervention_data=intervention_data,
                    cursor_loop_enabled=False,
                    preview_content="",
                    messages_for_stream=messages_for_stream,
                    llm_settings=llm_settings_dict,
                    key=f"editor-{message.id}",
                )
                if event:
                    event_type = event.get("type")
                    if event_type == "streaming_done":
                        if not st.session_state.get("is_generating", False):
                            logger.debug("render_messages: stale streaming_done, skipping")
                        else:
                            intervention_state = st.session_state.get("streaming_intervention")
                            if intervention_state and intervention_state.get("_cursor_loop"):
                                handle_cursor_loop_preview(
                                    event.get("content", ""),
                                    stream_key=event.get("streamKey", ""),
                                )
                                st.session_state.pop(f"editor-{message.id}", None)
                                st.rerun()
                            else:
                                intervention_before = st.session_state.get("streaming_intervention")
                                retried = handle_streaming_complete(event)
                                st.session_state.pop(f"editor-{message.id}", None)
                                if retried or intervention_before is not None:
                                    logger.info(
                                        "render_messages: rerun after streaming_done "
                                        "(retried=%s, had_intervention=%s)",
                                        retried,
                                        intervention_before is not None,
                                    )
                                    st.rerun()
                    elif event_type == "streaming_error":
                        logger.error("render_messages: streaming_error: %s", event.get("message"))
                        if not st.session_state.get("is_generating", False):
                            logger.debug("render_messages: stale streaming_error, skipping")
                        else:
                            intervention_state = st.session_state.get("streaming_intervention")
                            if intervention_state and intervention_state.get("_cursor_loop"):
                                handle_cursor_loop_error(
                                    event.get("message", "Unknown streaming error"),
                                    content=event.get("content", ""),
                                    stream_key=event.get("streamKey", ""),
                                )
                                st.rerun()
                            else:
                                handle_streaming_error(event)
                                st.rerun()
                    elif event_type == "inline_continue":
                        if not generating:
                            sel = int(event.get("selectionStart", 0))
                            insertion = str(event.get("insertion", ""))
                            action = "insert_and_continue" if insertion else "regenerate_from_here"
                            st.session_state["_intervention_event"] = {
                                "requestId": event.get("requestId") or f"{message.id}:inline:{sel}:{__import__('time').time()}",
                                "action": action,
                                "messageId": message.id,
                                "selectionStart": sel,
                                "selectionEnd": sel,
                                "insertion": insertion,
                            }
                            st.rerun()
                    elif event_type == "inline_continue_interrupt":
                        sel = int(event.get("selectionStart", 0))
                        current_content = str(event.get("currentContent", ""))
                        insertion = str(event.get("insertion", ""))
                        action = "insert_and_continue" if insertion else "regenerate_from_here"
                        if not current_content:
                            logger.warning("render_messages: inline_continue_interrupt with empty currentContent")
                        else:
                            messages_list: list[ChatMessage] = st.session_state["messages"]
                            if messages_list:
                                latest_msg = messages_list[-1]
                                if latest_msg.id == message.id:
                                    latest_msg.content = current_content
                                    latest_msg.status = "streaming"
                            st.session_state["_intervention_event"] = {
                                "requestId": event.get("requestId") or f"{message.id}:interrupt:{sel}:{__import__('time').time()}",
                                "action": action,
                                "messageId": message.id,
                                "selectionStart": sel,
                                "selectionEnd": sel,
                                "insertion": insertion,
                            }
                            st.rerun()
        elif message.role == "assistant" and message.status == "streaming":
            with st.chat_message("assistant"):
                content = _escape_html(message.content)
                if content:
                    content = content + _cursor_span()
                st.markdown(content, unsafe_allow_html=True)
        else:
            render_frozen_message(message)


def _finalize_intervention(state: dict[str, Any]) -> None:
    """Finalize an intervention after streaming completes.

    latest.content already contains the full streamed content set by
    handle_streaming_complete. We only push an undo snapshot and log.
    """
    logger.info("_finalize_intervention: action=%s, selection_start=%d", state["action"], state["selection_start"])
    messages: list[ChatMessage] = st.session_state["messages"]
    if not messages:
        return
    latest = messages[-1]

    before_content = state["before_content"]
    insertion = state["insertion"]
    action = state["action"]

    after_content = latest.content
    logger.info("_finalize_intervention: using latest.content=%d chars (not rebuilding)", len(after_content))

    push_undo_snapshot(
        st.session_state,
        message_id=latest.id,
        before_content=before_content,
        after_content=after_content,
        action=str(action),
    )

    if action == "insert_and_continue" and insertion:
        log: list[dict[str, str]] = st.session_state.setdefault("insertion_log", [])
        log.append({"text": insertion, "timestamp": datetime.now(timezone.utc).isoformat()})


def _find_bad_word(text: str, words: list[str]) -> int | None:
    text_lower = text.lower()
    for w in words:
        pos = text_lower.find(w.lower())
        if pos != -1:
            return pos
    return None


def _keyword_retry_from_position(position: int) -> bool:
    """Restart generation from *position*, truncating content before it.

    For SSE mode: sets intervention state so that the next stream request
    from React uses mode=intervention. Does NOT create a generator.
    """
    logger.info("_keyword_retry_from_position: position=%d (SSE mode)", position)
    messages: list[ChatMessage] = st.session_state["messages"]
    if not messages or messages[-1].role != "assistant":
        return False
    latest = messages[-1]

    before_content = latest.content
    prefix = before_content[:position]
    # Keep full original content in latest.content during retry to prevent
    # visible truncation. React will truncate to assistantPrefix when first token arrives.
    latest.content = before_content
    latest.status = "streaming"

    frozen = frozen_messages_before_latest(messages)
    st.session_state["streaming_intervention"] = {
        "base_content": prefix,
        "raw_continuation": "",
        "clean_continuation": "",
        "before_content": before_content,
        "selection_start": position,
        "insertion": "",
        "action": "regenerate_from_here",
        "frozen_messages": frozen,
        "assistant_prefix": prefix,
    }
    st.session_state["last_intervention_request_id"] = repr(("kw_filter", id(latest), position))
    # React will see status="streaming" + intervention state and auto-start
    set_generating(st.session_state, True)
    return True


def _check_keywords_in_stream(content: str) -> bool:
    """Per-token keyword check. Returns True if retry was triggered."""
    kw = st.session_state["kw_filter"]
    if not kw["enabled"]:
        return False
    bad_words = [w.strip() for w in kw["words"].split(",") if w.strip()]
    if not bad_words:
        return False

    pos = _find_bad_word(content, bad_words)
    if pos is None:
        return False

    logger.warning("_check_keywords_in_stream: bad word found at pos=%d, word match", pos)
    kw["retry_count"] += 1
    if kw["retry_count"] > kw["max_retries"]:
        st.session_state["validator"]["error"] = (
            f"禁止ワード検出、{kw['max_retries']}回リトライしても改善されませんでした"
        )
        kw["retry_count"] = 0
        return False

    return _keyword_retry_from_position(pos)


def _run_llm_validator(content: str) -> None:
    logger.info("_run_llm_validator: validating %d chars", len(content))
    settings: LlmSettings = st.session_state["llm_settings"]
    prompt_template = st.session_state["validator"]["prompt"]
    if not prompt_template:
        prompt = (
            "以下の文章に不自然・不適切な表現がないか分析し、"
            "問題箇所をJSON配列で出力してください。\n\n"
            "書式:\n"
            '```json\n'
            '[{"position": 数値, "length": 数値, "reason": "説明",\n'
            '  "suggestion": "regenerate_from_here"}]\n'
            '```\n'
            "問題がない場合は空配列 [] を出力。\n\n"
            "---\n" + content
        )
    else:
        prompt = prompt_template.replace("{text}", content)

    try:
        raw = generate_text(prompt, settings)
        st.session_state["validator"]["results"] = _parse_llm_issues(raw)
    except Exception as exc:
        st.session_state["validator"]["error"] = f"LLM検証エラー: {exc}"


def _parse_llm_issues(raw: str) -> list[dict[str, Any]]:
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw, re.DOTALL)
    if m:
        raw = m.group(1)
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


def _run_validation_pipeline() -> bool:
    """Run post-generation validation. Returns True if a retry was triggered.

    During intervention streaming, only the newly generated continuation
    (after base_content) is checked for bad words — the user-inserted text
    is intentionally excluded from keyword filter retries.
    """
    logger.debug("_run_validation_pipeline: running post-generation validation")
    messages: list[ChatMessage] = st.session_state["messages"]
    if not messages:
        return False
    text = messages[-1].content

    # During intervention, only check the newly generated part
    intervention = st.session_state.get("streaming_intervention")
    check_text = text
    offset = 0
    if intervention:
        base = intervention.get("base_content", "")
        if text.startswith(base):
            check_text = text[len(base):]
            offset = len(base)

    # 1) Post-stream keyword filter (final check after streaming stops)
    kw = st.session_state["kw_filter"]
    bad_words = [w.strip() for w in kw["words"].split(",") if w.strip()]
    if kw["enabled"] and bad_words:
        pos = _find_bad_word(check_text, bad_words)
        if pos is not None:
            kw["retry_count"] += 1
            if kw["retry_count"] <= kw["max_retries"]:
                full_pos = offset + pos
                _keyword_retry_from_position(full_pos)
                return True
            else:
                st.session_state["validator"]["error"] = (
                    f"禁止ワード検出、{kw['max_retries']}回リトライしても改善されませんでした"
                )
                kw["retry_count"] = 0

    # 2) LLM validator (post-generation)
    if st.session_state["validator"]["enabled"] and check_text:
        _run_llm_validator(check_text)

    return False


def handle_streaming_error(event: dict[str, Any]) -> None:
    """Handle streaming error signal from React component.

    Reverts latest assistant content safely and sets error/generating state.
    """
    logger.info("handle_streaming_error: message=%s, is_generating=%s",
                event.get("message"), st.session_state.get("is_generating"))
    messages: list[ChatMessage] = st.session_state["messages"]

    if not messages or messages[-1].role != "assistant":
        set_error(st.session_state, f"Streaming error: {event.get('message', 'Unknown')}")
        set_generating(st.session_state, False)
        st.session_state["streaming_intervention"] = None
        return

    latest = messages[-1]

    # Stale event guard
    if latest.status != "streaming":
        logger.debug("handle_streaming_error: skipping stale event (status=%s)", latest.status)
        return

    error_content = event.get("content", "")
    if error_content:
        latest.content = error_content
    else:
        # Fall back to content before intervention if available
        intervention = st.session_state.get("streaming_intervention")
        if intervention:
            before = intervention.get("before_content")
            if before:
                latest.content = before

    latest.status = "error"
    set_error(st.session_state, f"Streaming error: {event.get('message', 'Unknown')}")
    set_generating(st.session_state, False)
    st.session_state["streaming_intervention"] = None


def handle_user_prompt(prompt: str) -> None:
    logger.info("handle_user_prompt: prompt=%d chars, '%s'", len(prompt), prompt[:80])
    messages: list[ChatMessage] = st.session_state["messages"]
    settings: LlmSettings = st.session_state["llm_settings"]

    if not settings.base_url.strip():
        resolved = _probe_base_url("")
        if resolved:
            settings.base_url = resolved

    append_user_message(messages, prompt)
    set_error(st.session_state, None)
    set_generating(st.session_state, True)

    append_assistant_message(messages, "", status="streaming")

    st.session_state["kw_filter"]["retry_count"] = 0
    st.session_state["validator"]["error"] = None


def handle_streaming_complete(event: dict[str, Any]) -> bool:
    """Handle completion signal from React component after SSE streaming.
    Returns True if a retry was triggered (caller should clear component value then st.rerun)."""
    logger.info("handle_streaming_complete: content=%d chars, is_generating=%s, has_intervention=%s",
                len(event.get("content", "")),
                st.session_state.get("is_generating"),
                st.session_state.get("streaming_intervention") is not None)
    messages: list[ChatMessage] = st.session_state["messages"]
    if not messages:
        return False

    latest = messages[-1]
    if latest.role != "assistant":
        return False

    # Guard against stale events from persisted component values
    if latest.status != "streaming":
        logger.debug("handle_streaming_complete: skipping stale event (status=%s)", latest.status)
        return False

    content = event.get("content", "")

    # Run validation BEFORE setting status, so retry can override it
    latest.content = content
    retried = _run_validation_pipeline()

    if retried:
        # Retry was triggered — _keyword_retry_from_position already set
        # is_generating=True, status="streaming", and intervention state.
        # Do NOT override is_generating to False here; React needs it True
        # to auto-start the new intervention stream.
        logger.info("handle_streaming_complete: retry triggered, is_generating=True, streaming_intervention set")
        return True

    # No retry — finalize normally
    latest.content = content
    latest.status = "complete"
    set_generating(st.session_state, False)

    intervention = st.session_state.get("streaming_intervention")
    if intervention:
        _finalize_intervention(intervention)
        st.session_state["streaming_intervention"] = None
        logger.info("handle_streaming_complete: finalized intervention, is_generating=False")

    return False


def _event_request_id(event: dict[str, Any]) -> str:
    request_id = event.get("requestId")
    if isinstance(request_id, str) and request_id:
        return request_id
    return repr((
        event.get("action"), event.get("messageId"),
        event.get("selectionStart"), event.get("insertion") or "",
    ))


def handle_intervention_event(event: dict[str, Any]) -> bool:
    request_id = _event_request_id(event)
    logger.info("handle_intervention_event: action=%s, requestId=%s, selectionStart=%s",
                event.get("action"), request_id, event.get("selectionStart"))
    if st.session_state.get("last_intervention_request_id") == request_id:
        return False

    st.session_state["last_intervention_request_id"] = request_id

    messages: list[ChatMessage] = st.session_state["messages"]

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

    # 通常生成・介入生成のどちらでも、進行中のストリーミングを止める

    set_error(st.session_state, None)
    set_generating(st.session_state, True)

    prefix = before_content[:selection_start]
    effective_insertion = insertion if action == "insert_and_continue" else ""
    base_content = prefix + effective_insertion
    latest.content = base_content
    latest.status = "streaming"

    frozen = frozen_messages_before_latest(messages)
    st.session_state["streaming_intervention"] = {
        "base_content": base_content,
        "raw_continuation": "",
        "clean_continuation": "",
        "before_content": before_content,
        "selection_start": selection_start,
        "insertion": insertion,
        "action": action,
        "frozen_messages": frozen,
        "assistant_prefix": prefix,
    }

    st.session_state["kw_filter"]["retry_count"] = 0
    st.session_state["validator"]["error"] = None

    # Streaming will be handled by React component via SSE
    # No need to create a generator here

    return True


def undo_last_intervention() -> None:
    logger.info("undo_last_intervention")
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


def handle_cursor_loop_position(message_id: str, selection_start: int) -> None:
    """Start a cursor loop preview stream from the given position.

    This is preview-only: latest.content is NOT modified.
    The preview is stored separately in cursor_loop['preview_content'].
    """
    messages: list[ChatMessage] = st.session_state["messages"]
    if not messages:
        return

    latest = messages[-1]
    if latest.id != message_id or not is_intervenable(messages, message_id):
        return

    try:
        validate_selection_start(latest.content, selection_start)
    except (TypeError, ValueError) as exc:
        set_error(st.session_state, str(exc))
        return

    original_content = latest.content
    prefix = original_content[:selection_start]
    frozen = frozen_messages_before_latest(messages)

    stream_key = f"{message_id}:intervention:{selection_start}::regenerate_from_here"

    # P0-6: abort is handled by React's AbortController + stale guard (P1-1: removed dead stream_id code)

    # Save preview state — do NOT touch latest.content or latest.status (P0-2)
    st.session_state["cursor_loop"]["message_id"] = message_id
    st.session_state["cursor_loop"]["original_content"] = original_content
    st.session_state["cursor_loop"]["base_content"] = prefix
    st.session_state["cursor_loop"]["cursor_pos"] = selection_start
    st.session_state["cursor_loop"]["status"] = "streaming"
    st.session_state["cursor_loop"]["preview_content"] = prefix
    st.session_state["cursor_loop"]["stream_key"] = stream_key
    st.session_state["cursor_loop"]["error"] = None

    set_error(st.session_state, None)
    set_generating(st.session_state, True)

    st.session_state["streaming_intervention"] = {
        "base_content": prefix,
        "raw_continuation": "",
        "clean_continuation": "",
        "before_content": original_content,
        "selection_start": selection_start,
        "insertion": "",
        "action": "regenerate_from_here",
        "frozen_messages": frozen,
        "assistant_prefix": prefix,
        "_cursor_loop": True,
        "stream_key": stream_key,
    }
    st.session_state["kw_filter"]["retry_count"] = 0
    st.session_state["validator"]["error"] = None


def handle_cursor_loop_preview(content: str, stream_key: str = "") -> None:
    """Store cursor loop preview and mark complete.

    preview-only: latest.content is NOT modified.
    The completed preview content is stored in cursor_loop['preview_content'].
    """
    cl = st.session_state["cursor_loop"]

    # P0-5: stale guard — ignore if stream_key doesn't match (P1-3: empty is also stale)
    if not stream_key or (cl.get("stream_key") and stream_key != cl.get("stream_key")):
        logger.debug("handle_cursor_loop_preview: stale event ignored (stream_key mismatch)")
        return

    if not st.session_state.get("is_generating", False):
        logger.debug("handle_cursor_loop_preview: stale event ignored (not generating)")
        return

    # preview-only: do NOT touch latest.content or latest.status (P0-2)
    set_generating(st.session_state, False)
    st.session_state["streaming_intervention"] = None

    cl["preview_content"] = content
    cl["status"] = "complete"
    cl["error"] = None


def handle_cursor_loop_error(message: str, content: str = "", stream_key: str = "") -> None:
    """Handle cursor loop streaming error.

    Sets status="error" so the apply button is not shown.
    Never treats error as complete (P0-4). Never modifies latest.content.
    """
    cl = st.session_state["cursor_loop"]

    # P0-5: stale guard (P1-3: empty is also stale)
    if not stream_key or (cl.get("stream_key") and stream_key != cl.get("stream_key")):
        logger.debug("handle_cursor_loop_error: stale event ignored (stream_key mismatch)")
        return

    cl["status"] = "error"
    cl["error"] = message
    cl["preview_content"] = content if content else cl.get("preview_content", "")
    set_generating(st.session_state, False)
    st.session_state["streaming_intervention"] = None


def _apply_cursor_loop() -> None:
    """Apply the cursor loop preview to the actual message."""
    messages: list[ChatMessage] = st.session_state["messages"]
    cl = st.session_state["cursor_loop"]
    if not messages or not cl["preview_content"] or cl["status"] != "complete":
        return
    latest = messages[-1]
    before_content = cl.get("original_content", latest.content)
    after_content = cl["preview_content"]
    latest.content = after_content
    latest.status = "complete"
    push_undo_snapshot(
        st.session_state,
        message_id=latest.id,
        before_content=before_content,
        after_content=after_content,
        action="cursor_loop_apply",
    )
    cl["enabled"] = False
    cl["message_id"] = None
    cl["original_content"] = ""
    cl["base_content"] = ""
    cl["preview_content"] = ""
    cl["cursor_pos"] = None
    cl["status"] = "idle"
    cl["error"] = None
    cl["stream_key"] = None


def _cancel_cursor_loop() -> None:
    """Cancel cursor loop and restore original content."""
    messages: list[ChatMessage] = st.session_state["messages"]
    cl = st.session_state["cursor_loop"]
    if messages:
        latest = messages[-1]
        original = cl.get("original_content", "")
        if original:
            latest.content = original
        latest.status = "complete"
    set_generating(st.session_state, False)
    st.session_state["streaming_intervention"] = None
    cl["preview_content"] = ""
    cl["cursor_pos"] = None
    cl["status"] = "idle"
    cl["error"] = None
    cl["stream_key"] = None
    cl["base_content"] = ""
    cl["message_id"] = None


def _thinking_badge() -> None:
    if st.session_state["is_generating"]:
        st.markdown('<span class="bw-thinking">推論中</span>', unsafe_allow_html=True)


def render_validator_panel() -> None:
    is_generating = bool(st.session_state["is_generating"])
    messages: list[ChatMessage] = st.session_state["messages"]

    kw = st.session_state["kw_filter"]
    val = st.session_state["validator"]

    if val["error"]:
        st.sidebar.warning(val["error"])

    # ── キーワードフィルター ──
    st.sidebar.subheader("🚫 リアルタイムキーワードフィルター")
    st.sidebar.caption("1トークンごとにチェック、引っかかったら即リトライ")

    kw["enabled"] = st.sidebar.checkbox(
        "有効化",
        value=kw["enabled"],
        key="kw_enabled",
        disabled=is_generating,
    )

    kw["words"] = st.sidebar.text_area(
        "禁止ワード（カンマ区切り）",
        value=kw["words"],
        placeholder="ng, badword, ダメ",
        key="kw_words",
        disabled=not kw["enabled"] or is_generating,
    )

    rc = kw["retry_count"]
    if rc > 0:
        st.sidebar.caption(f"🔄 リトライ中 ({rc}/{kw['max_retries']})")

    kw["max_retries"] = st.sidebar.number_input(
        "最大リトライ回数",
        min_value=1,
        max_value=20,
        value=kw["max_retries"],
        step=1,
        key="kw_max_retries",
        disabled=not kw["enabled"] or is_generating,
    )

    st.sidebar.divider()

    # ── LLM検証器 ──
    st.sidebar.subheader("🤖 LLM検証器（事後）")
    st.sidebar.caption("生成完了後にLLMが問題箇所を分析、JSONで位置を返す")

    val["enabled"] = st.sidebar.checkbox(
        "有効化",
        value=val["enabled"],
        key="llm_enabled",
        disabled=is_generating,
    )

    val["prompt"] = st.sidebar.text_area(
        "カスタムプロンプト（任意）",
        value=val["prompt"],
        placeholder="空欄でデフォルトプロンプトを使用。{text} で生成文を埋め込めます",
        key="llm_prompt",
        disabled=not val["enabled"] or is_generating,
        height=100,
    )

    # 手動実行ボタン
    if val["enabled"] and messages:
        st.sidebar.caption("手動で実行する場合:")
        if st.sidebar.button("🔍 LLM検証を実行", key="llm_run_btn", disabled=is_generating):
            _run_llm_validator(messages[-1].content)
            st.rerun()

    # LLM検証結果
    llm_results = val["results"]
    if llm_results:
        st.sidebar.divider()
        st.sidebar.caption(f"📋 LLM検証: {len(llm_results)}件の問題")
        for i, issue in enumerate(llm_results):
            pos = issue.get("position", 0)
            reason = issue.get("reason", "?")
            length = issue.get("length", 0)
            frag = messages[-1].content[pos:pos + length] if messages and pos >= 0 else ""
            st.sidebar.error(f"#{i+1} pos={pos}: {reason}")
            if frag:
                st.sidebar.code(frag, line_limit=3)
            if st.sidebar.button("↩️ この位置から再生成", key=f"llm-fix-{i}", disabled=is_generating):
                _keyword_retry_from_position(pos)
                st.rerun()

def _first_launch_wizard() -> None:
    """初回起動時に自動プローブとモデル選択を案内する."""
    settings: LlmSettings = st.session_state["llm_settings"]
    if st.session_state["messages"] or settings.model.strip():
        return

    st.info("### 🚀 Branch Writer へようこそ！\n\nまずはAIモデルに接続します。")

    with st.spinner("ローカルLLMを検出中..."):
        resolved = _probe_base_url("")
        if resolved:
            settings.base_url = resolved
            st.success(f"✅ エンドポイントを検出: `{resolved}`")
        else:
            st.error(
                "❌ Ollama / LM Studio が見つかりません。\n\n"
                "- **Ollama**: https://ollama.com/download"
                " からインストール後、`ollama pull llama3.2:1b` を実行\n"
                "- **LM Studio**: https://lmstudio.ai"
                " からインストール後、モデルを読み込んで"
                "Local Inference Serverを起動\n\n"
                "設定後、画面左のサイドバーで接続設定を行ってください。"
            )
            return

    models = discover_models_sync(resolved)
    if models:
        st.session_state["available_models"] = models
        settings.model = models[0]["name"]
        ctx, out = lookup_model_capabilities(settings.model)
        settings.context_window = ctx
        settings.max_tokens = out
        st.success(f"✅ モデル `{settings.model}` を選択しました。")
        st.rerun()
    else:
        st.warning(
            "⚠️  エンドポイントは検出できましたが、利用可能なモデルが見つかりません。\n\n"
            "サイドバーの「🔄 モデル一覧を再取得」ボタンを試すか、モデル名を直接入力してください。"
        )

    st.button("OK, はじめる", key="wizard_dismiss")


def _start_streaming_server() -> None:
    """Start the SSE streaming server if not already running (idempotent)."""
    if not st.session_state.get("_streaming_server_started"):
        logger.info("_start_streaming_server: starting SSE server on port %d", _STREAMING_PORT)
        try:
            start_server(port=_STREAMING_PORT)
            st.session_state["_streaming_server_started"] = True
        except RuntimeError as exc:
            st.error(str(exc))
            set_error(st.session_state, str(exc))


def main() -> None:
    logger.info("main: Branch Writer starting")
    st.set_page_config(page_title="Branch Writer", page_icon="✍️", layout="wide")
    initialize_state(st.session_state)
    _inject_custom_css()
    _start_streaming_server()

    st.title("Branch Writer")
    _thinking_badge()

    _first_launch_wizard()

    render_sidebar()

    last_error = st.session_state.get("last_error")
    if last_error:
        st.error(last_error)

    # 介入イベントはrender_messagesより前に処理する
    # (古い全文が一瞬描画される「ちらつき」を防止するため)
    intervention_event = st.session_state.pop("_intervention_event", None)
    if intervention_event:
        handle_intervention_event(intervention_event)
        st.rerun()

    render_messages()

    if not component_available():
        event = render_intervention_panel()
        if event:
            handle_intervention_event(event)
            st.rerun()

    prompt = st.chat_input("メッセージを入力", disabled=bool(st.session_state["is_generating"]))
    if prompt:
        handle_user_prompt(prompt)
        st.rerun()


if __name__ == "__main__":
    main()
