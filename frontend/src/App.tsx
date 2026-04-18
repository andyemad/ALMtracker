import { Suspense, lazy, useState } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Menu } from 'lucide-react'
import Sidebar from './components/Sidebar'
import { DealerProvider, useDealer } from './context/DealerContext'
import { ScrapeProvider } from './context/ScrapeContext'

const Dashboard   = lazy(() => import('./pages/Dashboard'))
const Inventory   = lazy(() => import('./pages/Inventory'))
const Carfax      = lazy(() => import('./pages/Carfax'))
const Activity    = lazy(() => import('./pages/Activity'))
const Watchlist   = lazy(() => import('./pages/Watchlist'))
const Leads       = lazy(() => import('./pages/Leads'))
const TradeIns    = lazy(() => import('./pages/TradeIns'))
const FindInventory = lazy(() => import('./pages/FindInventory'))
const Analytics = lazy(() => import('./pages/Analytics'))

export default function App() {
  return (
    <DealerProvider>
      <ScrapeProvider>
        <AppFrame />
      </ScrapeProvider>
    </DealerProvider>
  )
}

function AppFrame() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const location = useLocation()
  const { selectedDealer } = useDealer()

  if (location.pathname === '/find') {
    return (
      <Suspense fallback={<RouteLoadingState />}>
        <Routes>
          <Route path="/find" element={<FindInventory />} />
        </Routes>
      </Suspense>
    )
  }

  return (
    <div className="min-h-dvh flex" style={{ background: 'var(--bg)' }}>
      <Sidebar />
      <Sidebar mobile open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Mobile header */}
        <header
          className="sticky top-0 z-30 flex items-center gap-3 px-4 py-3 lg:hidden"
          style={{ borderBottom: '1px solid var(--hairline)', background: 'var(--card)' }}
        >
          <button onClick={() => setMobileNavOpen(true)} className="btn-ghost p-2">
            <Menu className="h-4 w-4" />
          </button>
          <div className="min-w-0 flex-1">
            <p className="eyebrow truncate">
              {selectedDealer ? selectedDealer.name : 'All Locations'}
            </p>
            <p className="serif" style={{ fontSize: 18, color: 'var(--ink)', lineHeight: 1.1 }}>
              ALM Tracker
            </p>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto">
          <Suspense fallback={<RouteLoadingState />}>
            <Routes>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/find" element={<FindInventory />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/inventory" element={<Inventory />} />
              <Route path="/carfax" element={<Carfax />} />
              <Route path="/activity" element={<Activity />} />
              <Route path="/watchlist" element={<Watchlist />} />
              <Route path="/leads" element={<Leads />} />
              <Route path="/trade-ins" element={<TradeIns />} />
              <Route path="/analytics" element={<Analytics />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </div>
  )
}

function RouteLoadingState() {
  return (
    <div className="p-6 max-w-screen-xl mx-auto animate-pulse space-y-6">
      <div className="h-10 w-64 rounded" style={{ background: 'var(--bg-2)' }} />
      <div
        className="grid grid-cols-5"
        style={{ borderTop: '1px solid var(--hairline)', borderBottom: '1px solid var(--hairline)' }}
      >
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-24 p-4" style={{ borderLeft: i > 0 ? '1px solid var(--hairline)' : 'none' }}>
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
