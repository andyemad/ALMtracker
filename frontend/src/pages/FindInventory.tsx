import { useEffect, useRef, useState } from 'react'
import {
  ArrowRight, Car, CheckCircle2, Copy, ExternalLink, MapPin, PhoneCall, Search, ShieldCheck, Sparkles,
} from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { createLead, getFilterOptions, getLeadMatches } from '../api'
import type { FilterOptions, Vehicle } from '../types'

// ─── Formatters ──────────────────────────────────────────────────────────────

const fmt$ = (n: number | null) => (n != null ? `$${n.toLocaleString()}` : 'Call for price')
const fmtMi = (n: number | null) => (n != null ? `${n.toLocaleString()} mi` : '—')

const CONSENT_DISCLOSURE =
  'By submitting, you agree ALM may contact you using the options selected about matching inventory and appointment availability. Consent is not required to buy. Message and data rates may apply.'

// Budget quick-select presets
const BUDGET_PRESETS = [
  { label: 'Under $15k', value: '15000' },
  { label: '$15k–25k',   value: '25000' },
  { label: '$25k–40k',   value: '40000' },
  { label: '$40k–60k',   value: '60000' },
  { label: '$60k+',      value: '' },
]

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function FindInventory() {
  const [searchParams] = useSearchParams()
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [matches, setMatches] = useState<Vehicle[]>([])
  const [submitted, setSubmitted] = useState(false)
  const [copied, setCopied] = useState(false)
  const matchesPanelRef = useRef<HTMLDivElement>(null)

  const source   = searchParams.get('source')   ?? searchParams.get('utm_source')   ?? 'find-your-car'
  const campaign = searchParams.get('campaign') ?? searchParams.get('utm_campaign') ?? ''

  const [form, setForm] = useState({
    interested_make:      searchParams.get('make')       ?? '',
    interested_model:     searchParams.get('model')      ?? '',
    max_budget:           searchParams.get('max_budget') ?? '',
    interested_condition: searchParams.get('condition')  ?? '', // '' | 'new' | 'pre-owned'
    customer_name:  '',
    customer_phone: '',
    customer_email: '',
    smsConsent:  true,
    callConsent: false,
  })

  useEffect(() => { getFilterOptions().then(setFilterOptions) }, [])

  const setField = (key: keyof typeof form) =>
    (value: string | boolean) => setForm(prev => ({ ...prev, [key]: value as never }))

  // Matches come back already filtered server-side; alias for clarity
  const filteredMatches = matches

  const handleBudgetPreset = (value: string) => {
    setField('max_budget')(value)
  }

  const handleCopyUrl = () => {
    navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2200)
    })
  }

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()

    if (!form.customer_name.trim()) {
      toast.error('Your name is required')
      return
    }
    if (!form.customer_phone.trim() && !form.customer_email.trim()) {
      toast.error('Add a phone number or email so ALM can reach you')
      return
    }
    if (!form.smsConsent && !form.callConsent) {
      toast.error('Choose at least one contact method')
      return
    }

    setSubmitting(true)

    const noteLines = [
      `Public lead submitted ${new Date().toISOString()}`,
      `Campaign: ${[source, campaign].filter(Boolean).join(' / ') || 'Direct'}`,
      form.interested_condition ? `Condition preference: ${form.interested_condition}` : null,
    ].filter(Boolean)

    try {
      const lead = await createLead({
        customer_name:  form.customer_name.trim(),
        customer_phone: form.customer_phone.trim() || null,
        customer_email: form.customer_email.trim() || null,
        interested_make:  form.interested_make  || null,
        interested_model: form.interested_model || null,
        max_budget: form.max_budget ? +form.max_budget : null,
        source:   source   || 'find-your-car',
        campaign: campaign || null,
        sms_consent:  form.smsConsent,
        call_consent: form.callConsent,
        consent_text: CONSENT_DISCLOSURE,
        notes: noteLines.join('\n'),
      })

      const results = await getLeadMatches(lead.id, form.interested_condition || undefined)
      setMatches(results)
      setSubmitted(true)
      toast.success(`Found ${results.length} match${results.length === 1 ? '' : 'es'} — your request is saved`)

      // Scroll to matches panel on mobile (below the form)
      setTimeout(() => {
        matchesPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 150)
    } catch {
      toast.error('Could not submit — please try again')
    } finally {
      setSubmitting(false)
    }
  }

  const campaignLabel = [source, campaign].filter(Boolean).join(' / ') || 'Direct'

  return (
    <div className="min-h-dvh bg-slate-950 text-slate-100">
      <div className="mx-auto flex min-h-dvh max-w-7xl flex-col px-4 py-6 sm:px-6 lg:px-8">

        {/* Header */}
        <header className="flex flex-wrap items-center justify-between gap-3">
          <Link to="/" className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 via-cyan-400 to-emerald-400 p-[1px] shadow-[0_0_35px_rgba(79,70,229,0.35)]">
              <div className="flex h-full w-full items-center justify-center rounded-2xl bg-slate-950">
                <Car className="h-5 w-5 text-white" />
              </div>
            </div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-300/70">ALM Cars</div>
              <div className="text-sm font-semibold text-white">Find Your Next Car</div>
            </div>
          </Link>

          <a
            href="tel:+14046260000"
            className="hidden items-center gap-2 rounded-full border border-slate-700 bg-slate-800/60 px-4 py-2 text-sm text-slate-200 transition-colors hover:border-brand-500/40 hover:bg-slate-800 sm:flex"
          >
            <PhoneCall className="h-3.5 w-3.5 text-cyan-300" />
            Call ALM directly
          </a>
        </header>

        <main className="grid flex-1 gap-6 py-8 lg:grid-cols-[1.15fr,0.85fr]">

          {/* ── Left column: hero + form ── */}
          <section className="space-y-6">
            {/* Hero */}
            <div className="space-y-4">
              <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1.5 text-xs font-medium text-emerald-200">
                <Sparkles className="h-3.5 w-3.5" />
                6,900+ vehicles across 24 ALM locations
              </div>

              <div className="space-y-3">
                <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-white sm:text-5xl">
                  Tell ALM what you want.<br className="hidden sm:block" /> Get matched fast.
                </h1>
                <p className="max-w-xl text-base text-slate-300 sm:text-lg">
                  Real inventory. Real prices. ALM checks every lot and follows up with options that actually fit your budget.
                </p>
              </div>
            </div>

            {/* Value props */}
            <div className="grid gap-3 sm:grid-cols-3">
              <ValueCard icon={Search}    title="Real Matches"  body="Checked against live inventory across all 24 ALM locations — not a dead lead form." />
              <ValueCard icon={MapPin}    title="24 Stores"     body="Source from multiple lots. One request covers every location in the Atlanta metro." />
              <ValueCard icon={PhoneCall} title="Fast Follow-Up" body="Your dedicated sales contact reaches out within minutes — not days." />
            </div>

            {/* Form card */}
            <div className="card overflow-hidden">
              <form onSubmit={handleSubmit} className="grid gap-4 p-5 sm:grid-cols-2 sm:p-6">

                {/* Make */}
                <div>
                  <label className="mb-1.5 block text-xs text-slate-400">Make</label>
                  <select
                    className="select"
                    value={form.interested_make}
                    onChange={e => setField('interested_make')(e.target.value)}
                  >
                    <option value="">Any make</option>
                    {filterOptions?.makes.map(make => <option key={make}>{make}</option>)}
                  </select>
                </div>

                {/* Model */}
                <div>
                  <label className="mb-1.5 block text-xs text-slate-400">Model</label>
                  <input
                    className="input"
                    placeholder="Elantra, Rogue, F-150…"
                    value={form.interested_model}
                    onChange={e => setField('interested_model')(e.target.value)}
                  />
                </div>

                {/* Budget */}
                <div className="sm:col-span-2">
                  <label className="mb-1.5 block text-xs text-slate-400">Max Budget</label>
                  <div className="flex flex-wrap gap-2">
                    {BUDGET_PRESETS.map(p => {
                      // Only highlight if value is non-empty (prevents $60k+ glowing on initial load)
                      const active = p.value !== '' && form.max_budget === p.value
                      return (
                        <button
                          key={p.label}
                          type="button"
                          onClick={() => handleBudgetPreset(active ? '' : p.value)}
                          className={`rounded-xl border px-3 py-1.5 text-xs font-medium transition-all ${
                            active
                              ? 'border-brand-500/50 bg-brand-600/25 text-white shadow-[0_0_14px_rgba(79,70,229,0.25)]'
                              : 'border-slate-700 bg-slate-900/80 text-slate-300 hover:border-slate-600 hover:text-white'
                          }`}
                        >
                          {p.label}
                        </button>
                      )
                    })}
                    <input
                      className="input h-8 w-28 flex-shrink-0 py-0"
                      type="number"
                      inputMode="numeric"
                      placeholder="Custom…"
                      value={form.max_budget}
                      onChange={e => setField('max_budget')(e.target.value)}
                    />
                  </div>
                </div>

                {/* Condition */}
                <div className="sm:col-span-2">
                  <label className="mb-1.5 block text-xs text-slate-400">Condition</label>
                  <div className="flex gap-2">
                    {(['', 'new', 'pre-owned'] as const).map(cond => {
                      const labels: Record<string, string> = { '': 'Either', 'new': 'New', 'pre-owned': 'Pre-Owned' }
                      const active = form.interested_condition === cond
                      return (
                        <button
                          key={cond || 'either'}
                          type="button"
                          onClick={() => setField('interested_condition')(cond)}
                          className={`flex-1 rounded-xl border py-2 text-xs font-medium transition-all ${
                            active
                              ? 'border-brand-500/50 bg-brand-600/25 text-white'
                              : 'border-slate-700 bg-slate-900/80 text-slate-400 hover:border-slate-600 hover:text-slate-200'
                          }`}
                        >
                          {labels[cond]}
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* Name */}
                <div>
                  <label className="mb-1.5 block text-xs text-slate-400">Your Name <span className="text-red-400">*</span></label>
                  <input
                    className="input"
                    placeholder="First and last name"
                    value={form.customer_name}
                    onChange={e => setField('customer_name')(e.target.value)}
                  />
                </div>

                {/* Phone */}
                <div>
                  <label className="mb-1.5 block text-xs text-slate-400">Mobile Number</label>
                  <input
                    className="input"
                    type="tel"
                    placeholder="(404) 555-0100"
                    value={form.customer_phone}
                    onChange={e => setField('customer_phone')(e.target.value)}
                  />
                </div>

                {/* Email */}
                <div className="sm:col-span-2">
                  <label className="mb-1.5 block text-xs text-slate-400">Email (optional)</label>
                  <input
                    className="input"
                    type="email"
                    placeholder="you@example.com"
                    value={form.customer_email}
                    onChange={e => setField('customer_email')(e.target.value)}
                  />
                </div>

                {/* Consent */}
                <div className="sm:col-span-2 space-y-3 rounded-2xl border border-slate-700/60 bg-slate-950/60 p-4">
                  <label className="flex cursor-pointer items-start gap-3 text-sm text-slate-200">
                    <input
                      type="checkbox"
                      checked={form.smsConsent}
                      onChange={e => setField('smsConsent')(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-900 accent-brand-500"
                    />
                    <span>Text me matching inventory and pricing updates</span>
                  </label>
                  <label className="flex cursor-pointer items-start gap-3 text-sm text-slate-200">
                    <input
                      type="checkbox"
                      checked={form.callConsent}
                      onChange={e => setField('callConsent')(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-900 accent-brand-500"
                    />
                    <span>Call me about available vehicles and appointments</span>
                  </label>
                  <div className="flex items-start gap-2 text-xs text-slate-500">
                    <ShieldCheck className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400/70" />
                    <span>{CONSENT_DISCLOSURE}</span>
                  </div>
                </div>

                {/* Submit row */}
                <div className="sm:col-span-2 flex flex-wrap items-center justify-between gap-3">
                  <p className="text-[11px] text-slate-600">
                    Tracked as <span className="text-slate-500">{campaignLabel}</span>
                  </p>
                  <button
                    type="submit"
                    disabled={submitting}
                    className="btn-primary disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {submitting ? (
                      <>
                        <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                        Searching inventory…
                      </>
                    ) : (
                      <>Find Matching Cars <ArrowRight className="h-4 w-4" /></>
                    )}
                  </button>
                </div>
              </form>
            </div>
          </section>

          {/* ── Right column: matches ── */}
          <section className="space-y-4" ref={matchesPanelRef}>

            {/* Panel header */}
            <div className="card p-5">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-white">Matching Inventory</h2>
                  <p className="mt-0.5 text-sm text-slate-400">
                    {submitted
                      ? `${filteredMatches.length} vehicle${filteredMatches.length === 1 ? '' : 's'} match your request`
                      : 'Submit the form to see live ALM matches.'}
                  </p>
                </div>
                {submitted && (
                  <div className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-300">
                    Lead saved ✓
                  </div>
                )}
              </div>
            </div>

            {/* Loading skeletons */}
            {submitting && (
              <div className="space-y-3">
                {[1, 2, 3].map(i => <SkeletonCard key={i} />)}
              </div>
            )}

            {/* Pre-submission: share panel */}
            {!submitted && !submitting && (
              <div className="card flex min-h-[26rem] flex-col items-center justify-center gap-5 p-8 text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-600/20 ring-1 ring-brand-500/30">
                  <CheckCircle2 className="h-7 w-7 text-brand-400" />
                </div>
                <div className="space-y-2">
                  <h3 className="text-lg font-semibold text-white">Share this page anywhere</h3>
                  <p className="max-w-xs text-sm text-slate-400">
                    Drop the link in your TikTok bio, Facebook ads, or DMs. Every submission goes straight into your lead pipeline.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleCopyUrl}
                  className="btn-secondary gap-2 px-4 py-2"
                >
                  {copied ? (
                    <><CheckCircle2 className="h-4 w-4 text-emerald-400" /> Copied!</>
                  ) : (
                    <><Copy className="h-4 w-4" /> Copy link</>
                  )}
                </button>
                <div className="w-full rounded-xl border border-slate-700/60 bg-slate-900/60 px-3 py-2 text-center text-xs text-slate-500 break-all font-mono">
                  {window.location.href}
                </div>
              </div>
            )}

            {/* No matches after submission */}
            {submitted && !submitting && filteredMatches.length === 0 && (
              <div className="card p-8 text-center space-y-3">
                <div className="text-3xl">🔍</div>
                <h3 className="text-lg font-semibold text-white">No exact matches right now</h3>
                <p className="text-sm text-slate-400">
                  Your request is saved. When matching inventory arrives across any ALM location, you'll be the first to know.
                </p>
                <a href="tel:+14046260000" className="btn-primary mx-auto mt-2 w-fit">
                  <PhoneCall className="h-4 w-4" /> Call ALM now
                </a>
              </div>
            )}

            {/* Match cards */}
            {submitted && !submitting && filteredMatches.length > 0 && (
              <div className="space-y-3">
                {filteredMatches.map((vehicle, i) => (
                  <VehicleCard key={vehicle.id} vehicle={vehicle} index={i} />
                ))}
              </div>
            )}
          </section>
        </main>
      </div>
    </div>
  )
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function ValueCard({
  icon: Icon,
  title,
  body,
}: {
  icon: typeof Search
  title: string
  body: string
}) {
  return (
    <div className="card p-4">
      <div className="mb-3 flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600/20 text-brand-400 ring-1 ring-brand-500/25">
        <Icon className="h-4 w-4" />
      </div>
      <h3 className="text-sm font-semibold text-white">{title}</h3>
      <p className="mt-1 text-xs text-slate-400">{body}</p>
    </div>
  )
}

function SkeletonCard() {
  return (
    <div className="card overflow-hidden animate-pulse">
      <div className="h-36 w-full bg-slate-800/70" />
      <div className="p-4 space-y-3">
        <div className="h-4 w-3/4 rounded-lg bg-slate-800" />
        <div className="h-3 w-1/2 rounded-lg bg-slate-800" />
        <div className="h-8 w-full rounded-xl bg-slate-800 mt-2" />
      </div>
    </div>
  )
}

function VehicleCard({ vehicle, index }: { vehicle: Vehicle; index: number }) {
  const isNew = (vehicle.condition ?? '').toLowerCase() === 'new'

  return (
    <div
      className="card overflow-hidden transition-all"
      style={{ animationDelay: `${index * 60}ms` }}
    >
      {/* Vehicle image */}
      {vehicle.image_url ? (
        <img
          src={vehicle.image_url}
          alt={`${vehicle.year} ${vehicle.make} ${vehicle.model}`}
          className="h-44 w-full object-cover bg-slate-800"
          loading="lazy"
        />
      ) : (
        <div className="flex h-28 w-full items-center justify-center bg-slate-800/60 text-xs text-slate-600">
          <Car className="h-8 w-8 opacity-30" />
        </div>
      )}

      <div className="p-4">
        {/* Title row */}
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-white">
              {[vehicle.year, vehicle.make, vehicle.model, vehicle.trim].filter(Boolean).join(' ')}
            </h3>
            <p className="mt-0.5 text-xs text-slate-400">{fmtMi(vehicle.mileage)}</p>
          </div>
          <div className="shrink-0 text-right">
            <div className="text-base font-bold text-white">{fmt$(vehicle.price)}</div>
            <span className={isNew ? 'badge-new-vehicle' : 'badge-used'}>
              {isNew ? 'New' : 'Pre-Owned'}
            </span>
          </div>
        </div>

        {/* Location + days on lot */}
        <div className="mt-3 flex items-center gap-1.5 text-xs text-slate-400">
          <MapPin className="h-3.5 w-3.5 shrink-0 text-cyan-300/70" />
          <span className="truncate">{vehicle.location_name ?? 'ALM location'}</span>
          <span className="ml-auto shrink-0 whitespace-nowrap tabular-nums">
            {vehicle.days_on_lot}d on lot
          </span>
        </div>

        {/* CTA */}
        {vehicle.listing_url ? (
          <a
            href={vehicle.listing_url}
            target="_blank"
            rel="noreferrer"
            className="btn-primary mt-4 w-full justify-center py-2.5"
          >
            See this {vehicle.make}
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
        ) : (
          <div className="mt-4 rounded-xl border border-slate-700/60 bg-slate-900/40 px-3 py-2.5 text-center text-xs text-slate-500">
            Stock #{vehicle.stock_number} · Ask ALM about this vehicle
          </div>
        )}
      </div>
    </div>
  )
}
