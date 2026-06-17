import React, { ChangeEvent, useEffect, useRef, useState } from "react"
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

function createRequestId(action: InterventionAction, messageId: string): string {
  return `${messageId}:${action}:${Date.now()}:${Math.random().toString(36).slice(2)}`
}

function LatestMessageEditor(props: ComponentProps) {
  const args = props.args as {
    messageId?: string
    content?: string
    disabled?: boolean
  }

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
    <section className="branch-writer-editor" aria-label="Latest assistant intervention editor">
      <div className="branch-writer-header">
        <div>
          <div className="branch-writer-kicker">Editable latest assistant message</div>
          <h3>介入ポイントを選ぶ</h3>
        </div>
        <div className="branch-writer-badge">latest only</div>
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
        rows={Math.min(Math.max(content.split("\n").length + 2, 9), 26)}
      />

      <div className="branch-writer-meta-row">
        <span>cut: <code>{selectionStart}</code></span>
        <span>end: <code>{selectionEnd}</code></span>
        <span>selected: <code>{selectedLength}</code></span>
      </div>

      <div className="branch-writer-action-panel">
        <button
          className="branch-writer-primary"
          type="button"
          disabled={disabled}
          onClick={() => emit("regenerate_from_here")}
        >
          <span>ここから再生成</span>
          <small>選択地点以降を破棄して続ける</small>
        </button>

        <div className="branch-writer-insert-card">
          <label htmlFor="branch-writer-insertion">入力して続ける</label>
          <textarea
            id="branch-writer-insertion"
            className="branch-writer-insertion"
            value={insertion}
            disabled={disabled}
            onChange={onInsertionChange}
            placeholder="ここに作者側の一文を入れる"
            rows={3}
          />
          <button
            className="branch-writer-secondary"
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
