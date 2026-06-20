import React, { CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ComponentProps, Streamlit } from "streamlit-component-lib"

type StreamingDoneEvent = { type: "streaming_done"; content: string; messageId: string; streamKey?: string }
type StreamingErrorEvent = { type: "streaming_error"; message: string; content: string; messageId: string; streamKey?: string }

type LatestMessageEditorArgs = {
  messageId?: string; content?: string; disabled?: boolean; streamingUrl?: string
  isStreaming?: boolean; interventionData?: Record<string, unknown> | null
  cursorLoopEnabled?: boolean; previewContent?: string
  messagesForStream?: Array<{ role: string; content: string; id: string }>
  llmSettings?: {
    base_url: string; api_key: string; model: string; temperature: number
    max_tokens: number; system_prompt: string; request_timeout_seconds: number; context_window: number
  } | null
}

type StreamlitTheme = { base?: "light" | "dark"; primaryColor?: string; backgroundColor?: string; secondaryBackgroundColor?: string; textColor?: string; font?: string }

function themeVars(theme?: StreamlitTheme): CSSProperties {
  const isDark = theme?.base === "dark"
  const textColor = theme?.textColor ?? (isDark ? "#fafafa" : "#31333f")
  const mutedColor = isDark ? "rgba(250,250,250,0.55)" : "rgba(49,51,63,0.55)"
  const borderColor = isDark ? "rgba(250,250,250,0.12)" : "rgba(49,51,63,0.12)"
  const primaryColor = theme?.primaryColor ?? "#ff4b4b"
  const bg = isDark ? "rgba(14,17,23,0.6)" : "rgba(255,255,255,0.85)"
  const surface = isDark ? "rgba(38,39,48,0.5)" : "rgba(240,242,246,0.6)"
  return {
    "--bw-text": textColor, "--bw-muted": mutedColor, "--bw-border": borderColor,
    "--bw-primary": primaryColor, "--bw-bg": bg, "--bw-surface": surface,
    fontFamily: theme?.font,
  } as CSSProperties
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
  const [streamId, setStreamId] = useState<string | null>(null)
  const [hoveredLine, setHoveredLine] = useState<number | null>(null)
  const [selectedLine, setSelectedLine] = useState<number | null>(null)
  const [selectionStart, setSelectionStart] = useState(0)
  const [draftInsertion, setDraftInsertion] = useState("")
  const [editSnapshotContent, setEditSnapshotContent] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const accumulatedRef = useRef("")
  const doneSentRef = useRef(false)
  const completedRef = useRef(false)
  const failedStreamKeyRef = useRef("")
  const streamModeRef = useRef("normal")
  const isComposingRef = useRef(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const isActivelyStreaming = isStreaming && streamId !== null
  const renderContent = editSnapshotContent ?? (isActivelyStreaming ? displayContent + "\u258c" : displayContent)
  const lines = useMemo(() => renderContent.split("\n"), [renderContent])

  useEffect(() => { Streamlit.setFrameHeight() }, [renderContent, selectedLine])

  useEffect(() => {
    setDisplayContent(initialContent)
    setEditSnapshotContent(null)
    setSelectedLine(null)
    setDraftInsertion("")
    setHoveredLine(null)
  }, [initialContent])

  useEffect(() => {
    if (selectedLine !== null && inputRef.current) {
      inputRef.current.focus()
    }
  }, [selectedLine])

  const generateStreamId = useCallback(() => `${messageId}:stream:${Date.now()}:${Math.random().toString(36).slice(2)}`, [messageId])

  const startStreaming = useCallback(async (mode: string, extraParams: Record<string, unknown> = {}) => {
    if (!streamingUrl || !llmSettings) return
    const newStreamId = generateStreamId()
    streamModeRef.current = mode
    const thisStreamKey = (extraParams.streamKey as string) || `${messageId}:${mode}:${extraParams.streamKeySuffix ?? ""}`
    doneSentRef.current = false
    failedStreamKeyRef.current = ""
    setStreamId(newStreamId)
    accumulatedRef.current = mode === "intervention" ? (typeof extraParams.baseContent === "string" ? extraParams.baseContent : "") : ""
    abortControllerRef.current?.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller
    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null
    try {
      const body: Record<string, unknown> = { streamId: newStreamId, mode, settings: llmSettings, messages: messagesForStream, ...extraParams }
      const response = await fetch(`${streamingUrl}/api/stream`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: controller.signal,
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
                setDisplayContent(accumulatedRef.current)
              } else if (eventType === "done") {
                const finalContent = parsed.fullContent ?? accumulatedRef.current
                accumulatedRef.current = finalContent
                setDisplayContent(finalContent)
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
      } else { failedStreamKeyRef.current = thisStreamKey }
      if (abortControllerRef.current === controller) setStreamId(null)
    } finally { reader?.releaseLock() }
  }, [streamingUrl, generateStreamId, messageId, messagesForStream, llmSettings])

  const interventionKeyRef = useRef("")
  const streamKeyFromData = (interventionData?.streamKey as string) || ""
  const interventionKey = streamKeyFromData || (interventionData
    ? `${interventionData.selectionStart}:${interventionData.insertion ?? ""}:${interventionData.action ?? ""}` : "")

  useEffect(() => {
    const keyChanged = interventionKeyRef.current !== interventionKey
    if (keyChanged) interventionKeyRef.current = interventionKey
    if (keyChanged && interventionKey) {
      completedRef.current = false; failedStreamKeyRef.current = ""; abortControllerRef.current?.abort(); setStreamId(null)
    }
    const currentStreamKey = streamKeyFromData || `${messageId}:${streamModeRef.current}:${interventionKey}`
    if (isStreaming && !completedRef.current && streamingUrl && !streamId) {
      if (failedStreamKeyRef.current !== currentStreamKey) {
        completedRef.current = true
        const hasIntervention = interventionData && Object.keys(interventionData).length > 0
        if (hasIntervention) {
          startStreaming("intervention", {
            baseContent: interventionData.baseContent, assistantPrefix: interventionData.assistantPrefix,
            insertion: interventionData.insertion, action: interventionData.action,
            beforeContent: interventionData.beforeContent, selectionStart: interventionData.selectionStart,
            frozenMessages: interventionData.frozenMessages, streamKey: interventionData.streamKey,
            streamKeySuffix: interventionKey,
          })
        } else { startStreaming("normal") }
      }
    }
    if (!isStreaming) { completedRef.current = false; failedStreamKeyRef.current = "" }
  }, [isStreaming, streamingUrl, streamId, startStreaming, interventionData, interventionKey, messageId, streamKeyFromData])

  useEffect(() => () => { abortControllerRef.current?.abort() }, [])
  useEffect(() => {
    if (!isStreaming && streamId) { abortControllerRef.current?.abort(); setStreamId(null) }
  }, [isStreaming, streamId])

  const calcLinePos = useCallback((lineIndex: number, content: string): number => {
    const codePoints = content.split("\n").map(l => Array.from(l).length)
    let pos = 0
    for (let i = 0; i < lineIndex && i < codePoints.length; i++) pos += codePoints[i] + 1
    return Math.min(pos, Array.from(content).length)
  }, [])

  const sendInlineEvent = useCallback((pos: number, insertion: string) => {
    const isInterrupt = isStreaming
    if (isInterrupt && streamId) {
      fetch(`${streamingUrl}/api/abort`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ streamId }) }).catch(() => { })
    }
    if (isInterrupt) abortControllerRef.current?.abort()
    const type = isInterrupt ? "inline_continue_interrupt" : "inline_continue"
    const prefix = isInterrupt ? "interrupt" : "inline"
    Streamlit.setComponentValue({
      type, messageId, currentContent: displayContent, selectionStart: pos, insertion,
      requestId: `${messageId}:${prefix}:${pos}:${Date.now()}`,
    })
    setSelectedLine(null)
    setDraftInsertion("")
    setEditSnapshotContent(null)
    setHoveredLine(null)
  }, [isStreaming, streamId, streamingUrl, messageId, displayContent])

  const handleContainerKeyDown = useCallback((e: React.KeyboardEvent<HTMLDivElement>) => {
    const native = e.nativeEvent as KeyboardEvent
    if (isComposingRef.current || native.isComposing || native.keyCode === 229) return
    if (selectedLine !== null) return
    if (hoveredLine === null) return

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      const pos = calcLinePos(hoveredLine, displayContent)
      sendInlineEvent(pos, "")
    } else if (e.key === "Escape") {
      setHoveredLine(null)
    } else if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault()
      const base = displayContent
      const pos = calcLinePos(hoveredLine, base)
      setEditSnapshotContent(base)
      setSelectionStart(pos)
      setSelectedLine(hoveredLine)
      setDraftInsertion(e.key)
    }
  }, [hoveredLine, selectedLine, displayContent, calcLinePos, sendInlineEvent])

  const handleInputKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    const native = e.nativeEvent as KeyboardEvent
    if (isComposingRef.current || native.isComposing || native.keyCode === 229) return
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      sendInlineEvent(selectionStart, draftInsertion)
    } else if (e.key === "Escape") {
      setSelectedLine(null)
      setDraftInsertion("")
      setEditSnapshotContent(null)
    }
  }, [selectionStart, draftInsertion, sendInlineEvent])

  const canClick = !disabled

  return (
    <div style={themeVars(theme)}>
      <div
        ref={containerRef}
        tabIndex={-1}
        style={{ outline: "none", position: "relative" }}
        onKeyDown={handleContainerKeyDown}
        onMouseEnter={() => {
          const active = document.activeElement
          if (active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA")) return
          containerRef.current?.focus()
        }}
        onMouseLeave={() => { if (selectedLine === null) setHoveredLine(null) }}
      >
        {lines.map((line, i) => {
          const isHovered = canClick && (hoveredLine === i || selectedLine === i)
          return (
            <React.Fragment key={i}>
              <div
                style={{
                  lineHeight: 1.7, cursor: canClick ? "pointer" : "default",
                  background: isHovered ? "rgba(255,75,75,0.12)" : "transparent",
                  borderLeft: isHovered ? "3px solid var(--bw-primary)" : "3px solid transparent",
                  paddingLeft: isHovered ? 5 : 8,
                  transition: "background 0.1s, border-color 0.1s",
                  whiteSpace: "pre-wrap", wordWrap: "break-word",
                  borderRadius: isHovered ? "2px 0 0 2px" : 0,
                }}
                onMouseEnter={() => setHoveredLine(i)}
                onMouseLeave={() => setHoveredLine(prev => prev === i ? null : prev)}
              >
                {line || "\u00a0"}
              </div>
              {selectedLine === i && (
                <div style={{ margin: "4px 0 8px 0", display: "flex", gap: 6, alignItems: "center" }}>
                  <input
                    ref={inputRef}
                    type="text"
                    value={draftInsertion}
                    onChange={e => setDraftInsertion(e.target.value)}
                    onKeyDown={handleInputKeyDown}
                    onCompositionStart={() => { isComposingRef.current = true }}
                    onCompositionEnd={() => { isComposingRef.current = false }}
                    placeholder={"\u258c\u258c Enter\u3067\u3053\u3053\u304b\u3089\u518d\u751f\u6210"}
                    style={{
                      flex: 1, padding: "8px 12px", fontSize: "inherit", fontFamily: "inherit",
                      color: "var(--bw-text)", background: "var(--bw-bg)",
                      border: "1px solid var(--bw-border)", borderRadius: 4, outline: "none",
                      boxSizing: "border-box",
                    }}
                  />
                </div>
              )}
            </React.Fragment>
          )
        })}
        {isStreaming && selectedLine === null && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6, fontSize: "0.85rem", color: "var(--bw-muted)" }}>
            <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: "var(--bw-primary)", animation: "bw-blink 0.9s step-end infinite" }} />
            \u751f\u6210\u4e2d \u2014 Enter\u3067\u5272\u308a\u8fbc\u307f\u518d\u751f\u6210
          </div>
        )}
      </div>
    </div>
  )
}

export default LatestMessageEditor
