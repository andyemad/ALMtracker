import { useEffect, useState } from 'react'
import { formatDistanceToNow, format } from 'date-fns'
import { TrendingUp, TrendingDown, DollarSign, Filter, ChevronLeft, ChevronRight, MapPin, Search, ExternalLink } from 'lucide-react'
import { getEvents } from '../api'
import type { VehicleEvent } from '../types'
import { useDealer } from '../context/DealerContext'
import { useSearchParams } from 'react-router-dom'
import { useDebounce } from '../hooks/useDebounce'
import { LocationChip } from '../components/LocationChip'

const EVENT_ICONS = {
  added: { Icon: TrendingUp, color: 'text-emerald-400', bg: 'bg-emerald-500/10', badge: 'badge-new', label: 'Added' },
  removed: { Icon: TrendingDown, color: 'text-red-400', bg: 'bg-red-500/10', badge: 'badge-removed', label: 'Removed' },
  price_change: { Icon: DollarSign, color: 'text-amber-400', bg: 'bg-amber-500/10', badge: 'badge-price', label: 'Price Change' },
}

export default function Activity() {
  const { selectedDealer } = useDealer()
  const dealerId = selectedDealer?.id
  const [searchParams] = useSearchParams()

  const [events, setEvents] = useState<VehicleEvent[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pages, setPages] = useState(1)
  const [eventType, setEventType] = useState(searchParams.get('event_type') ?? '')
  const validDays = [3, 7, 14, 30, 90]
  const rawDays = +(searchParams.get('days') ?? '7')
  const [days, setDays] = useState(validDays.includes(rawDays) ? rawDays : 7)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebounce(search, 300)

  useEffect(() => {
    setLoading(true)
    getEvents({
      event_type: eventType || undefined,
      days,
      page,
      page_size: 25,
      dealer_id: dealerId,
      search: debouncedSearch || undefined,
    }).then(r => {
      setEvents(r.data)
      setTotal(r.total)
      setPages(r.pages)
    }).finally(() => setLoading(false))
  }, [eventType, days, page, dealerId, debouncedSearch])

  const counts = {
    added: events.filter(e => e.event_type === 'added').length,
    removed: events.filter(e => e.event_type === 'removed').length,
    price_change: events.filter(e => e.event_type === 'price_change').length,
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4 sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Activity Log</h1>
          <p className="text-slate-400 text-sm mt-0.5">Every inventory change tracked automatically</p>
        </div>
        <LocationChip />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {(['added', 'removed', 'price_change'] as const).map(type => {
          const s = EVENT_ICONS[type]
          return (
            <button
              key={type}
              onClick={() => { setEventType(eventType === type ? '' : type); setPage(1) }}
              className={`card p-4 text-left transition-all hover:border-slate-600 ${
                eventType === type ? 'ring-1 ring-brand-500 border-brand-500/50' : ''
              }`}
            >
              <div className={`w-8 h-8 rounded-lg ${s.bg} flex items-center justify-center mb-2`}>
                <s.Icon className={`w-4 h-4 ${s.color}`} />
              </div>
              <div className="text-xl font-bold text-white">{counts[type]}</div>
              <div className="text-xs text-slate-400">{s.label} (this page)</div>
            </button>
          )
        })}
      </div>

      {/* Filters */}
      <div className="card p-4 flex items-center gap-3 flex-wrap">
        <Filter className="w-4 h-4 text-slate-400 flex-shrink-0" />
        <div className="flex gap-1">
          {['', 'added', 'removed', 'price_change'].map(t => (
            <button
              key={t}
              onClick={() => { setEventType(t); setPage(1) }}
              className={`text-xs px-3 py-1.5 rounded-lg transition-colors ${
                eventType === t
                  ? 'bg-brand-600 text-white'
                  : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
              }`}
            >
              {t === '' ? 'All' : t === 'added' ? 'Added' : t === 'removed' ? 'Removed' : 'Price Changes'}
            </button>
          ))}
        </div>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
          <input
            className="input pl-9 w-48"
            placeholder="Stock #, VIN, make..."
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(1) }}
          />
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-slate-400">Show last</span>
          <select
            className="select w-auto"
            value={days}
            onChange={e => { setDays(+e.target.value); setPage(1) }}
          >
            <option value={3}>3 days</option>
            <option value={7}>7 days</option>
            <option value={14}>14 days</option>
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
          </select>
        </div>
        <span className="text-xs text-slate-500">{total.toLocaleString()} events</span>
      </div>

      {/* Timeline */}
      <div className="card divide-y divide-slate-700/30">
        {loading ? (
          [...Array(8)].map((_, i) => (
            <div key={i} className="p-4 flex gap-4 animate-pulse">
              <div className="w-8 h-8 rounded-lg bg-slate-700 flex-shrink-0" />
              <div className="flex-1 space-y-2">
                <div className="h-4 bg-slate-700 rounded w-3/4" />
                <div className="h-3 bg-slate-800 rounded w-1/2" />
              </div>
            </div>
          ))
        ) : events.length === 0 ? (
          <div className="py-16 text-center text-slate-500">No events found</div>
        ) : (
          events.map(ev => <EventItem key={ev.id} ev={ev} />)
        )}
      </div>

      {/* Pagination */}
      {pages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-slate-400 text-xs">
            {total.toLocaleString()} events · page {page} of {pages}
          </span>
          <div className="flex items-center gap-1">
            <button onClick={() => setPage(1)} disabled={page === 1} className="btn-ghost p-1.5 disabled:opacity-30 text-xs text-slate-400">
              First
            </button>
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="btn-ghost p-1.5 disabled:opacity-30">
              <ChevronLeft className="w-4 h-4" />
            </button>
            {Array.from({ length: Math.min(7, pages) }, (_, i) => {
              const p = Math.max(1, Math.min(pages - 6, page - 3)) + i
              return (
                <button
                  key={p}
                  onClick={() => setPage(p)}
                  className={`w-7 h-7 rounded text-xs transition-colors ${
                    p === page ? 'bg-brand-600 text-white' : 'text-slate-400 hover:text-slate-100 hover:bg-slate-700'
                  }`}
                >
                  {p}
                </button>
              )
            })}
            <button onClick={() => setPage(p => Math.min(pages, p + 1))} disabled={page >= pages} className="btn-ghost p-1.5 disabled:opacity-30">
              <ChevronRight className="w-4 h-4" />
            </button>
            <button onClick={() => setPage(pages)} disabled={page >= pages} className="btn-ghost p-1.5 disabled:opacity-30 text-xs text-slate-400">
              Last
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function EventItem({ ev }: { ev: VehicleEvent }) {
  const s = EVENT_ICONS[ev.event_type] ?? EVENT_ICONS.added
  const fmt$ = (n: number | null) => n ? `$${n.toLocaleString()}` : null

  return (
    <div className="p-4 flex items-start gap-4 hover:bg-slate-700/20 transition-colors">
      <div className={`w-8 h-8 rounded-lg ${s.bg} flex items-center justify-center flex-shrink-0 mt-0.5`}>
        <s.Icon className={`w-4 h-4 ${s.color}`} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${s.badge}`}>
            {s.label}
          </span>
          <p className="text-sm text-slate-200 font-medium">
            {[ev.year, ev.make, ev.model, ev.trim].filter(Boolean).join(' ')}
          </p>
          {fmt$(ev.price) && (
            <span className="text-sm text-white font-semibold">{fmt$(ev.price)}</span>
          )}
        </div>

        {ev.event_type === 'price_change' && ev.old_value && ev.new_value && (() => {
          const oldP = Number(ev.old_value)
          const newP = Number(ev.new_value)
          const dropped = newP < oldP
          return (
            <p className="text-xs text-slate-400 mt-1">
              <span className="text-slate-400">${oldP.toLocaleString()}</span>
              <span className="mx-1">→</span>
              <span className={dropped ? 'text-red-400' : 'text-emerald-400'}>${newP.toLocaleString()}</span>
              <span className={`ml-1 ${dropped ? 'text-red-500' : 'text-emerald-500'}`}>
                ({dropped ? '↓' : '↑'} ${Math.abs(newP - oldP).toLocaleString()})
              </span>
            </p>
          )
        })()}

        <p className="text-xs text-slate-500 mt-1 flex items-center gap-2 flex-wrap">
          <span>Stock #{ev.stock_number}</span>
          {ev.vin && <span className="font-mono">{ev.vin}</span>}
          {ev.location_name && (
            <span className="flex items-center gap-1 text-slate-400">
              <MapPin className="w-3 h-3" />{ev.location_name}
            </span>
          )}
        </p>
      </div>

      <div className="flex items-center gap-3 flex-shrink-0">
        {ev.stock_number && (
          <a
            href={`https://www.almcars.com/inventory/${ev.stock_number.toLowerCase()}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-brand-400 hover:text-brand-300 transition-colors"
            title="View listing"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        )}
        <div className="text-right">
          <p className="text-xs text-slate-400">
            {formatDistanceToNow(new Date(ev.timestamp + 'Z'), { addSuffix: true })}
          </p>
          <p className="text-[11px] text-slate-600 mt-0.5">
            {format(new Date(ev.timestamp + 'Z'), 'MMM d, h:mm a')}
          </p>
        </div>
      </div>
    </div>
  )
}
