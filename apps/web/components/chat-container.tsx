'use client'

import { useState, useRef, useEffect, useCallback } from 'react'
import { useStreamingChat } from '@/hooks/use-streaming-chat'
import { ScrollArea } from '@/components/ui/scroll-area'
import { ChatMessage } from '@/components/chat-message'
import { ChatInput } from '@/components/chat-input'
import { WelcomeScreen } from '@/components/welcome-screen'

export function ChatContainer() {
  const scrollRef = useRef<HTMLDivElement>(null)
  const [hasInteracted, setHasInteracted] = useState(false)

  const apiUrl = process.env.NEXT_PUBLIC_API_URL
    ? `${process.env.NEXT_PUBLIC_API_URL}/chat`
    : '/api/chat'
  const { messages, sendMessage, status, stop } = useStreamingChat({ api: apiUrl })

  const isLoading = status === 'streaming'

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) {
      const viewport = scrollRef.current.querySelector('[data-slot="scroll-area-viewport"]')
      if (viewport) {
        viewport.scrollTop = viewport.scrollHeight
      }
    }
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  const handleSend = (text: string) => {
    if (!hasInteracted) setHasInteracted(true)
    sendMessage(text)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <ScrollArea ref={scrollRef} className="flex-1 overflow-hidden">
        <div className="mx-auto max-w-2xl px-4">
          {messages.length === 0 && !hasInteracted ? (
            <WelcomeScreen onSuggestionClick={handleSend} />
          ) : (
            <div className="py-4">
              {messages.map((message) => (
                <ChatMessage key={message.id} message={message} />
              ))}

              {isLoading &&
                messages.length > 0 &&
                messages[messages.length - 1].role === 'user' && (
                  <div className="flex gap-3 py-4">
                    <div className="size-8 rounded-full bg-primary flex items-center justify-center shrink-0">
                      <span className="text-xs font-medium text-primary-foreground">RH</span>
                    </div>
                    <div className="flex items-center gap-1.5 pt-2">
                      <span className="size-2 rounded-full bg-primary/40 animate-bounce [animation-delay:0ms]" />
                      <span className="size-2 rounded-full bg-primary/40 animate-bounce [animation-delay:150ms]" />
                      <span className="size-2 rounded-full bg-primary/40 animate-bounce [animation-delay:300ms]" />
                    </div>
                  </div>
                )}
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Input area */}
      <div className="border-t border-border bg-background/80 backdrop-blur-sm">
        <div className="mx-auto max-w-2xl px-4 py-3">
          <ChatInput onSend={handleSend} isLoading={isLoading} onStop={stop} />
          <p className="text-center text-xs text-muted-foreground mt-2">
            {'Restaurant Helper can make mistakes. Verify important info.'}
          </p>
        </div>
      </div>
    </div>
  )
}
