import axios from 'axios'
import type {
  Vehicle, VehicleEvent, WatchlistAlert, Lead, ScrapeLog,
  Stats, Paginated, FilterOptions, Dealer, MyStats
} from './types'

const api = axios.create({ baseURL: import.meta.env.VITE_API_URL || '/api' })

// Dealers
export const getDealers = (activeOnly = true) =>
  api.get<Dealer[]>('/dealers', { params: { active_only: activeOnly } }).then(r => r.data)
export const getDealerStats = (dealerId: number) =>
  api.get(`/dealers/${dealerId}/stats`).then(r => r.data)

// Stats
export const getStats = (dealerId?: number) =>
  api.get<Stats>('/stats', { params: dealerId ? { dealer_id: dealerId } : {} }).then(r => r.data)
export const getMyStats = () =>
  api.get<MyStats>('/my-stats').then(r => r.data)

// Vehicles
export interface VehicleFilters {
  dealer_id?: number
  search?: string
  make?: string
  model?: string
  min_year?: number
  max_year?: number
  min_price?: number
  max_price?: number
  max_mileage?: number
  min_days_on_lot?: number
  max_days_on_lot?: number
  condition?: string
  body_style?: string
  is_active?: boolean
  is_trade_in?: boolean
  sort_by?: string
  sort_order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}
export const getVehicles = (f: VehicleFilters = {}) =>
  api.get<Paginated<Vehicle>>('/vehicles', { params: f }).then(r => r.data)
export const getFilterOptions = (dealerId?: number) =>
  api.get<FilterOptions>('/filter-options', { params: dealerId ? { dealer_id: dealerId } : {} }).then(r => r.data)

// Events
export const getEvents = (params: {
  event_type?: string; days?: number; page?: number; page_size?: number; dealer_id?: number; search?: string
}) => api.get<Paginated<VehicleEvent>>('/events', { params }).then(r => r.data)

// Watchlist
export const getWatchlist = (dealerId?: number) =>
  api.get<WatchlistAlert[]>('/watchlist', { params: dealerId ? { dealer_id: dealerId } : {} }).then(r => r.data)
export const createWatchlist = (data: Partial<WatchlistAlert>) =>
  api.post<WatchlistAlert>('/watchlist', data).then(r => r.data)
export const updateWatchlist = (id: number, data: Partial<WatchlistAlert>) =>
  api.put<WatchlistAlert>(`/watchlist/${id}`, data).then(r => r.data)
export const deleteWatchlist = (id: number) =>
  api.delete(`/watchlist/${id}`).then(r => r.data)

// Leads
export const getLeads = (params: {
  status?: string; search?: string; page?: number; page_size?: number
}) => api.get<Paginated<Lead>>('/leads', { params }).then(r => r.data)
export const createLead = (data: Partial<Lead>) =>
  api.post<Lead>('/leads', data).then(r => r.data)
export const updateLead = (id: number, data: Partial<Lead>) =>
  api.put<Lead>(`/leads/${id}`, data).then(r => r.data)
export const deleteLead = (id: number) =>
  api.delete(`/leads/${id}`).then(r => r.data)
export const getLeadMatches = (id: number, condition?: string) =>
  api.get<Vehicle[]>(`/leads/${id}/matches`, {
    params: condition ? { condition } : {},
  }).then(r => r.data)

// Scrape
export const getScrapeLogs = () =>
  api.get<ScrapeLog[]>('/scrape-logs').then(r => r.data)
export const triggerScrape = () =>
  api.post('/scrape/trigger').then(r => r.data)
