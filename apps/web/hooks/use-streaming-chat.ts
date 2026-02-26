'use client'

import { useState, useCallback, useRef } from 'react'
import type { ChatMessage, SSEEvent, ToolInvocation } from '@/lib/types'

interface UseStreamingChatOptions {
  /** The SSE endpoint URL — can be a Next.js route or your FastAPI URL */
  api: string
}

interface UseStreamingChatReturn {
  messages: ChatMessage[]
  sendMessage: (text: string) => void
  status: 'ready' | 'streaming' | 'error'
  stop: () => void
  reset: () => void
  error: string | null
}

let msgCounter = 0
function newId() {
  return `msg-${Date.now()}-${++msgCounter}`
}

/**
 * Custom streaming chat hook — replaces AI SDK's useChat.
 *
 * Consumes standard SSE from any backend (FastAPI, Express, etc.)
 * and builds a ChatMessage[] array with text and tool-invocation parts.
 */
export function useStreamingChat({ api }: UseStreamingChatOptions): UseStreamingChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [status, setStatus] = useState<'ready' | 'streaming' | 'error'>('ready')
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const stop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setStatus('ready')
  }, [])

  const reset = useCallback(() => {
    stop()
    setMessages([])
    setError(null)
  }, [stop])

  const sendMessage = useCallback(
    async (text: string) => {
      // Add user message
      const userMsg: ChatMessage = {
        id: newId(),
        role: 'user',
        parts: [{ type: 'text', text }],
        createdAt: new Date(),
      }

      const assistantId = newId()
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        parts: [],
        createdAt: new Date(),
      }

      setMessages((prev) => [...prev, userMsg, assistantMsg])
      setStatus('streaming')
      setError(null)

      const controller = new AbortController()
      abortRef.current = controller

      try {
        // Build history for context (exclude the in-progress assistant message)
        const history = [...messages, userMsg].map((m) => ({
          role: m.role,
          content: m.parts
            .filter((p): p is { type: 'text'; text: string } => p.type === 'text')
            .map((p) => p.text)
            .join(''),
        }))

        const response = await fetch(api, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ messages: history }),
          signal: controller.signal,
        })

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`)
        }

        if (!response.body) {
          throw new Error('No response body')
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        // We accumulate the assistant message state here and push updates via setMessages
        let currentReasoning = '' // text streamed before the first tool call
        let currentText = ''      // text streamed after tool calls finish
        let hasSeenToolCall = false
        const toolInvocations = new Map<string, ToolInvocation>()

        const buildParts = () => {
          const parts: ChatMessage['parts'] = []
          const hasTools = toolInvocations.size > 0

          // Show pre-tool text as regular text (preamble like "Let me check that for you!")
          // only when tools were actually used; otherwise it merges into the final text below.
          if (hasTools && currentReasoning) {
            parts.push({ type: 'text', text: currentReasoning })
          }

          for (const inv of toolInvocations.values()) {
            parts.push({ type: 'tool-invocation', toolInvocation: { ...inv } })
          }

          const textContent = hasTools ? currentText : currentReasoning + currentText
          if (textContent) {
            parts.push({ type: 'text', text: textContent })
          }

          return parts
        }

        const updateAssistant = () => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, parts: buildParts() } : m
            )
          )
        }

        const processLines = (lines: string[]) => {
          for (const line of lines) {
            const trimmed = line.trim()
            if (!trimmed || !trimmed.startsWith('data:')) continue

            // Bug fix 2 – strip CRLF before slicing
            const data = trimmed.replace(/\r$/, '').slice(5).trim()
            if (data === '[DONE]') continue

            try {
              const event: SSEEvent = JSON.parse(data)

              switch (event.type) {
                case 'text-delta':
                  if (hasSeenToolCall) {
                    currentText += event.delta
                  } else {
                    currentReasoning += event.delta
                  }
                  updateAssistant()
                  break

                case 'tool-call-start':
                  hasSeenToolCall = true
                  toolInvocations.set(event.toolCallId, {
                    toolCallId: event.toolCallId,
                    toolName: event.toolName,
                    state: 'loading',
                    input: event.input,
                  })
                  updateAssistant()
                  break

                // Bug fix 3 – guard against missing tool-call-start entry
                case 'tool-result': {
                  const existing = toolInvocations.get(event.toolCallId)
                  if (existing) {
                    toolInvocations.set(event.toolCallId, {
                      ...existing,
                      state: 'complete',
                      output: event.output,
                    })
                    updateAssistant()
                  }
                  break
                }

                case 'tool-error': {
                  const existing = toolInvocations.get(event.toolCallId)
                  if (existing) {
                    toolInvocations.set(event.toolCallId, {
                      ...existing,
                      state: 'error',
                      error: event.error,
                    })
                    updateAssistant()
                  }
                  break
                }

                case 'error':
                  setError(event.error)
                  setStatus('error')
                  return

                case 'done':
                  // Resolve any tool invocations that never received a tool-result
                  // event (the backend doesn't emit them yet).
                  for (const [id, inv] of toolInvocations) {
                    if (inv.state === 'loading') {
                      toolInvocations.set(id, { ...inv, state: 'complete' })
                    }
                  }
                  updateAssistant()
                  break
              }
            } catch {
              // Skip malformed JSON
            }
          }
        }

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          processLines(lines)
        }

        // Bug fix 1 – flush remaining bytes from TextDecoder
        buffer += decoder.decode()
        if (buffer) {
          const lines = buffer.split('\n')
          processLines(lines)
        }

        setStatus('ready')
      } catch (err) {
        if ((err as Error).name === 'AbortError') {
          setStatus('ready')
          return
        }
        setError((err as Error).message)
        setStatus('error')
      } finally {
        abortRef.current = null
      }
    },
    [api, messages]
  )

  return { messages, sendMessage, status, stop, reset, error }
}
