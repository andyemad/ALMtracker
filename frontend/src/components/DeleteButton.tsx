import { useState, useRef, useEffect } from 'react'
import { Trash2 } from 'lucide-react'

interface DeleteButtonProps {
  onConfirm: () => void
  confirmLabel?: string
  timeoutMs?: number
}

export function DeleteButton({
  onConfirm,
  confirmLabel = 'Confirm?',
  timeoutMs = 3000,
}: DeleteButtonProps) {
  const [confirming, setConfirming] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearTimer = () => {
    if (timerRef.current) clearTimeout(timerRef.current)
  }

  const handleFirstClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    clearTimer()
    setConfirming(true)
    timerRef.current = setTimeout(() => setConfirming(false), timeoutMs)
  }

  const handleConfirm = (e: React.MouseEvent) => {
    e.stopPropagation()
    clearTimer()
    setConfirming(false)
    onConfirm()
  }

  const handleCancel = (e: React.MouseEvent) => {
    e.stopPropagation()
    clearTimer()
    setConfirming(false)
  }

  useEffect(() => () => clearTimer(), [])

  if (confirming) {
    return (
      <button
        onClick={handleConfirm}
        onBlur={handleCancel as unknown as React.FocusEventHandler<HTMLButtonElement>}
        className="btn-delete-confirm"
        autoFocus
        aria-label="Confirm delete"
      >
        <Trash2 className="w-3.5 h-3.5" />
        {confirmLabel}
      </button>
    )
  }

  return (
    <button
      onClick={handleFirstClick}
      className="btn-ghost p-1.5 hover:text-red-400"
      title="Delete"
      aria-label="Delete"
    >
      <Trash2 className="w-3.5 h-3.5" />
    </button>
  )
}
