import React, { CSSProperties, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react"
import { ComponentProps, Streamlit } from "streamlit-component-lib"

type StreamingDoneEvent = { type: "streaming_done"; content: string; messageId: string; streamKey?: string }
type StreamingErrorEvent = { type: "streaming_error"; message: string; content: string; messageId: string; streamKey?: string }

type LatestMessageEditorArgs = {
  messageId?: string; content?: string; disabled?: boolean; streamingUrl?: string
  isStreaming?: boolean; interventionData?: Record<string, unknown> | null
  cursorLoopEnabled?: boolean; previewContent?: string
  messagesForStream?: Array<{ role: string; content: string; id: string }>
  keywordFilter?: { enabled?: boolean; words?: string } | null
  llmSettings?: {
    base_url: string; api_key: string; model: string; temperature: number
    max_tokens: number; system_prompt: string; request_timeout_seconds: number; context_window: number
  } | null
}

type StreamlitTheme = { base?: "light" | "dark"; primaryColor?: string; backgroundColor?: string; secondaryBackgroundColor?: string; textColor?: string; font?: string }

function parseBadWords(words: string): string[] {
  return words.split(",").map((word) => word.trim()).filter(Boolean)
}

function containsBadWord(text: string, words: string[]): boolean {
  const textLower = text.toLowerCase()
  return words.some((word) => textLower.includes(word.toLowerCase()))
}

function themeVars(theme?: StreamlitTheme): CSSProperties {
  const isDark = theme?.base === "dark"
  const textColor = theme?.textColor ?? (isDark ? "#fafafa" : "#262730")
  const mutedColor = isDark ? "rgba(250,250,250,0.52)" : "rgba(38,39,48,0.55)"
  const primaryColor = theme?.primaryColor ?? "#ff4b4b"
  return {
    "--bw-text": textColor, "--bw-muted": mutedColor,
    "--bw-primary": primaryColor,
    fontFamily: theme?.font,
  } as CSSProperties
}

function codePointOffsetFromDomOffset(text: string, domOffset: number): number {
  let count = 0
  const iter = text[Symbol.iterator]()
  let pos = 0
  for (const ch of iter) {
    if (pos >= domOffset) break
    pos += ch.length
    count++
  }
  return count
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
  const keywordFilter = args.keywordFilter ?? null
  const keywordWords = keywordFilter?.enabled ? parseBadWords(keywordFilter.words ?? "") : []
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
  const selectionRef = useRef<{ start: number; end: number } | null>(null)
  const isStreamUpdateRef = useRef(false)

  useEffect(() => {
    const id = window.requestAnimationFrame(() => {
      Streamlit.setFrameHeight()
    })
    return () => window.cancelAnimationFrame(id)
  }, [draftContent])

  useEffect(() => {
    if (!isEditingRef.current) {
      isStreamUpdateRef.current = true
      setDraftContent(initialContent)
    }
  }, [initialContent])

  useLayoutEffect(() => {
    if (!isStreamUpdateRef.current) return
    isStreamUpdateRef.current = false
    const ta = textareaRef.current
    if (ta && selectionRef.current && document.activeElement === ta) {
      const clamped = {
        start: Math.min(selectionRef.current.start, ta.value.length),
        end: Math.min(selectionRef.current.end, ta.value.length),
      }
      if (ta.selectionStart !== clamped.start || ta.selectionEnd !== clamped.end) {
        ta.setSelectionRange(clamped.start, clamped.end)
      }
    }
  })

  useLayoutEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = "auto"
    ta.style.height = `${Math.min(ta.scrollHeight, 520)}px`
  }, [draftContent])

  const generateStreamId = useCallback(() => `${messageId}:stream:${Date.now()}:${Math.random().toString(36).slice(2)}`, [messageId])

  const startStreaming = useCallback(async (mode: string, extraParams: Record<string, unknown> = {}) => {
    if (!streamingUrl || !llmSettings) return
    const newStreamId = generateStreamId()
    streamModeRef.current = mode
    const thisStreamKey = (extraParams.streamKey as string) || `${messageId}:${mode}:${extraParams.streamKeySuffix ?? ""}`
    doneSentRef.current = false
    failedStreamKeyRef.current = ""
    setStreamId(newStreamId)
    const baseContent = mode === "intervention" && typeof extraParams.baseContent === "string"
      ? extraParams.baseContent : ""
    const keywordCheckStart = baseContent.length
    accumulatedRef.current = mode === "intervention" ? baseContent : ""
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
                const nextContent = parsed.fullContent ?? (accumulatedRef.current + (parsed.text ?? ""))
                if (nextContent.length >= accumulatedRef.current.length) {
                  accumulatedRef.current = nextContent
                }
                if (!isEditingRef.current) {
                  isStreamUpdateRef.current = true
                  setDraftContent(accumulatedRef.current)
                }
                const keywordCheckText = accumulatedRef.current.slice(keywordCheckStart)
                if (keywordWords.length > 0 && containsBadWord(keywordCheckText, keywordWords)) {
                  failedStreamKeyRef.current = ""
                  if (!doneSentRef.current) {
                    doneSentRef.current = true
                    controller.abort()
                    Streamlit.setComponentValue({ type: "streaming_done" as const, content: accumulatedRef.current, messageId, streamKey: thisStreamKey })
                  }
                  if (abortControllerRef.current === controller) setStreamId(null)
                  return
                }
              } else if (eventType === "done") {
                const finalContent = parsed.fullContent ?? accumulatedRef.current
                accumulatedRef.current = finalContent
                if (!isEditingRef.current) {
                  isStreamUpdateRef.current = true
                  setDraftContent(finalContent)
                }
                failedStreamKeyRef.current = ""
                if (!doneSentRef.current && !completedRef.current && finalContent.length > 0) {
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
  }, [streamingUrl, generateStreamId, messageId, messagesForStream, llmSettings, keywordWords])

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
            generationPrefix: interventionData.generationPrefix,
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

  const handleSelect = useCallback(() => {
    const ta = textareaRef.current
    if (ta && document.activeElement === ta) {
      selectionRef.current = { start: ta.selectionStart, end: ta.selectionEnd }
    }
  }, [])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const native = e.nativeEvent as KeyboardEvent
    if (isComposingRef.current || native.isComposing || native.keyCode === 229) return
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      const ta = textareaRef.current
      if (!ta) return
      sendInlineEvent(ta.value, codePointOffsetFromDomOffset(ta.value, ta.selectionStart))
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
        onChange={e => {
          isEditingRef.current = true
          const ta = e.currentTarget
          selectionRef.current = { start: ta.selectionStart, end: ta.selectionEnd }
          setDraftContent(ta.value)
        }}
        onKeyDown={handleKeyDown}
        onSelect={handleSelect}
        onMouseUp={handleSelect}
        onKeyUp={handleSelect}
        onCompositionStart={() => { isComposingRef.current = true }}
        onCompositionEnd={() => { isComposingRef.current = false }}
        disabled={disabled}
        style={{
          width: "100%", boxSizing: "border-box", padding: "8px 12px",
          fontSize: "inherit", fontFamily: "inherit", lineHeight: 1.7,
          color: "var(--bw-text)", background: "transparent",
          border: "none", borderRadius: 0, outline: "none", boxShadow: "none",
          minHeight: "3rem", maxHeight: "520px", resize: "none", overflowY: "auto",
          whiteSpace: "pre-wrap", wordWrap: "break-word",
        }}
      />
    </div>
  )
}

export default LatestMessageEditor
