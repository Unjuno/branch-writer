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

function themeStyle(theme?: StreamlitTheme): CSSProperties {
  const isDark = theme?.base === "dark"
  const backgroundColor = theme?.backgroundColor ?? (isDark ? "#0e1117" : "#ffffff")
  const secondaryBackgroundColor = theme?.secondaryBackgroundColor ?? (isDark ? "#262730" : "#f0f2f6")
  const textColor = theme?.textColor ?? (isDark ? "#fafafa" : "#31333f")
  const primaryColor = theme?.primaryColor ?? "#ff4b4b"
  const mutedColor = isDark ? "rgba(250, 250, 250, 0.62)" : "rgba(49, 51, 63, 0.62)"
  const borderColor = isDark ? "rgba(250, 250, 250, 0.14)" : "rgba(49, 51, 63, 0.14)"
  const inputBackground = isDark ? "rgba(14, 17, 23, 0.68)" : "rgba(255, 255, 255, 0.92)"

  return {
    "--bw-bg": backgroundColor,
    "--bw-surface": secondaryBackgroundColor,
    "--bw-surface-soft": isDark ? "rgba(38, 39, 48, 0.62)" : "rgba(240, 242, 246, 0.72)",
    "--bw-input-bg": inputBackground,
    "--bw-text": textColor,
    "--bw-muted": mutedColor,
    "--bw-border": borderColor,
    "--bw-primary": primaryColor,
    "--bw-primary-text": "#ffffff",
    "--bw-shadow": isDark ? "none" : "0 2px 10px rgba(49, 51, 63, 0.08)",
    fontFamily: theme?.font,
  } as CSSProperties
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
  const rootStyle = useMemo(() => themeStyle(theme), [theme])

  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const [selectionStart, setSelectionStart] = useState(0)
  const [selectionEnd, setSelectionEnd] = useState(0)
  const [insertion, setInsertion] = useState("")

  useEffect(() => {
    Streamlit.setFrameHeight()
  }, [content, insertion])

  const updateSelection = () => {
    const element = textareaRef.current
    if (!element) return

    const nextStart = element.selectionStart
    const nextEnd = element.selectionEnd

    if (nextStart !== selectionStart) {
      setSelectionStart(nextStart)
    }
    if (nextEnd !== selectionEnd) {
      setSelectionEnd(nextEnd)
    }
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

  const onInsertionChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    setInsertion(event.target.value)
  }

  const selectedLength = Math.max(0, selectionEnd - selectionStart)
  const canInsert = insertion.trim().length > 0

  return (
    <section className="branch-writer-editor" style={rootStyle} aria-label="Latest assistant intervention editor">
      <div className="branch-writer-header">
        <div>
          <div className="branch-writer-kicker">Latest assistant</div>
          <h3>途中から曲げる</h3>
        </div>
        <div className="branch-writer-badge">editable</div>
      </div>

      <textarea
        ref={textareaRef}
        className="branch-writer-textarea"
        value={content}
        readOnly
        disabled={disabled}
        onClick={updateSelection}
        onKeyUp={updateSelection}
        onSelect={updateSelection}
        onMouseUp={updateSelection}
        rows={Math.min(Math.max(content.split("\n").length + 2, 8), 22)}
      />

      <div className="branch-writer-toolbar">
        <div className="branch-writer-meta-row">
          <span>cut <code>{selectionStart}</code></span>
          <span>end <code>{selectionEnd}</code></span>
          <span>selected <code>{selectedLength}</code></span>
        </div>
        <button
          className="branch-writer-button branch-writer-primary"
          type="button"
          disabled={disabled}
          onClick={() => emit("regenerate_from_here")}
        >
          選択位置から再生成
        </button>
      </div>

      <div className="branch-writer-insert-card">
        <label htmlFor="branch-writer-insertion">一文を入れて続ける</label>
        <textarea
          id="branch-writer-insertion"
          className="branch-writer-insertion"
          value={insertion}
          disabled={disabled}
          onChange={onInsertionChange}
          placeholder="例: しかし、"
          rows={2}
        />
        <div className="branch-writer-insert-actions">
          <button
            className="branch-writer-button branch-writer-secondary"
            type="button"
            disabled={disabled || !canInsert}
            onClick={() => emit("insert_and_continue")}
          >
            挿入して続きを生成
          </button>
        </div>
      </div>
    </section>
  )
}

export default LatestMessageEditor
