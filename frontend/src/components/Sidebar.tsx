import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Car, Activity, Bell, Users, RefreshCw,
  MapPin, ChevronDown, Check, ArrowRightLeft, X, FileText, BarChart2,
  Sun, Moon,
} from 'lucide-react'
import { useState, useRef, useEffect } from 'react'
import toast from 'react-hot-toast'
import { triggerScrape, getScrapeLogs } from '../api'
import { useDealer } from '../context/DealerContext'
import { useScrape } from '../context/ScrapeContext'

const NAV_LINKS = [
  { to: '/dashboard', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/analytics', icon: BarChart2,       label: 'Analytics' },
  { to: '/carfax',    icon: FileText,        label: 'CARFAX'    },
  { to: '/inventory', icon: Car,             label: 'Inventory' },
  { to: '/trade-ins', icon: ArrowRightLeft,  label: 'Trade-Ins' },
  { to: '/activity',  icon: Activity,        label: 'Activity'  },
  { to: '/watchlist', icon: Bell,            label: 'Watchlist' },
  { to: '/leads',     icon: Users,           label: 'Leads'     },
]

interface SidebarProps {
  mobile?: boolean
  open?: boolean
  onClose?: () => void
}

export default function Sidebar({ mobile = false, open = false, onClose }: SidebarProps) {
  const [showPicker, setShowPicker] = useState(false)
  const [isDark, setIsDark] = useState(
    () => document.documentElement.getAttribute('data-theme') === 'dark'
  )
  const pickerRef = useRef<HTMLDivElement>(null)
  const location = useLocation()
  const { dealers, selectedDealer, setSelectedDealer } = useDealer()
  const { scraping, triggerScraping } = useScrape()

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

  const handleToggleTheme = () => {
    const current = document.documentElement.getAttribute('data-theme') || 'light'
    const next = current === 'dark' ? 'light' : 'dark'
    document.documentElement.setAttribute('data-theme', next)
    localStorage.setItem('alm-theme', next)
    setIsDark(next === 'dark')
  }

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
    <div
      className="flex h-full flex-col"
      style={{ width: 264, background: 'var(--card)', borderRight: '1px solid var(--hairline)' }}
    >
      {/* Brand */}
      <div className="px-5 pt-6 pb-5" style={{ borderBottom: '1px solid var(--hairline)' }}>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div
              className="w-8 h-8 flex items-center justify-center flex-shrink-0"
              style={{
                background: 'var(--ink)',
                color: 'var(--card)',
                borderRadius: 3,
                border: '1px solid var(--hairline-2)',
              }}
            >
              <span className="serif" style={{ fontSize: 16, lineHeight: 1 }}>A</span>
            </div>
            <div>
              <div className="eyebrow" style={{ lineHeight: 1.5 }}>ALM · Tracker</div>
              <div className="serif" style={{ fontSize: 20, color: 'var(--ink)', lineHeight: 1 }}>
                Concierge
              </div>
            </div>
          </div>
          {mobile && (
            <button onClick={onClose} className="btn-ghost p-1.5">
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Location picker */}
      <div className="px-4 py-3 relative" style={{ borderBottom: '1px solid var(--hairline)' }} ref={pickerRef}>
        <button
          onClick={() => setShowPicker(p => !p)}
          className="w-full flex items-start gap-2 px-3 py-2.5 text-left t"
          style={{ borderRadius: 4, border: '1px solid var(--hairline)', background: 'var(--bg-2)' }}
        >
          <MapPin className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" style={{ color: 'var(--accent)' }} />
          <div className="flex-1 min-w-0">
            <div className="text-xs font-semibold truncate" style={{ color: 'var(--ink)' }}>
              {selectedDealer ? selectedDealer.name : 'All Locations'}
            </div>
            <div className="mt-0.5 truncate" style={{ fontSize: 10.5, color: 'var(--muted)' }}>
              {selectedDealer
                ? `${selectedDealer.active_vehicle_count} vehicles · ${selectedDealer.city}`
                : `${dealers.length} locations · ${totalVehicles.toLocaleString()} vehicles`}
            </div>
          </div>
          <ChevronDown
            className={`w-3.5 h-3.5 flex-shrink-0 t ${showPicker ? 'rotate-180' : ''}`}
            style={{ color: 'var(--muted)' }}
          />
        </button>

        {showPicker && (
          <div
            className="absolute left-4 right-4 z-50 overflow-y-auto no-scrollbar"
            style={{
              top: '100%',
              marginTop: 4,
              border: '1px solid var(--hairline)',
              borderRadius: 4,
              background: 'var(--card)',
              boxShadow: '0 20px 60px oklch(0 0 0 / 0.12)',
              maxHeight: 320,
            }}
          >
            <button
              onClick={() => { setSelectedDealer(null); setShowPicker(false) }}
              className="w-full flex items-center justify-between px-3 py-2.5 text-left t"
              style={{ background: !selectedDealer ? 'var(--bg-2)' : undefined }}
            >
              <div>
                <div className="text-xs font-medium" style={{ color: 'var(--ink)' }}>All Locations</div>
                <div style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 2 }}>
                  {dealers.length} lots · {totalVehicles.toLocaleString()} units
                </div>
              </div>
              {!selectedDealer && <Check className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />}
            </button>
            <div style={{ borderTop: '1px solid var(--hairline)' }} />
            {dealers.map(dealer => (
              <button
                key={dealer.id}
                onClick={() => { setSelectedDealer(dealer); setShowPicker(false) }}
                className="w-full flex items-center justify-between px-3 py-2 text-left t row-hover"
                style={{ background: selectedDealer?.id === dealer.id ? 'var(--bg-2)' : undefined }}
              >
                <div className="min-w-0">
                  <div className="text-xs font-medium truncate" style={{ color: 'var(--ink)' }}>
                    {dealer.name}
                  </div>
                  <div className="truncate" style={{ fontSize: 10.5, color: 'var(--muted)', marginTop: 2 }}>
                    {dealer.city} · {dealer.active_vehicle_count}
                  </div>
                </div>
                {selectedDealer?.id === dealer.id && (
                  <Check className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--accent)' }} />
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-3 overflow-y-auto no-scrollbar space-y-0.5">
        {NAV_LINKS.map(({ to, icon: Icon, label }) => (
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

      {/* Refresh + theme toggle */}
      <div className="px-3 py-3" style={{ borderTop: '1px solid var(--hairline)' }}>
        <button
          onClick={handleScrape}
          disabled={scraping}
          className="w-full btn justify-center"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${scraping ? 'animate-spin' : ''}`} />
          {scraping ? 'Scraping...' : 'Refresh now'}
        </button>
        <div className="mt-2 flex items-center justify-between px-1">
          <span className="mono" style={{ fontSize: 10.5, color: 'var(--muted)' }}>Auto · every 6h</span>
          <button onClick={handleToggleTheme} className="btn-ghost p-1.5" title="Toggle theme">
            {isDark ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>
    </div>
  )

  if (mobile) {
    return (
      <>
        <div
          onClick={onClose}
          className={`fixed inset-0 z-40 transition-opacity duration-200 ${
            open ? 'opacity-100' : 'pointer-events-none opacity-0'
          }`}
          style={{ background: 'oklch(0 0 0 / 0.45)' }}
        />
        <aside
          className={`fixed inset-y-0 left-0 z-50 transform transition-transform duration-300 ease-out ${
            open ? 'translate-x-0' : '-translate-x-full'
          }`}
        >
          {sidebarContent}
        </aside>
      </>
    )
  }

  return (
    <aside className="hidden h-screen flex-shrink-0 sticky top-0 lg:flex">
      {sidebarContent}
    </aside>
  )
}
