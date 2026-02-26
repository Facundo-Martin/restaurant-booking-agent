'use client'

import { Button } from '@/components/ui/button'
import { UtensilsCrossed, MapPin, CalendarCheck, Search, Clock } from 'lucide-react'

interface WelcomeScreenProps {
  onSuggestionClick: (text: string) => void
}

const suggestions = [
  {
    icon: <Search className="size-4" />,
    label: 'Discover restaurants',
    text: 'What restaurants do you have in San Francisco?',
  },
  {
    icon: <UtensilsCrossed className="size-4" />,
    label: 'Browse a menu',
    text: "Can you show me the menu for Rice & Spice?",
  },
  {
    icon: <CalendarCheck className="size-4" />,
    label: 'Make a reservation',
    text: 'I want to book a table at La Bella Cucina for tomorrow at 7pm for 2 people.',
  },
  {
    icon: <Clock className="size-4" />,
    label: 'Check a booking',
    text: 'Can you look up my reservation? The booking ID is abc12345 at The Golden Fork.',
  },
]

export function WelcomeScreen({ onSuggestionClick }: WelcomeScreenProps) {
  return (
    <div className="flex flex-col items-center justify-center flex-1 px-4 py-12">
      <div className="flex items-center justify-center size-16 rounded-2xl bg-primary/10 mb-6">
        <UtensilsCrossed className="size-8 text-primary" />
      </div>

      <h1 className="text-2xl font-semibold text-foreground text-center text-balance mb-2">
        Restaurant Helper
      </h1>
      <p className="text-sm text-muted-foreground text-center text-pretty max-w-md mb-8 leading-relaxed">
        Your AI-powered dining concierge. Discover restaurants, browse menus, and manage reservations through conversation.
      </p>

      <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-6">
        <MapPin className="size-3" />
        <span>101W 87th Street, New York, NY 10024</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-lg">
        {suggestions.map((suggestion) => (
          <Button
            key={suggestion.label}
            variant="outline"
            className="h-auto justify-start gap-3 px-4 py-3 text-left hover:border-primary/30 hover:bg-primary/5 transition-colors"
            onClick={() => onSuggestionClick(suggestion.text)}
          >
            <span className="text-primary shrink-0">{suggestion.icon}</span>
            <span className="text-sm font-medium">{suggestion.label}</span>
          </Button>
        ))}
      </div>
    </div>
  )
}
