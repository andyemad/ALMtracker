import { MapPin } from 'lucide-react'
import { useDealer } from '../context/DealerContext'

interface LocationChipProps {
  className?: string
}

export function LocationChip({ className = '' }: LocationChipProps) {
  const { selectedDealer } = useDealer()

  if (selectedDealer) {
    return (
      <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1
                        rounded-full border bg-brand-600/15 text-brand-400 border-brand-600/30 ${className}`}>
        <MapPin className="w-3 h-3" />
        {selectedDealer.name}
      </span>
    )
  }

  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1
                      rounded-full border bg-slate-700/50 text-slate-400 border-slate-600/50 ${className}`}>
      <MapPin className="w-3 h-3" />
      All Locations
    </span>
  )
}
