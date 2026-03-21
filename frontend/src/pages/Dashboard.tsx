import { useEffect, useState } from 'react'
import {
  Car, TrendingUp, TrendingDown, Bell, DollarSign,
  Clock, CheckCircle, XCircle, AlertCircle, RefreshCw, ExternalLink,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar
} from 'recharts'
import { formatDistanceToNow } from 'date-fns'
import { getStats, getEvents, getScrapeLogs, getVehicles } from '../api'
import type { Stats, VehicleEvent, ScrapeLog, Vehicle } from '../types'
import { useDealer } from '../context/DealerContext'
import { Link } from 'react-router-dom'
import { useScrape } from '../context/ScrapeContext'

const fmt$ = (n: number | null) => n != null ? `$${n.toLocaleString()}` : '—'
const fmtMi = (n: number | null) => n != null ? `${n.toLocaleString()} mi` : '—'

export default function Dashboard() {
  const { selectedDealer } = useDealer()
  const dealerId = selectedDealer?.id
  const { scraping } = useScrape()

  const [stats, setStats] = useState<Stats | null>(null)
  const [events, setEvents] = useState<VehicleEvent[]>([])
  const [logs, setLogs] = useState<ScrapeLog[]>([])
  const [priorityUnits, setPriorityUnits] = useState<Vehicle[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      getStats(dealerId),
      getEvents({ days: 7, page_size: 12, dealer_id: dealerId }),
      getScrapeLogs(),
      getVehicles({
        dealer_id: dealerId,
        is_active: true,
        sort_by: 'days_on_lot',
        sort_order: 'desc',
        page_size: 6,
      }),
    ]).then(([s, e, l, v]) => {
      setStats(s)
      setEvents(e.data)
      setLogs(l)
      setPriorityUnits(v.data)
    }).finally(() => setLoading(false))
  }, [dealerId])

  if (loading) return <LoadingScreen />

  const statCards = [
    {
      label: 'Total Inventory',
      value: stats?.total_active ?? 0,
      icon: Car,
      color: 'text-blue-400',
      bg: 'bg-blue-500/10',
      border: 'border-blue-500/20',
      to: null as string | null,
    },
    {
      label: 'Added Today',
      value: stats?.added_today ?? 0,
      icon: TrendingUp,
      color: 'text-emerald-400',
      bg: 'bg-emerald-500/10',
      border: 'border-emerald-500/20',
      to: '/activity?event_type=added&days=1' as string | null,
    },
    {
      label: 'Removed Today',
      value: stats?.removed_today ?? 0,
      icon: TrendingDown,
      color: 'text-red-400',
      bg: 'bg-red-500/10',
      border: 'border-red-500/20',
      to: '/activity?event_type=removed&days=1' as string | null,
    },
    {
      label: 'Active Alerts',
      value: stats?.active_alerts ?? 0,
      icon: Bell,
      color: 'text-amber-400',
      bg: 'bg-amber-500/10',
      border: 'border-amber-500/20',
      to: '/watchlist' as string | null,
    },
    {
      label: 'Avg List Price',
      value: stats?.avg_price ? `$${(stats.avg_price / 1000).toFixed(1)}k` : '—',
      icon: DollarSign,
      color: 'text-violet-400',
      bg: 'bg-violet-500/10',
      border: 'border-violet-500/20',
      to: null as string | null,
    },
  ]

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Dashboard</h1>
          <p className="text-slate-400 text-sm mt-0.5">
          {selectedDealer ? `${selectedDealer.name} · ${selectedDealer.city}` : 'All 24 ALM Locations'} — live inventory intel
        </p>
        </div>
        <ScrapeStatus stats={stats} scraping={scraping} />
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {statCards.map(card => {
          const inner = (
            <>
              <div className={`w-8 h-8 rounded-lg ${card.bg} flex items-center justify-center mb-3`}>
                <card.icon className={`w-4 h-4 ${card.color}`} />
              </div>
              <div className="text-2xl font-bold text-white">{card.value}</div>
              <div className="text-xs text-slate-400 mt-0.5">{card.label}</div>
            </>
          )
          const cls = `card p-4 border ${card.border} ${card.to ? 'hover:border-slate-500 cursor-pointer transition-all' : ''}`
          return card.to ? (
            <Link key={card.label} to={card.to} className={cls}>{inner}</Link>
          ) : (
            <div key={card.label} className={cls}>{inner}</div>
          )
        })}
      </div>

      {/* Charts + Activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Inventory Trend */}
        <div className="lg:col-span-2 card p-5">
          <h2 className="text-sm font-semibold text-slate-300 mb-4">Inventory Trend (14 days)</h2>
          {stats?.trend && stats.trend.length > 0 ? (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={stats.trend}>
                <defs>
                  <linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="date" stroke="#64748b" tick={{ fontSize: 11 }} />
                <YAxis stroke="#64748b" tick={{ fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} />
                <Area type="monotone" dataKey="count" stroke="#3b82f6" fill="url(#grad)" strokeWidth={2} dot={false} name="Total" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <EmptyChart />
          )}
        </div>

        {/* Recent Activity */}
        <div className="card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-semibold text-slate-300">Recent Activity</h2>
            <Link to="/activity" className="text-xs text-brand-400 hover:text-brand-300 transition-colors">
              View all →
            </Link>
          </div>
          <div className="space-y-2 overflow-y-auto max-h-[220px]">
            {events.length === 0 ? (
              <p className="text-slate-500 text-xs text-center py-8">No activity yet</p>
            ) : (
              events.map(ev => <EventRow key={ev.id} ev={ev} />)
            )}
          </div>
        </div>
      </div>

      {/* Daily Add/Remove Chart + Scrape Logs */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Daily Adds/Removes */}
        {stats?.trend && stats.trend.length > 0 && (
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-slate-300 mb-4">Daily Changes</h2>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={stats.trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="date" stroke="#64748b" tick={{ fontSize: 11 }} />
                <YAxis stroke="#64748b" tick={{ fontSize: 11 }} />
                <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} />
                <Bar dataKey="added" fill="#22c55e" name="Added" radius={[3, 3, 0, 0]} />
                <Bar dataKey="removed" fill="#ef4444" name="Removed" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Scrape History */}
        <div className="card p-5">
          <h2 className="text-sm font-semibold text-slate-300 mb-4">Scrape History</h2>
          <div className="space-y-2 overflow-y-auto max-h-[180px]">
            {logs.length === 0 ? (
              <p className="text-slate-500 text-xs text-center py-6">No scrapes yet</p>
            ) : (
              logs.slice(0, 8).map(log => <LogRow key={log.id} log={log} />)
            )}
          </div>
        </div>
      </div>

      <div className="card p-5">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-300">Units To Move First</h2>
            <p className="mt-1 text-xs text-slate-500">
              Oldest active inventory, sorted by days on lot so the team has a sell-now queue.
            </p>
          </div>
          <Link to="/inventory" className="text-xs text-brand-400 hover:text-brand-300 transition-colors">
            Open inventory →
          </Link>
        </div>

        {priorityUnits.length === 0 ? (
          <p className="py-8 text-center text-xs text-slate-500">No active units available for prioritization yet</p>
        ) : (
          <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
            {priorityUnits.map(vehicle => (
              <PriorityUnitCard key={vehicle.id} vehicle={vehicle} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ScrapeStatus({ stats, scraping }: { stats: Stats | null; scraping: boolean }) {
  if (scraping) {
    return (
      <div className="flex items-center gap-2 text-xs px-3 py-1.5 rounded-full border
                      bg-amber-500/10 text-amber-400 border-amber-500/30 animate-pulse">
        <RefreshCw className="w-3 h-3 animate-spin" />
        Scraping...
      </div>
    )
  }
  if (!stats?.last_scrape) return null
  const ok = stats.last_scrape_status === 'success'
  return (
    <div className={`flex items-center gap-2 text-xs px-3 py-1.5 rounded-full border
      ${ok ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
            : 'bg-red-500/10 text-red-400 border-red-500/30'}`}>
      {ok ? <CheckCircle className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
      Last sync {formatDistanceToNow(new Date(stats.last_scrape + 'Z'), { addSuffix: true })}
    </div>
  )
}

function EventRow({ ev }: { ev: VehicleEvent }) {
  const map = {
    added: { cls: 'text-emerald-400', dot: 'bg-emerald-500' },
    removed: { cls: 'text-red-400', dot: 'bg-red-500' },
    price_change: { cls: 'text-amber-400', dot: 'bg-amber-500' },
  }
  const s = map[ev.event_type] ?? map.added
  return (
    <div className="flex items-start gap-2.5 py-1.5">
      <div className={`w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0 ${s.dot}`} />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-slate-300 truncate">{ev.description}</p>
        <p className="text-[11px] text-slate-500 mt-0.5">
          {ev.location_name && <span className="text-slate-400">{ev.location_name} · </span>}
          {formatDistanceToNow(new Date(ev.timestamp + 'Z'), { addSuffix: true })}
        </p>
      </div>
    </div>
  )
}

function LogRow({ log }: { log: ScrapeLog }) {
  const ok = log.status === 'success'
  const Icon = ok ? CheckCircle : log.status === 'error' ? XCircle : AlertCircle
  const cls = ok ? 'text-emerald-400' : log.status === 'error' ? 'text-red-400' : 'text-amber-400'
  return (
    <div className="flex items-center gap-3 py-1.5 text-xs">
      <Icon className={`w-3.5 h-3.5 flex-shrink-0 ${cls}`} />
      <div className="flex-1 min-w-0">
        <span className="text-slate-300">{log.vehicles_found} vehicles</span>
        {log.added_count > 0 && <span className="text-emerald-400 ml-1">+{log.added_count}</span>}
        {log.removed_count > 0 && <span className="text-red-400 ml-1">-{log.removed_count}</span>}
        {log.method && <span className="text-slate-600 ml-1">({log.method})</span>}
      </div>
      <div className="text-slate-500 flex items-center gap-1 flex-shrink-0">
        <Clock className="w-3 h-3" />
        {formatDistanceToNow(new Date(log.timestamp + 'Z'), { addSuffix: true })}
      </div>
    </div>
  )
}

function PriorityUnitCard({ vehicle }: { vehicle: Vehicle }) {
  const urgencyTone = vehicle.days_on_lot > 60
    ? 'border-red-500/30 bg-red-500/5'
    : vehicle.days_on_lot > 45
      ? 'border-amber-500/30 bg-amber-500/5'
      : 'border-slate-800 bg-slate-900/70'

  const badgeTone = vehicle.days_on_lot > 60
    ? 'border-red-500/30 bg-red-500/10 text-red-300'
    : vehicle.days_on_lot > 45
      ? 'border-amber-500/30 bg-amber-500/10 text-amber-300'
      : 'border-slate-700 bg-slate-800 text-slate-300'

  return (
    <div className={`rounded-2xl border p-4 ${urgencyTone}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
            Stock #{vehicle.stock_number}
          </p>
          <h3 className="mt-1 truncate text-sm font-semibold text-white">
            {[vehicle.year, vehicle.make, vehicle.model].filter(Boolean).join(' ')}
          </h3>
          <p className="mt-1 truncate text-xs text-slate-400">{vehicle.trim || vehicle.body_style || 'No trim listed'}</p>
        </div>
        <div className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${badgeTone}`}>
          {vehicle.days_on_lot} days
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
        <div>
          <p className="text-slate-500">Price</p>
          <p className="mt-1 font-semibold text-white">{fmt$(vehicle.price)}</p>
        </div>
        <div>
          <p className="text-slate-500">Mileage</p>
          <p className="mt-1 text-slate-200">{fmtMi(vehicle.mileage)}</p>
        </div>
      </div>

      <p className="mt-3 text-[11px] text-slate-500">
        First seen {formatDistanceToNow(new Date(vehicle.first_seen + 'Z'), { addSuffix: true })}
      </p>

      <div className="mt-4 flex items-center gap-2">
        <Link to={`/inventory?search=${encodeURIComponent(vehicle.stock_number)}`} className="btn-secondary px-3 py-2 text-xs">
          Review in ALM
        </Link>
        {vehicle.listing_url && (
          <a
            href={vehicle.listing_url}
            target="_blank"
            rel="noreferrer"
            className="btn-ghost px-3 py-2 text-xs"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            Listing
          </a>
        )}
      </div>
    </div>
  )
}


function EmptyChart() {
  return (
    <div className="h-[200px] flex items-center justify-center">
      <p className="text-slate-600 text-sm">Chart data will appear after first scrape</p>
    </div>
  )
}

function LoadingScreen() {
  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="animate-pulse space-y-6">
        <div className="h-8 w-48 bg-slate-800 rounded" />
        <div className="grid grid-cols-5 gap-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-24 bg-slate-800 rounded-xl" />
          ))}
        </div>
        <div className="grid grid-cols-3 gap-6">
          <div className="col-span-2 h-64 bg-slate-800 rounded-xl" />
          <div className="h-64 bg-slate-800 rounded-xl" />
        </div>
        <div className="h-56 bg-slate-800 rounded-xl" />
      </div>
    </div>
  )
}
