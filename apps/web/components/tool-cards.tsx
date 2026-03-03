'use client'

import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import {
  MapPin,
  Clock,
  UtensilsCrossed,
  CalendarCheck,
  Users,
  User,
  Hash,
  Search,
  Trash2,
  Timer,
} from 'lucide-react'

// --- Restaurant Info Card ---
export function RestaurantInfoCard({
  data,
}: {
  data: {
    results: {
      restaurant_name: string
      description: string
      cuisine: string
      location: string
      hours: string
      menu: { name: string; price: string; description: string }[]
    }[]
  }
}) {
  return (
    <div className="flex flex-col gap-3 my-2">
      {data.results.map((restaurant) => (
        <Card key={restaurant.restaurant_name} className="border-border/60 py-4">
          <CardHeader className="pb-0">
            <div className="flex items-start justify-between">
              <div>
                <CardTitle className="text-base font-semibold text-foreground">
                  {restaurant.restaurant_name}
                </CardTitle>
                <CardDescription className="mt-1 text-sm">
                  {restaurant.description}
                </CardDescription>
              </div>
              <Badge variant="secondary" className="shrink-0 text-xs">
                {restaurant.cuisine}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="pt-3">
            <div className="flex flex-col gap-2 text-sm text-muted-foreground">
              <div className="flex items-center gap-2">
                <MapPin className="size-3.5 text-primary" />
                <span>{restaurant.location}</span>
              </div>
              <div className="flex items-center gap-2">
                <Clock className="size-3.5 text-primary" />
                <span>{restaurant.hours}</span>
              </div>
            </div>

            {restaurant.menu && restaurant.menu.length > 0 && (
              <>
                <Separator className="my-3" />
                <div>
                  <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2.5">
                    <UtensilsCrossed className="size-3" />
                    Menu Highlights
                  </h4>
                  <div className="flex flex-col gap-2">
                    {restaurant.menu.map((item) => (
                      <div
                        key={item.name}
                        className="flex items-start justify-between gap-3"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-foreground">{item.name}</p>
                          <p className="text-xs text-muted-foreground leading-relaxed">{item.description}</p>
                        </div>
                        <span className="text-sm font-semibold text-primary shrink-0">
                          {item.price}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

// --- Booking Confirmation Card ---
export function BookingConfirmationCard({
  data,
}: {
  data: {
    booking_id: string
    restaurant_name: string
    date: string
    hour: string
    guest_name: string
    num_guests: number
    status: string
    message?: string
  }
}) {
  return (
    <Card className="border-primary/20 bg-primary/5 py-4 my-2">
      <CardHeader className="pb-0">
        <div className="flex items-center gap-2">
          <CalendarCheck className="size-4 text-primary" />
          <CardTitle className="text-sm font-semibold text-foreground">
            Reservation {data.status === 'confirmed' ? 'Confirmed' : 'Details'}
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent className="pt-3">
        <div className="grid grid-cols-2 gap-y-2.5 gap-x-4 text-sm">
          <div className="flex items-center gap-2 text-muted-foreground">
            <Hash className="size-3.5" />
            <span>Booking ID</span>
          </div>
          <span className="font-mono text-xs text-foreground">{data.booking_id}</span>

          <div className="flex items-center gap-2 text-muted-foreground">
            <UtensilsCrossed className="size-3.5" />
            <span>Restaurant</span>
          </div>
          <span className="text-foreground">{data.restaurant_name}</span>

          <div className="flex items-center gap-2 text-muted-foreground">
            <CalendarCheck className="size-3.5" />
            <span>Date</span>
          </div>
          <span className="text-foreground">{data.date}</span>

          <div className="flex items-center gap-2 text-muted-foreground">
            <Clock className="size-3.5" />
            <span>Time</span>
          </div>
          <span className="text-foreground">{data.hour}</span>

          <div className="flex items-center gap-2 text-muted-foreground">
            <User className="size-3.5" />
            <span>Guest</span>
          </div>
          <span className="text-foreground">{data.guest_name}</span>

          <div className="flex items-center gap-2 text-muted-foreground">
            <Users className="size-3.5" />
            <span>Party Size</span>
          </div>
          <span className="text-foreground">{data.num_guests} guests</span>
        </div>
        {data.status === 'confirmed' && (
          <Badge className="mt-3" variant="default">
            Confirmed
          </Badge>
        )}
      </CardContent>
    </Card>
  )
}

// --- Booking Deletion Card ---
export function BookingDeletionCard({
  data,
}: {
  data: {
    booking_id: string
    status: string
    message: string
  }
}) {
  return (
    <Card className="border-destructive/20 bg-destructive/5 py-4 my-2">
      <CardHeader className="pb-0">
        <div className="flex items-center gap-2">
          <Trash2 className="size-4 text-destructive" />
          <CardTitle className="text-sm font-semibold text-foreground">
            Reservation Cancelled
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent className="pt-2">
        <p className="text-sm text-muted-foreground">{data.message}</p>
        <Badge className="mt-2" variant="outline">
          ID: {data.booking_id}
        </Badge>
      </CardContent>
    </Card>
  )
}

// --- Time Display Card ---
export function TimeDisplayCard({
  data,
}: {
  data: {
    date: string
    time: string
    day_of_week: string
  }
}) {
  return (
    <div className="flex items-center gap-2 my-1 text-xs text-muted-foreground">
      <Timer className="size-3" />
      <span>
        {data.day_of_week}, {data.date} at {data.time}
      </span>
    </div>
  )
}

// --- Tool Loading Indicator ---
export function ToolLoadingIndicator({ toolName }: { toolName: string }) {
  const labelMap: Record<string, { label: string; icon: React.ReactNode }> = {
    retrieve: {
      label: 'Searching knowledge base...',
      icon: <Search className="size-3.5" />,
    },
    retrieveRestaurantInfo: {
      label: 'Searching restaurants...',
      icon: <Search className="size-3.5" />,
    },
    createBooking: {
      label: 'Creating reservation...',
      icon: <CalendarCheck className="size-3.5" />,
    },
    getBookingDetails: {
      label: 'Looking up booking...',
      icon: <Hash className="size-3.5" />,
    },
    deleteBooking: {
      label: 'Cancelling reservation...',
      icon: <Trash2 className="size-3.5" />,
    },
    getCurrentTime: {
      label: 'Checking current time...',
      icon: <Timer className="size-3.5" />,
    },
  }

  const info = labelMap[toolName] || { label: 'Working...', icon: <Search className="size-3.5" /> }

  return (
    <div className="flex items-center gap-2 my-2 text-sm text-muted-foreground animate-pulse">
      <div className="flex items-center justify-center size-5 rounded-md bg-secondary">
        {info.icon}
      </div>
      <span>{info.label}</span>
    </div>
  )
}
