'use client'

import type { ChatMessage as ChatMessageType, MessagePart } from '@/lib/types'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { cn } from '@/lib/utils'
import ReactMarkdown from 'react-markdown'
import {
  RestaurantInfoCard,
  BookingConfirmationCard,
  BookingDeletionCard,
  TimeDisplayCard,
  ToolLoadingIndicator,
} from '@/components/tool-cards'
import { UtensilsCrossed, User } from 'lucide-react'

function renderToolPart(part: MessagePart & { type: 'tool-invocation' }) {
  const { toolInvocation } = part
  const { toolName, state, output } = toolInvocation

  if (state === 'loading') {
    return <ToolLoadingIndicator toolName={toolName} />
  }

  if (state === 'complete' && output) {
    if (toolName === 'retrieveRestaurantInfo' && output.results) {
      return <RestaurantInfoCard data={output as Parameters<typeof RestaurantInfoCard>[0]['data']} />
    }

    if (toolName === 'createBooking' && output.booking_id) {
      return <BookingConfirmationCard data={output as Parameters<typeof BookingConfirmationCard>[0]['data']} />
    }

    if (toolName === 'getBookingDetails' && output.booking_id) {
      return <BookingConfirmationCard data={output as Parameters<typeof BookingConfirmationCard>[0]['data']} />
    }

    if (toolName === 'deleteBooking' && output.status) {
      return <BookingDeletionCard data={output as Parameters<typeof BookingDeletionCard>[0]['data']} />
    }

    if (toolName === 'getCurrentTime' && output.date) {
      return <TimeDisplayCard data={output as Parameters<typeof TimeDisplayCard>[0]['data']} />
    }

    return null
  }

  if (state === 'error') {
    return (
      <div className="my-2 text-sm text-destructive">
        <span>Something went wrong: {toolInvocation.error || 'Unknown error'}</span>
      </div>
    )
  }

  return null
}

export function ChatMessage({ message }: { message: ChatMessageType }) {
  const isUser = message.role === 'user'

  return (
    <div
      className={cn(
        'flex gap-3 py-4',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
      <Avatar className={cn('size-8 shrink-0 mt-0.5', isUser ? 'bg-secondary' : 'bg-primary')}>
        <AvatarFallback className={isUser ? 'bg-secondary text-secondary-foreground' : 'bg-primary text-primary-foreground'}>
          {isUser ? <User className="size-4" /> : <UtensilsCrossed className="size-4" />}
        </AvatarFallback>
      </Avatar>

      <div
        className={cn(
          'flex flex-col gap-1 max-w-[85%] min-w-0',
          isUser ? 'items-end' : 'items-start'
        )}
      >
        <span className="text-xs font-medium text-muted-foreground mb-0.5">
          {isUser ? 'You' : 'Restaurant Helper'}
        </span>

        {message.parts.map((part, index) => {
          if (part.type === 'text') {
            if (!part.text) return null
            return (
              <div
                key={index}
                className={cn(
                  'rounded-2xl px-4 py-2.5 text-sm leading-relaxed',
                  isUser
                    ? 'bg-primary text-primary-foreground rounded-tr-sm'
                    : 'bg-card border border-border rounded-tl-sm text-card-foreground'
                )}
              >
                <div className="max-w-none [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0.5 [&_h1]:my-2 [&_h2]:my-2 [&_h3]:my-2 [&_strong]:text-inherit [&_a]:text-primary [&_a]:underline [&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-xs [&_code]:font-mono [&_pre]:rounded-lg [&_pre]:bg-muted [&_pre]:p-3 [&_ul]:list-disc [&_ul]:pl-4 [&_ol]:list-decimal [&_ol]:pl-4">
                  <ReactMarkdown>{part.text}</ReactMarkdown>
                </div>
              </div>
            )
          }

          if (part.type === 'tool-invocation') {
            return (
              <div key={index} className="w-full">
                {renderToolPart(part)}
              </div>
            )
          }

          return null
        })}
      </div>
    </div>
  )
}
