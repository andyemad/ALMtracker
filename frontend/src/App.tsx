import { Suspense, lazy, useState } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Menu, MapPin } from 'lucide-react'
import Sidebar from './components/Sidebar'
import { DealerProvider, useDealer } from './context/DealerContext'
import { ScrapeProvider } from './context/ScrapeContext'

const Dashboard = lazy(() => import('./pages/Dashboard'))
const Inventory = lazy(() => import('./pages/Inventory'))
const Activity = lazy(() => import('./pages/Activity'))
const Watchlist = lazy(() => import('./pages/Watchlist'))
const Leads = lazy(() => import('./pages/Leads'))
const TradeIns = lazy(() => import('./pages/TradeIns'))
const FindInventory = lazy(() => import('./pages/FindInventory'))

export default function App() {
  return (
    <DealerProvider>
      <ScrapeProvider>
        <AppFrame />
      </ScrapeProvider>
    </DealerProvider>
  )
}

const ROUTE_META: Record<string, { title: string; subtitle: string }> = {
  '/dashboard': { title: 'Dashboard', subtitle: 'Live inventory intelligence' },
  '/inventory': { title: 'Inventory', subtitle: 'Search, sort, and export the live lot' },
  '/trade-ins': { title: 'Trade-Ins', subtitle: 'Monitor inbound appraisals and aging units' },
  '/activity': { title: 'Activity Log', subtitle: 'Track every inventory movement in one feed' },
  '/watchlist': { title: 'Watchlist', subtitle: 'Saved vehicle criteria and alert coverage' },
  '/leads': { title: 'Leads', subtitle: 'Pipeline health across every active deal' },
}

function AppFrame() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const location = useLocation()
  const { selectedDealer, dealers } = useDealer()

  if (location.pathname === '/find') {
    return (
      <Suspense fallback={<RouteLoadingState />}>
        <Routes>
          <Route path="/find" element={<FindInventory />} />
        </Routes>
      </Suspense>
    )
  }

  const routeMeta = ROUTE_META[location.pathname] ?? ROUTE_META['/dashboard']
  const dealerLabel = selectedDealer
    ? `${selectedDealer.name} · ${selectedDealer.city}`
    : `All ${dealers.length || 24} locations`

  return (
    <div className="min-h-dvh bg-slate-950 text-slate-100">
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute inset-x-0 top-[-18rem] h-[32rem] bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.18),transparent_52%),radial-gradient(circle_at_20%_20%,rgba(99,102,241,0.22),transparent_28%)]" />
        <div className="absolute bottom-[-12rem] right-[-8rem] h-[24rem] w-[24rem] rounded-full bg-emerald-500/10 blur-3xl" />
      </div>

      <div className="relative flex min-h-dvh overflow-hidden">
        <Sidebar />
        <Sidebar mobile open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />

        <div className="relative flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b border-slate-800/80 bg-slate-950/85 px-4 py-3 backdrop-blur lg:hidden">
            <div className="flex items-start gap-3">
              <button onClick={() => setMobileNavOpen(true)} className="btn-secondary px-3 py-2">
                <Menu className="h-4 w-4" />
              </button>
              <div className="min-w-0 flex-1">
                <p className="text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-300/70">{routeMeta.title}</p>
                <h1 className="truncate text-base font-semibold text-white">{routeMeta.subtitle}</h1>
                <div className="mt-1 flex items-center gap-1 text-xs text-slate-400">
                  <MapPin className="h-3 w-3 text-brand-400" />
                  <span className="truncate">{dealerLabel}</span>
                </div>
              </div>
            </div>
          </header>

          <main className="flex-1 overflow-y-auto">
            <div className="lg:p-3">
              <div className="min-h-full border border-slate-800/70 bg-slate-950/55 shadow-[0_20px_80px_rgba(15,23,42,0.45)] backdrop-blur-xl lg:rounded-[28px]">
                <Suspense fallback={<RouteLoadingState />}>
                  <Routes>
                    <Route path="/" element={<Navigate to="/dashboard" replace />} />
                    <Route path="/find" element={<FindInventory />} />
                    <Route path="/dashboard" element={<Dashboard />} />
                    <Route path="/inventory" element={<Inventory />} />
                    <Route path="/activity" element={<Activity />} />
                    <Route path="/watchlist" element={<Watchlist />} />
                    <Route path="/leads" element={<Leads />} />
                    <Route path="/trade-ins" element={<TradeIns />} />
                  </Routes>
                </Suspense>
              </div>
            </div>
          </main>
        </div>
      </div>
    </div>
  )
}

function RouteLoadingState() {
  return (
    <div className="p-4 sm:p-6">
      <div className="animate-pulse space-y-6">
        <div className="h-8 w-56 rounded-full bg-slate-800" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {[...Array(4)].map((_, index) => (
            <div key={index} className="h-28 rounded-2xl bg-slate-900/80" />
          ))}
        </div>
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="h-72 rounded-2xl bg-slate-900/80 lg:col-span-2" />
          <div className="h-72 rounded-2xl bg-slate-900/80" />
        </div>
      </div>
    </div>
  )
}
