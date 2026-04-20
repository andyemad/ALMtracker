import { useEffect, useState, useCallback, useMemo } from 'react'
import {
  useReactTable, getCoreRowModel, getSortedRowModel,
  flexRender, type ColumnDef, type SortingState
} from '@tanstack/react-table'
import {
  Search, Download, ChevronUp, ChevronDown, ChevronsUpDown,
  ExternalLink, ChevronLeft, ChevronRight, ArrowRightLeft, X
} from 'lucide-react'
import { formatDistanceToNow } from 'date-fns'
import { getVehicles, getFilterOptions } from '../api'
import type { Vehicle, FilterOptions } from '../types'
import { useDealer } from '../context/DealerContext'
import { useDebounce } from '../hooks/useDebounce'
import { LocationChip } from '../components/LocationChip'

const fmt$ = (n: number | null) => n != null ? `$${n.toLocaleString()}` : '—'
const fmtMi = (n: number | null) => n != null ? `${n.toLocaleString()} mi` : '—'

const SUFFIX_COLORS: Record<string, string> = {
  A: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
  B: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  C: 'bg-violet-500/20 text-violet-300 border-violet-500/30',
  D: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
  E: 'bg-red-500/20 text-red-300 border-red-500/30',
}

function StockCell({ stock }: { stock: string }) {
  const last = stock.slice(-1).toUpperCase()
  const suffix = SUFFIX_COLORS[last]
  if (!suffix) return <span className="font-mono text-xs text-[color:var(--muted)]">{stock}</span>
  const base = stock.slice(0, -1)
  return (
    <span className="flex items-center gap-1">
      <span className="font-mono text-xs text-[color:var(--muted)]">{base}</span>
      <span className={`font-mono text-[10px] font-bold px-1 py-0.5 rounded border ${suffix}`}>{last}</span>
    </span>
  )
}

