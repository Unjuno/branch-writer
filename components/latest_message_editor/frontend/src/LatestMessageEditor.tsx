import React, { CSSProperties, useEffect, useMemo, useRef, useState, useCallback } from "react"
import { ComponentProps, Streamlit } from "streamlit-component-lib"

type StreamingDoneEvent = {
  type: "streaming_done"
  content: string
  messageId: string
}

type StreamingErrorEvent = {
  type: "streaming_error"
  message: string
  content: string
  messageId: string
}

type LatestMessageEditorArgs = {
  messageId?: string
  content?: string
  disabled?: boolean
  streamingUrl?: string
  isStreaming?: boolean
  interventionData?: Record<string, unknown> | null
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
  const abortControllerRef = useRef<AbortController | null>(null)
  const accumulatedRef = useRef("")
  const doneSentRef = useRef(false)
  const completedRef = useRef(false)

  const isActivelyStreaming = isStreaming && streamId !== null

  const textWithCursor = useMemo(() => {
    if (isActivelyStreaming) {
      return displayContent + "▌"
    }
    return displayContent
  }, [displayContent, isActivelyStreaming])

  useEffect(() => {
    Streamlit.setFrameHeight()
  }, [textWithCursor, hoveredLine])

  useEffect(() => {
    if (!isActivelyStreaming) {
      setDisplayContent(initialContent)
    }
  }, [initialContent, isActivelyStreaming])

  const generateStreamId = useCallback(() => {
    return `${messageId}:stream:${Date.now()}:${Math.random().toString(36).slice(2)}`
  }, [messageId])

  const startStreaming = useCallback(async (mode: string, extraParams: Record<string, unknown> = {}) => {
    if (!streamingUrl || !llmSettings) return

    const newStreamId = generateStreamId()
    console.log("[BranchWriter] startStreaming:", { mode, streamId: newStreamId })
    doneSentRef.current = false
    setStreamId(newStreamId)
    // For intervention mode, start from the assistant prefix so tokens append correctly
    accumulatedRef.current = mode === "intervention" && extraParams.assistantPrefix
      ? (extraParams.assistantPrefix as string)
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
          // Stream ended without an SSE done/error event (e.g. server crash)
          completedRef.current = false
          if (!doneSentRef.current) {
            doneSentRef.current = true
            const finalContent = accumulatedRef.current
            const errorEvent: StreamingErrorEvent = {
              type: "streaming_error",
              message: "Stream ended unexpectedly",
              content: finalContent,
              messageId,
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
                  // Intervention mode: use the pre-computed full content
                  // (includes prefix + insertion + overlap-stripped continuation)
                  accumulatedRef.current = parsed.fullContent
                  setDisplayContent(parsed.fullContent)
                } else {
                  // Normal mode: accumulate text char by char
                  accumulatedRef.current += parsed.text
                  setDisplayContent(accumulatedRef.current)
                }
              } else if (eventType === "done") {
                const finalContent = parsed.fullContent ?? accumulatedRef.current
                accumulatedRef.current = finalContent
                setDisplayContent(finalContent)
                console.log("[BranchWriter] streaming done:", { contentLen: finalContent.length })
                if (!doneSentRef.current && finalContent.length > 0) {
                  doneSentRef.current = true
                  const doneEvent: StreamingDoneEvent = {
                    type: "streaming_done",
                    content: finalContent,
                    messageId,
                  }
                  Streamlit.setComponentValue(doneEvent)
                }
                if (abortControllerRef.current === controller) {
                  setStreamId(null)
                }
                return
              } else if (eventType === "error") {
                console.error("Stream error:", parsed.message)
                completedRef.current = false
                const finalContent = accumulatedRef.current
                if (!doneSentRef.current) {
                  doneSentRef.current = true
                  const errorEvent: StreamingErrorEvent = {
                    type: "streaming_error",
                    message: parsed.message ?? "Unknown stream error",
                    content: finalContent,
                    messageId,
                  }
                  Streamlit.setComponentValue(errorEvent)
                }
                if (abortControllerRef.current === controller) {
                  setStreamId(null)
                }
                return
              } else if (eventType === "aborted") {
                completedRef.current = false
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
        completedRef.current = false
        const finalContent = accumulatedRef.current
        if (!doneSentRef.current) {
          doneSentRef.current = true
          const errorEvent: StreamingErrorEvent = {
            type: "streaming_error",
            message: `Fetch error: ${(err as Error).message}`,
            content: finalContent,
            messageId,
          }
          Streamlit.setComponentValue(errorEvent)
        }
      } else {
        // AbortError: stream was intentionally cancelled, not an error
        completedRef.current = false
      }
      if (abortControllerRef.current === controller) {
        setStreamId(null)
      }
    } finally {
      reader?.releaseLock()
    }
  }, [streamingUrl, generateStreamId, messageId, messagesForStream, llmSettings])

  const interventionKeyRef = useRef("")
  const interventionKey = interventionData
    ? `${interventionData.selectionStart}:${interventionData.insertion ?? ""}:${interventionData.action ?? ""}`
    : ""

  useEffect(() => {
    const keyChanged = interventionKeyRef.current !== interventionKey
    if (keyChanged) {
      interventionKeyRef.current = interventionKey
    }

    // When interventionData changes semantically, abort old stream and reset
    if (keyChanged && interventionKey) {
      completedRef.current = false
      abortControllerRef.current?.abort()
      setStreamId(null)
    }

    if (isStreaming && !completedRef.current && streamingUrl && !streamId) {
      completedRef.current = true
      const hasIntervention = interventionData && Object.keys(interventionData).length > 0
      if (hasIntervention) {
        startStreaming("intervention", {
          assistantPrefix: interventionData.assistantPrefix,
          insertion: interventionData.insertion,
          action: interventionData.action,
          beforeContent: interventionData.beforeContent,
          selectionStart: interventionData.selectionStart,
          frozenMessages: interventionData.frozenMessages,
        })
      } else {
        startStreaming("normal")
      }
    }
    if (!isStreaming) {
      completedRef.current = false
    }
  }, [isStreaming, streamingUrl, streamId, startStreaming, interventionData, interventionKey])

  useEffect(() => {
    return () => { abortControllerRef.current?.abort() }
  }, [])

  const selectLine = useCallback((lineIndex: number) => {
    if (disabled) return

    const lines = displayContent.split("\n")
    let charPos = 0
    for (let i = 0; i < lineIndex && i < lines.length; i++) {
      charPos += lines[i].length + 1
    }
    charPos = Math.min(charPos, displayContent.length)

    setSelectionStart(charPos)
    setHoveredLine(lineIndex)
  }, [disabled, isActivelyStreaming, displayContent])

  const confirmSelection = useCallback(() => {
    if (hoveredLine === null) return
    console.log("[BranchWriter] confirmSelection:", { selectionStart, hoveredLine })
    Streamlit.setComponentValue({ type: "line_selected", selectionStart, lineIndex: hoveredLine, messageId })
  }, [hoveredLine, selectionStart, messageId])

  const canPositionCursor = !disabled

  const lines = useMemo(() => textWithCursor.split("\n"), [textWithCursor])

  return (
    <div style={themeVars(theme)}>
      <div style={{ position: "relative" }}>
        {lines.map((line, i) => {
          const isHovered = canPositionCursor && hoveredLine === i
          return (
            <div
              key={i}
              style={{
                lineHeight: 1.7,
                cursor: canPositionCursor ? "pointer" : "default",
                background: isHovered ? "rgba(255,75,75,0.15)" : "transparent",
                borderLeft: isHovered ? "3px solid var(--bw-primary)" : "3px solid transparent",
                paddingLeft: isHovered ? 5 : 8,
                transition: "background 0.1s, border-color 0.1s",
                whiteSpace: "pre-wrap",
                wordWrap: "break-word",
                borderRadius: isHovered ? "2px 0 0 2px" : 0,
                position: "relative",
              }}
              onMouseEnter={() => canPositionCursor && selectLine(i)}
              onClick={() => canPositionCursor && confirmSelection()}
            >
              {isHovered && (
                <span style={{
                  position: "absolute",
                  left: -3,
                  top: 0,
                  bottom: 0,
                  width: 3,
                  background: "var(--bw-primary)",
                  borderRadius: "2px 0 0 2px",
                  boxShadow: "0 0 6px rgba(255,75,75,0.5)",
                }} />
              )}
              {line || "\u00a0"}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default LatestMessageEditor
