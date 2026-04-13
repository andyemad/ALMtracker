import React, { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, LineChart, Line, Legend,
} from 'recharts'
import { TrendingUp, Car, DollarSign, Gauge, AlertTriangle, ExternalLink } from 'lucide-react'
import { getAnalytics } from '../api'
import { useDealer } from '../context/DealerContext'
import type { AnalyticsData } from '../types'

const BRAND_COLORS = ['#6366f1', '#22d3ee', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f97316', '#84cc16', '#0ea5e9', '#a855f7']
const MOG_DEALER_ID = 323

const COLOR_MAP: Record<string, string> = {
  white: '#f1f5f9', gray: '#94a3b8', silver: '#cbd5e1', black: '#1e293b',
  red: '#ef4444', blue: '#3b82f6', green: '#22c55e', brown: '#92400e',
  beige: '#d4b483', gold: '#d97706', orange: '#f97316', yellow: '#eab308',
  purple: '#a855f7', maroon: '#9f1239', tan: '#c9a96e', navy: '#1e3a5f',
  charcoal: '#374151', champagne: '#f5e8c7',
}

function guessColorHex(name: string): string {
  const lower = name.toLowerCase()
  for (const [key, hex] of Object.entries(COLOR_MAP)) {
    if (lower.includes(key)) return hex
  }
  return '#64748b'
}

function fmt$(n: number) {
  return n >= 1000 ? `$${(n / 1000).toFixed(1)}k` : `$${n}`
}

function fmtFull$(n: number) {
  return `$${n.toLocaleString()}`
}

interface KpiCardProps {
  icon: React.ReactNode
  label: string
  value: string
  sub?: string
  accent?: string
}

function KpiCard({ icon, label, value, sub, accent = 'from-brand-500/20 to-cyan-500/10' }: KpiCardProps) {
  return (
    <div className={`relative overflow-hidden rounded-2xl border border-slate-800/80 bg-gradient-to-br ${accent} p-5 backdrop-blur-sm`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-400">{label}</p>
          <p className="mt-1.5 text-3xl font-bold text-white">{value}</p>
          {sub && <p className="mt-1 text-xs text-slate-500">{sub}</p>}
        </div>
        <div className="rounded-xl bg-slate-800/60 p-2.5 text-slate-300">{icon}</div>
      </div>
    </div>
  )
}

const urgencyConfig = {
  critical: { label: 'Critical', bg: 'bg-red-500/15 border-red-500/30 text-red-400', dot: 'bg-red-400' },
  high:     { label: 'High',     bg: 'bg-orange-500/15 border-orange-500/30 text-orange-400', dot: 'bg-orange-400' },
  medium:   { label: 'Medium',   bg: 'bg-amber-500/15 border-amber-500/30 text-amber-400', dot: 'bg-amber-400' },
}

function UrgencyBadge({ urgency }: { urgency: 'critical' | 'high' | 'medium' }) {
  const cfg = urgencyConfig[urgency]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${cfg.bg}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  )
}

const CustomBarTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 shadow-xl text-xs">
      <p className="font-semibold text-white mb-1">{label}</p>
      {payload.map((p: any, i: number) => (
        <p key={i} style={{ color: p.color }}>{p.name}: <span className="font-bold">{p.value}</span></p>
      ))}
    </div>
  )
}

const CustomLineTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2 shadow-xl text-xs">
      <p className="font-semibold text-slate-400 mb-1">{label}</p>
      <p className="text-cyan-400 font-bold">{payload[0].value} sold</p>
    </div>
  )
}

