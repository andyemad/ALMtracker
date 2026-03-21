import { useState, useRef, useCallback, useEffect } from 'react'
import { getScrapeLogs } from '../api'

export function useScrapeStatus() {
  const [scraping, setScraping] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const baselineIdRef = useRef<number | null>(null)

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const startPolling = useCallback(() => {
    stopPolling()
    pollRef.current = setInterval(async () => {
      try {
        const logs = await getScrapeLogs()
        if (logs.length > 0) {
          const newest = logs[0]
          if (baselineIdRef.current === null || newest.id > baselineIdRef.current) {
            setScraping(false)
            stopPolling()
          }
        }
      } catch {
        // polling failure is silent — don't interrupt UX
      }
    }, 5000)
  }, [stopPolling])

  const triggerScraping = useCallback((baselineId: number | null) => {
    baselineIdRef.current = baselineId
    setScraping(true)
    startPolling()
  }, [startPolling])

  useEffect(() => () => { stopPolling() }, [stopPolling])

  return { scraping, triggerScraping }
}
