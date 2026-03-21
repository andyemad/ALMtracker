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
import { LocationChip } from '../components/LocationChip'

const fmt$ = (n: number | null) => n != null ? `$${n.toLocaleString()}` : '—'
const fmtMi = (n: number | null) => n != null ? `${n.toLocaleString()} mi` : '—'
const isNewVehicle = (v: Vehicle) => {
  const d = new Date(v.first_seen + 'Z')
  return Date.now() - d.getTime() < 1000 * 60 * 60 * 24
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

  // Filters — initialized from URL params
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

  // Debounced filter values
  const debouncedSearch     = useDebounce(search, 300)
  const debouncedMinYear    = useDebounce(minYear, 300)
  const debouncedMaxYear    = useDebounce(maxYear, 300)
  const debouncedMinPrice   = useDebounce(minPrice, 300)
  const debouncedMaxPrice   = useDebounce(maxPrice, 300)
  const debouncedMaxMileage = useDebounce(maxMileage, 300)
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

  // Reset to page 1 when debounced text filter values change
  useEffect(() => {
    setPage(1)
  }, [debouncedSearch, debouncedMinYear, debouncedMaxYear,
      debouncedMinPrice, debouncedMaxPrice, debouncedMaxMileage,
      debouncedMinDaysOnLot, debouncedMaxDaysOnLot])

  // Reset to page 1 on filter change
  const resetPage = () => setPage(1)

  const columns = useMemo<ColumnDef<Vehicle>[]>(() => [
    {
      id: 'status',
      header: '',
      size: 50,
      cell: ({ row }) => isNewVehicle(row.original)
        ? <span className="badge-new">NEW</span>
        : <span className="w-2 h-2 rounded-full bg-emerald-500/50 inline-block" />,
    },
    {
      id: 'image',
      header: '',
      size: 60,
      cell: ({ row }) => row.original.image_url
        ? <img src={row.original.image_url} alt="" className="w-12 h-8 object-cover rounded bg-slate-700" />
        : <div className="w-12 h-8 rounded bg-slate-700 flex items-center justify-center text-slate-600 text-[10px]">No img</div>,
    },
    {
      accessorKey: 'stock_number',
      header: 'Stock #',
      size: 100,
      cell: ({ getValue }) => <span className="font-mono text-xs text-slate-400">{getValue() as string}</span>,
    },
    {
      accessorKey: 'year',
      header: 'Year',
      size: 70,
      cell: ({ getValue }) => <span className="font-semibold text-white">{getValue() as number}</span>,
    },
    {
      accessorKey: 'make',
      header: 'Make',
      size: 110,
      cell: ({ getValue }) => <span className="text-slate-200">{getValue() as string}</span>,
    },
    {
      accessorKey: 'model',
      header: 'Model',
      size: 120,
      cell: ({ getValue }) => <span className="text-slate-200">{getValue() as string}</span>,
    },
    {
      accessorKey: 'trim',
      header: 'Trim',
      size: 120,
      cell: ({ getValue }) => <span className="text-slate-400 text-xs">{getValue() as string || '—'}</span>,
    },
    {
      accessorKey: 'price',
      header: 'Price',
      size: 100,
      cell: ({ getValue }) => (
        <span className="font-semibold text-white">{fmt$(getValue() as number | null)}</span>
      ),
    },
    {
      accessorKey: 'mileage',
      header: 'Mileage',
      size: 100,
      cell: ({ getValue }) => <span className="text-slate-300">{fmtMi(getValue() as number | null)}</span>,
    },
    {
      accessorKey: 'exterior_color',
      header: 'Color',
      size: 100,
      cell: ({ getValue }) => <span className="text-slate-400">{getValue() as string || '—'}</span>,
    },
    {
      accessorKey: 'days_on_lot',
      header: 'Days',
      size: 70,
      cell: ({ getValue }) => {
        const d = getValue() as number
        return (
          <span className={d > 60 ? 'text-red-400' : d > 30 ? 'text-amber-400' : 'text-slate-400'}>
            {d}
          </span>
        )
      },
    },
    {
      id: 'actions',
      header: '',
      size: 50,
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
    onSortingChange: (updater) => {
      setSorting(updater)
      resetPage()
    },
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
    setMinDaysOnLot(min)
    setMaxDaysOnLot(max)
    setSorting(min ? [{ id: 'days_on_lot', desc: true }] : [])
    setShowFilters(true)
    resetPage()
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-800 px-4 py-4 sm:px-6">
        <div>
          <h1 className="text-xl font-bold text-white">Inventory</h1>
          <p className="text-slate-400 text-xs mt-0.5">
            {total.toLocaleString()} vehicles
          </p>
          <LocationChip className="mt-1" />
        </div>

        {/* Condition Toggle */}
        <div className="flex gap-1 bg-slate-900 border border-slate-700 rounded-lg p-1 ml-auto">
          {([['Active', true], ['Sold', false], ['All', null]] as const).map(([lbl, val]) => (
            <button
              key={lbl}
              onClick={() => { setShowActive(val); resetPage() }}
              className={`text-xs px-3 py-1 rounded-md transition-colors ${
                showActive === val
                  ? 'bg-brand-600 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {lbl}
            </button>
          ))}
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
          <input
            className="input pl-9 w-52"
            placeholder="Search make, model, stock..."
            value={search}
            onChange={e => { setSearch(e.target.value) }}
          />
        </div>

        <div className="flex flex-wrap gap-2">
          {[
            { label: 'Fresh ≤7d', min: '', max: '7' },
            { label: '30+ days', min: '30', max: '' },
            { label: '45+ days', min: '45', max: '' },
            { label: '60+ days', min: '60', max: '' },
          ].map(preset => {
            const active = minDaysOnLot === preset.min && maxDaysOnLot === preset.max
            return (
              <button
                key={preset.label}
                onClick={() => applyAgingPreset(preset.min, preset.max)}
                className={`rounded-lg border px-3 py-2 text-xs font-medium transition-colors ${
                  active
                    ? 'border-brand-500/60 bg-brand-600 text-white'
                    : 'border-slate-700 bg-slate-900 text-slate-300 hover:border-slate-500 hover:text-white'
                }`}
              >
                {preset.label}
              </button>
            )
          })}
        </div>

        {/* Filter Toggle */}
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`btn-secondary relative ${showFilters ? 'bg-slate-600' : ''}`}
        >
          <SlidersHorizontal className="w-3.5 h-3.5" />
          Filters
          {activeFiltersCount > 0 && (
            <span className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-brand-600 text-white text-[10px] flex items-center justify-center">
              {activeFiltersCount}
            </span>
          )}
        </button>

        {/* Export */}
        <a href="/api/vehicles/export" download className="btn-secondary">
          <Download className="w-3.5 h-3.5" />
          Export CSV
        </a>
      </div>

      {/* Filter Panel */}
      {showFilters && (
        <div className="grid grid-cols-2 gap-3 border-b border-slate-800 bg-slate-900/50 px-6 py-4 md:grid-cols-4 lg:grid-cols-9">
          <select className="select" value={make} onChange={e => { setMake(e.target.value); resetPage() }}>
            <option value="">All Makes</option>
            {filterOptions?.makes.map(m => <option key={m}>{m}</option>)}
          </select>
          <input className="input" placeholder="Min Year" type="number" value={minYear}
            onChange={e => { setMinYear(e.target.value) }} />
          <input className="input" placeholder="Max Year" type="number" value={maxYear}
            onChange={e => { setMaxYear(e.target.value) }} />
          <input className="input" placeholder="Min Price $" type="number" value={minPrice}
            onChange={e => { setMinPrice(e.target.value) }} />
          <input className="input" placeholder="Max Price $" type="number" value={maxPrice}
            onChange={e => { setMaxPrice(e.target.value) }} />
          <input className="input" placeholder="Max Mileage" type="number" value={maxMileage}
            onChange={e => { setMaxMileage(e.target.value) }} />
          <input className="input" placeholder="Min Days" type="number" value={minDaysOnLot}
            onChange={e => { setMinDaysOnLot(e.target.value) }} />
          <input className="input" placeholder="Max Days" type="number" value={maxDaysOnLot}
            onChange={e => { setMaxDaysOnLot(e.target.value) }} />
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
      <div className="flex-1 overflow-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-slate-900/95 backdrop-blur-sm z-10">
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
                        h.column.getIsSorted() === 'asc' ? <ChevronUp className="w-3 h-3" /> :
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
                <tr key={i} className="border-b border-slate-700/30">
                  {columns.map((_, j) => (
                    <td key={j} className="table-cell">
                      <div className="h-4 bg-slate-800 rounded animate-pulse" />
                    </td>
                  ))}
                </tr>
              ))
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="text-center py-16 text-slate-500">
                  No vehicles found
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map(row => (
                <tr
                  key={row.id}
                  className="table-row"
                >
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
      <div className="px-6 py-3 border-t border-slate-800 flex items-center justify-between text-sm">
        <span className="text-slate-400 text-xs">
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
          {/* Page numbers */}
          {Array.from({ length: Math.min(5, pages) }, (_, i) => {
            const p = Math.max(1, Math.min(pages - 4, page - 2)) + i
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
