import React, { ChangeEvent, CSSProperties, useEffect, useMemo, useRef, useState } from "react"
import { ComponentProps, Streamlit } from "streamlit-component-lib"

type InterventionAction = "regenerate_from_here" | "insert_and_continue"

type InterventionEvent = {
  requestId: string
  action: InterventionAction
  messageId: string
  selectionStart: number
  selectionEnd: number
  insertion?: string
}

type StreamlitTheme = {
  base?: "light" | "dark"
  primaryColor?: string
  backgroundColor?: string
  secondaryBackgroundColor?: string
  textColor?: string
  font?: string
}

function createRequestId(action: InterventionAction, messageId: string): string {
  return `${messageId}:${action}:${Date.now()}:${Math.random().toString(36).slice(2)}`
}

function themeVars(theme?: StreamlitTheme): CSSProperties {
  const isDark = theme?.base === "dark"
  const textColor = theme?.textColor ?? (isDark ? "#fafafa" : "#31333f")
  const mutedColor = isDark ? "rgba(250,250,250,0.55)" : "rgba(49,51,63,0.55)"
  const borderColor = isDark ? "rgba(250,250,250,0.12)" : "rgba(49,51,63,0.12)"
  const primaryColor = theme?.primaryColor ?? "#ff4b4b"
  const bg = isDark ? "rgba(14,17,23,0.6)" : "rgba(255,255,255,0.85)"
  const surface = isDark ? "rgba(38,39,48,0.5)" : "rgba(240,242,246,0.6)"

  return {
    "--bw-text": textColor,
    "--bw-muted": mutedColor,
    "--bw-border": borderColor,
    "--bw-primary": primaryColor,
    "--bw-bg": bg,
    "--bw-surface": surface,
    fontFamily: theme?.font,
  } as CSSProperties
}

function openaiLogo(code: boolean): string {
  return code
    ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 18l6-6-6-6M8 6l-6 6 6 6"/></svg>`
    : ""
}

function LatestMessageEditor(props: ComponentProps) {
  const args = props.args as {
    messageId?: string
    content?: string
    disabled?: boolean
  }
  const theme = (props as ComponentProps & { theme?: StreamlitTheme }).theme

  const messageId = args.messageId ?? ""
  const content = args.content ?? ""
  const disabled = Boolean(args.disabled)

  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const [selectionStart, setSelectionStart] = useState(0)
  const [selectionEnd, setSelectionEnd] = useState(0)
  const [insertion, setInsertion] = useState("")

  useEffect(() => {
    Streamlit.setFrameHeight()
  }, [content, insertion])

  const updateSelection = () => {
    const el = textareaRef.current
    if (!el) return
    const ns = el.selectionStart
    const ne = el.selectionEnd
    if (ns !== selectionStart) setSelectionStart(ns)
    if (ne !== selectionEnd) setSelectionEnd(ne)
  }

  const emit = (action: InterventionAction) => {
    const event: InterventionEvent = {
      requestId: createRequestId(action, messageId),
      action,
      messageId,
      selectionStart,
      selectionEnd,
    }
    if (action === "insert_and_continue") {
      event.insertion = insertion
    }
    Streamlit.setComponentValue(event)
  }

  const atEnd = selectionStart >= content.length

  const cursorIndicator = !disabled && !atEnd ? (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        bottom: -2,
        height: 2,
        background: "var(--bw-primary)",
        opacity: 0.3,
        borderRadius: 1,
        transition: "opacity 0.15s",
        pointerEvents: "none",
      }}
    />
  ) : null

  return (
    <div style={themeVars(theme)}>
      <div
        style={{
          position: "relative",
        }}
      >
        <textarea
          ref={textareaRef}
          value={content}
          readOnly
          disabled={disabled}
          onClick={updateSelection}
          onKeyUp={updateSelection}
          onSelect={updateSelection}
          onMouseUp={updateSelection}
          rows={content.split("\n").length + 1}
          style={{
            width: "100%",
            border: "none",
            borderRadius: 0,
            padding: 0,
            font: "inherit",
            lineHeight: 1.7,
            resize: "none",
            background: "transparent",
            color: "var(--bw-text)",
            outline: "none",
            cursor: "text",
            overflow: "hidden",
            whiteSpace: "pre-wrap",
            wordWrap: "break-word",
          }}
        />
        {cursorIndicator}
      </div>

      {!disabled && (
        <div
          style={{
            marginTop: 8,
            opacity: 0.55,
            transition: "opacity 0.2s",
            display: "flex",
            gap: 8,
            flexWrap: "wrap" as const,
            alignItems: "center",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.opacity = "1")}
          onMouseLeave={(e) => (e.currentTarget.style.opacity = "0.55")}
        >
          {!atEnd && (
            <button
              type="button"
              disabled={disabled}
              onClick={() => emit("regenerate_from_here")}
              style={{
                border: "none",
                borderRadius: 4,
                padding: "2px 10px",
                font: "inherit",
                fontSize: "0.78rem",
                cursor: "pointer",
                background: "var(--bw-surface)",
                color: "var(--bw-primary)",
                lineHeight: "22px",
              }}
            >
              ✂ ここから再生成
            </button>
          )}

          <div style={{ display: "flex", gap: 4, alignItems: "center", flex: 1, minWidth: 140 }}>
            <input
              value={insertion}
              disabled={disabled}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setInsertion(e.target.value)}
              placeholder="続きを入力..."
              style={{
                flex: 1,
                border: "none",
                borderBottom: "1px solid var(--bw-border)",
                padding: "2px 4px",
                font: "inherit",
                fontSize: "0.78rem",
                lineHeight: "22px",
                background: "transparent",
                color: "var(--bw-text)",
                outline: "none",
                minWidth: 80,
              }}
            />
            <button
              type="button"
              disabled={disabled || !insertion.trim()}
              onClick={() => emit("insert_and_continue")}
              style={{
                border: "none",
                borderRadius: 4,
                padding: "2px 10px",
                font: "inherit",
                fontSize: "0.78rem",
                cursor: "pointer",
                whiteSpace: "nowrap",
                background: insertion.trim() ? "var(--bw-primary)" : "transparent",
                color: insertion.trim() ? "#fff" : "var(--bw-muted)",
                lineHeight: "22px",
                opacity: disabled || !insertion.trim() ? 0.4 : 1,
              }}
            >
              挿入
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default LatestMessageEditor
