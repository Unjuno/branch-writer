import React, { CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ComponentProps, Streamlit } from "streamlit-component-lib"

type StreamingDoneEvent = { type: "streaming_done"; content: string; messageId: string; streamKey?: string }

type StreamingErrorEvent = { type: "streaming_error"; message: string; content: string; messageId: string; streamKey?: string }

type LatestMessageEditorArgs = {
  messageId?: string
  content?: string
  disabled?: boolean
  streamingUrl?: string
  isStreaming?: boolean
  interventionData?: Record<string, unknown> | null
  cursorLoopEnabled?: boolean
  previewContent?: string
  messagesForStream?: Array<{ role: string; content: string; id: string }>
  llmSettings?: {
    base_url: string
    api_key: string
    model: string
    temperature: number
    max_tokens: number
    system_prompt: string
    request_timeout_seconds: number
    context_window: number
  } | null
}

type StreamlitTheme = {
  base?: "light" | "dark"
  primaryColor?: string
  backgroundColor?: string
  secondaryBackgroundColor?: string
  textColor?: string
  font?: string
}

type RenderLine = {
  text: string
  start: number
  end: number
  after: number
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

function codePointLength(text: string): number {
  return Array.from(text).length
}

function sliceCodePoints(text: string, start: number, end?: number): string {
  return Array.from(text).slice(start, end).join("")
}

function clampCodePointOffset(text: string, offset: number): number {
  return Math.max(0, Math.min(offset, codePointLength(text)))
}

function buildRenderLines(content: string): RenderLine[] {
  const rawLines = content.split("\n")
  let offset = 0
  return rawLines.map((text, index) => {
    const start = offset
    const end = start + codePointLength(text)
    const after = end + (index < rawLines.length - 1 ? 1 : 0)
    offset = after
    return { text, start, end, after }
  })
}

function LatestMessageEditor(props: ComponentProps) {
  const args = props.args as LatestMessageEditorArgs
  const theme = (props as ComponentProps & { theme?: StreamlitTheme }).theme

  const messageId = args.messageId ?? ""
  const initialContent = args.content ?? ""
  const disabled = Boolean(args.disabled)
  const streamingUrl = args.streamingUrl ?? ""
  const isStreaming = Boolean(args.isStreaming)
  const interventionData = args.interventionData ?? null
  const messagesForStream = args.messagesForStream ?? []
  const llmSettings = args.llmSettings ?? null

  const [displayContent, setDisplayContent] = useState(initialContent)
  const [selectedLine, setSelectedLine] = useState<number | null>(null)
  const [selectionStart, setSelectionStart] = useState<number | null>(null)
  const [draftInsertion, setDraftInsertion] = useState("")
  const [editSnapshotContent, setEditSnapshotContent] = useState<string | null>(null)
  const [streamId, setStreamId] = useState<string | null>(null)

  const abortControllerRef = useRef<AbortController | null>(null)
  const accumulatedRef = useRef(initialContent)
  const doneSentRef = useRef(false)
  const completedRef = useRef(false)
  const failedStreamKeyRef = useRef("")
  const streamModeRef = useRef("normal")
  const isComposingRef = useRef(false)
  const isEditingRef = useRef(false)
  const inlineInputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => { Streamlit.setFrameHeight() }, [displayContent, editSnapshotContent, selectedLine, draftInsertion])

  useEffect(() => {
    accumulatedRef.current = initialContent
    if (isEditingRef.current) return
    setDisplayContent(initialContent)
    setSelectedLine(null)
    setSelectionStart(null)
    setDraftInsertion("")
    setEditSnapshotContent(null)
  }, [initialContent])

  useEffect(() => {
    if (selectedLine !== null) inlineInputRef.current?.focus()
  }, [selectedLine])

  const generateStreamId = useCallback(() => {
    return `${messageId}:stream:${Date.now()}:${Math.random().toString(36).slice(2)}`
  }, [messageId])

  const startStreaming = useCallback(async (mode: string, extraParams: Record<string, unknown> = {}) => {
    if (!streamingUrl || !llmSettings) return
    const newStreamId = generateStreamId()
    streamModeRef.current = mode
    const thisStreamKey = (extraParams.streamKey as string) || `${messageId}:${mode}:${extraParams.streamKeySuffix ?? ""}`
    doneSentRef.current = false
    failedStreamKeyRef.current = ""
    setStreamId(newStreamId)
    accumulatedRef.current = mode === "intervention"
      ? (typeof extraParams.baseContent === "string" ? extraParams.baseContent : "")
      : ""

    abortControllerRef.current?.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller

    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null
    try {
      const body: Record<string, unknown> = {
        streamId: newStreamId, mode, settings: llmSettings, messages: messagesForStream, ...extraParams,
      }
      const response = await fetch(`${streamingUrl}/api/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      reader = response.body?.getReader() ?? null
      if (!reader) throw new Error("No reader")
      const decoder = new TextDecoder()
      let buffer = ""
      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          failedStreamKeyRef.current = thisStreamKey
          if (!doneSentRef.current) {
            doneSentRef.current = true
            Streamlit.setComponentValue({ type: "streaming_error" as const, message: "Stream ended unexpectedly", content: accumulatedRef.current, messageId, streamKey: thisStreamKey })
          }
          break
        }
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() ?? ""
        let eventType = ""
        for (const line of lines) {
          if (line.startsWith("event:")) eventType = line.slice(6).trim()
          else if (line.startsWith("data:")) {
            const data = line.slice(5).trim()
            try {
              const parsed = JSON.parse(data)
              if (eventType === "token") {
                accumulatedRef.current = parsed.fullContent ?? (accumulatedRef.current + (parsed.text ?? ""))
                if (!isEditingRef.current) setDisplayContent(accumulatedRef.current)
              } else if (eventType === "done") {
                const finalContent = parsed.fullContent ?? accumulatedRef.current
                accumulatedRef.current = finalContent
                if (!isEditingRef.current) setDisplayContent(finalContent)
                failedStreamKeyRef.current = ""
                if (!doneSentRef.current && finalContent.length > 0) {
                  doneSentRef.current = true
                  Streamlit.setComponentValue({ type: "streaming_done" as const, content: finalContent, messageId, streamKey: thisStreamKey })
                }
                if (abortControllerRef.current === controller) setStreamId(null)
                return
              } else if (eventType === "error") {
                failedStreamKeyRef.current = thisStreamKey
                if (!doneSentRef.current) {
                  doneSentRef.current = true
                  Streamlit.setComponentValue({ type: "streaming_error" as const, message: parsed.message ?? "Unknown", content: accumulatedRef.current, messageId, streamKey: thisStreamKey })
                }
                if (abortControllerRef.current === controller) setStreamId(null)
                return
              } else if (eventType === "aborted") {
                failedStreamKeyRef.current = thisStreamKey
                if (abortControllerRef.current === controller) setStreamId(null)
                return
              }
            } catch { }
          }
        }
      }
      if (abortControllerRef.current === controller) setStreamId(null)
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        failedStreamKeyRef.current = thisStreamKey
        if (!doneSentRef.current) {
          doneSentRef.current = true
          Streamlit.setComponentValue({ type: "streaming_error" as const, message: `Fetch error: ${(err as Error).message}`, content: accumulatedRef.current, messageId, streamKey: thisStreamKey })
        }
      } else {
        failedStreamKeyRef.current = thisStreamKey
      }
      if (abortControllerRef.current === controller) setStreamId(null)
    } finally { reader?.releaseLock() }
  }, [streamingUrl, generateStreamId, messageId, messagesForStream, llmSettings])

  const interventionKeyRef = useRef("")
  const streamKeyFromData = (interventionData?.streamKey as string) || ""
  const interventionKey = streamKeyFromData || (interventionData
    ? `${interventionData.selectionStart}:${interventionData.insertion ?? ""}:${interventionData.action ?? ""}`
    : "")

  useEffect(() => {
    const keyChanged = interventionKeyRef.current !== interventionKey
    if (keyChanged) interventionKeyRef.current = interventionKey
    if (keyChanged && interventionKey) {
      completedRef.current = false
      failedStreamKeyRef.current = ""
      abortControllerRef.current?.abort()
      setStreamId(null)
    }
    const currentStreamKey = streamKeyFromData || `${messageId}:${streamModeRef.current}:${interventionKey}`
    if (isStreaming && !completedRef.current && streamingUrl && !streamId) {
      if (failedStreamKeyRef.current !== currentStreamKey) {
        completedRef.current = true
        const hasIntervention = interventionData && Object.keys(interventionData).length > 0
        if (hasIntervention) {
          startStreaming("intervention", {
            baseContent: interventionData.baseContent,
            assistantPrefix: interventionData.assistantPrefix,
            insertion: interventionData.insertion,
            action: interventionData.action,
            beforeContent: interventionData.beforeContent,
            selectionStart: interventionData.selectionStart,
            frozenMessages: interventionData.frozenMessages,
            streamKey: interventionData.streamKey,
            streamKeySuffix: interventionKey,
          })
        } else {
          startStreaming("normal")
        }
      }
    }
    if (!isStreaming) {
      completedRef.current = false
      failedStreamKeyRef.current = ""
    }
  }, [isStreaming, streamingUrl, streamId, startStreaming, interventionData, interventionKey, messageId, streamKeyFromData])

  useEffect(() => () => { abortControllerRef.current?.abort() }, [])

  useEffect(() => {
    if (!isStreaming && streamId) {
      abortControllerRef.current?.abort()
      setStreamId(null)
    }
  }, [isStreaming, streamId])

  const resetEditState = useCallback(() => {
    isEditingRef.current = false
    setSelectedLine(null)
    setSelectionStart(null)
    setDraftInsertion("")
    setEditSnapshotContent(null)
  }, [])

  const cancelEdit = useCallback(() => {
    resetEditState()
    if (isStreaming) setDisplayContent(accumulatedRef.current)
  }, [isStreaming, resetEditState])

  const sendIntervention = useCallback((action: "inline_continue" | "inline_continue_interrupt") => {
    const base = editSnapshotContent ?? displayContent
    const posInBase = clampCodePointOffset(base, selectionStart ?? codePointLength(base))
    const prefix = sliceCodePoints(base, 0, posInBase)
    const currentContent = prefix + draftInsertion
    const nextSelectionStart = codePointLength(currentContent)
    const requestId = `${messageId}:${action === "inline_continue" ? "inline" : "interrupt"}:${nextSelectionStart}:${Date.now()}`

    accumulatedRef.current = currentContent
    setDisplayContent(currentContent)
    Streamlit.setComponentValue({
      type: action,
      messageId,
      selectionStart: nextSelectionStart,
      currentContent,
      insertion: "",
      requestId,
    })
    resetEditState()
  }, [displayContent, draftInsertion, editSnapshotContent, messageId, resetEditState, selectionStart])

  const handleLineClick = useCallback((lineIndex: number) => {
    if (disabled) return
    const snapshot = displayContent
    const lines = buildRenderLines(snapshot)
    const selected = lines[lineIndex]
    if (!selected) return

    isEditingRef.current = true
    setEditSnapshotContent(snapshot)
    setSelectedLine(lineIndex)
    setSelectionStart(selected.after)
    setDraftInsertion("")
  }, [disabled, displayContent])

  const handleDraftKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const native = e.nativeEvent as KeyboardEvent
    if (isComposingRef.current || native.isComposing || native.keyCode === 229) return

    if (e.key === "Enter" && e.shiftKey) return

    if (e.key === "Enter") {
      e.preventDefault()
      if (isStreaming) {
        if (streamId) {
          fetch(`${streamingUrl}/api/abort`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ streamId }),
          }).catch(() => { })
        }
        abortControllerRef.current?.abort()
        sendIntervention("inline_continue_interrupt")
      } else {
        sendIntervention("inline_continue")
      }
    } else if (e.key === "Escape") {
      e.preventDefault()
      cancelEdit()
    }
  }, [cancelEdit, isStreaming, sendIntervention, streamId, streamingUrl])

  const renderContent = editSnapshotContent ?? displayContent
  const renderedLines = useMemo(() => buildRenderLines(renderContent), [renderContent])
  const draftRows = Math.min(6, Math.max(1, draftInsertion.split("\n").length))

  return (
    <div style={themeVars(theme)}>
      <div
        style={{
          width: "100%",
          boxSizing: "border-box",
          padding: "8px 12px",
          fontSize: "inherit",
          fontFamily: "inherit",
          lineHeight: 1.7,
          color: "var(--bw-text)",
          background: "var(--bw-surface)",
          border: "1px solid var(--bw-border)",
          borderRadius: 4,
          whiteSpace: "pre-wrap",
          wordWrap: "break-word",
        }}
      >
        {renderedLines.map((line, index) => (
          <React.Fragment key={`${index}:${line.start}:${line.end}`}>
            <div
              onClick={() => handleLineClick(index)}
              title="この行の直後から続ける"
              style={{
                cursor: disabled ? "default" : "text",
                minHeight: "1.7em",
                borderRadius: 3,
                padding: "1px 2px",
                background: selectedLine === index ? "var(--bw-bg)" : "transparent",
              }}
            >
              {line.text || "\u00A0"}
            </div>
            {selectedLine === index && (
              <textarea
                ref={inlineInputRef}
                value={draftInsertion}
                onChange={e => { setDraftInsertion(e.target.value); isEditingRef.current = true }}
                onKeyDown={handleDraftKeyDown}
                onCompositionStart={() => { isComposingRef.current = true }}
                onCompositionEnd={() => { isComposingRef.current = false }}
                rows={draftRows}
                disabled={disabled}
                placeholder="ここに書いてEnter / 空Enterでここから続ける"
                style={{
                  width: "100%",
                  boxSizing: "border-box",
                  margin: "4px 0",
                  padding: "6px 8px",
                  fontSize: "inherit",
                  fontFamily: "inherit",
                  lineHeight: 1.6,
                  color: "var(--bw-text)",
                  background: "var(--bw-bg)",
                  border: "1px solid var(--bw-primary)",
                  borderRadius: 4,
                  outline: "none",
                  resize: "vertical",
                }}
              />
            )}
          </React.Fragment>
        ))}
      </div>
      {isStreaming && (
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6, fontSize: "0.85rem", color: "var(--bw-muted)" }}>
          <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "var(--bw-primary)", animation: "bw-blink 0.9s step-end infinite" }} />
          生成中 — Enterで割り込み再生成
        </div>
      )}
    </div>
  )
}

export default LatestMessageEditor
