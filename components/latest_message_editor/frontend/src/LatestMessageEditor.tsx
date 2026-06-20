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

  const [draftContent, setDraftContent] = useState(initialContent)
  const [streamId, setStreamId] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const accumulatedRef = useRef(initialContent)
  const doneSentRef = useRef(false)
  const completedRef = useRef(false)
  const failedStreamKeyRef = useRef("")
  const streamModeRef = useRef("normal")
  const isComposingRef = useRef(false)
  const isEditingRef = useRef(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const cursorLineCount = useMemo(() => Math.max(draftContent.split("\n").length, 1), [draftContent])

  useEffect(() => { Streamlit.setFrameHeight() }, [draftContent])

  useEffect(() => {
    setDraftContent(initialContent)
    isEditingRef.current = false
  }, [initialContent])

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
        const pylines = buffer.split("\n")
        buffer = pylines.pop() ?? ""
        let eventType = ""
        for (const line of pylines) {
          if (line.startsWith("event:")) eventType = line.slice(6).trim()
          else if (line.startsWith("data:")) {
            const data = line.slice(5).trim()
            try {
              const parsed = JSON.parse(data)
              if (eventType === "token") {
                accumulatedRef.current = parsed.fullContent ?? (accumulatedRef.current + (parsed.text ?? ""))
                if (!isEditingRef.current) setDraftContent(accumulatedRef.current)
              } else if (eventType === "done") {
                const finalContent = parsed.fullContent ?? accumulatedRef.current
                accumulatedRef.current = finalContent
                if (!isEditingRef.current) setDraftContent(finalContent)
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

  const sendInlineEvent = useCallback((content: string, pos: number) => {
    const isInterrupt = isStreaming
    if (isInterrupt && streamId) {
      fetch(`${streamingUrl}/api/abort`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ streamId }) }).catch(() => { })
    }
    if (isInterrupt) abortControllerRef.current?.abort()
    const type = isInterrupt ? "inline_continue_interrupt" : "inline_continue"
    const pfx = isInterrupt ? "interrupt" : "inline"
    Streamlit.setComponentValue({
      type, messageId, currentContent: content, selectionStart: pos, insertion: "",
      requestId: `${messageId}:${pfx}:${pos}:${Date.now()}`,
    })
    isEditingRef.current = false
  }, [isStreaming, streamId, streamingUrl, messageId])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const native = e.nativeEvent as KeyboardEvent
    if (isComposingRef.current || native.isComposing || native.keyCode === 229) return
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      const ta = textareaRef.current
      if (!ta) return
      sendInlineEvent(ta.value, ta.selectionStart)
    } else if (e.key === "Escape") {
      isEditingRef.current = false
      setDraftContent(accumulatedRef.current)
    }
  }, [sendInlineEvent])

  return (
    <div style={themeVars(theme)}>
      <textarea
        ref={textareaRef}
        value={draftContent}
        onChange={e => { isEditingRef.current = true; setDraftContent(e.target.value) }}
        onFocus={() => { isEditingRef.current = true }}
        onKeyDown={handleKeyDown}
        onCompositionStart={() => { isComposingRef.current = true }}
        onCompositionEnd={() => { isComposingRef.current = false }}
        rows={cursorLineCount}
        disabled={disabled}
        style={{
          width: "100%", boxSizing: "border-box", padding: "8px 12px",
          fontSize: "inherit", fontFamily: "inherit", lineHeight: 1.7,
          color: "var(--bw-text)", background: "var(--bw-surface)",
          border: "1px solid var(--bw-border)", borderRadius: 4, outline: "none",
          resize: "none", overflow: "hidden", whiteSpace: "pre-wrap", wordWrap: "break-word",
        }}
      />
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
