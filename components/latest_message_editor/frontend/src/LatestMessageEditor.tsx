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

  const [selectionStart, setSelectionStart] = useState(0)
  const [displayContent, setDisplayContent] = useState(initialContent)
  const [streamId, setStreamId] = useState<string | null>(null)
  const [hoveredLine, setHoveredLine] = useState<number | null>(null)
  const [selectedLine, setSelectedLine] = useState<number | null>(null)
  const [draftInsertion, setDraftInsertion] = useState("")
  const abortControllerRef = useRef<AbortController | null>(null)
  const accumulatedRef = useRef("")
  const doneSentRef = useRef(false)
  const completedRef = useRef(false)
  const failedStreamKeyRef = useRef("")
  const streamModeRef = useRef("normal")
  const isComposingRef = useRef(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const isActivelyStreaming = isStreaming && streamId !== null

  const textWithCursor = useMemo(() => {
    if (isActivelyStreaming) {
      return displayContent + "▌"
    }
    return displayContent
  }, [displayContent, isActivelyStreaming])

  useEffect(() => {
    Streamlit.setFrameHeight()
  }, [textWithCursor, hoveredLine, selectedLine])

  useEffect(() => {
    if (!isActivelyStreaming) {
      setDisplayContent(initialContent)
    }
  }, [initialContent, isActivelyStreaming])

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
                  setDisplayContent(parsed.fullContent)
                } else {
                  accumulatedRef.current += parsed.text
                  setDisplayContent(accumulatedRef.current)
                }
              } else if (eventType === "done") {
                const finalContent = parsed.fullContent ?? accumulatedRef.current
                accumulatedRef.current = finalContent
                setDisplayContent(finalContent)
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

  const clickLine = useCallback((lineIndex: number) => {
    if (disabled || isActivelyStreaming) return
    if (selectedLine === lineIndex) {
      setSelectedLine(null)
      setDraftInsertion("")
      return
    }
    const base = initialContent
    const lines = base.split("\n")
    const codePointCounts = lines.map(l => Array.from(l).length)
    let charPos = 0
    for (let i = 0; i < lineIndex && i < lines.length; i++) {
      charPos += codePointCounts[i] + 1
    }
    const totalCodePoints = Array.from(base).length
    charPos = Math.min(charPos, totalCodePoints)
    setSelectionStart(charPos)
    setSelectedLine(lineIndex)
    setDraftInsertion("")
  }, [disabled, isActivelyStreaming, initialContent, selectedLine])

  useEffect(() => {
    if (selectedLine !== null && inputRef.current) {
      inputRef.current.focus()
    }
  }, [selectedLine])

  const handleInputKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (isComposingRef.current) return
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      if (selectedLine !== null) {
        Streamlit.setComponentValue({
          type: "inline_continue",
          messageId,
          selectionStart,
          insertion: draftInsertion,
          requestId: `${messageId}:inline:${selectionStart}:${Date.now()}`,
        })
      }
    } else if (e.key === "Escape") {
      setSelectedLine(null)
      setDraftInsertion("")
    }
  }, [selectedLine, selectionStart, draftInsertion, messageId])

  const canClick = !disabled && !isActivelyStreaming
  const lines = useMemo(() => textWithCursor.split("\n"), [textWithCursor])

  return (
    <div style={themeVars(theme)}>
      <div style={{ position: "relative" }}>
        {lines.map((line, i) => {
          const isHovered = canClick && hoveredLine === i
          const isSelected = canClick && selectedLine === i
          return (
            <React.Fragment key={i}>
              <div
                style={{
                  lineHeight: 1.7,
                  cursor: canClick ? "pointer" : "default",
                  background: isSelected
                    ? "rgba(255,75,75,0.12)"
                    : isHovered
                      ? "rgba(255,75,75,0.06)"
                      : "transparent",
                  borderLeft: isSelected
                    ? "3px solid var(--bw-primary)"
                    : isHovered
                      ? "3px solid rgba(255,75,75,0.4)"
                      : "3px solid transparent",
                  paddingLeft: isSelected || isHovered ? 5 : 8,
                  transition: "background 0.1s, border-color 0.1s",
                  whiteSpace: "pre-wrap",
                  wordWrap: "break-word",
                  borderRadius: isSelected || isHovered ? "2px 0 0 2px" : 0,
                  position: "relative",
                }}
                onMouseEnter={() => canClick && setHoveredLine(i)}
                onMouseLeave={() => canClick && setHoveredLine(null)}
                onClick={() => canClick && clickLine(i)}
              >
                {line || "\u00a0"}
              </div>
              {isSelected && !isActivelyStreaming && (
                <div style={{ margin: "4px 0 8px 0" }}>
                  <input
                    ref={inputRef}
                    type="text"
                    value={draftInsertion}
                    onChange={e => setDraftInsertion(e.target.value)}
                    onKeyDown={handleInputKeyDown}
                    onCompositionStart={() => { isComposingRef.current = true }}
                    onCompositionEnd={() => { isComposingRef.current = false }}
                    disabled={disabled}
                    placeholder="入力してEnter / 空Enterでここから再生成"
                    style={{
                      width: "100%",
                      boxSizing: "border-box",
                      padding: "8px 12px",
                      fontSize: "inherit",
                      fontFamily: "inherit",
                      color: "var(--bw-text)",
                      background: "var(--bw-bg)",
                      border: "1px solid var(--bw-border)",
                      borderRadius: 4,
                      outline: "none",
                    }}
                  />
                </div>
              )}
            </React.Fragment>
          )
        })}
      </div>
    </div>
  )
}

export default LatestMessageEditor
