import React, { CSSProperties, useEffect, useMemo, useRef, useState, useCallback } from "react"
import { ComponentProps, Streamlit } from "streamlit-component-lib"

type StreamingDoneEvent = {
  type: "streaming_done"
  content: string
  messageId: string
  streamKey?: string
}

type StreamingErrorEvent = {
  type: "streaming_error"
  message: string
  content: string
  messageId: string
  streamKey?: string
}

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
  const [cursorPosition, setCursorPosition] = useState(0)
  const [streamId, setStreamId] = useState<string | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const accumulatedRef = useRef("")
  const doneSentRef = useRef(false)
  const completedRef = useRef(false)
  const failedStreamKeyRef = useRef("")
  const streamModeRef = useRef("normal")
  const isComposingRef = useRef(false)
  const userEditedRef = useRef(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    Streamlit.setFrameHeight()
  }, [draftContent])

  useEffect(() => {
    setDraftContent(initialContent)
    userEditedRef.current = false
  }, [initialContent])

  const getInterventionBase = (p: Record<string, unknown>): string => {
    if (typeof p.baseContent === "string") return p.baseContent
    const prefix = typeof p.assistantPrefix === "string" ? p.assistantPrefix : ""
    const insertion = typeof p.insertion === "string" ? p.insertion : ""
    return prefix + insertion
  }

  const generateStreamId = useCallback(() => {
    return `${messageId}:stream:${Date.now()}:${Math.random().toString(36).slice(2)}`
  }, [messageId])

  const startStreaming = useCallback(async (mode: string, extraParams: Record<string, unknown> = {}) => {
    if (!streamingUrl || !llmSettings) return

    const newStreamId = generateStreamId()
    streamModeRef.current = mode
    const thisStreamKey = (extraParams.streamKey as string) || `${messageId}:${mode}:${extraParams.streamKeySuffix ?? ""}`
    console.log("[BranchWriter] startStreaming:", { mode, streamId: newStreamId, streamKey: thisStreamKey })
    doneSentRef.current = false
    failedStreamKeyRef.current = ""
    setStreamId(newStreamId)
    accumulatedRef.current = mode === "intervention"
      ? getInterventionBase(extraParams)
      : ""

    abortControllerRef.current?.abort()
    const controller = new AbortController()
    abortControllerRef.current = controller

    let reader: ReadableStreamDefaultReader<Uint8Array> | null = null
    try {
      const body: Record<string, unknown> = {
        streamId: newStreamId,
        mode,
        settings: llmSettings,
        messages: messagesForStream,
        ...extraParams,
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
            const finalContent = accumulatedRef.current
            const errorEvent: StreamingErrorEvent = {
              type: "streaming_error",
              message: "Stream ended unexpectedly",
              content: finalContent,
              messageId,
              streamKey: thisStreamKey,
            }
            Streamlit.setComponentValue(errorEvent)
          }
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split("\n")
        buffer = lines.pop() ?? ""

        let eventType = ""
        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventType = line.slice(6).trim()
          } else if (line.startsWith("data:")) {
            const data = line.slice(5).trim()
            try {
              const parsed = JSON.parse(data)
              if (eventType === "token") {
                if (parsed.fullContent) {
                  accumulatedRef.current = parsed.fullContent
                } else {
                  accumulatedRef.current += parsed.text
                }
                if (!userEditedRef.current) {
                  setDraftContent(accumulatedRef.current)
                }
              } else if (eventType === "done") {
                const finalContent = parsed.fullContent ?? accumulatedRef.current
                accumulatedRef.current = finalContent
                setDraftContent(finalContent)
                console.log("[BranchWriter] streaming done:", { contentLen: finalContent.length, streamKey: thisStreamKey })
                failedStreamKeyRef.current = ""
                if (!doneSentRef.current && finalContent.length > 0) {
                  doneSentRef.current = true
                  const doneEvent: StreamingDoneEvent = {
                    type: "streaming_done",
                    content: finalContent,
                    messageId,
                    streamKey: thisStreamKey,
                  }
                  Streamlit.setComponentValue(doneEvent)
                }
                if (abortControllerRef.current === controller) {
                  setStreamId(null)
                }
                return
              } else if (eventType === "error") {
                console.error("Stream error:", parsed.message)
                failedStreamKeyRef.current = thisStreamKey
                const finalContent = accumulatedRef.current
                if (!doneSentRef.current) {
                  doneSentRef.current = true
                  const errorEvent: StreamingErrorEvent = {
                    type: "streaming_error",
                    message: parsed.message ?? "Unknown stream error",
                    content: finalContent,
                    messageId,
                    streamKey: thisStreamKey,
                  }
                  Streamlit.setComponentValue(errorEvent)
                }
                if (abortControllerRef.current === controller) {
                  setStreamId(null)
                }
                return
              } else if (eventType === "aborted") {
                failedStreamKeyRef.current = thisStreamKey
                if (abortControllerRef.current === controller) {
                  setStreamId(null)
                }
                return
              }
            } catch { /* ignore */ }
          }
        }
      }
      if (abortControllerRef.current === controller) {
        setStreamId(null)
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        console.error("Streaming error:", err)
        failedStreamKeyRef.current = thisStreamKey
        const finalContent = accumulatedRef.current
        if (!doneSentRef.current) {
          doneSentRef.current = true
          const errorEvent: StreamingErrorEvent = {
            type: "streaming_error",
            message: `Fetch error: ${(err as Error).message}`,
            content: finalContent,
            messageId,
            streamKey: thisStreamKey,
          }
          Streamlit.setComponentValue(errorEvent)
        }
      } else {
        failedStreamKeyRef.current = thisStreamKey
      }
      if (abortControllerRef.current === controller) {
        setStreamId(null)
      }
    } finally {
      reader?.releaseLock()
    }
  }, [streamingUrl, generateStreamId, messageId, messagesForStream, llmSettings])

  const interventionKeyRef = useRef("")
  const streamKeyFromData = (interventionData?.streamKey as string) || ""
  const interventionKey = streamKeyFromData || (interventionData
    ? `${interventionData.selectionStart}:${interventionData.insertion ?? ""}:${interventionData.action ?? ""}`
    : "")

  useEffect(() => {
    const keyChanged = interventionKeyRef.current !== interventionKey
    if (keyChanged) {
      interventionKeyRef.current = interventionKey
    }

    if (keyChanged && interventionKey) {
      completedRef.current = false
      failedStreamKeyRef.current = ""
      abortControllerRef.current?.abort()
      setStreamId(null)
      userEditedRef.current = false
    }

    const currentStreamKey = streamKeyFromData || `${messageId}:${streamModeRef.current}:${interventionKey}`

    if (isStreaming && !completedRef.current && streamingUrl && !streamId) {
      if (failedStreamKeyRef.current === currentStreamKey) {
        console.log("[BranchWriter] skip re-stream (previous attempt failed):", currentStreamKey)
      } else {
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

  useEffect(() => {
    return () => { abortControllerRef.current?.abort() }
  }, [])

  useEffect(() => {
    if (!isStreaming && streamId) {
      abortControllerRef.current?.abort()
      setStreamId(null)
    }
  }, [isStreaming, streamId])

  const handleChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setDraftContent(e.target.value)
    userEditedRef.current = true
  }, [])

  const updateCursor = useCallback((e: React.SyntheticEvent<HTMLTextAreaElement>) => {
    setCursorPosition(e.currentTarget.selectionStart)
  }, [])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const native = e.nativeEvent as KeyboardEvent
    if (isComposingRef.current || native.isComposing || native.keyCode === 229) return

    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      const ta = textareaRef.current
      if (!ta) return
      const pos = ta.selectionStart
      const content = ta.value

      if (isStreaming) {
        if (streamId) {
          fetch(`${streamingUrl}/api/abort`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ streamId }),
          }).catch(() => {})
        }
        abortControllerRef.current?.abort()
        Streamlit.setComponentValue({
          type: "inline_continue_interrupt",
          messageId,
          selectionStart: pos,
          currentContent: content,
          requestId: `${messageId}:interrupt:${pos}:${Date.now()}`,
        })
      } else {
        Streamlit.setComponentValue({
          type: "inline_continue",
          messageId,
          selectionStart: pos,
          currentContent: content,
          requestId: `${messageId}:inline:${pos}:${Date.now()}`,
        })
      }
    } else if (e.key === "Escape") {
      setDraftContent(initialContent)
      userEditedRef.current = false
    }
  }, [messageId, isStreaming, streamId, streamingUrl, initialContent])

  const cursorLineCount = useMemo(() => {
    return Math.max(draftContent.split("\n").length, 1)
  }, [draftContent])

  return (
    <div style={themeVars(theme)}>
      <textarea
        ref={textareaRef}
        value={draftContent}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        onSelect={updateCursor}
        onKeyUp={updateCursor}
        onClick={updateCursor}
        onCompositionStart={() => { isComposingRef.current = true }}
        onCompositionEnd={() => { isComposingRef.current = false }}
        rows={cursorLineCount}
        disabled={disabled}
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
          outline: "none",
          resize: "none",
          overflow: "hidden",
          whiteSpace: "pre-wrap",
          wordWrap: "break-word",
        }}
      />
      {isStreaming && (
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: 6,
          marginTop: 6,
          fontSize: "0.85rem",
          color: "var(--bw-muted)",
        }}>
          <span style={{
            display: "inline-block",
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: "var(--bw-primary)",
            animation: "bw-blink 0.9s step-end infinite",
          }} />
          生成中 — Enterで割り込み再生成
        </div>
      )}
    </div>
  )
}

export default LatestMessageEditor
