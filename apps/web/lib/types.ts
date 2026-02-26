/**
 * Frontend chat UI types.
 *
 * These are pure frontend state types — they describe what the chat UI holds
 * in memory, not what crosses the network.
 *
 * API contract types (ChatApiMessage, ChatApiRequest, Booking, etc.) live in
 * lib/client/types.gen.ts, generated from the backend OpenAPI spec via
 * `pnpm generate:client`. Never hand-edit that file.
 */

// --- Tool invocation state ---
export type ToolState = 'loading' | 'complete' | 'error'

export interface ToolInvocation {
  toolCallId: string
  toolName: string
  state: ToolState
  input: Record<string, unknown>
  output?: Record<string, unknown>
  error?: string
}

// --- A single message part (text or tool) ---
export type MessagePart =
  | { type: 'text'; text: string }
  | { type: 'tool-invocation'; toolInvocation: ToolInvocation }

// --- A complete chat message (UI state) ---
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  parts: MessagePart[]
  createdAt: Date
}

// --- SSE events emitted by the backend ---
export type SSEEvent =
  | { type: 'text-delta'; delta: string }
  | { type: 'tool-call-start'; toolCallId: string; toolName: string; input: Record<string, unknown> }
  | { type: 'tool-result'; toolCallId: string; toolName: string; output: Record<string, unknown> }
  | { type: 'tool-error'; toolCallId: string; toolName: string; error: string }
  | { type: 'done' }
  | { type: 'error'; error: string }

