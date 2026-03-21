import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { getDealers } from '../api'
import type { Dealer } from '../types'

const STORAGE_KEY = 'alm:selectedDealerId'

interface DealerContextValue {
  dealers: Dealer[]
  selectedDealer: Dealer | null   // null = all locations
  setSelectedDealer: (d: Dealer | null) => void
  loading: boolean
}

const DealerContext = createContext<DealerContextValue | null>(null)

export function DealerProvider({ children }: { children: ReactNode }) {
  const [dealers, setDealers] = useState<Dealer[]>([])
  const [selectedDealerId, setSelectedDealerId] = useState<number | null>(() => {
    if (typeof window === 'undefined') return null
    const saved = window.localStorage.getItem(STORAGE_KEY)
    if (!saved) return null
    const parsed = Number(saved)
    return Number.isFinite(parsed) ? parsed : null
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getDealers().then(setDealers).finally(() => setLoading(false))
  }, [])

  const selectedDealer = dealers.find(dealer => dealer.id === selectedDealerId) ?? null

  const handleSetSelectedDealer = (dealer: Dealer | null) => {
    const nextId = dealer?.id ?? null
    setSelectedDealerId(nextId)

    if (typeof window === 'undefined') return
    if (nextId == null) {
      window.localStorage.removeItem(STORAGE_KEY)
      return
    }
    window.localStorage.setItem(STORAGE_KEY, String(nextId))
  }

  return (
    <DealerContext.Provider value={{ dealers, selectedDealer, setSelectedDealer: handleSetSelectedDealer, loading }}>
      {children}
    </DealerContext.Provider>
  )
}

export function useDealer() {
  const ctx = useContext(DealerContext)
  if (!ctx) throw new Error('useDealer must be used inside DealerProvider')
  return ctx
}
