"""Branch Writer の Streamlit アプリ。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import streamlit as st

from branch_writer.config import LlmSettings, lookup_model_capabilities, validate_llm_settings
from branch_writer.model_discovery import discover_models_sync
from branch_writer.intervention import (
    insert_and_continue,
    regenerate_from_here,
    strip_continuation_overlap,
    validate_selection_start,
)
from branch_writer.llm import (
    LlmError,
    generate_text,
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
from branch_writer.code_validator import (
    TEMPLATES,
    VALIDATOR_HELP,
    VALIDATOR_EXTRA_DOCS,
    execute_validator_code,
    code_generation_prompt,
)
from branch_writer.state import (
    initialize_state,
    pop_undo_snapshot,
    push_undo_snapshot,
    set_error,
    set_generating,
)

VALID_INTERVENTION_ACTIONS = {"regenerate_from_here", "insert_and_continue"}
DEFAULT_RENDER_MESSAGE_LIMIT = 80
MIN_RENDER_MESSAGE_LIMIT = 10
MAX_RENDER_MESSAGE_LIMIT = 500

_CHARS_PER_TOKEN_ESTIMATE = 4

_DEFAULT_ENDPOINTS = [
    "http://localhost:11434/v1",   # Ollama
    "http://localhost:1234/v1",    # LM Studio
]

_CODE_PANEL_STATE_KEYS = [
    "code_panel_code",
    "code_panel_template",
    "code_panel_result",
    "code_panel_error",
    "_code_checked_msg_id",
]


def _inject_custom_css() -> None:
    if st.session_state.get("_custom_css_injected"):
        return
    st.session_state["_custom_css_injected"] = True
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

.bw-thinking {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 10px;
    border-radius: 12px;
    background: #ff4b4b;
    color: white;
    font-size: 0.85rem;
    font-weight: 600;
    animation: bw-pulse 1.5s ease-in-out infinite;
}
@keyframes bw-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
}

.code-panel {
    border-left: 1px solid rgba(128,128,128,0.2);
    padding-left: 1rem;
}
.code-panel .stTextArea textarea {
    font-family: "Cascadia Code", "Fira Code", "Consolas", monospace;
    font-size: 0.8rem;
    line-height: 1.4;
}
</style>""",
        unsafe_allow_html=True,
    )


def _cursor_span() -> str:
    return '<span class="bw-cursor">▌</span>'


def _probe_base_url(url: str) -> str:
    if url.strip():
        return url
    import httpx
    for candidate in _DEFAULT_ENDPOINTS:
        try:
            resp = httpx.get(f"{candidate.rstrip('/v1')}/api/tags", timeout=2)
            if resp.status_code < 500:
                return candidate
        except Exception:
            try:
                resp = httpx.get(f"{candidate}/models", timeout=2)
                if resp.status_code < 500:
                    return candidate
            except Exception:
                continue
    return url


