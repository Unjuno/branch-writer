import React, { ChangeEvent, useEffect, useRef, useState } from "react"
import { ComponentProps, Streamlit } from "@streamlit/component-lib"

type InterventionAction = "regenerate_from_here" | "insert_and_continue"

type InterventionEvent = {
  action: InterventionAction
  messageId: string
  selectionStart: number
  selectionEnd: number
  insertion?: string
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
  })

  const updateSelection = () => {
    const element = textareaRef.current
    if (!element) return

    setSelectionStart(element.selectionStart)
    setSelectionEnd(element.selectionEnd)
  }

  const emit = (action: InterventionAction) => {
    const event: InterventionEvent = {
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
    Streamlit.setFrameHeight()
  }

  return (
    <div className="branch-writer-editor">
      <label className="branch-writer-label">Latest assistant message</label>
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
        rows={Math.min(Math.max(content.split("\n").length + 2, 8), 24)}
      />

      <div className="branch-writer-selection">
        selectionStart: <code>{selectionStart}</code> / selectionEnd: <code>{selectionEnd}</code>
      </div>

      <div className="branch-writer-actions">
        <button
          type="button"
          disabled={disabled}
          onClick={() => emit("regenerate_from_here")}
        >
          ここから再生成
        </button>
      </div>

      <div className="branch-writer-insert-block">
        <textarea
          className="branch-writer-insertion"
          value={insertion}
          disabled={disabled}
          onChange={onInsertionChange}
          placeholder="ここに挿入する文を入力"
          rows={3}
        />
        <button
          type="button"
          disabled={disabled || insertion.length === 0}
          onClick={() => emit("insert_and_continue")}
        >
          入力して続ける
        </button>
      </div>
    </div>
  )
}

export default LatestMessageEditor
