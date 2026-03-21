import { createContext, useContext, type ReactNode } from 'react'
import { useScrapeStatus } from '../hooks/useScrapeStatus'

interface ScrapeContextValue {
  scraping: boolean
  triggerScraping: (baselineId: number | null) => void
}

const ScrapeContext = createContext<ScrapeContextValue | null>(null)

export function ScrapeProvider({ children }: { children: ReactNode }) {
  const { scraping, triggerScraping } = useScrapeStatus()
  return (
    <ScrapeContext.Provider value={{ scraping, triggerScraping }}>
      {children}
    </ScrapeContext.Provider>
  )
}

export function useScrape() {
  const ctx = useContext(ScrapeContext)
  if (!ctx) throw new Error('useScrape must be inside ScrapeProvider')
  return ctx
}
