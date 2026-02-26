'use client'

import { useState, useCallback } from 'react'
import { AppSidebar } from '@/components/app-sidebar'
import { ChatContainer } from '@/components/chat-container'
import { Button } from '@/components/ui/button'
import { Menu, X } from 'lucide-react'

export default function Home() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [chatKey, setChatKey] = useState(0)

  const handleNewChat = useCallback(() => {
    setChatKey((k) => k + 1)
    setSidebarOpen(false)
  }, [])

  return (
    <div className="flex h-dvh overflow-hidden bg-background">
      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-foreground/20 backdrop-blur-sm lg:hidden"
          onClick={() => setSidebarOpen(false)}
          role="presentation"
        />
      )}

      {/* Sidebar */}
      <div
        className={`
          fixed inset-y-0 left-0 z-50 w-72 transform transition-transform duration-200 ease-in-out
          lg:relative lg:translate-x-0 lg:z-auto
          ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        <AppSidebar onNewChat={handleNewChat} />
      </div>

      {/* Main content */}
      <main className="flex-1 flex flex-col min-w-0">
        {/* Top bar */}
        <header className="flex items-center gap-3 px-4 h-14 border-b border-border bg-background/80 backdrop-blur-sm shrink-0">
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label="Toggle sidebar"
          >
            {sidebarOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </Button>

          <div className="flex-1 min-w-0">
            <h1 className="text-sm font-semibold text-foreground truncate">Restaurant Helper</h1>
            <p className="text-xs text-muted-foreground hidden sm:block">AI-powered dining concierge</p>
          </div>

          <div className="flex items-center gap-1">
            <div className="size-2 rounded-full bg-chart-2 animate-pulse" />
            <span className="text-xs text-muted-foreground">Online</span>
          </div>
        </header>

        {/* Chat */}
        <div className="flex-1 overflow-hidden">
          <ChatContainer key={chatKey} />
        </div>
      </main>
    </div>
  )
}
