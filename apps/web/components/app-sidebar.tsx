'use client'

import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  UtensilsCrossed,
  MessageSquarePlus,
  Clock,
  MapPin,
  Phone,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface AppSidebarProps {
  className?: string
  onNewChat: () => void
}

const recentChats = [
  { id: '1', title: 'Dinner at Rice & Spice', time: '2 hours ago' },
  { id: '2', title: 'La Bella Cucina menu', time: 'Yesterday' },
  { id: '3', title: 'Birthday reservation', time: '3 days ago' },
]

export function AppSidebar({ className, onNewChat }: AppSidebarProps) {
  return (
    <aside
      className={cn(
        'flex flex-col h-full bg-sidebar text-sidebar-foreground',
        className
      )}
    >
      {/* Brand header */}
      <div className="flex items-center gap-3 px-5 pt-5 pb-4">
        <div className="flex items-center justify-center size-9 rounded-xl bg-sidebar-primary text-sidebar-primary-foreground">
          <UtensilsCrossed className="size-4" />
        </div>
        <div>
          <h2 className="text-sm font-semibold leading-none">Restaurant Helper</h2>
          <p className="text-xs text-sidebar-foreground/60 mt-0.5">AI Concierge</p>
        </div>
      </div>

      <div className="px-3">
        <Button
          onClick={onNewChat}
          variant="ghost"
          className="w-full justify-start gap-2 text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground h-9"
        >
          <MessageSquarePlus className="size-4" />
          <span className="text-sm">New conversation</span>
        </Button>
      </div>

      <Separator className="my-3 bg-sidebar-border" />

      {/* Recent conversations */}
      <div className="flex-1 px-3 overflow-y-auto">
        <p className="px-2 text-xs font-medium text-sidebar-foreground/50 uppercase tracking-wider mb-2">
          Recent
        </p>
        <div className="flex flex-col gap-0.5">
          {recentChats.map((chat) => (
            <button
              key={chat.id}
              className="flex items-start gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-sidebar-accent transition-colors group"
            >
              <Clock className="size-3.5 mt-0.5 text-sidebar-foreground/40 group-hover:text-sidebar-foreground/60 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="truncate text-sm text-sidebar-foreground/80 group-hover:text-sidebar-foreground">
                  {chat.title}
                </p>
                <p className="text-xs text-sidebar-foreground/40">{chat.time}</p>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Footer info */}
      <div className="px-5 py-4 border-t border-sidebar-border">
        <div className="flex flex-col gap-1.5 text-xs text-sidebar-foreground/50">
          <div className="flex items-center gap-1.5">
            <MapPin className="size-3 shrink-0" />
            <span>101W 87th St, NY 10024</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Phone className="size-3 shrink-0" />
            <span>+1 999 999 99 9999</span>
          </div>
        </div>
      </div>
    </aside>
  )
}
