import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Car, Activity, Bell, Users, RefreshCw,
  MapPin, ChevronDown, Check, ArrowRightLeft, X, FileText, BarChart2
} from 'lucide-react'
import { useState, useRef, useEffect } from 'react'
import toast from 'react-hot-toast'
import { triggerScrape, getScrapeLogs } from '../api'
import { useDealer } from '../context/DealerContext'
import { useScrape } from '../context/ScrapeContext'

const links = [
  { to: '/dashboard',  icon: LayoutDashboard, label: 'Dashboard'    },
  { to: '/analytics',  icon: BarChart2,        label: 'Analytics'    },
  { to: '/carfax',     icon: FileText,        label: 'CARFAX'       },
  { to: '/inventory',  icon: Car,             label: 'Inventory'    },
  { to: '/trade-ins',  icon: ArrowRightLeft,  label: 'Trade-Ins'    },
  { to: '/activity',   icon: Activity,        label: 'Activity Log' },
  { to: '/watchlist',  icon: Bell,            label: 'Watchlist'    },
  { to: '/leads',      icon: Users,           label: 'Leads'        },
]

interface SidebarProps {
  mobile?: boolean
  open?: boolean
  onClose?: () => void
}

export default function Sidebar({ mobile = false, open = false, onClose }: SidebarProps) {
  const [showPicker, setShowPicker] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)
  const location = useLocation()
  const { dealers, selectedDealer, setSelectedDealer } = useDealer()
  const { scraping, triggerScraping } = useScrape()

  // Close picker when clicking outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setShowPicker(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  useEffect(() => {
    if (mobile) {
      setShowPicker(false)
      onClose?.()
    }
  }, [location.pathname])

  const handleScrape = async () => {
    try {
      const currentLogs = await getScrapeLogs()
      const baselineId = currentLogs.length > 0 ? currentLogs[0].id : null
      await triggerScrape()
      toast.success('Scrape triggered — updating inventory...')
      triggerScraping(baselineId)
    } catch {
      toast.error('Failed to trigger scrape')
    }
  }

  const totalVehicles = dealers.reduce((sum, d) => sum + d.active_vehicle_count, 0)

  const sidebarContent = (
    <div className="flex h-full flex-col overflow-hidden rounded-r-[28px] border-r border-slate-800/80 bg-slate-950/80 backdrop-blur-xl">
      <div className="px-5 py-5 border-b border-slate-800/80">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-2xl bg-gradient-to-br from-brand-500 via-cyan-400 to-emerald-400 p-[1px] shadow-[0_0_30px_rgba(99,102,241,0.35)]">
              <div className="flex h-full w-full items-center justify-center rounded-2xl bg-slate-950">
                <Car className="w-4 h-4 text-white" />
              </div>
            </div>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.24em] text-cyan-300/70">ALM Tracker</div>
              <div className="text-sm font-semibold text-white leading-none">Inventory Intelligence</div>
            </div>
          </div>
          {mobile && (
            <button onClick={onClose} className="btn-ghost p-1.5">
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      <div className="relative border-b border-slate-800 px-3 py-3" ref={pickerRef}>
        <button
          onClick={() => setShowPicker(p => !p)}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-800 border border-slate-700
                     hover:border-slate-600 text-left transition-colors group"
        >
          <MapPin className="w-3.5 h-3.5 text-brand-400 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="text-xs font-medium text-white truncate">
              {selectedDealer ? selectedDealer.name : 'All Locations'}
            </div>
            <div className="text-[10px] text-slate-500 mt-0.5">
              {selectedDealer
                ? `${selectedDealer.active_vehicle_count} vehicles`
                : `${dealers.length} locations · ${totalVehicles} vehicles`}
            </div>
          </div>
          <ChevronDown className={`w-3.5 h-3.5 text-slate-500 flex-shrink-0 transition-transform ${showPicker ? 'rotate-180' : ''}`} />
        </button>

        {showPicker && (
          <div className="absolute left-3 right-3 mt-1 z-50 overflow-hidden rounded-xl border border-slate-700 bg-slate-800 shadow-xl" style={{ width: '13.5rem' }}>
            <button
              onClick={() => { setSelectedDealer(null); setShowPicker(false) }}
              className="w-full flex items-center gap-3 px-3 py-2.5 hover:bg-slate-700 transition-colors text-left"
            >
              <div className="w-5 h-5 rounded-full bg-brand-600/20 flex items-center justify-center flex-shrink-0">
                <MapPin className="w-3 h-3 text-brand-400" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium text-white">All Locations</div>
                <div className="text-[10px] text-slate-500">{dealers.length} dealers · {totalVehicles} vehicles</div>
              </div>
              {!selectedDealer && <Check className="w-3.5 h-3.5 text-brand-400 flex-shrink-0" />}
            </button>

            <div className="border-t border-slate-700/50 max-h-72 overflow-y-auto">
              {dealers.map(dealer => (
                <button
                  key={dealer.id}
                  onClick={() => { setSelectedDealer(dealer); setShowPicker(false) }}
                  className="w-full flex items-center gap-3 px-3 py-2 hover:bg-slate-700 transition-colors text-left"
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium text-slate-200 truncate">{dealer.name}</div>
                    <div className="text-[10px] text-slate-500">{dealer.city} · {dealer.active_vehicle_count} vehicles</div>
                  </div>
                  {selectedDealer?.id === dealer.id && <Check className="w-3.5 h-3.5 text-brand-400 flex-shrink-0" />}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {links.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            onClick={() => onClose?.()}
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="px-3 py-4 border-t border-slate-800">
        <button
          onClick={handleScrape}
          disabled={scraping}
          className="w-full flex items-center justify-center gap-2 rounded-xl border border-slate-700 bg-slate-800/90
                     py-2.5 text-sm font-medium text-slate-300 transition-colors hover:bg-slate-700 hover:text-white disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${scraping ? 'animate-spin' : ''}`} />
          {scraping ? 'Scraping...' : 'Refresh Now'}
        </button>
        <p className="text-center text-[11px] text-slate-600 mt-2">Auto-refreshes every 6h</p>
      </div>
    </div>
  )

  if (mobile) {
    return (
      <>
        <div
          onClick={onClose}
          className={`fixed inset-0 z-40 bg-slate-950/70 backdrop-blur-sm transition-opacity duration-200 ${
            open ? 'opacity-100' : 'pointer-events-none opacity-0'
          }`}
        />
        <aside
          className={`fixed inset-y-0 left-0 z-50 w-[18rem] max-w-[85vw] transform transition-transform duration-300 ease-out ${
            open ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          {sidebarContent}
        </aside>
      </>
    )
  }

  return (
    <aside className="hidden h-full w-72 flex-shrink-0 lg:block">
      {sidebarContent}
    </aside>
  )
}
