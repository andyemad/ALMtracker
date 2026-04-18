import { useEffect, useState } from 'react'
import {
  CheckCircle, XCircle, AlertCircle, RefreshCw, ExternalLink,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar,
} from 'recharts'
import { format, formatDistanceToNow } from 'date-fns'
import { getStats, getEvents, getScrapeLogs, getVehicles } from '../api'
import type { Stats, VehicleEvent, ScrapeLog, Vehicle } from '../types'
import { useDealer } from '../context/DealerContext'
import { Link } from 'react-router-dom'
import { useScrape } from '../context/ScrapeContext'

// OKLCH color constants for recharts SVG attributes (CSS vars not supported in SVG presentation attrs)
const C = {
  accent:   'oklch(0.62 0.14 48)',
  positive: 'oklch(0.58 0.08 170)',
  danger:   'oklch(0.58 0.16 28)',
  hairline: 'oklch(0.88 0.010 75)',
  muted:    'oklch(0.52 0.008 65)',
}

const fmt$ = (n: number | null) => n != null ? `$${n.toLocaleString()}` : '—'
const fmtMi = (n: number | null) => n != null ? `${n.toLocaleString()} mi` : '—'

const ChartTick = ({ x, y, payload }: Record<string, any>) => (
  <text x={x} y={y} dy={12} textAnchor="middle"
    style={{ fill: 'var(--muted)', fontFamily: 'var(--font-mono)', fontSize: 9 }}>
    {payload.value}
  </text>
)

const YChartTick = ({ x, y, payload }: Record<string, any>) => (
  <text x={x} y={y} dy={4} textAnchor="end"
    style={{ fill: 'var(--muted)', fontFamily: 'var(--font-mono)', fontSize: 9 }}>
    {payload.value}
  </text>
)

const ChartTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--card)',
      border: '1px solid var(--hairline)',
      padding: '8px 12px',
      borderRadius: 4,
      fontSize: 11,
      fontFamily: 'var(--font-mono)',
      color: 'var(--ink)',
    }}>
      <p style={{ color: 'var(--muted)', marginBottom: 4 }}>{label}</p>
      {payload.map((p: any) => (
        <p key={p.name} style={{ color: p.color || 'var(--ink-2)' }}>
          {p.name}: {p.value}
        </p>
      ))}
    </div>
  )
}

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
      getEvents({ days: 7, page_size: 8, dealer_id: dealerId }),
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

  const locationLabel = selectedDealer
    ? selectedDealer.name
    : 'All locations'

  const locationSub = selectedDealer
    ? `${selectedDealer.city} — live inventory intelligence`
    : `${stats?.total_active?.toLocaleString() ?? '—'} vehicles tracked`

  const statCells = [
    {
      key: 'Total inventory',
      value: (stats?.total_active ?? 0).toLocaleString(),
      sub: 'active lots',
      tint: undefined as string | undefined,
      to: null as string | null,
    },
    {
      key: 'Added today',
      value: `+${stats?.added_today ?? 0}`,
      sub: 'across all lots',
      tint: 'var(--positive)',
      to: '/activity?event_type=added',
    },
    {
      key: 'Removed today',
      value: `−${stats?.removed_today ?? 0}`,
      sub: 'sold or pulled',
      tint: 'var(--danger)',
      to: '/activity?event_type=removed',
    },
    {
      key: 'Active alerts',
      value: (stats?.active_alerts ?? 0).toString(),
      sub: 'watchlist triggers',
      tint: undefined,
      to: '/watchlist',
    },
    {
      key: 'Avg list',
      value: stats?.avg_price ? `$${(stats.avg_price / 1000).toFixed(1)}k` : '—',
      sub: 'weighted by lot',
      tint: undefined,
      to: null,
    },
  ]

  return (
    <div style={{ maxWidth: 1280, margin: '0 auto', padding: '2rem 2.5rem' }}>
      {/* Header */}
      <header
        className="flex items-start justify-between flex-wrap gap-6 pb-6"
        style={{ borderBottom: '1px solid var(--hairline)' }}
      >
        <div className="min-w-0" style={{ flex: '1 1 320px' }}>
          <div className="eyebrow">Dashboard</div>
          <h1
            className="serif mt-3"
            style={{
              fontSize: 'clamp(32px, 4vw, 44px)',
              lineHeight: 1.1,
              letterSpacing: '-0.015em',
              color: 'var(--ink)',
            }}
          >
            {locationLabel}
          </h1>
          <p className="text-sm mt-3" style={{ color: 'var(--muted)', lineHeight: 1.5 }}>
            {locationSub}
          </p>
        </div>
        <ScrapeStatus stats={stats} scraping={scraping} />
      </header>

      {/* 5-metric stat strip */}
      <section
        className="grid grid-cols-2 md:grid-cols-5 mt-8"
        style={{ borderTop: '1px solid var(--hairline)', borderBottom: '1px solid var(--hairline)' }}
      >
        {statCells.map((cell, i) => {
          const inner = (
            <>
              <div className="eyebrow">{cell.key}</div>
              <div
                className="midnum mt-2 tnum"
                style={{ color: cell.tint ?? 'var(--ink)' }}
              >
                {cell.value}
              </div>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 4 }}>{cell.sub}</div>
            </>
          )
          const cellStyle: React.CSSProperties = {
            padding: '20px 20px',
            borderLeft: i > 0 ? '1px solid var(--hairline)' : 'none',
          }
          return cell.to ? (
            <Link
              key={cell.key}
              to={cell.to}
              style={cellStyle}
              className="block t"
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-2)')}
              onMouseLeave={e => (e.currentTarget.style.background = '')}
            >
              {inner}
            </Link>
          ) : (
            <div key={cell.key} style={cellStyle}>{inner}</div>
          )
        })}
      </section>

      {/* Trend chart + Activity stream */}
      <section className="grid grid-cols-12 gap-8 mt-10">
        <div className="col-span-12 lg:col-span-8">
          <div className="flex items-baseline justify-between flex-wrap gap-4">
            <div className="eyebrow">Inventory · last 14 days</div>
            <div className="flex items-center gap-4" style={{ fontSize: 11, color: 'var(--muted)' }}>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full" style={{ background: C.accent }} />
                Total units
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2 h-0.5" style={{ background: C.positive }} />
                Added
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="w-2 h-0.5" style={{ background: C.danger }} />
                Removed
              </span>
            </div>
          </div>
          <div className="mt-4">
            {stats?.trend && stats.trend.length > 0 ? (
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={stats.trend} margin={{ top: 8, right: 4, left: 0, bottom: 16 }}>
                  <defs>
                    <linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor={C.accent} stopOpacity={0.12} />
                      <stop offset="95%" stopColor={C.accent} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="2 5" stroke={C.hairline} />
                  <XAxis dataKey="date" tick={<ChartTick />} tickLine={false} axisLine={false} />
                  <YAxis tick={<YChartTick />} tickLine={false} axisLine={false} width={36} />
                  <Tooltip content={<ChartTooltip />} />
                  <Area
                    type="monotone" dataKey="count"
                    stroke={C.accent} fill="url(#trendGrad)"
                    strokeWidth={1.6} dot={false} name="Total"
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <EmptyChart height={240} />
            )}
          </div>
        </div>

        {/* Activity stream */}
        <div className="col-span-12 lg:col-span-4 lg:pl-8 hairline-v">
          <div className="flex items-baseline justify-between">
            <div className="eyebrow">Activity stream</div>
            <Link to="/activity" style={{ fontSize: 11, color: 'var(--accent)' }}
              className="hover:underline">Full log →</Link>
          </div>
          <div className="mt-4">
            {events.length === 0 ? (
              <p style={{ fontSize: 13, color: 'var(--muted)', paddingTop: 24, textAlign: 'center' }}>
                No activity yet
              </p>
            ) : (
              events.map((ev, i) => <EventRow key={ev.id} ev={ev} border={i > 0} />)
            )}
          </div>
        </div>
      </section>

      {/* Daily changes + Scrape history */}
      <section className="grid grid-cols-12 gap-8 mt-10">
        <div className="col-span-12 lg:col-span-5">
          <div className="eyebrow">Daily changes</div>
          {stats?.trend && stats.trend.length > 0 ? (
            <div className="mt-4">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={stats.trend} margin={{ top: 8, right: 4, left: 0, bottom: 16 }}>
                  <CartesianGrid strokeDasharray="2 5" stroke={C.hairline} />
                  <XAxis dataKey="date" tick={<ChartTick />} tickLine={false} axisLine={false} />
                  <YAxis tick={<YChartTick />} tickLine={false} axisLine={false} width={28} />
                  <Tooltip content={<ChartTooltip />} />
                  <Bar dataKey="added" fill={C.positive} name="Added" radius={[2, 2, 0, 0]} />
                  <Bar dataKey="removed" fill={C.danger} name="Removed" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <EmptyChart height={200} />
          )}
        </div>

        {/* Scrape history */}
        <div className="col-span-12 lg:col-span-7 lg:pl-8 hairline-v">
          <div className="flex items-baseline justify-between">
            <div className="eyebrow">Scrape history</div>
            <span className="mono" style={{ fontSize: 11, color: 'var(--muted)' }}>
              {logs.length} runs
            </span>
          </div>
          <div className="mt-4">
            {logs.length === 0 ? (
              <p style={{ fontSize: 13, color: 'var(--muted)', paddingTop: 24, textAlign: 'center' }}>
                No scrapes yet
              </p>
            ) : (
              logs.slice(0, 8).map((log, i) => <LogRow key={log.id} log={log} border={i > 0} />)
            )}
          </div>
        </div>
      </section>

      {/* Aging inventory queue */}
      <section className="mt-12">
        <div
          className="flex items-baseline justify-between flex-wrap gap-4 pb-4"
          style={{ borderBottom: '1px solid var(--hairline)' }}
        >
          <div>
            <div className="eyebrow">Move first</div>
            <h2
              className="serif mt-1"
              style={{ fontSize: 30, color: 'var(--ink)', lineHeight: 1.1 }}
            >
              Aging inventory queue
            </h2>
            <p className="text-sm mt-2 max-w-lg" style={{ color: 'var(--muted)', lineHeight: 1.5 }}>
              Units past 30 days on the lot — sorted by urgency. Review pricing or stage for featured placement.
            </p>
          </div>
          <Link to="/inventory" className="btn">Open inventory →</Link>
        </div>

        {priorityUnits.length === 0 ? (
          <p style={{ fontSize: 13, color: 'var(--muted)', padding: '48px 0', textAlign: 'center' }}>
            No active units available for prioritization yet
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3">
            {priorityUnits.map((vehicle, i) => (
              <PriorityUnitCard key={vehicle.id} vehicle={vehicle} index={i} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function ScrapeStatus({ stats, scraping }: { stats: Stats | null; scraping: boolean }) {
  const isScraping = scraping || stats?.scraping_now
  if (isScraping) {
    return (
      <div className="flex items-center gap-2">
        <div className="chip animate-pulse">
          <RefreshCw className="w-3 h-3 animate-spin" style={{ color: 'var(--accent)' }} />
          <span>Scraping...</span>
        </div>
      </div>
    )
  }
  if (!stats?.last_scrape) return null

  const lastScrape = new Date(`${stats.last_scrape}Z`)
  const ok = stats.last_scrape_status === 'success'
  const stale = ok && Date.now() - lastScrape.getTime() > 12 * 60 * 60 * 1000
  const Icon = !ok ? XCircle : stale ? AlertCircle : CheckCircle
  const iconColor = !ok ? 'var(--danger)' : stale ? 'var(--warn)' : 'var(--positive)'

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <a
        href="https://almtracker.vercel.app"
        target="_blank"
        rel="noreferrer"
        className="btn"
        title="Open ALM Tracker"
      >
        <ExternalLink className="h-3 w-3" />
        almtracker.vercel.app
      </a>
      <div className="chip">
        <span className="w-1.5 h-1.5 rounded-full live-dot" style={{ background: iconColor }} />
        <Icon className="w-3 h-3" style={{ color: iconColor }} />
        <span className="mono" style={{ fontSize: 11 }}>
          {ok ? 'Synced' : 'Failed'} {formatDistanceToNow(lastScrape, { addSuffix: true })}
        </span>
      </div>
      <span className="mono" style={{ fontSize: 10.5, color: 'var(--muted)' }}>
        {format(lastScrape, "MMM d 'at' h:mm a")}
      </span>
    </div>
  )
}

function EventRow({ ev, border }: { ev: VehicleEvent; border: boolean }) {
  const dotColor =
    ev.event_type === 'added' ? 'var(--positive)'
    : ev.event_type === 'removed' ? 'var(--danger)'
    : 'var(--accent)'
  return (
    <div
      className="flex gap-3 py-3"
      style={{ borderTop: border ? '1px solid var(--hairline)' : 'none' }}
    >
      <div
        className="mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0"
        style={{ background: dotColor }}
      />
      <div className="flex-1 min-w-0">
        <p className="truncate" style={{ fontSize: 12.5, color: 'var(--ink)', lineHeight: 1.4 }}>
          {ev.description}
        </p>
        <p className="mono truncate mt-0.5" style={{ fontSize: 11, color: 'var(--muted)', lineHeight: 1.4 }}>
          {ev.location_name && <span style={{ color: 'var(--ink-2)' }}>{ev.location_name} · </span>}
          {formatDistanceToNow(new Date(ev.timestamp + 'Z'), { addSuffix: true })}
        </p>
      </div>
    </div>
  )
}

function LogRow({ log, border }: { log: ScrapeLog; border: boolean }) {
  const ok = log.status === 'success'
  const Icon = ok ? CheckCircle : log.status === 'error' ? XCircle : AlertCircle
  const iconColor = ok ? 'var(--positive)' : log.status === 'error' ? 'var(--danger)' : 'var(--warn)'
  return (
    <div
      className="flex items-center gap-4 py-3"
      style={{ borderTop: border ? '1px solid var(--hairline)' : 'none' }}
    >
      <Icon className="w-3.5 h-3.5 flex-shrink-0" style={{ color: iconColor }} />
      <div className="flex-1 min-w-0 flex items-center gap-3 flex-wrap">
        <span className="mono tnum" style={{ fontSize: 12, color: 'var(--ink)' }}>
          {log.vehicles_found.toLocaleString()} vehicles
        </span>
        {log.added_count > 0 && (
          <span className="mono tnum" style={{ fontSize: 11, color: 'var(--positive)' }}>+{log.added_count}</span>
        )}
        {log.removed_count > 0 && (
          <span className="mono tnum" style={{ fontSize: 11, color: 'var(--danger)' }}>−{log.removed_count}</span>
        )}
        {log.method && (
          <span className="mono truncate" style={{ fontSize: 10.5, color: 'var(--muted)' }}>({log.method})</span>
        )}
      </div>
      <span className="mono flex-shrink-0" style={{ fontSize: 10.5, color: 'var(--muted)' }}>
        {formatDistanceToNow(new Date(log.timestamp + 'Z'), { addSuffix: true })}
      </span>
    </div>
  )
}

function AgingBar({ days }: { days: number }) {
  const pct = Math.min(1, days / 90)
  const color = days >= 60 ? 'var(--danger)' : days >= 45 ? 'var(--warn)' : days >= 15 ? 'var(--accent)' : 'var(--positive)'
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="relative flex-1 overflow-hidden" style={{ height: 10 }}>
        <div className="absolute inset-y-0 left-0 w-full matrix" style={{ color: 'var(--hairline-2)' }} />
        <div className="absolute inset-y-0 left-0 matrix" style={{ width: `${pct * 100}%`, color }} />
      </div>
      <span className="mono tnum whitespace-nowrap" style={{ fontSize: 10, color }}>{days}d</span>
    </div>
  )
}

function PriorityUnitCard({ vehicle, index }: { vehicle: Vehicle; index: number }) {
  const ageColor =
    vehicle.days_on_lot >= 60 ? 'var(--danger)'
    : vehicle.days_on_lot >= 45 ? 'var(--warn)'
    : 'var(--muted)'

  return (
    <article
      style={{
        padding: '20px 20px',
        borderLeft: '1px solid var(--hairline)',
        borderBottom: '1px solid var(--hairline)',
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mono tnum" style={{ fontSize: 10.5, color: 'var(--muted)' }}>
            #{vehicle.stock_number}
          </div>
          <h3 className="serif mt-1" style={{ fontSize: 22, color: 'var(--ink)', lineHeight: 1.2 }}>
            {vehicle.year} {vehicle.make}
          </h3>
          <div style={{ fontSize: 13, color: 'var(--ink-2)', marginTop: 6 }}>
            {vehicle.model}{vehicle.trim ? ` · ${vehicle.trim}` : ''}
          </div>
        </div>
        <div className="text-right flex-shrink-0">
          <span className="mono tnum" style={{ fontSize: 11, color: ageColor }}>
            {vehicle.days_on_lot}d
          </span>
          <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 2 }}>on lot</div>
        </div>
      </div>

      {/* Striped image placeholder */}
      <div
        className="stripes mt-4 w-full flex items-end justify-between gap-2 p-2 mono"
        style={{ aspectRatio: '16/7', fontSize: 10, color: 'var(--muted)' }}
      >
        <span className="truncate">{vehicle.exterior_color || '—'}</span>
        <span className="flex-shrink-0">product shot</span>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2">
        <div>
          <div className="eyebrow">Price</div>
          <div className="serif tnum mt-0.5" style={{ fontSize: 18, color: 'var(--ink)' }}>
            {fmt$(vehicle.price)}
          </div>
        </div>
        <div>
          <div className="eyebrow">Mileage</div>
          <div className="mono tnum mt-1" style={{ fontSize: 12, color: 'var(--ink-2)' }}>
            {fmtMi(vehicle.mileage)}
          </div>
        </div>
        <div>
          <div className="eyebrow">Lot</div>
          <div className="mt-1 truncate" style={{ fontSize: 12, color: 'var(--ink-2)' }}>
            {(vehicle.location_name ?? '—').replace('ALM ', '')}
          </div>
        </div>
      </div>

      <div className="mt-4">
        <AgingBar days={vehicle.days_on_lot} />
      </div>

      <div className="mt-4 flex items-center gap-2">
        <Link
          to={`/inventory?search=${encodeURIComponent(vehicle.stock_number)}`}
          className="btn"
        >
          Review unit
        </Link>
        {vehicle.listing_url && (
          <a href={vehicle.listing_url} target="_blank" rel="noreferrer" className="btn btn-ghost">
            View listing
          </a>
        )}
      </div>
    </article>
  )
}

function EmptyChart({ height = 200 }: { height?: number }) {
  return (
    <div
      className="flex items-center justify-center"
      style={{ height, borderTop: '1px dashed var(--hairline)' }}
    >
      <p style={{ fontSize: 13, color: 'var(--muted)' }}>Chart data will appear after first scrape</p>
    </div>
  )
}

function LoadingScreen() {
  return (
    <div style={{ maxWidth: 1280, margin: '0 auto', padding: '2rem 2.5rem' }}
      className="animate-pulse space-y-8">
      <div className="h-10 w-64 rounded" style={{ background: 'var(--bg-2)' }} />
      <div
        className="grid grid-cols-5"
        style={{ borderTop: '1px solid var(--hairline)', borderBottom: '1px solid var(--hairline)' }}
      >
        {[...Array(5)].map((_, i) => (
          <div key={i} style={{ padding: '20px', borderLeft: i > 0 ? '1px solid var(--hairline)' : 'none' }}>
            <div className="h-2 w-16 rounded mb-3" style={{ background: 'var(--bg-2)' }} />
            <div className="h-8 w-20 rounded" style={{ background: 'var(--bg-2)' }} />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-12 gap-8">
        <div className="col-span-8 h-64 rounded" style={{ background: 'var(--bg-2)' }} />
        <div className="col-span-4 h-64 rounded" style={{ background: 'var(--bg-2)' }} />
      </div>
    </div>
  )
}