export default function Analytics() {
  const { selectedDealer } = useDealer()
  const [data, setData] = useState<AnalyticsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [urgencyFilter, setUrgencyFilter] = useState<'all' | 'critical' | 'high' | 'medium'>('all')
  const [selectedMake, setSelectedMake] = useState<string | null>(null)
  const [selectedModel, setSelectedModel] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    getAnalytics(selectedDealer?.id)
      .then(setData)
      .finally(() => setLoading(false))
  }, [selectedDealer?.id])

  if (loading) {
    return (
      <div className="p-6 space-y-6 animate-pulse">
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <div key={i} className="h-28 rounded-2xl bg-slate-800/60" />)}
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="h-72 rounded-2xl bg-slate-800/60" />
          <div className="h-72 rounded-2xl bg-slate-800/60" />
        </div>
      </div>
    )
  }

  if (!data || data.summary.total_sold === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-center">
        <Car className="w-12 h-12 text-slate-600 mb-4" />
        <p className="text-slate-400">No sold vehicle data available yet.</p>
        <p className="text-slate-600 text-sm mt-1">Analytics will populate once vehicles cycle off the lot.</p>
      </div>
    )
  }

  const { summary, top_makes, top_models, top_years, top_colors, body_styles, condition_split,
    price_buckets, velocity_by_make, weekly_trend, location_performance,
    branded_location_split, make_model_breakdown, model_year_breakdown, cars_to_move } = data

  const filteredCarsToMove = urgencyFilter === 'all'
    ? cars_to_move
    : cars_to_move.filter(c => c.urgency === urgencyFilter)

  // For pie chart we want a nice donut
  const bodyPieData = body_styles.slice(0, 6)
  return (
    <div className="p-4 sm:p-6 space-y-8">

      {/* Page header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-white">Sales Analytics</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {selectedDealer ? selectedDealer.name : 'All 24 Locations'} ·{' '}
            {summary.date_from && summary.date_to
              ? `${summary.date_from} → ${summary.date_to}`
              : 'All time'}
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs text-emerald-400 font-semibold">
          <TrendingUp className="w-3.5 h-3.5" />
          {summary.total_sold.toLocaleString()} vehicles sold
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard
          icon={<Car className="w-5 h-5" />}
          label="Total Sold"
          value={summary.total_sold.toLocaleString()}
          sub={`${condition_split.new} new · ${condition_split.preowned} pre-owned`}
          accent="from-brand-500/20 to-brand-600/5"
        />
        <KpiCard
          icon={<DollarSign className="w-5 h-5" />}
          label="Avg Sale Price"
          value={fmtFull$(summary.avg_price)}
          sub="per vehicle"
          accent="from-emerald-500/20 to-emerald-600/5"
        />
        <KpiCard
          icon={<Gauge className="w-5 h-5" />}
          label="Avg Mileage"
          value={summary.avg_mileage.toLocaleString()}
          sub="miles at sale"
          accent="from-amber-500/20 to-amber-600/5"
        />
        <KpiCard
          icon={<TrendingUp className="w-5 h-5" />}
          label="Most Popular Make"
          value={top_makes[0]?.make ?? '—'}
          sub={top_makes[0] ? `${top_makes[0].pct}% of all sales · ${top_makes[0].count} units` : undefined}
          accent="from-violet-500/20 to-violet-600/5"
        />
      </div>

      {/* Top Makes + Body Styles row */}
      <div className="grid gap-6 lg:grid-cols-3">

        {/* Top Makes horizontal bar */}
        <div className="lg:col-span-2 rounded-2xl border border-slate-800/80 bg-slate-900/40 p-5">
          <div className="flex items-start justify-between gap-2 mb-1">
            <h2 className="text-sm font-bold text-white">Best-Selling Makes</h2>
            {selectedMake && (
              <button
                onClick={() => setSelectedMake(null)}
                className="text-[10px] font-semibold text-slate-500 hover:text-slate-300 transition-colors flex items-center gap-1"
              >
                ✕ clear
              </button>
            )}
          </div>
          <p className="text-xs text-slate-500 mb-4">
            {selectedMake ? `Showing models for ${selectedMake} — click another bar or clear` : '% of all sold vehicles · click a bar to see models'}
          </p>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={top_makes}
                layout="vertical"
                margin={{ left: 8, right: 24 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} unit="%" />
                <YAxis type="category" dataKey="make" tick={{ fill: '#94a3b8', fontSize: 11 }} width={72} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomBarTooltip />} cursor={{ fill: 'rgba(99,102,241,0.07)' }} />
                <Bar dataKey="pct" name="% of Sales" radius={[0, 6, 6, 0]}>
                  {top_makes.map((m, i) => (
                    <Cell key={i} fill={BRAND_COLORS[i % BRAND_COLORS.length]} opacity={selectedMake && selectedMake !== m.make ? 0.3 : 1} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Clickable make buttons */}
          <div className="flex flex-wrap gap-1.5 mt-3">
            {top_makes.map((m, i) => (
              <button
                key={m.make}
                onClick={() => setSelectedMake(prev => prev === m.make ? null : m.make)}
                className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-all ${
                  selectedMake === m.make
                    ? 'border-brand-500/50 bg-brand-500/20 text-white'
                    : 'border-slate-700/50 bg-slate-800/40 text-slate-400 hover:text-white hover:border-slate-600'
                }`}
              >
                <span className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: BRAND_COLORS[i % BRAND_COLORS.length] }} />
                {m.make}
                <span className="text-slate-600">{m.count}</span>
              </button>
            ))}
          </div>

          {/* Model drilldown — expands when a make is selected */}
          {selectedMake && make_model_breakdown?.[selectedMake] && make_model_breakdown[selectedMake].length > 0 && (
            <div className="mt-3 border-t border-slate-800 pt-3">
              <p className="text-xs font-bold text-white mb-2">
                {selectedMake} — top models sold
              </p>
              <div className="flex flex-wrap gap-2">
                {make_model_breakdown[selectedMake].map((m) => {
                  const makeIdx = top_makes.findIndex(mk => mk.make === selectedMake)
                  const color = BRAND_COLORS[makeIdx % BRAND_COLORS.length]
                  return (
                    <div
                      key={m.model}
                      className="flex items-center gap-2 rounded-lg border border-slate-700/50 bg-slate-800/60 px-3 py-2 text-xs"
                    >
                      <span className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: color }} />
                      <span className="font-bold text-white">{m.model}</span>
                      <span className="text-slate-400">{m.count} sold</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>

        {/* Body Style donut */}
        <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-5">
          <h2 className="text-sm font-bold text-white mb-1">Body Style Mix</h2>
          <p className="text-xs text-slate-500 mb-4">sold vehicles by type</p>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={bodyPieData} dataKey="count" nameKey="body_style" cx="50%" cy="50%"
                  innerRadius="54%" outerRadius="78%" paddingAngle={3}>
                  {bodyPieData.map((_, i) => (
                    <Cell key={i} fill={BRAND_COLORS[i % BRAND_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(val: number) => [`${val} units`, '']} contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 12, fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3 space-y-1.5">
            {bodyPieData.map((b, i) => (
              <div key={b.body_style} className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: BRAND_COLORS[i % BRAND_COLORS.length] }} />
                  <span className="text-slate-400">{b.body_style}</span>
                </div>
                <span className="font-semibold text-white">{b.pct}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Best Selling Model Years */}
      {top_years.length > 0 && (
        <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-5">
          <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
            <div>
              <h2 className="text-sm font-bold text-white">Best Selling Model Years</h2>
              <p className="text-xs text-slate-500 mt-0.5">volume by vehicle model year — newer years reflect franchise new-car sales</p>
            </div>
            <div className="flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1.5 text-slate-500">
                <span className="h-2 w-2 rounded-sm bg-brand-500" />New inventory
              </span>
              <span className="flex items-center gap-1.5 text-slate-500">
                <span className="h-2 w-2 rounded-sm bg-cyan-500" />Recent used
              </span>
              <span className="flex items-center gap-1.5 text-slate-500">
                <span className="h-2 w-2 rounded-sm bg-slate-600" />Older
              </span>
            </div>
          </div>
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={[...top_years].sort((a, b) => b.year - a.year)}
                margin={{ left: 0, right: 12 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="year" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomBarTooltip />} cursor={{ fill: 'rgba(99,102,241,0.07)' }} />
                <Bar dataKey="count" name="Units Sold" radius={[6, 6, 0, 0]}>
                  {[...top_years].sort((a, b) => b.year - a.year).map((y) => (
                    <Cell
                      key={y.year}
                      fill={y.year >= 2025 ? '#6366f1' : y.year >= 2022 ? '#22d3ee' : '#475569'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          {/* Year breakdown pills */}
          <div className="mt-3 flex flex-wrap gap-2">
            {[...top_years].sort((a, b) => b.year - a.year).map((y) => (
              <div key={y.year}
                className="flex items-center gap-1.5 rounded-lg border border-slate-700/50 bg-slate-800/40 px-2.5 py-1 text-xs">
                <span className="font-bold text-white">{y.year}</span>
                <span className="text-slate-400">{y.count} sold</span>
                <span className="text-slate-600">·</span>
                <span className="text-slate-500">{y.pct}%</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Weekly Trend + Price Distribution */}
      <div className="grid gap-6 lg:grid-cols-2">

        {/* Weekly trend line */}
        <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-5">
          <h2 className="text-sm font-bold text-white mb-1">Weekly Sales Trend</h2>
          <p className="text-xs text-slate-500 mb-4">vehicles leaving the lot per week</p>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={weekly_trend} margin={{ left: 0, right: 12 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="week" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} interval="preserveStartEnd" />
                <YAxis tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip content={<CustomLineTooltip />} />
                <Line type="monotone" dataKey="sold" stroke="#22d3ee" strokeWidth={2.5}
                  dot={{ r: 3, fill: '#22d3ee', strokeWidth: 0 }}
                  activeDot={{ r: 5, fill: '#22d3ee', stroke: '#0f172a', strokeWidth: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Price distribution */}
        <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-5">
          <h2 className="text-sm font-bold text-white mb-1">Price Distribution</h2>
          <p className="text-xs text-slate-500 mb-4">% of sold vehicles by price range</p>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={price_buckets} margin={{ left: 0, right: 12 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="range" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} unit="%" />
                <Tooltip content={<CustomBarTooltip />} cursor={{ fill: 'rgba(16,185,129,0.07)' }} />
                <Bar dataKey="pct" name="% of Sales" radius={[6, 6, 0, 0]}>
                  {price_buckets.map((_, i) => (
                    <Cell key={i} fill={BRAND_COLORS[i % BRAND_COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Top colors */}
      <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-5">
        <h2 className="text-sm font-bold text-white mb-1">Top Exterior Colors</h2>
        <p className="text-xs text-slate-500 mb-4">most popular colors among sold vehicles</p>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
          {top_colors.slice(0, 10).map((c) => (
            <div key={c.color} className="flex items-center gap-2.5 rounded-xl border border-slate-700/50 bg-slate-800/40 px-3 py-2">
              <span
                className="h-7 w-7 rounded-lg flex-shrink-0 border border-slate-700/60"
                style={{ background: guessColorHex(c.color) }}
              />
              <div className="min-w-0">
                <p className="text-xs font-medium text-slate-200 truncate">{c.color}</p>
                <p className="text-[10px] text-slate-500">{c.count} sold · {c.pct}%</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Top Models table */}
      <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-5">
        <h2 className="text-sm font-bold text-white mb-1">Top Selling Models</h2>
        <p className="text-xs text-slate-500 mb-4">click any row to see year breakdown</p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-slate-800">
                <th className="pb-2 text-left font-semibold text-slate-500 w-8">#</th>
                <th className="pb-2 text-left font-semibold text-slate-500">Model</th>
                <th className="pb-2 text-right font-semibold text-slate-500">Units</th>
                <th className="pb-2 text-right font-semibold text-slate-500">Avg Price</th>
                <th className="pb-2 w-6" />
              </tr>
            </thead>
            <tbody>
              {top_models.map((m, i) => {
                const modelKey = `${m.make}|${m.model}`
                const isOpen = selectedModel === modelKey
                const years = model_year_breakdown?.[modelKey]
                return (
                  <React.Fragment key={modelKey}>
                    <tr
                      onClick={() => setSelectedModel(prev => prev === modelKey ? null : modelKey)}
                      className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors cursor-pointer"
                    >
                      <td className="py-2.5 text-slate-600 font-mono">{i + 1}</td>
                      <td className="py-2.5">
                        <span className="font-semibold text-white">{m.make} {m.model}</span>
                      </td>
                      <td className="py-2.5 text-right">
                        <span className="font-bold text-cyan-400">{m.count}</span>
                      </td>
                      <td className="py-2.5 text-right text-slate-300">{m.avg_price ? fmtFull$(m.avg_price) : '—'}</td>
                      <td className="py-2.5 text-right text-slate-600">
                        <span className={`inline-block transition-transform ${isOpen ? 'rotate-90' : ''}`}>›</span>
                      </td>
                    </tr>
                    {isOpen && years && years.length > 0 && (
                      <tr className="border-b border-slate-800/50 bg-slate-800/20">
                        <td />
                        <td colSpan={4} className="py-2.5 pr-2">
                          <div className="flex flex-wrap gap-2">
                            {years.map((y: { year: number; count: number }) => (
                              <div key={y.year} className="flex items-center gap-1.5 rounded-lg border border-slate-700/50 bg-slate-900/60 px-2.5 py-1 text-xs">
                                <span className="font-bold text-white">{y.year}</span>
                                <span className="text-slate-400">{y.count} sold</span>
                              </div>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Location Performance (all-locations only) */}
      {!selectedDealer && location_performance.length > 0 && (
        <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-5">
          <h2 className="text-sm font-bold text-white mb-1">Location Performance</h2>
          <p className="text-xs text-slate-500 mb-4">all 24 ALM locations ranked by sold volume</p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="pb-2 text-left font-semibold text-slate-500">Location</th>
                  <th className="pb-2 text-right font-semibold text-slate-500">Sold</th>
                  <th className="pb-2 text-right font-semibold text-slate-500">% Share</th>
                  <th className="pb-2 text-right font-semibold text-slate-500 hidden sm:table-cell">Avg Price</th>
                  <th className="pb-2 text-right font-semibold text-slate-500 hidden sm:table-cell">Avg Days</th>
                  <th className="pb-2 text-right font-semibold text-slate-500 hidden md:table-cell">Top Make</th>
                </tr>
              </thead>
              <tbody>
                {location_performance.map((loc) => {
                  const isMog = loc.dealer_id === MOG_DEALER_ID
                  return (
                    <tr key={loc.dealer_id}
                      className={`border-b border-slate-800/50 transition-colors ${isMog ? 'bg-brand-900/20' : 'hover:bg-slate-800/30'}`}>
                      <td className="py-2.5">
                        <div className="flex items-center gap-2">
                          {isMog && <span className="h-1.5 w-1.5 rounded-full bg-brand-400 flex-shrink-0" />}
                          <span className={`font-medium ${isMog ? 'text-brand-300' : 'text-slate-200'}`}>{loc.name}</span>
                          {isMog && <span className="text-[10px] font-bold text-brand-400 bg-brand-500/20 rounded px-1.5 py-0.5">MOG</span>}
                        </div>
                      </td>
                      <td className="py-2.5 text-right">
                        <span className={`font-bold ${isMog ? 'text-brand-300' : 'text-cyan-400'}`}>{loc.sold}</span>
                      </td>
                      <td className="py-2.5 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <div className="hidden sm:block w-16 h-1.5 rounded-full bg-slate-800 overflow-hidden">
                            <div className="h-full rounded-full" style={{ width: `${Math.min(loc.pct * 3, 100)}%`, background: isMog ? '#6366f1' : '#22d3ee' }} />
                          </div>
                          <span className="text-slate-400">{loc.pct}%</span>
                        </div>
                      </td>
                      <td className="py-2.5 text-right text-slate-400 hidden sm:table-cell">{loc.avg_price ? fmtFull$(loc.avg_price) : '—'}</td>
                      <td className="py-2.5 text-right hidden sm:table-cell">
                        <span className={loc.avg_days <= 10 ? 'text-emerald-400' : loc.avg_days <= 20 ? 'text-amber-400' : 'text-red-400'}>
                          {loc.avg_days}d
                        </span>
                      </td>
                      <td className="py-2.5 text-right text-slate-400 hidden md:table-cell">{loc.top_make || '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Franchise: New vs Used Split */}
      {branded_location_split.length > 0 && (
        <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-5">
          <div className="flex items-center gap-3 mb-1">
            <h2 className="text-sm font-bold text-white">New vs. Used — Franchise Locations</h2>
            <span className="rounded-full border border-brand-500/30 bg-brand-500/10 px-2 py-0.5 text-[10px] font-bold text-brand-400 uppercase tracking-wide">
              {branded_location_split.length} Branded Dealers
            </span>
          </div>
          <p className="text-xs text-slate-500 mb-5">OEM franchise stores only · used-only lots excluded · sorted by total volume</p>

          {/* Stacked bar chart */}
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={branded_location_split}
                layout="vertical"
                margin={{ left: 8, right: 48 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                <XAxis type="number" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis
                  type="category"
                  dataKey="name"
                  tick={{ fill: '#94a3b8', fontSize: 10 }}
                  width={130}
                  axisLine={false}
                  tickLine={false}
                  tickFormatter={(v: string) => v.replace('ALM ', '').replace(' South', ' S.').replace(' West', ' W.').replace(' Marietta', ' Mar.')}
                />
                <Tooltip
                  content={({ active, payload, label }) => {
                    if (!active || !payload?.length) return null
                    const d = branded_location_split.find(x => x.name === label)
                    return (
                      <div className="rounded-xl border border-slate-700 bg-slate-900 px-3 py-2.5 shadow-xl text-xs min-w-[180px]">
                        <p className="font-bold text-white mb-2 text-[11px]">{label}</p>
                        <div className="space-y-1">
                          <div className="flex justify-between gap-4">
                            <span className="text-emerald-400">New</span>
                            <span className="font-bold text-white">{d?.new} <span className="text-slate-500 font-normal">({d?.new_pct}%)</span></span>
                          </div>
                          <div className="flex justify-between gap-4">
                            <span className="text-cyan-400">Used</span>
                            <span className="font-bold text-white">{d?.used} <span className="text-slate-500 font-normal">({d?.used_pct}%)</span></span>
                          </div>
                          {d?.avg_new_price ? (
                            <div className="flex justify-between gap-4 pt-1 border-t border-slate-800 mt-1">
                              <span className="text-slate-500">Avg New</span>
                              <span className="text-slate-300">${d.avg_new_price.toLocaleString()}</span>
                            </div>
                          ) : null}
                          {d?.avg_used_price ? (
                            <div className="flex justify-between gap-4">
                              <span className="text-slate-500">Avg Used</span>
                              <span className="text-slate-300">${d.avg_used_price.toLocaleString()}</span>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    )
                  }}
                  cursor={{ fill: 'rgba(99,102,241,0.06)' }}
                />
                <Legend
                  iconType="square"
                  iconSize={8}
                  formatter={(v) => <span className="text-xs text-slate-400 capitalize">{v}</span>}
                  wrapperStyle={{ paddingTop: 8 }}
                />
                <Bar dataKey="new" name="New" stackId="a" fill="#10b981" radius={[0, 0, 0, 0]} />
                <Bar dataKey="used" name="Used" stackId="a" fill="#6366f1" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Summary table for franchise locations */}
          <div className="mt-5 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="pb-2 text-left font-semibold text-slate-500">Location</th>
                  <th className="pb-2 text-right font-semibold text-emerald-500">New</th>
                  <th className="pb-2 text-right font-semibold text-brand-400">Used</th>
                  <th className="pb-2 text-right font-semibold text-slate-500">Total</th>
                  <th className="pb-2 text-right font-semibold text-slate-500 hidden sm:table-cell">Avg New $</th>
                  <th className="pb-2 text-right font-semibold text-slate-500 hidden sm:table-cell">Avg Used $</th>
                  <th className="pb-2 text-right font-semibold text-slate-500">New %</th>
                </tr>
              </thead>
              <tbody>
                {branded_location_split.map((loc) => (
                  <tr key={loc.dealer_id} className="border-b border-slate-800/40 hover:bg-slate-800/20 transition-colors">
                    <td className="py-2 font-medium text-slate-200">{loc.name}</td>
                    <td className="py-2 text-right font-bold text-emerald-400">{loc.new}</td>
                    <td className="py-2 text-right font-bold text-brand-400">{loc.used}</td>
                    <td className="py-2 text-right text-slate-300">{loc.total}</td>
                    <td className="py-2 text-right text-slate-400 hidden sm:table-cell">
                      {loc.avg_new_price ? `$${loc.avg_new_price.toLocaleString()}` : '—'}
                    </td>
                    <td className="py-2 text-right text-slate-400 hidden sm:table-cell">
                      {loc.avg_used_price ? `$${loc.avg_used_price.toLocaleString()}` : '—'}
                    </td>
                    <td className="py-2 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="hidden sm:block w-14 h-1.5 rounded-full bg-slate-800 overflow-hidden">
                          <div className="h-full rounded-full bg-emerald-500" style={{ width: `${loc.new_pct}%` }} />
                        </div>
                        <span className="text-emerald-400 font-semibold">{loc.new_pct}%</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Cars to Move */}
      <div className="rounded-2xl border border-slate-800/80 bg-slate-900/40 p-5">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
          <div>
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400" />
              <h2 className="text-sm font-bold text-white">Cars to Move</h2>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">active units aging past their make's avg · needs attention</p>
          </div>
          <div className="flex items-center gap-1.5">
            {(['all', 'critical', 'high', 'medium'] as const).map(f => (
              <button
                key={f}
                onClick={() => setUrgencyFilter(f)}
                className={`rounded-lg border px-2.5 py-1 text-xs font-semibold capitalize transition-colors ${
                  urgencyFilter === f
                    ? 'border-brand-500/50 bg-brand-500/20 text-brand-300'
                    : 'border-slate-700 bg-slate-800/60 text-slate-400 hover:text-slate-200'
                }`}
              >
                {f === 'all' ? `All (${cars_to_move.length})` : f}
              </button>
            ))}
          </div>
        </div>

        {filteredCarsToMove.length === 0 ? (
          <p className="text-sm text-slate-500 py-4 text-center">No vehicles in this urgency tier.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="pb-2 text-left font-semibold text-slate-500">Vehicle</th>
                  <th className="pb-2 text-left font-semibold text-slate-500 hidden sm:table-cell">Location</th>
                  <th className="pb-2 text-right font-semibold text-slate-500">Days on Lot</th>
                  <th className="pb-2 text-right font-semibold text-slate-500 hidden sm:table-cell">Make Avg</th>
                  <th className="pb-2 text-right font-semibold text-slate-500">Price</th>
                  <th className="pb-2 text-center font-semibold text-slate-500">Urgency</th>
                  <th className="pb-2 w-8" />
                </tr>
              </thead>
              <tbody>
                {filteredCarsToMove.map((c) => (
                  <tr key={c.id} className="border-b border-slate-800/50 hover:bg-slate-800/30 transition-colors">
                    <td className="py-2.5">
                      <p className="font-semibold text-white">{c.year} {c.make} {c.model}</p>
                      <p className="text-slate-500">{c.stock_number} · {c.exterior_color}</p>
                    </td>
                    <td className="py-2.5 text-slate-400 hidden sm:table-cell">
                      {c.location_name || '—'}
                      {c.dealer_id === MOG_DEALER_ID && (
                        <span className="ml-1.5 text-[10px] font-bold text-brand-400 bg-brand-500/20 rounded px-1 py-0.5">MOG</span>
                      )}
                    </td>
                    <td className="py-2.5 text-right">
                      <span className={`font-bold text-sm ${c.urgency === 'critical' ? 'text-red-400' : c.urgency === 'high' ? 'text-orange-400' : 'text-amber-400'}`}>
                        {c.days_on_lot}d
                      </span>
                    </td>
                    <td className="py-2.5 text-right text-slate-500 hidden sm:table-cell">{c.category_avg}d avg</td>
                    <td className="py-2.5 text-right text-slate-300">
                      {c.price ? fmtFull$(c.price) : '—'}
                    </td>
                    <td className="py-2.5 text-center">
                      <UrgencyBadge urgency={c.urgency} />
                    </td>
                    <td className="py-2.5 text-right">
                      {c.listing_url && (
                        <a href={c.listing_url} target="_blank" rel="noreferrer"
                          className="inline-flex items-center justify-center rounded-lg p-1.5 text-slate-500 hover:text-brand-400 hover:bg-slate-700/50 transition-colors">
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

    </div>
  )
}
