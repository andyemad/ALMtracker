export interface Vehicle {
  id: number
  vin: string
  stock_number: string
  dealer_id: number | null
  location_name: string | null
  year: number
  make: string
  model: string
  trim: string
  price: number | null
  mileage: number | null
  exterior_color: string
  interior_color: string
  body_style: string
  condition: string
  fuel_type: string
  transmission: string
  image_url: string
  listing_url: string
  is_active: boolean
  first_seen: string
  last_seen: string
  days_on_lot: number
}

export interface VehicleEvent {
  id: number
  stock_number: string
  vin: string
  dealer_id: number | null
  location_name: string | null
  event_type: 'added' | 'removed' | 'price_change'
  description: string
  old_value: string | null
  new_value: string | null
  timestamp: string
  year: number | null
  make: string | null
  model: string | null
  trim: string | null
  price: number | null
}

export interface WatchlistAlert {
  id: number
  name: string
  make: string | null
  model: string | null
  max_price: number | null
  min_price: number | null
  max_mileage: number | null
  min_year: number | null
  max_year: number | null
  condition: string | null
  notification_email: string | null
  is_active: boolean
  created_at: string
  last_triggered: string | null
  trigger_count: number
  match_count: number
}

export interface Lead {
  id: number
  customer_name: string
  customer_phone: string | null
  customer_email: string | null
  interested_make: string | null
  interested_model: string | null
  max_budget: number | null
  notes: string | null
  status: 'new' | 'contacted' | 'hot' | 'sold' | 'lost'
  source: string | null
  campaign: string | null
  sms_consent: boolean
  sms_consent_at: string | null
  call_consent: boolean
  call_consent_at: string | null
  consent_text: string | null
  created_at: string
  updated_at: string
  sold_at: string | null
}

export interface ScrapeLog {
  id: number
  timestamp: string
  vehicles_found: number
  added_count: number
  removed_count: number
  price_change_count: number
  status: string
  method: string | null
  error: string | null
  duration_seconds: number | null
}

export interface Stats {
  total_active: number
  added_today: number
  removed_today: number
  active_alerts: number
  avg_price: number
  last_scrape: string | null
  last_scrape_status: string | null
  trend: Array<{
    date: string
    count: number
    added: number
    removed: number
  }>
}

export interface Paginated<T> {
  total: number
  page: number
  page_size: number
  pages: number
  data: T[]
  counts?: { added: number; removed: number; price_change: number }
}

export interface FilterOptions {
  makes: string[]
  body_styles: string[]
  price_range: [number | null, number | null]
  year_range: [number | null, number | null]
}

export interface MyStats {
  goal: number
  sold_this_month: number
  days_elapsed: number
  days_remaining: number
  days_in_month: number
  pace_per_day: number
  projected_eom: number
  needed_per_day: number
  on_track: boolean
  deficit: number
  hot_leads: Lead[]
}

export interface Dealer {
  id: number
  name: string
  city: string
  state: string
  is_active: boolean
  scrape_priority: number
  active_vehicle_count: number
  created_at: string
  last_scraped: string | null
}
