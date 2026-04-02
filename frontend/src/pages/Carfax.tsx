import { FormEvent, useState } from 'react'
import axios from 'axios'
import { formatDistanceToNow } from 'date-fns'
import {
  Search, FileText, ExternalLink, Copy, RefreshCw,
} from 'lucide-react'
import toast from 'react-hot-toast'

import { lookupCarfax } from '../api'
import { useDealer } from '../context/DealerContext'
import type { CarfaxLookupResult, Vehicle } from '../types'


const vehicleLabel = (v: Vehicle) =>
  [v.year, v.make, v.model, v.trim].filter(Boolean).join(' ')


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
        toast.success(data.cached ? 'Loaded from cache' : 'CARFAX found')
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
      toast.success('Copied')
    } catch {
      toast.error('Could not copy')
    }
  }

  const resolvedVehicle = result?.status === 'resolved' ? result.vehicle : null
  const cachedAt = resolvedVehicle?.carfax_fetched_at
    ? formatDistanceToNow(new Date(`${resolvedVehicle.carfax_fetched_at}Z`), { addSuffix: true })
    : null

  return (
    <div className="flex h-full flex-col">
      {/* Search bar */}
      <div className="border-b border-slate-800 px-4 py-5 sm:px-6">
        <form onSubmit={handleSubmit} className="mx-auto max-w-2xl">
          <h1 className="text-lg font-semibold text-white">CARFAX Lookup</h1>
          <p className="mt-1 text-sm text-slate-400">
            Enter a stock number or VIN to pull the CARFAX report.
          </p>
          <div className="mt-4 flex gap-3">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="input w-full pl-10"
                placeholder="e.g. S5100275"
                autoFocus
              />
            </div>
            <button type="submit" disabled={loading} className="btn-primary h-[42px] px-5">
              {loading && loadingVehicleId === null
                ? <RefreshCw className="h-4 w-4 animate-spin" />
                : <Search className="h-4 w-4" />}
              {loading && loadingVehicleId === null ? 'Searching...' : 'Pull CARFAX'}
            </button>
          </div>
        </form>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6">
        {/* Resolved result */}
        {result?.status === 'resolved' && resolvedVehicle && result.carfax_url && (
          <div className="mx-auto max-w-2xl">
            <section className="card overflow-hidden">
              <div className="border-b border-slate-800 bg-emerald-500/10 px-5 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="text-lg font-semibold text-white">{vehicleLabel(resolvedVehicle)}</h3>
                    <p className="mt-0.5 text-sm text-slate-300">
                      Stock #{resolvedVehicle.stock_number}
                      {resolvedVehicle.location_name ? ` · ${resolvedVehicle.location_name}` : ''}
                      {result.cached && cachedAt ? ` · cached ${cachedAt}` : ''}
                    </p>
                  </div>
                </div>
              </div>

              <div className="space-y-4 px-5 py-5">
                {/* Action buttons */}
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
                      Listing
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
                    Refresh
                  </button>
                </div>

                {/* Vehicle details */}
                <div className="grid gap-3 sm:grid-cols-4">
                  <Detail label="VIN" value={resolvedVehicle.vin || '—'} mono />
                  <Detail label="Price" value={resolvedVehicle.price ? `$${resolvedVehicle.price.toLocaleString()}` : '—'} />
                  <Detail label="Mileage" value={resolvedVehicle.mileage ? `${resolvedVehicle.mileage.toLocaleString()} mi` : '—'} />
                  <Detail label="Condition" value={resolvedVehicle.condition || '—'} />
                </div>
              </div>
            </section>
          </div>
        )}

        {/* Ambiguous matches — rare but handle gracefully */}
        {result?.status === 'ambiguous' && result.matches && (
          <div className="mx-auto max-w-2xl">
            <p className="mb-4 text-sm text-slate-400">
              Multiple vehicles matched — pick one:
            </p>
            <div className="space-y-3">
              {result.matches.map((vehicle) => (
                <div key={vehicle.id} className="card flex items-center justify-between gap-4 px-5 py-4">
                  <div className="min-w-0">
                    <p className="font-medium text-white">{vehicleLabel(vehicle)}</p>
                    <p className="mt-0.5 text-sm text-slate-400">
                      Stock #{vehicle.stock_number}
                      {vehicle.location_name ? ` · ${vehicle.location_name}` : ''}
                    </p>
                  </div>
                  <button
                    onClick={() => runLookup({ vehicle_id: vehicle.id })}
                    disabled={loading}
                    className="btn-primary shrink-0"
                  >
                    {loading && loadingVehicleId === vehicle.id
                      ? <RefreshCw className="h-4 w-4 animate-spin" />
                      : <FileText className="h-4 w-4" />}
                    CARFAX
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty state */}
        {!result && !loading && (
          <div className="mx-auto max-w-2xl pt-12 text-center">
            <Search className="mx-auto h-10 w-10 text-slate-700" />
            <p className="mt-3 text-sm text-slate-500">
              Results will appear here after you search.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}


function Detail({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-500">{label}</p>
      <p className={`mt-1 text-sm text-slate-200 ${mono ? 'font-mono break-all text-xs' : ''}`}>{value}</p>
    </div>
  )
}
