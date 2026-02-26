'use client'

import { useState, useRef, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { Send, Square } from 'lucide-react'

interface ChatInputProps {
  onSend: (text: string) => void
  isLoading: boolean
  onStop?: () => void
}

export function ChatInput({ onSend, isLoading, onStop }: ChatInputProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`
    }
  }, [input])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return
    onSend(input.trim())
    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="relative">
      <div className="flex items-end gap-2 rounded-2xl border border-border bg-card p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring/20 focus-within:border-primary/30 transition-all">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about restaurants, menus, or make a reservation..."
          className={cn(
            'flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none',
            'min-h-[36px] max-h-[160px]'
          )}
          rows={1}
          disabled={isLoading}
          aria-label="Chat message input"
        />
        {isLoading ? (
          <Button
            type="button"
            size="icon"
            variant="ghost"
            onClick={onStop}
            className="shrink-0 size-9 rounded-xl text-muted-foreground hover:text-foreground"
            aria-label="Stop generating"
          >
            <Square className="size-4" />
          </Button>
        ) : (
          <Button
            type="submit"
            size="icon"
            disabled={!input.trim()}
            className="shrink-0 size-9 rounded-xl"
            aria-label="Send message"
          >
            <Send className="size-4" />
          </Button>
        )}
      </div>
    </form>
  )
}
