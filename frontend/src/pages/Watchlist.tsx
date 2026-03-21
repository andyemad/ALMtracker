import { useEffect, useState } from 'react'
import { Bell, Plus, Car, ToggleLeft, ToggleRight, Edit2, X, Check, Trash2 } from 'lucide-react'
import toast from 'react-hot-toast'
import { getWatchlist, createWatchlist, updateWatchlist, deleteWatchlist } from '../api'
import type { WatchlistAlert } from '../types'
import { DeleteButton } from '../components/DeleteButton'
import { Link } from 'react-router-dom'
import { useDealer } from '../context/DealerContext'
import { LocationChip } from '../components/LocationChip'

const EMPTY_FORM = {
  name: '', make: '', model: '',
  max_price: '', min_price: '',
  max_mileage: '', min_year: '', max_year: '',
  condition: '', notification_email: '',
}

export default function Watchlist() {
  const { selectedDealer } = useDealer()
  const dealerId = selectedDealer?.id

  const [alerts, setAlerts] = useState<WatchlistAlert[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<WatchlistAlert | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)

  const load = () => {
    setLoading(true)
    getWatchlist(dealerId).then(setAlerts).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [dealerId])

  const openCreate = () => {
    setEditing(null)
    setForm(EMPTY_FORM)
    setShowForm(true)
  }

  const openEdit = (a: WatchlistAlert) => {
    setEditing(a)
    setForm({
      name: a.name,
      make: a.make || '',
      model: a.model || '',
      max_price: a.max_price?.toString() || '',
      min_price: a.min_price?.toString() || '',
      max_mileage: a.max_mileage?.toString() || '',
      min_year: a.min_year?.toString() || '',
      max_year: a.max_year?.toString() || '',
      condition: a.condition || '',
      notification_email: a.notification_email || '',
    })
    setShowForm(true)
  }

  const handleSubmit = async () => {
    if (!form.name.trim()) { toast.error('Name is required'); return }
    const payload = {
      name: form.name,
      make: form.make || null,
      model: form.model || null,
      max_price: form.max_price ? +form.max_price : null,
      min_price: form.min_price ? +form.min_price : null,
      max_mileage: form.max_mileage ? +form.max_mileage : null,
      min_year: form.min_year ? +form.min_year : null,
      max_year: form.max_year ? +form.max_year : null,
      condition: form.condition || null,
      notification_email: form.notification_email || null,
      dealer_id: dealerId ?? null,
    }
    try {
      if (editing) {
        await updateWatchlist(editing.id, payload)
        toast.success('Alert updated')
      } else {
        await createWatchlist(payload)
        toast.success('Alert created')
      }
      setShowForm(false)
      load()
    } catch {
      toast.error('Failed to save alert')
    }
  }

  const handleToggle = async (a: WatchlistAlert) => {
    try {
      await updateWatchlist(a.id, { is_active: !a.is_active })
      load()
    } catch {
      toast.error('Failed to toggle alert')
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await deleteWatchlist(id)
      toast.success('Alert deleted')
      load()
    } catch {
      toast.error('Failed to delete')
    }
  }

  const f = (k: keyof typeof EMPTY_FORM) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(prev => ({ ...prev, [k]: e.target.value }))

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4 sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Watchlist</h1>
          <p className="text-slate-400 text-sm mt-0.5">
            Get notified when matching vehicles arrive
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <LocationChip />
          <button onClick={openCreate} className="btn-primary">
            <Plus className="w-4 h-4" />
            New Alert
          </button>
        </div>
      </div>

      {/* Example hint */}
      <div className="card p-4 border-dashed flex items-start gap-3">
        <Bell className="w-4 h-4 text-brand-400 mt-0.5 flex-shrink-0" />
        <p className="text-sm text-slate-400">
          Example: <span className="text-slate-200">Tesla Model Y</span> under{' '}
          <span className="text-slate-200">$25,000</span> with less than{' '}
          <span className="text-slate-200">50,000 miles</span> — set it and get alerted the moment it lands.
        </p>
      </div>

      {/* Create/Edit Form */}
      {showForm && (
        <div className="card p-6 border-brand-600/30">
          <div className="flex items-center justify-between mb-5">
            <h2 className="text-base font-semibold text-white">
              {editing ? 'Edit Alert' : 'Create Alert'}
            </h2>
            <button onClick={() => setShowForm(false)} className="btn-ghost p-1.5">
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="sm:col-span-2">
              <label className="block text-xs text-slate-400 mb-1.5">Alert Name *</label>
              <input className="input" placeholder="e.g. Tesla Model Y Deal" value={form.name} onChange={f('name')} />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Make</label>
              <input className="input" placeholder="e.g. Tesla" value={form.make} onChange={f('make')} />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Model</label>
              <input className="input" placeholder="e.g. Model Y" value={form.model} onChange={f('model')} />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Min Price ($)</label>
              <input className="input" type="number" placeholder="0" value={form.min_price} onChange={f('min_price')} />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Max Price ($)</label>
              <input className="input" type="number" placeholder="25000" value={form.max_price} onChange={f('max_price')} />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Max Mileage</label>
              <input className="input" type="number" placeholder="50000" value={form.max_mileage} onChange={f('max_mileage')} />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Condition</label>
              <select className="select" value={form.condition} onChange={f('condition')}>
                <option value="">Any</option>
                <option value="new">New</option>
                <option value="used">Used</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Min Year</label>
              <input className="input" type="number" placeholder="2020" value={form.min_year} onChange={f('min_year')} />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Max Year</label>
              <input className="input" type="number" placeholder="2025" value={form.max_year} onChange={f('max_year')} />
            </div>
            <div className="sm:col-span-2">
              <label className="block text-xs text-slate-400 mb-1.5">
                Email Notification <span className="text-slate-600">(optional — configure SMTP in .env)</span>
              </label>
              <input className="input" type="email" placeholder="you@example.com" value={form.notification_email} onChange={f('notification_email')} />
            </div>
            <div className="sm:col-span-2">
              <label className="block text-xs text-slate-400 mb-1.5">Location Scope</label>
              <div className="text-xs text-slate-300 px-3 py-2 bg-slate-900 border border-slate-700 rounded-lg">
                {selectedDealer ? `Scoped to: ${selectedDealer.name}` : 'All Locations (no dealer filter)'}
              </div>
              <p className="text-[11px] text-slate-500 mt-1">
                Switch location in the sidebar to scope this alert to a specific store.
              </p>
            </div>
          </div>

          <div className="flex justify-end gap-3 mt-5">
            <button onClick={() => setShowForm(false)} className="btn-secondary">Cancel</button>
            <button onClick={handleSubmit} className="btn-primary">
              <Check className="w-4 h-4" />
              {editing ? 'Save Changes' : 'Create Alert'}
            </button>
          </div>
        </div>
      )}

      {/* Alert List */}
      {loading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="card p-5 animate-pulse h-24" />
          ))}
        </div>
      ) : alerts.length === 0 ? (
        <div className="card p-16 text-center">
          <Bell className="w-10 h-10 text-slate-700 mx-auto mb-3" />
          <p className="text-slate-500">No alerts yet. Create one to monitor for specific vehicles.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {alerts.map(a => (
            <AlertCard
              key={a.id}
              alert={a}
              onToggle={() => handleToggle(a)}
              onEdit={() => openEdit(a)}
              onDelete={() => handleDelete(a.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function AlertCard({ alert: a, onToggle, onEdit, onDelete }: {
  alert: WatchlistAlert
  onToggle: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  const criteria = [
    a.make && a.model ? `${a.make} ${a.model}` : a.make || a.model,
    a.max_price && `Under $${a.max_price.toLocaleString()}`,
    a.min_price && `Over $${a.min_price.toLocaleString()}`,
    a.max_mileage && `Under ${a.max_mileage.toLocaleString()} mi`,
    a.min_year && a.max_year ? `${a.min_year}–${a.max_year}` : a.min_year ? `${a.min_year}+` : null,
    a.condition && a.condition.charAt(0).toUpperCase() + a.condition.slice(1),
  ].filter(Boolean)

  return (
    <div className={`card p-5 flex items-start gap-4 transition-all ${
      !a.is_active ? 'opacity-50' : ''
    }`}>
      {/* Icon */}
      <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${
        a.is_active ? 'bg-brand-600/20' : 'bg-slate-700'
      }`}>
        <Bell className={`w-5 h-5 ${a.is_active ? 'text-brand-400' : 'text-slate-500'}`} />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <h3 className="font-semibold text-white">{a.name}</h3>
          {a.match_count > 0 && (() => {
            const params = new URLSearchParams()
            if (a.make) params.set('make', a.make)
            if (a.model) params.set('model', a.model)
            return (
              <Link
                to={`/inventory?${params.toString()}`}
                onClick={e => e.stopPropagation()}
                className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400
                           border border-emerald-500/30 flex items-center gap-1
                           hover:bg-emerald-500/25 transition-colors"
              >
                <Car className="w-3 h-3" />
                {a.match_count} match{a.match_count !== 1 ? 'es' : ''} in inventory
              </Link>
            )
          })()}
        </div>

        {criteria.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {criteria.map((c, i) => (
              <span key={i} className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">
                {c}
              </span>
            ))}
          </div>
        )}

        <div className="flex items-center gap-4 mt-2 text-[11px] text-slate-500">
          {a.notification_email && (
            <span>Email: {a.notification_email}</span>
          )}
          {a.trigger_count > 0 && (
            <span>Triggered {a.trigger_count}x</span>
          )}
          {a.last_triggered && (
            <span>Last: {new Date(a.last_triggered + 'Z').toLocaleDateString()}</span>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 flex-shrink-0">
        <button onClick={onEdit} className="btn-ghost p-1.5" title="Edit">
          <Edit2 className="w-3.5 h-3.5" />
        </button>
        <button onClick={onToggle} className="btn-ghost p-1.5" title={a.is_active ? 'Disable' : 'Enable'}>
          {a.is_active
            ? <ToggleRight className="w-4 h-4 text-emerald-400" />
            : <ToggleLeft className="w-4 h-4 text-slate-500" />}
        </button>
        <DeleteButton onConfirm={onDelete} />
      </div>
    </div>
  )
}
