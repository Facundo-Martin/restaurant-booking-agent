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

// --- API contract — must mirror backend Pydantic models exactly ---
export interface ChatApiMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface ChatApiRequest {
  messages: ChatApiMessage[]
}