export default function TradeIns() {
  const { selectedDealer } = useDealer()
  const dealerId = selectedDealer?.id

  const [data, setData] = useState<Vehicle[]>([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [sorting, setSorting] = useState<SortingState>([])
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(null)

  const [search, setSearch] = useState('')
  const [make, setMake] = useState('')
  const [minYear, setMinYear] = useState('')
  const [maxYear, setMaxYear] = useState('')
  const [minPrice, setMinPrice] = useState('')
  const [maxPrice, setMaxPrice] = useState('')
  const [maxMileage, setMaxMileage] = useState('')
  const [showFilters, setShowFilters] = useState(false)

  const debouncedSearch     = useDebounce(search, 300)
  const debouncedMinYear    = useDebounce(minYear, 300)
  const debouncedMaxYear    = useDebounce(maxYear, 300)
  const debouncedMinPrice   = useDebounce(minPrice, 300)
  const debouncedMaxPrice   = useDebounce(maxPrice, 300)
  const debouncedMaxMileage = useDebounce(maxMileage, 300)

  useEffect(() => {
    getFilterOptions(dealerId).then(setFilterOptions)
    setPage(1)
  }, [dealerId])

  const sortBy = sorting[0]?.id
  const sortOrder = sorting[0]?.desc ? 'desc' : 'asc'

  const load = useCallback(() => {
    setLoading(true)
    getVehicles({
      dealer_id: dealerId,
      is_trade_in: true,
      is_active: true,
      search:      debouncedSearch || undefined,
      make:        make || undefined,
      min_year:    debouncedMinYear ? +debouncedMinYear : undefined,
      max_year:    debouncedMaxYear ? +debouncedMaxYear : undefined,
      min_price:   debouncedMinPrice ? +debouncedMinPrice : undefined,
      max_price:   debouncedMaxPrice ? +debouncedMaxPrice : undefined,
      max_mileage: debouncedMaxMileage ? +debouncedMaxMileage : undefined,
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
      sortBy, sortOrder, page])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    setPage(1)
  }, [debouncedSearch, debouncedMinYear, debouncedMaxYear,
      debouncedMinPrice, debouncedMaxPrice, debouncedMaxMileage])

  const resetPage = () => setPage(1)

  const columns = useMemo<ColumnDef<Vehicle>[]>(() => [
    {
      id: 'suffix',
      header: 'Type',
      size: 60,
      cell: ({ row }) => {
        const last = row.original.stock_number.slice(-1).toUpperCase()
        const cls = SUFFIX_COLORS[last] ?? ''
        return cls ? (
          <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${cls}`}>
            T/I-{last}
          </span>
        ) : null
      },
    },
    {
      accessorKey: 'stock_number',
      header: 'Stock #',
      size: 120,
      cell: ({ row }) => (
        <a
          href={row.original.listing_url || `https://www.almcars.com/inventory/${(row.original.stock_number || '').toLowerCase()}`}
          target="_blank"
          rel="noreferrer"
          className="hover:underline"
          onClick={e => e.stopPropagation()}
        >
          <StockCell stock={row.original.stock_number} />
        </a>
      ),
    },
    {
      accessorKey: 'year',
      header: 'Year',
      size: 70,
      cell: ({ getValue }) => <span className="font-semibold text-[color:var(--ink)]">{getValue() as number}</span>,
    },
    {
      accessorKey: 'make',
      header: 'Make',
      size: 110,
      cell: ({ getValue }) => <span className="text-[color:var(--ink)]">{getValue() as string}</span>,
    },
    {
      accessorKey: 'model',
      header: 'Model',
      size: 130,
      cell: ({ getValue }) => <span className="text-[color:var(--ink)]">{getValue() as string}</span>,
    },
    {
      accessorKey: 'trim',
      header: 'Trim',
      size: 120,
      cell: ({ getValue }) => <span className="text-[color:var(--muted)] text-xs">{getValue() as string || '—'}</span>,
    },
    {
      accessorKey: 'price',
      header: 'Price',
      size: 100,
      cell: ({ getValue }) => (
        <span className="font-semibold text-[color:var(--ink)]">{fmt$(getValue() as number | null)}</span>
      ),
    },
    {
      accessorKey: 'mileage',
      header: 'Mileage',
      size: 100,
      cell: ({ getValue }) => <span className="text-[color:var(--ink-2)]">{fmtMi(getValue() as number | null)}</span>,
    },
    {
      accessorKey: 'exterior_color',
      header: 'Color',
      size: 100,
      cell: ({ getValue }) => <span className="text-[color:var(--muted)]">{getValue() as string || '—'}</span>,
    },
    {
      accessorKey: 'days_on_lot',
      header: 'Days',
      size: 70,
      cell: ({ getValue }) => {
        const d = getValue() as number
        return (
          <span className={d > 60 ? 'text-[color:var(--danger)]' : d > 30 ? 'text-[color:var(--warn)]' : 'text-[color:var(--muted)]'}>
            {d}
          </span>
        )
      },
    },
    {
      accessorKey: 'first_seen',
      header: 'Taken In',
      size: 110,
      cell: ({ getValue }) => (
        <span className="text-[color:var(--muted)] text-xs">
          {formatDistanceToNow(new Date((getValue() as string) + 'Z'), { addSuffix: true })}
        </span>
      ),
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
    onSortingChange: (updater) => { setSorting(updater); resetPage() },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    manualSorting: true,
    manualPagination: true,
  })

  const activeFiltersCount = [search, make, minYear, maxYear, minPrice, maxPrice, maxMileage].filter(Boolean).length

  const clearFilters = () => {
    setSearch(''); setMake(''); setMinYear(''); setMaxYear('')
    setMinPrice(''); setMaxPrice(''); setMaxMileage('')
    resetPage()
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 border-b border-[color:var(--hairline)] px-4 py-4 sm:px-6">
        <div>
          <div className="flex items-center gap-2">
            <ArrowRightLeft className="w-4 h-4 text-[color:var(--warn)]" />
            <h1 className="text-xl font-bold text-[color:var(--ink)]">Trade-In Inventory</h1>
          </div>
          <p className="text-[color:var(--muted)] text-xs mt-0.5">
            {total.toLocaleString()} trade-in{total !== 1 ? 's' : ''} — stock numbers ending A/B/C/D/E
          </p>
          <LocationChip className="mt-1" />
        </div>

        {/* Legend */}
        <div className="flex items-center gap-2 ml-4">
          {Object.entries(SUFFIX_COLORS).map(([letter, cls]) => (
            <span key={letter} className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${cls}`}>
              T/I-{letter}
            </span>
          ))}
        </div>

        {/* Search */}
        <div className="relative ml-auto">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[color:var(--muted)]" />
          <input
            className="input pl-9 w-52"
            placeholder="Search make, model, stock..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        {/* Quick Sort */}
        <select
          className="select w-auto text-xs"
          value={sorting[0] ? `${sorting[0].id}_${sorting[0].desc ? 'desc' : 'asc'}` : 'first_seen_desc'}
          onChange={e => {
            const [id, dir] = e.target.value.split('_')
            setSorting([{ id, desc: dir === 'desc' }])
            resetPage()
          }}
        >
          <option value="first_seen_desc">Recently Added</option>
          <option value="first_seen_asc">Oldest Added</option>
          <option value="price_desc">Price: High → Low</option>
          <option value="price_asc">Price: Low → High</option>
          <option value="days_on_lot_desc">Days: Most → Least</option>
          <option value="days_on_lot_asc">Days: Least → Most</option>
          <option value="year_desc">Year: Newest</option>
          <option value="year_asc">Year: Oldest</option>
          <option value="mileage_asc">Mileage: Low → High</option>
          <option value="mileage_desc">Mileage: High → Low</option>
        </select>

        {/* Filter Toggle */}
        <button
          onClick={() => setShowFilters(!showFilters)}
          className={`btn-secondary relative ${showFilters ? 'bg-[color:var(--hairline-2)]' : ''}`}
        >
          Filters
          {activeFiltersCount > 0 && (
            <span className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-brand-600 text-[color:var(--ink)] text-[10px] flex items-center justify-center">
              {activeFiltersCount}
            </span>
          )}
        </button>

        {/* Export */}
        <a
          href={`/api/vehicles/export?is_trade_in=true${dealerId ? `&dealer_id=${dealerId}` : ''}`}
          download
          className="btn-secondary"
        >
          <Download className="w-3.5 h-3.5" />
          Export CSV
        </a>
      </div>

      {/* Filter Panel */}
      {showFilters && (
        <div className="px-6 py-4 bg-[color:var(--card)] border-b border-[color:var(--hairline)] grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
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
          <div className="flex gap-2">
            {activeFiltersCount > 0 && (
              <button onClick={clearFilters} className="btn-ghost px-2 w-full">
                <X className="w-3.5 h-3.5 mr-1" /> Clear
              </button>
            )}
          </div>
        </div>
      )}

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full">
          <thead className="sticky top-0 bg-[color:var(--card)] backdrop-blur-sm z-10">
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
                <tr key={i} className="border-b border-[color:var(--hairline-2)]">
                  {columns.map((_, j) => (
                    <td key={j} className="table-cell">
                      <div className="h-4 bg-[color:var(--bg-2)] rounded animate-pulse" />
                    </td>
                  ))}
                </tr>
              ))
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="text-center py-16 text-[color:var(--muted)]">
                  No trade-in vehicles found
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
      <div className="px-6 py-3 border-t border-[color:var(--hairline)] flex items-center justify-between text-sm">
        <span className="text-[color:var(--muted)] text-xs">
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
                className={`w-7 h-7 rounded text-xs transition-colors ${
                  p === page ? 'bg-brand-600 text-[color:var(--ink)]' : 'text-[color:var(--muted)] hover:text-[color:var(--ink)] hover:bg-[color:var(--hairline)]'
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
