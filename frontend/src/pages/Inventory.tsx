import { useEffect, useState, useCallback, useMemo } from 'react'
import {
  useReactTable, getCoreRowModel, getSortedRowModel,
  flexRender, type ColumnDef, type SortingState
} from '@tanstack/react-table'
import {
  Search, Download, ChevronUp, ChevronDown, ChevronsUpDown,
  ExternalLink, ChevronLeft, ChevronRight, SlidersHorizontal, X
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { getVehicles, getFilterOptions } from '../api'
import type { Vehicle, FilterOptions } from '../types'
import { useDealer } from '../context/DealerContext'
import { useSearchParams } from 'react-router-dom'
import { useDebounce } from '../hooks/useDebounce'

const fmt$ = (n: number | null) => n != null ? `$${n.toLocaleString()}` : '—'
const fmtMi = (n: number | null) => n != null ? `${n.toLocaleString()} mi` : '—'
const isNewVehicle = (v: Vehicle) => Date.now() - new Date(v.first_seen + 'Z').getTime() < 86_400_000

function AgingBar({ days }: { days: number }) {
  const pct = Math.min(1, days / 90)
  const color = days >= 60 ? 'var(--danger)' : days >= 45 ? 'var(--warn)' : days >= 15 ? 'var(--accent)' : 'var(--positive)'
  return (
    <div className="flex items-center gap-2 w-full" style={{ minWidth: 100 }}>
      <div className="relative flex-1 overflow-hidden" style={{ height: 10 }}>
        <div className="absolute inset-y-0 left-0 w-full matrix" style={{ color: 'var(--hairline-2)' }} />
        <div className="absolute inset-y-0 left-0 matrix" style={{ width: `${pct * 100}%`, color }} />
      </div>
      <span className="mono tnum whitespace-nowrap" style={{ fontSize: 10, color }}>{days}d</span>
    </div>
  )
}

export default function Inventory() {
  const { selectedDealer } = useDealer()
  const dealerId = selectedDealer?.id
  const [searchParams] = useSearchParams()
  const seededDaysMin = searchParams.get('min_days_on_lot') ?? ''
  const seededDaysMax = searchParams.get('max_days_on_lot') ?? ''

  const [data, setData] = useState<Vehicle[]>([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [sorting, setSorting] = useState<SortingState>([])
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(null)
  const [showFilters, setShowFilters] = useState(Boolean(seededDaysMin || seededDaysMax))

  const [search, setSearch] = useState(() => {
    const model = searchParams.get('model')
    const makeParam = searchParams.get('make')
    return (model && !makeParam) ? model : (searchParams.get('search') ?? '')
  })
  const [make, setMake] = useState(searchParams.get('make') ?? '')
  const [minYear, setMinYear] = useState('')
  const [maxYear, setMaxYear] = useState('')
  const [minPrice, setMinPrice] = useState('')
  const [maxPrice, setMaxPrice] = useState('')
  const [maxMileage, setMaxMileage] = useState('')
  const [minDaysOnLot, setMinDaysOnLot] = useState(seededDaysMin)
  const [maxDaysOnLot, setMaxDaysOnLot] = useState(seededDaysMax)
  const [condition, setCondition] = useState('')
  const [showActive, setShowActive] = useState<boolean | null>(true)

  const debouncedSearch      = useDebounce(search, 300)
  const debouncedMinYear     = useDebounce(minYear, 300)
  const debouncedMaxYear     = useDebounce(maxYear, 300)
  const debouncedMinPrice    = useDebounce(minPrice, 300)
  const debouncedMaxPrice    = useDebounce(maxPrice, 300)
  const debouncedMaxMileage  = useDebounce(maxMileage, 300)
  const debouncedMinDaysOnLot = useDebounce(minDaysOnLot, 300)
  const debouncedMaxDaysOnLot = useDebounce(maxDaysOnLot, 300)

  useEffect(() => {
    getFilterOptions(dealerId).then(setFilterOptions)
    resetPage()
  }, [dealerId])

  const sortBy = sorting[0]?.id
  const sortOrder = sorting[0]?.desc ? 'desc' : 'asc'

  const load = useCallback(() => {
    setLoading(true)
    getVehicles({
      dealer_id: dealerId,
      search:      debouncedSearch || undefined,
      make: make || undefined,
      min_year:    debouncedMinYear ? +debouncedMinYear : undefined,
      max_year:    debouncedMaxYear ? +debouncedMaxYear : undefined,
      min_price:   debouncedMinPrice ? +debouncedMinPrice : undefined,
      max_price:   debouncedMaxPrice ? +debouncedMaxPrice : undefined,
      max_mileage: debouncedMaxMileage ? +debouncedMaxMileage : undefined,
      min_days_on_lot: debouncedMinDaysOnLot ? +debouncedMinDaysOnLot : undefined,
      max_days_on_lot: debouncedMaxDaysOnLot ? +debouncedMaxDaysOnLot : undefined,
      condition: condition || undefined,
      is_active: showActive ?? undefined,
      sort_by: sortBy,
      sort_order: sortOrder as 'asc' | 'desc',
      page,
      page_size: 50,
    })
      .then(r => {
        setData(r.data)
        setTotal(r.total)
        setPages(r.pages)
      })
      .finally(() => setLoading(false))
  }, [dealerId, debouncedSearch, make, debouncedMinYear, debouncedMaxYear,
    debouncedMinPrice, debouncedMaxPrice, debouncedMaxMileage,
    debouncedMinDaysOnLot, debouncedMaxDaysOnLot,
    condition, showActive, sortBy, sortOrder, page])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    setPage(1)
  }, [debouncedSearch, debouncedMinYear, debouncedMaxYear,
      debouncedMinPrice, debouncedMaxPrice, debouncedMaxMileage,
      debouncedMinDaysOnLot, debouncedMaxDaysOnLot])

  const resetPage = () => setPage(1)

  const columns = useMemo<ColumnDef<Vehicle>[]>(() => [
    {
      id: 'status',
      header: '',
      size: 40,
      cell: ({ row }) => isNewVehicle(row.original)
        ? <span className="badge-new">NEW</span>
        : <span className="block w-1.5 h-1.5 rounded-full" style={{ background: 'var(--positive)', opacity: 0.6 }} />,
    },
    {
      id: 'image',
      header: '',
      size: 60,
      cell: ({ row }) => row.original.image_url
        ? <img src={row.original.image_url} alt="" className="w-12 h-8 object-cover" style={{ borderRadius: 2 }} />
        : <div className="stripes w-12 h-8 flex items-center justify-center"
            style={{ borderRadius: 2 }}>
            <span style={{ fontSize: 9, color: 'var(--muted)' }}>—</span>
          </div>,
    },
    {
      accessorKey: 'stock_number',
      header: 'Stock',
      size: 100,
      cell: ({ getValue }) => (
        <span className="mono tnum" style={{ fontSize: 11, color: 'var(--muted)' }}>
          {getValue() as string}
        </span>
      ),
    },
    {
      accessorKey: 'year',
      header: 'Year',
      size: 70,
      cell: ({ getValue }) => (
        <span className="serif tnum" style={{ fontSize: 18, color: 'var(--ink)' }}>
          {getValue() as number}
        </span>
      ),
    },
    {
      id: 'make_model',
      accessorKey: 'make',
      header: 'Make / Model',
      size: 220,
      cell: ({ row }) => (
        <div>
          <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--ink)' }}>
            {row.original.make} {row.original.model}
          </div>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 2 }}>
            {row.original.trim || '—'}
          </div>
        </div>
      ),
    },
    {
      accessorKey: 'price',
      header: 'Price',
      size: 110,
      cell: ({ getValue }) => (
        <div className="serif tnum" style={{ fontSize: 17, color: 'var(--ink)', lineHeight: 1 }}>
          {fmt$(getValue() as number | null)}
        </div>
      ),
    },
    {
      accessorKey: 'mileage',
      header: 'Mileage',
      size: 100,
      cell: ({ getValue }) => (
        <span className="mono tnum" style={{ fontSize: 12, color: 'var(--ink-2)' }}>
          {fmtMi(getValue() as number | null)}
        </span>
      ),
    },
    {
      accessorKey: 'exterior_color',
      header: 'Color',
      size: 110,
      cell: ({ getValue }) => (
        <span style={{ fontSize: 12, color: 'var(--ink-2)' }}>{getValue() as string || '—'}</span>
      ),
    },
    {
      accessorKey: 'days_on_lot',
      header: 'On lot',
      size: 160,
      cell: ({ getValue }) => <AgingBar days={getValue() as number} />,
    },
    {
      id: 'actions',
      header: '',
      size: 40,
      cell: ({ row }) => row.original.listing_url ? (
        <a
          href={row.original.listing_url}
          target="_blank"
          rel="noreferrer"
          onClick={e => e.stopPropagation()}
          className="btn-ghost p-1.5"
        >
          <ExternalLink className="w-3.5 h-3.5" />
        </a>
      ) : null,
    },
  ], [])

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: (updater) => { setSorting(updater); resetPage() },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualSorting: true,
    manualPagination: true,
  })

  const activeFiltersCount = [search, make, minYear, maxYear, minPrice, maxPrice, maxMileage, minDaysOnLot, maxDaysOnLot, condition]
    .filter(Boolean).length

  const clearFilters = () => {
    setSearch(''); setMake(''); setMinYear(''); setMaxYear('')
    setMinPrice(''); setMaxPrice(''); setMaxMileage('')
    setMinDaysOnLot(''); setMaxDaysOnLot(''); setCondition('')
    resetPage()
  }

  const applyAgingPreset = (min: string, max = '') => {
    setMinDaysOnLot(min); setMaxDaysOnLot(max)
    setSorting(min ? [{ id: 'days_on_lot', desc: true }] : [])
    setShowFilters(true); resetPage()
  }

  // Summary stats for the strip
  const avgPrice = data.length
    ? Math.round(data.reduce((s, v) => s + (v.price ?? 0), 0) / data.length)
    : null
  const avgDays = data.length
    ? Math.round(data.reduce((s, v) => s + v.days_on_lot, 0) / data.length)
    : null
  const aged60 = data.filter(v => v.days_on_lot >= 60).length

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div
        className="px-6 lg:px-10 py-8"
        style={{ borderBottom: '1px solid var(--hairline)' }}
      >
        <div className="flex items-end justify-between flex-wrap gap-4">
          <div>
            <div className="eyebrow">
              Inventory · {selectedDealer ? selectedDealer.name : 'All lots'}
            </div>
            <h1 className="serif mt-2" style={{ fontSize: 44, lineHeight: 1, color: 'var(--ink)' }}>
              The lot.
            </h1>
            <p className="text-sm mt-2" style={{ color: 'var(--muted)' }}>
              Search, sort and triage every active unit.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <a href="/api/vehicles/export" download className="btn">
              <Download className="w-3.5 h-3.5" />
              Export CSV
            </a>
          </div>
        </div>
      </div>

      {/* Summary strip */}
      <div
        className="grid grid-cols-2 md:grid-cols-4"
        style={{ borderBottom: '1px solid var(--hairline)' }}
      >
        {[
          { k: 'Matches',  v: total.toLocaleString(), tint: undefined as string | undefined },
          { k: 'Avg list', v: avgPrice ? `$${(Math.round(avgPrice / 100) / 10).toFixed(1)}k` : '—', tint: undefined },
          { k: 'Avg days', v: avgDays != null ? `${avgDays}d` : '—', tint: undefined },
          { k: 'Aged 60+', v: `${aged60} units`, tint: 'var(--danger)' },
        ].map((s, i) => (
          <div key={s.k} style={{
            padding: '16px 20px',
            borderLeft: i > 0 ? '1px solid var(--hairline)' : 'none',
          }}>
            <div className="eyebrow">{s.k}</div>
            <div
              className="tnum mt-1.5"
              style={{
                fontFamily: 'var(--font-serif)',
                fontWeight: 400,
                fontSize: 28,
                lineHeight: 1,
                letterSpacing: '-0.01em',
                color: s.tint ?? 'var(--ink)',
              }}
            >
              {s.v}
            </div>
          </div>
        ))}
      </div>

      {/* Filters bar */}
      <div
        className="flex flex-wrap items-center gap-2 px-6 py-3"
        style={{ borderBottom: '1px solid var(--hairline)', background: 'var(--bg)' }}
      >
        {/* Active / Sold / All toggle */}
        <div className="flex overflow-hidden" style={{ border: '1px solid var(--hairline)', borderRadius: 4 }}>
          {([['Active', true], ['Sold', false], ['All', null]] as const).map(([lbl, val]) => (
            <button
              key={lbl}
              onClick={() => { setShowActive(val); resetPage() }}
              className="t"
              style={{
                padding: '5px 12px',
                fontSize: 11,
                background: showActive === val ? 'var(--accent)' : 'var(--card)',
                color: showActive === val ? 'var(--accent-ink)' : 'var(--ink-2)',
                border: 'none',
                cursor: 'pointer',
              }}
            >
              {lbl}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5" style={{ color: 'var(--muted)' }} />
          <input
            className="input pl-9"
            style={{ width: 260 }}
            placeholder="Search make, model, stock…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        {/* Make filter */}
        <select
          className="select"
          style={{ width: 140 }}
          value={make}
          onChange={e => { setMake(e.target.value); resetPage() }}
        >
          <option value="">All makes</option>
          {filterOptions?.makes.map(m => <option key={m}>{m}</option>)}
        </select>

        {/* Aging presets */}
        <div className="w-px self-stretch" style={{ background: 'var(--hairline)', margin: '0 2px' }} />
        {[
          { label: 'Fresh ≤7d', min: '', max: '7' },
          { label: '30+',       min: '30', max: '' },
          { label: '45+',       min: '45', max: '' },
          { label: '60+',       min: '60', max: '' },
        ].map(preset => {
          const active = minDaysOnLot === preset.min && maxDaysOnLot === preset.max
          return (
            <button
              key={preset.label}
              onClick={() => applyAgingPreset(preset.min, preset.max)}
              className="t"
              style={{
                padding: '5px 10px',
                fontSize: 11,
                borderRadius: 4,
                border: `1px solid ${active ? 'var(--accent)' : 'var(--hairline)'}`,
                background: active ? 'var(--accent)' : 'var(--card)',
                color: active ? 'var(--accent-ink)' : 'var(--ink-2)',
                cursor: 'pointer',
              }}
            >
              {preset.label}
            </button>
          )
        })}

        {/* More filters toggle */}
        <button
          onClick={() => setShowFilters(!showFilters)}
          className="btn-ghost ml-auto relative"
        >
          <SlidersHorizontal className="w-3.5 h-3.5" />
          Filters
          {activeFiltersCount > 0 && (
            <span
              className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full flex items-center justify-center"
              style={{ background: 'var(--accent)', color: 'var(--accent-ink)', fontSize: 9 }}
            >
              {activeFiltersCount}
            </span>
          )}
        </button>
      </div>

      {/* Expanded filters */}
      {showFilters && (
        <div
          className="grid grid-cols-2 gap-3 px-6 py-4 md:grid-cols-4 lg:grid-cols-9"
          style={{ borderBottom: '1px solid var(--hairline)', background: 'var(--bg-2)' }}
        >
          <select className="select" value={make} onChange={e => { setMake(e.target.value); resetPage() }}>
            <option value="">All Makes</option>
            {filterOptions?.makes.map(m => <option key={m}>{m}</option>)}
          </select>
          <input className="input" placeholder="Min Year" type="number" value={minYear}
            onChange={e => setMinYear(e.target.value)} />
          <input className="input" placeholder="Max Year" type="number" value={maxYear}
            onChange={e => setMaxYear(e.target.value)} />
          <input className="input" placeholder="Min Price $" type="number" value={minPrice}
            onChange={e => setMinPrice(e.target.value)} />
          <input className="input" placeholder="Max Price $" type="number" value={maxPrice}
            onChange={e => setMaxPrice(e.target.value)} />
          <input className="input" placeholder="Max Mileage" type="number" value={maxMileage}
            onChange={e => setMaxMileage(e.target.value)} />
          <input className="input" placeholder="Min Days" type="number" value={minDaysOnLot}
            onChange={e => setMinDaysOnLot(e.target.value)} />
          <input className="input" placeholder="Max Days" type="number" value={maxDaysOnLot}
            onChange={e => setMaxDaysOnLot(e.target.value)} />
          <div className="flex gap-2">
            <select className="select" value={condition} onChange={e => { setCondition(e.target.value); resetPage() }}>
              <option value="">Condition</option>
              <option value="new">New</option>
              <option value="used">Used</option>
            </select>
            {activeFiltersCount > 0 && (
              <button onClick={clearFilters} className="btn-ghost px-2">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      )}

      {/* Table */}
      <div className="flex-1 overflow-auto thin-scroll">
        <table className="w-full tnum" style={{ minWidth: 1100 }}>
          <thead style={{ position: 'sticky', top: 0, zIndex: 10, background: 'var(--bg)' }}>
            {table.getHeaderGroups().map(hg => (
              <tr key={hg.id}>
                {hg.headers.map(h => (
                  <th
                    key={h.id}
                    className="table-header"
                    style={{ width: h.getSize() }}
                    onClick={h.column.getToggleSortingHandler()}
                  >
                    <div className="flex items-center gap-1">
                      {flexRender(h.column.columnDef.header, h.getContext())}
                      {h.column.getCanSort() && (
                        h.column.getIsSorted() === 'asc'  ? <ChevronUp className="w-3 h-3" /> :
                        h.column.getIsSorted() === 'desc' ? <ChevronDown className="w-3 h-3" /> :
                        <ChevronsUpDown className="w-3 h-3 opacity-30" />
                      )}
                    </div>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {loading ? (
              [...Array(10)].map((_, i) => (
                <tr key={i}>
                  {columns.map((_, j) => (
                    <td key={j} className="table-cell">
                      <div className="h-4 rounded animate-pulse" style={{ background: 'var(--bg-2)' }} />
                    </td>
                  ))}
                </tr>
              ))
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} style={{ textAlign: 'center', padding: '64px 0', fontSize: 13, color: 'var(--muted)' }}>
                  No vehicles match your filters
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map(row => (
                <tr key={row.id} className="table-row">
                  {row.getVisibleCells().map(cell => (
                    <td key={cell.id} className="table-cell">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div
        className="px-6 py-3 flex items-center justify-between"
        style={{ borderTop: '1px solid var(--hairline)' }}
      >
        <span className="mono tnum" style={{ fontSize: 11, color: 'var(--muted)' }}>
          {total.toLocaleString()} total · page {page} of {pages}
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="btn-ghost p-1.5 disabled:opacity-30"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          {Array.from({ length: Math.min(5, pages) }, (_, i) => {
            const p = Math.max(1, Math.min(pages - 4, page - 2)) + i
            return (
              <button
                key={p}
                onClick={() => setPage(p)}
                className="t"
                style={{
                  width: 28, height: 28,
                  borderRadius: 4,
                  fontSize: 12,
                  background: p === page ? 'var(--accent)' : 'transparent',
                  color: p === page ? 'var(--accent-ink)' : 'var(--muted)',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                {p}
              </button>
            )
          })}
          <button
            onClick={() => setPage(p => Math.min(pages, p + 1))}
            disabled={page >= pages}
            className="btn-ghost p-1.5 disabled:opacity-30"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
