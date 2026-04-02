import { FormEvent, useState } from 'react'
import axios from 'axios'
import { formatDistanceToNow } from 'date-fns'
import {
  Search, FileText, ExternalLink, Copy, RefreshCw, MapPin, Car,
} from 'lucide-react'
import toast from 'react-hot-toast'

import { lookupCarfax } from '../api'
import { useDealer } from '../context/DealerContext'
import { LocationChip } from '../components/LocationChip'
import type { CarfaxLookupResult, Vehicle } from '../types'


const vehicleLabel = (vehicle: Vehicle) =>
  [vehicle.year, vehicle.make, vehicle.model, vehicle.trim].filter(Boolean).join(' ')


export default function Carfax() {
  const { selectedDealer } = useDealer()
  const [query, setQuery] = useState('')
  const [result, setResult] = useState<CarfaxLookupResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadingVehicleId, setLoadingVehicleId] = useState<number | null>(null)

  const runLookup = async (params: {
    query?: string
    vehicle_id?: number
    refresh?: boolean
  }) => {
    setLoading(true)
    setLoadingVehicleId(params.vehicle_id ?? null)
    try {
      const data = await lookupCarfax({
        ...params,
        dealer_id: selectedDealer?.id,
      })
      setResult(data)
      if (data.status === 'resolved') {
        toast.success(data.cached ? 'CARFAX ready from cache' : 'Fresh CARFAX link loaded')
      }
    } catch (error) {
      const detail = axios.isAxiosError(error)
        ? error.response?.data?.detail ?? 'Could not pull a CARFAX right now'
        : 'Could not pull a CARFAX right now'
      toast.error(detail)
    } finally {
      setLoading(false)
      setLoadingVehicleId(null)
    }
  }

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmed = query.trim()
    if (!trimmed) {
      toast.error('Enter a stock number or VIN')
      return
    }
    await runLookup({ query: trimmed })
  }

  const handleCopy = async (url: string) => {
    try {
      await navigator.clipboard.writeText(url)
      toast.success('CARFAX link copied')
    } catch {
      toast.error('Could not copy the link')
    }
  }

  const resolvedVehicle = result?.status === 'resolved' ? result.vehicle : null
  const cachedAt = resolvedVehicle?.carfax_fetched_at
    ? formatDistanceToNow(new Date(`${resolvedVehicle.carfax_fetched_at}Z`), { addSuffix: true })
    : null

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-slate-800 px-4 py-4 sm:px-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-cyan-500/10 text-cyan-300 ring-1 ring-cyan-400/20">
                <FileText className="h-4 w-4" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white">CARFAX Lookup</h1>
                <p className="mt-0.5 text-xs text-slate-400">
                  Paste a stock number or VIN and open the report without digging through the listing.
                </p>
              </div>
            </div>
            <LocationChip className="mt-3" />
          </div>

          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-3 text-xs text-slate-400">
            <div className="flex items-center gap-2 text-slate-200">
              <MapPin className="h-3.5 w-3.5 text-brand-400" />
              {selectedDealer ? selectedDealer.name : 'All locations'}
            </div>
            <p className="mt-1 max-w-xs">
              {selectedDealer
                ? 'This store is being used to break ties when the same stock exists at multiple ALM locations.'
                : 'Pick a store in the sidebar if you want duplicate stock numbers narrowed automatically.'}
            </p>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 sm:p-6">
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_minmax(22rem,0.9fr)]">
          <section className="card overflow-hidden">
            <div className="border-b border-slate-800 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.16),transparent_48%),linear-gradient(135deg,rgba(15,23,42,0.96),rgba(2,6,23,0.94))] px-5 py-5">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-500/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-cyan-200/90">
                Fast Path
              </div>
              <h2 className="mt-3 text-2xl font-semibold text-white">Stock number in, CARFAX out</h2>
              <p className="mt-2 max-w-2xl text-sm text-slate-300">
                The app checks the matching ALM inventory record, opens the public listing behind the scenes,
                and pulls the embedded CARFAX link for you.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5 px-5 py-5">
              <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_auto]">
                <label className="block">
                  <span className="mb-2 block text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">
                    Stock Number Or VIN
                  </span>
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
                    <input
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                      className="input pl-10"
                      placeholder="S5100275 or 1HGCM82633A123456"
                    />
                  </div>
                </label>

                <button type="submit" disabled={loading} className="btn-primary h-[42px] self-end px-5">
                  {loading && loadingVehicleId === null ? <RefreshCw className="h-4 w-4 animate-spin" /> : <FileText className="h-4 w-4" />}
                  {loading && loadingVehicleId === null ? 'Finding...' : 'Find CARFAX'}
                </button>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  'Uses your selected store to narrow duplicate stock numbers',
                  'Caches resolved reports so repeat lookups come back instantly',
                  'Still works with VINs when the stock number is not handy',
                ].map((item) => (
                  <div key={item} className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-4 text-sm text-slate-300">
                    {item}
                  </div>
                ))}
              </div>
            </form>
          </section>

          <section className="card p-5">
            <div className="flex items-center gap-2">
              <Car className="h-4 w-4 text-cyan-300" />
              <h2 className="text-lg font-semibold text-white">What You’ll Get</h2>
            </div>
            <div className="mt-4 space-y-3 text-sm text-slate-300">
              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-4">
                One input field for the stock number you already have.
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-4">
                One click to open the CARFAX, plus copy and listing buttons if you need to share it.
              </div>
              <div className="rounded-2xl border border-slate-800 bg-slate-900/70 px-4 py-4">
                A fallback picker when the same stock exists at more than one ALM store.
              </div>
            </div>
          </section>
        </div>

        {result?.status === 'resolved' && resolvedVehicle && result.carfax_url && (
          <section className="card mt-6 overflow-hidden">
            <div className="border-b border-slate-800 bg-emerald-500/10 px-5 py-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-emerald-300/80">CARFAX Ready</p>
                  <h3 className="mt-1 text-xl font-semibold text-white">{vehicleLabel(resolvedVehicle)}</h3>
                  <p className="mt-1 text-sm text-slate-300">
                    Stock #{resolvedVehicle.stock_number}
                    {resolvedVehicle.location_name ? ` · ${resolvedVehicle.location_name}` : ''}
                    {result.cached && cachedAt ? ` · cached ${cachedAt}` : ''}
                    {!result.cached ? ' · pulled live from ALM just now' : ''}
                  </p>
                </div>
                <div className="inline-flex items-center rounded-full border border-emerald-400/20 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-200">
                  {result.cached ? 'Instant cache hit' : 'Fresh live lookup'}
                </div>
              </div>
            </div>

            <div className="grid gap-6 px-5 py-5 lg:grid-cols-[minmax(0,1.1fr)_minmax(18rem,0.9fr)]">
              <div className="space-y-4">
                <div className="flex flex-wrap gap-3">
                  <a href={result.carfax_url} target="_blank" rel="noreferrer" className="btn-primary">
                    <ExternalLink className="h-4 w-4" />
                    Open CARFAX
                  </a>

                  <button onClick={() => handleCopy(result.carfax_url!)} className="btn-secondary">
                    <Copy className="h-4 w-4" />
                    Copy Link
                  </button>

                  {result.listing_url && (
                    <a href={result.listing_url} target="_blank" rel="noreferrer" className="btn-secondary">
                      <FileText className="h-4 w-4" />
                      Open Listing
                    </a>
                  )}

                  <button
                    onClick={() => runLookup({ vehicle_id: resolvedVehicle.id, refresh: true })}
                    disabled={loading}
                    className="btn-secondary"
                  >
                    {loading && loadingVehicleId === resolvedVehicle.id
                      ? <RefreshCw className="h-4 w-4 animate-spin" />
                      : <RefreshCw className="h-4 w-4" />}
                    Refresh Live
                  </button>
                </div>

                <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">CARFAX URL</p>
                  <p className="mt-2 break-all font-mono text-xs text-cyan-200">{result.carfax_url}</p>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
                <DetailCard label="VIN" value={resolvedVehicle.vin || '—'} mono />
                <DetailCard label="Price" value={resolvedVehicle.price ? `$${resolvedVehicle.price.toLocaleString()}` : '—'} />
                <DetailCard label="Mileage" value={resolvedVehicle.mileage ? `${resolvedVehicle.mileage.toLocaleString()} mi` : '—'} />
                <DetailCard label="Condition" value={resolvedVehicle.condition || '—'} />
              </div>
            </div>
          </section>
        )}

        {result?.status === 'ambiguous' && result.matches && (
          <section className="card mt-6 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-amber-300/80">Needs A Store Pick</p>
                <h3 className="mt-1 text-xl font-semibold text-white">
                  {result.matches.length} active vehicles share “{result.query}”
                </h3>
                <p className="mt-1 text-sm text-slate-400">
                  Choose the right ALM location and I’ll pull the matching CARFAX.
                </p>
              </div>
            </div>

            <div className="mt-5 grid gap-4 lg:grid-cols-2">
              {result.matches.map((vehicle) => (
                <div key={vehicle.id} className="rounded-3xl border border-slate-800 bg-slate-900/70 p-5">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-500">
                    {vehicle.location_name || 'Unknown Location'}
                  </p>
                  <h4 className="mt-2 text-lg font-semibold text-white">{vehicleLabel(vehicle)}</h4>
                  <p className="mt-1 text-sm text-slate-400">
                    Stock #{vehicle.stock_number} · {vehicle.vin || 'VIN unavailable'}
                  </p>

                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <DetailCard label="Price" value={vehicle.price ? `$${vehicle.price.toLocaleString()}` : '—'} />
                    <DetailCard label="Mileage" value={vehicle.mileage ? `${vehicle.mileage.toLocaleString()} mi` : '—'} />
                  </div>

                  <div className="mt-4 flex flex-wrap gap-3">
                    <button
                      onClick={() => runLookup({ vehicle_id: vehicle.id })}
                      disabled={loading}
                      className="btn-primary"
                    >
                      {loading && loadingVehicleId === vehicle.id
                        ? <RefreshCw className="h-4 w-4 animate-spin" />
                        : <FileText className="h-4 w-4" />}
                      Get CARFAX
                    </button>

                    {vehicle.listing_url && (
                      <a href={vehicle.listing_url} target="_blank" rel="noreferrer" className="btn-secondary">
                        <ExternalLink className="h-4 w-4" />
                        Open Listing
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}


function DetailCard({
  label,
  value,
  mono = false,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">{label}</p>
      <p className={`mt-2 text-sm text-slate-200 ${mono ? 'font-mono break-all text-xs' : ''}`}>{value}</p>
    </div>
  )
}