def estimate_tokens(text: str) -> int:
    return max(len(text) // _CHARS_PER_TOKEN_ESTIMATE, 0)


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
    settings.api_key = st.sidebar.text_input("API キー", value=settings.api_key, type="password", disabled=is_generating)

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
    settings.temperature = st.sidebar.slider("温度 (Temperature)", min_value=0.0, max_value=2.0, value=float(settings.temperature), step=0.1, disabled=is_generating)

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


def reset_chat_state() -> None:
    st.session_state["messages"] = []
    st.session_state["undo_stack"] = []
    st.session_state["last_error"] = None
    st.session_state["is_generating"] = False
    st.session_state["last_intervention_request_id"] = None
    st.session_state["insertion_log"] = []
    st.session_state["reuse_insertion"] = None
    st.session_state["streaming_generator"] = None
    st.session_state["streaming_intervention"] = None
    st.session_state["_in_intervention_streaming"] = False
    st.session_state["available_models"] = []
    st.session_state["_code_checked_msg_id"] = None


def render_frozen_message(message: ChatMessage) -> None:
    with st.chat_message(message.role):
        st.markdown(message.content, unsafe_allow_html=True)
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
    if st.session_state.get("_in_intervention_streaming"):
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

    # プレビュー表示
    prefix = latest.content[:selection_start]
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

    for index, message in enumerate(visible_messages):
        if message.role == "assistant" and message.status == "streaming":
            with st.chat_message("assistant"):
                content = message.content
                if content:
                    content = content + _cursor_span()
                st.markdown(content, unsafe_allow_html=True)
        else:
            render_frozen_message(message)


def _finalize_intervention(state: dict[str, Any]) -> None:
    """Finalize an intervention after streaming completes."""
    messages: list[ChatMessage] = st.session_state["messages"]
    if not messages:
        return
    latest = messages[-1]

    before_content = state["before_content"]
    selection_start = state["selection_start"]
    insertion = state["insertion"]
    clean_continuation = state["clean_continuation"]
    action = state["action"]

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
        log: list[dict[str, str]] = st.session_state.setdefault("insertion_log", [])
        log.append({"text": insertion, "timestamp": datetime.now(timezone.utc).isoformat()})


def continue_streaming() -> None:
    generator = st.session_state.get("streaming_generator")
    if generator is None:
        return

    messages: list[ChatMessage] = st.session_state["messages"]
    if not messages or messages[-1].status != "streaming":
        st.session_state["streaming_generator"] = None
        st.session_state["streaming_intervention"] = None
        st.session_state["_in_intervention_streaming"] = False
        set_generating(st.session_state, False)
        return

    assistant = messages[-1]
    intervention = st.session_state.get("streaming_intervention")

    try:
        chunk = next(generator)
        if intervention:
            raw = intervention["raw_continuation"] + chunk
            intervention["raw_continuation"] = raw
            base = intervention["base_content"]
            clean = strip_continuation_overlap(base, raw)
            intervention["clean_continuation"] = clean
            assistant.content = base + clean
        else:
            assistant.content += chunk

    except StopIteration:
        if intervention:
            _finalize_intervention(intervention)
            st.session_state["streaming_intervention"] = None
            st.session_state["_in_intervention_streaming"] = False

        assistant.status = "complete"
        st.session_state["streaming_generator"] = None
        set_generating(st.session_state, False)

    except LlmError as exc:
        set_error(st.session_state, str(exc))
        if intervention:
            assistant.content = intervention["base_content"]
        else:
            assistant.content = "ローカルLLMへの接続または生成に失敗しました。サイドバーの設定を確認してください。"
        assistant.status = "error"
        st.session_state["streaming_generator"] = None
        st.session_state["streaming_intervention"] = None
        st.session_state["_in_intervention_streaming"] = False
        set_generating(st.session_state, False)

    except Exception as exc:
        set_error(st.session_state, f"Unexpected generation error: {type(exc).__name__}: {exc}")
        if intervention:
            assistant.content = intervention["base_content"]
        else:
            assistant.content = "予期しないエラーで生成に失敗しました。エラー表示を確認してください。"
        assistant.status = "error"
        st.session_state["streaming_generator"] = None
        st.session_state["streaming_intervention"] = None
        st.session_state["_in_intervention_streaming"] = False
        set_generating(st.session_state, False)


def handle_user_prompt(prompt: str) -> None:
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

    generator = iter_chat_response(messages[:-1], settings)
    st.session_state["streaming_generator"] = generator


def _event_request_id(event: dict[str, Any]) -> str:
    request_id = event.get("requestId")
    if isinstance(request_id, str) and request_id:
        return request_id
    return repr((event.get("action"), event.get("messageId"), event.get("selectionStart"), event.get("insertion") or ""))


def handle_intervention_event(event: dict[str, Any]) -> bool:
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

    # 通常生成・介入生成のどちらでも、進行中のストリーミングを止める
    st.session_state["streaming_generator"] = None

    set_error(st.session_state, None)
    set_generating(st.session_state, True)

    prefix = before_content[:selection_start]
    effective_insertion = insertion if action == "insert_and_continue" else ""
    base_content = prefix + effective_insertion
    latest.content = base_content
    latest.status = "streaming"

    st.session_state["streaming_intervention"] = {
        "base_content": base_content,
        "raw_continuation": "",
        "clean_continuation": "",
        "before_content": before_content,
        "selection_start": selection_start,
        "insertion": insertion,
        "action": action,
    }
    st.session_state["_in_intervention_streaming"] = True

    generator = iter_intervention_continuation(
        frozen_messages=frozen_messages_before_latest(messages),
        assistant_prefix=prefix,
        insertion=effective_insertion,
        settings=settings,
    )
    st.session_state["streaming_generator"] = generator

    return True


def undo_last_intervention() -> None:
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


def _thinking_badge() -> None:
    if st.session_state["is_generating"]:
        st.markdown('<span class="bw-thinking">🤖 推論中...</span>', unsafe_allow_html=True)


def _init_code_panel_state() -> None:
    for k in _CODE_PANEL_STATE_KEYS:
        st.session_state.setdefault(k, None)


def render_code_panel() -> None:
    _init_code_panel_state()
    settings: LlmSettings = st.session_state["llm_settings"]
    is_generating = bool(st.session_state["is_generating"])
    messages: list[ChatMessage] = st.session_state["messages"]
    last_content = messages[-1].content if messages else ""

    with st.container():
        st.markdown('<div class="code-panel">', unsafe_allow_html=True)
        st.subheader("🧪 コード検証")

        # 新着メッセージ通知
        if messages and last_content:
            last_id = messages[-1].id if messages[-1].role == "assistant" else None
            prev_checked = st.session_state.get("_code_checked_msg_id")
            if last_id and last_id != prev_checked and not is_generating:
                st.success("📩 新しいメッセージが届きました — 検証コードを実行して分析できます")
                if st.button("🔍 クイック分析", key="quick_analyze_btn"):
                    code = TEMPLATES.get("LLMで文体チェック", "")
                    if code:
                        st.session_state["code_panel_code"] = code
                        st.session_state["code_panel_template"] = "LLMで文体チェック"
                    st.session_state["_code_checked_msg_id"] = last_id
                    st.rerun()

        with st.expander("📖 使い方"):
            st.markdown(VALIDATOR_HELP)
            st.markdown(VALIDATOR_EXTRA_DOCS)

        # テンプレート選択
        template_names = list(TEMPLATES.keys())
        prev_template = st.session_state.get("code_panel_template")
        selected = st.selectbox(
            "テンプレート",
            options=["（選択してください）"] + template_names,
            key="code_panel_template_selector",
            disabled=is_generating,
        )
        if selected and selected != "（選択してください）" and selected != prev_template:
            st.session_state["code_panel_code"] = TEMPLATES[selected]
            st.session_state["code_panel_template"] = selected
            st.rerun()

        # コードエディタ
        st.caption("検証コード")
        code = st.text_area(
            "コード",
            value=st.session_state.get("code_panel_code") or "",
            height=300,
            key="code_panel_editor",
            disabled=is_generating,
            label_visibility="collapsed",
        )

        # アクションボタン
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("🤖 コードを生成", disabled=is_generating or not messages, key="code_gen_btn"):
                with st.spinner("コードを生成中..."):
                    _generate_code_with_llm()
                st.rerun()
        with btn_col2:
            if st.button("▶️ 実行", disabled=not code or not messages, key="code_exec_btn"):
                with st.spinner("コードを実行中..."):
                    result = _execute_code(code)
                    st.session_state["code_panel_result"] = result
                    st.session_state["code_panel_error"] = None
                st.rerun()

        # 結果表示
        result = st.session_state.get("code_panel_result")
        if result:
            analysis = result.get("analysis", "")
            if analysis:
                st.info(analysis)

            suggestions = result.get("suggestions", [])
            if suggestions:
                st.success(f"💡 {len(suggestions)}件の提案があります")
                for i, sug in enumerate(suggestions):
                    action = sug.get("action", "?")
                    pos = sug.get("position", 0)
                    text = sug.get("text", "")
                    st.caption(f"{i+1}. {action} @ pos={pos}" + (f' — "{text[:40]}..."' if text else ""))

                if st.button("✅ 提案を適用", key="code_apply_btn"):
                    _apply_code_suggestion(suggestions)
                    st.session_state["code_panel_result"] = None
                    st.rerun()
            else:
                st.caption("提案はありません")
        elif st.session_state.get("code_panel_error"):
            st.error(st.session_state["code_panel_error"])

        st.markdown('</div>', unsafe_allow_html=True)


def _generate_code_with_llm() -> None:
    messages: list[ChatMessage] = st.session_state["messages"]
    settings: LlmSettings = st.session_state["llm_settings"]
    if not messages:
        return

    last_user = ""
    for m in reversed(messages):
        if m.role == "user":
            last_user = m.content
            break
    last_assistant = messages[-1].content if messages[-1].role == "assistant" else ""

    if not last_assistant:
        return

    prompt = code_generation_prompt(last_user, last_assistant)
    try:
        code = generate_text(prompt, settings)
        st.session_state["code_panel_code"] = code
        st.session_state["code_panel_template"] = None
    except LlmError as exc:
        st.session_state["code_panel_error"] = str(exc)


def _execute_code(code: str) -> dict[str, Any]:
    messages: list[ChatMessage] = st.session_state["messages"]
    settings: LlmSettings = st.session_state["llm_settings"]
    last_content = messages[-1].content if messages else ""

    env = {
        "messages": messages,
        "last_content": last_content,
        "settings": settings,
        "generate_text": generate_text,
    }
    return execute_validator_code(code, env)


def _apply_code_suggestion(suggestions: list[dict[str, Any]]) -> None:
    messages: list[ChatMessage] = st.session_state["messages"]
    if not messages or not suggestions:
        return
    latest = messages[-1]
    if latest.role != "assistant":
        return

    sug = suggestions[0]
    action = sug.get("action", "insert_and_continue")
    pos = sug.get("position", len(latest.content))
    insertion = sug.get("text", "")
    if action == "regenerate_from_here":
        event = {
            "requestId": str(uuid4()),
            "action": "regenerate_from_here",
            "messageId": latest.id,
            "selectionStart": pos,
            "selectionEnd": pos,
        }
    else:
        event = {
            "requestId": str(uuid4()),
            "action": "insert_and_continue",
            "messageId": latest.id,
            "selectionStart": pos,
            "selectionEnd": pos,
            "insertion": insertion,
        }
    handle_intervention_event(event)


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
                "- **Ollama**: https://ollama.com/download からインストール後、`ollama pull llama3.2:1b` を実行\n"
                "- **LM Studio**: https://lmstudio.ai からインストール後、モデルを読み込んでLocal Inference Serverを起動\n\n"
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
    else:
        st.warning(
            "⚠️  エンドポイントは検出できましたが、利用可能なモデルが見つかりません。\n\n"
            "サイドバーの「🔄 モデル一覧を再取得」ボタンを試すか、モデル名を直接入力してください。"
        )

    st.button("OK, はじめる", key="wizard_dismiss")


def main() -> None:
    st.set_page_config(page_title="Branch Writer", page_icon="✍️", layout="wide")
    initialize_state(st.session_state)
    _inject_custom_css()

    st.title("Branch Writer")
    _thinking_badge()

    _first_launch_wizard()

    if st.session_state["is_generating"] and st.session_state.get("streaming_generator"):
        continue_streaming()
        st.rerun()

    render_sidebar()

    last_error = st.session_state.get("last_error")
    if last_error:
        st.error(last_error)

    col_chat, col_code = st.columns([0.65, 0.35], gap="large")
    with col_chat:
        render_messages()
        event = render_intervention_panel()
        if event:
            handle_intervention_event(event)
            st.rerun()

        prompt = st.chat_input("メッセージを入力", disabled=bool(st.session_state["is_generating"]))
        if prompt:
            handle_user_prompt(prompt)
            st.rerun()

    with col_code:
        render_code_panel()


if __name__ == "__main__":
    main()
