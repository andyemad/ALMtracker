import { useEffect, useState } from 'react'
import {
  Users, Plus, Search, Phone, Mail, DollarSign,
  Car, Edit2, X, Check, ExternalLink, ChevronRight
} from 'lucide-react'
import toast from 'react-hot-toast'
import { formatDistanceToNow } from 'date-fns'
import { getLeads, createLead, updateLead, deleteLead, getLeadMatches } from '../api'
import type { Lead, Vehicle } from '../types'
import { DeleteButton } from '../components/DeleteButton'
import { LocationChip } from '../components/LocationChip'

const STATUSES = ['new', 'contacted', 'hot', 'sold', 'lost'] as const
const STATUS_LABELS: Record<string, string> = {
  new: 'New Lead', contacted: 'Contacted', hot: 'Hot Lead', sold: 'Sold', lost: 'Lost',
}
const SOURCES = ['Walk-in', 'Phone', 'Internet', 'Referral', 'Social Media']

const EMPTY_FORM = {
  customer_name: '', customer_phone: '', customer_email: '',
  interested_make: '', interested_model: '', max_budget: '',
  notes: '', status: 'new' as Lead['status'], source: '',
}

export default function Leads() {
  const [leads, setLeads] = useState<Lead[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState<Lead | null>(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [expanded, setExpanded] = useState<number | null>(null)
  const [matches, setMatches] = useState<Record<number, Vehicle[]>>({})

  const load = () => {
    setLoading(true)
    getLeads({ status: filterStatus || undefined, search: search || undefined, page_size: 100 })
      .then(r => { setLeads(r.data); setTotal(r.total) })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [search, filterStatus])

  const openCreate = () => {
    setEditing(null); setForm(EMPTY_FORM); setShowForm(true)
  }

  const openEdit = (l: Lead) => {
    setEditing(l)
    setForm({
      customer_name: l.customer_name, customer_phone: l.customer_phone || '',
      customer_email: l.customer_email || '', interested_make: l.interested_make || '',
      interested_model: l.interested_model || '', max_budget: l.max_budget?.toString() || '',
      notes: l.notes || '', status: l.status, source: l.source || '',
    })
    setShowForm(true)
  }

  const handleSubmit = async () => {
    if (!form.customer_name.trim()) { toast.error('Customer name required'); return }
    const payload = {
      ...form,
      max_budget: form.max_budget ? +form.max_budget : null,
      customer_phone: form.customer_phone || null,
      customer_email: form.customer_email || null,
      interested_make: form.interested_make || null,
      interested_model: form.interested_model || null,
      source: form.source || null,
    }
    try {
      editing ? await updateLead(editing.id, payload) : await createLead(payload)
      toast.success(editing ? 'Lead updated' : 'Lead added')
      setShowForm(false); load()
    } catch { toast.error('Failed to save lead') }
  }

  const handleStatusChange = async (l: Lead, status: string) => {
    try {
      await updateLead(l.id, { status: status as Lead['status'] })
      load(); toast.success(`Moved to ${STATUS_LABELS[status]}`)
    } catch { toast.error('Failed to update') }
  }

  const handleDelete = async (id: number) => {
    try { await deleteLead(id); toast.success('Deleted'); load() }
    catch { toast.error('Failed to delete') }
  }

  const toggleExpand = async (id: number) => {
    if (expanded === id) { setExpanded(null); return }
    setExpanded(id)
    if (!matches[id]) {
      const m = await getLeadMatches(id)
      setMatches(prev => ({ ...prev, [id]: m }))
    }
  }

  const f = (k: keyof typeof EMPTY_FORM) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setForm(prev => ({ ...prev, [k]: e.target.value }))

  const statusCounts = STATUSES.reduce((acc, s) => {
    acc[s] = leads.filter(l => l.status === s).length; return acc
  }, {} as Record<string, number>)

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-4 sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[color:var(--ink)]">Leads</h1>
          <p className="text-[color:var(--muted)] text-sm mt-0.5">{total} customers · track every deal</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <LocationChip />
          <button onClick={openCreate} className="btn-primary">
            <Plus className="w-4 h-4" />
            Add Lead
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {STATUSES.map(s => (
          <button
            key={s}
            onClick={() => setFilterStatus(filterStatus === s ? '' : s)}
            className={`card p-3 text-left transition-all hover:border-slate-600 ${
              filterStatus === s ? 'ring-1 ring-brand-500 border-brand-500/50' : ''
            }`}
          >
            <div className="text-xl font-bold text-[color:var(--ink)]">{statusCounts[s]}</div>
            <div className={`text-xs mt-0.5 font-medium px-1.5 py-0.5 rounded-full border inline-block
              status-${s}`}>{STATUS_LABELS[s]}</div>
          </button>
        ))}
      </div>

      {/* Search */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[color:var(--muted)]" />
          <input
            className="input pl-9"
            placeholder="Search by name, phone, email..."
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
        {filterStatus && (
          <button onClick={() => setFilterStatus('')} className="btn-secondary">
            <X className="w-3.5 h-3.5" />
            Clear filter
          </button>
        )}
      </div>

      {/* Form */}
      {showForm && (
        <div className="card p-6 border-brand-600/30">
          <div className="flex items-center justify-between mb-5">
            <h2 className="font-semibold text-[color:var(--ink)]">{editing ? 'Edit Lead' : 'New Lead'}</h2>
            <button onClick={() => setShowForm(false)} className="btn-ghost p-1.5">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-[color:var(--muted)] mb-1.5">Customer Name *</label>
              <input className="input" placeholder="John Smith" value={form.customer_name} onChange={f('customer_name')} />
            </div>
            <div>
              <label className="block text-xs text-[color:var(--muted)] mb-1.5">Phone</label>
              <input className="input" type="tel" placeholder="(555) 123-4567" value={form.customer_phone} onChange={f('customer_phone')} />
            </div>
            <div>
              <label className="block text-xs text-[color:var(--muted)] mb-1.5">Email</label>
              <input className="input" type="email" value={form.customer_email} onChange={f('customer_email')} />
            </div>
            <div>
              <label className="block text-xs text-[color:var(--muted)] mb-1.5">Source</label>
              <select className="select" value={form.source} onChange={f('source')}>
                <option value="">Select source</option>
                {SOURCES.map(s => <option key={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs text-[color:var(--muted)] mb-1.5">Interested In — Make</label>
              <input className="input" placeholder="e.g. Toyota" value={form.interested_make} onChange={f('interested_make')} />
            </div>
            <div>
              <label className="block text-xs text-[color:var(--muted)] mb-1.5">Model</label>
              <input className="input" placeholder="e.g. Camry" value={form.interested_model} onChange={f('interested_model')} />
            </div>
            <div>
              <label className="block text-xs text-[color:var(--muted)] mb-1.5">Max Budget ($)</label>
              <input className="input" type="number" placeholder="20000" value={form.max_budget} onChange={f('max_budget')} />
            </div>
            <div>
              <label className="block text-xs text-[color:var(--muted)] mb-1.5">Status</label>
              <select className="select" value={form.status} onChange={f('status')}>
                {STATUSES.map(s => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
              </select>
            </div>
            <div className="sm:col-span-2">
              <label className="block text-xs text-[color:var(--muted)] mb-1.5">Notes</label>
              <textarea
                className="input h-20 resize-none"
                placeholder="Customer preferences, notes from conversation..."
                value={form.notes}
                onChange={f('notes')}
              />
            </div>
          </div>
          <div className="flex justify-end gap-3 mt-5">
            <button onClick={() => setShowForm(false)} className="btn-secondary">Cancel</button>
            <button onClick={handleSubmit} className="btn-primary">
              <Check className="w-4 h-4" />
              {editing ? 'Save' : 'Add Lead'}
            </button>
          </div>
        </div>
      )}

      {/* Leads List */}
      {loading ? (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="card p-5 h-20 animate-pulse" />
          ))}
        </div>
      ) : leads.length === 0 ? (
        <div className="card p-16 text-center">
          <Users className="w-10 h-10 text-slate-700 mx-auto mb-3" />
          <p className="text-[color:var(--muted)]">No leads yet. Add your first customer.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {leads.map(l => (
            <div key={l.id} className="card overflow-hidden">
              {/* Lead Row */}
              <div className="p-4 flex items-start gap-4">
                {/* Avatar */}
                <div className="w-9 h-9 rounded-full bg-[color:var(--hairline)] flex items-center justify-center flex-shrink-0 text-sm font-semibold text-[color:var(--ink-2)]">
                  {l.customer_name.charAt(0).toUpperCase()}
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-[color:var(--ink)]">{l.customer_name}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-full border font-medium status-${l.status}`}>
                      {STATUS_LABELS[l.status]}
                    </span>
                    {l.source && (
                      <span className="text-xs text-[color:var(--muted)] bg-[color:var(--bg-2)] px-2 py-0.5 rounded-full">
                        {l.source}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-4 mt-1.5 text-xs text-[color:var(--muted)] flex-wrap">
                    {l.customer_phone && (
                      <a href={`tel:${l.customer_phone}`} className="flex items-center gap-1 hover:text-[color:var(--ink)]">
                        <Phone className="w-3 h-3" />{l.customer_phone}
                      </a>
                    )}
                    {l.customer_email && (
                      <a href={`mailto:${l.customer_email}`} className="flex items-center gap-1 hover:text-[color:var(--ink)]">
                        <Mail className="w-3 h-3" />{l.customer_email}
                      </a>
                    )}
                    {(l.interested_make || l.interested_model) && (
                      <span className="flex items-center gap-1 text-[color:var(--ink-2)]">
                        <Car className="w-3 h-3" />
                        {[l.interested_make, l.interested_model].filter(Boolean).join(' ')}
                      </span>
                    )}
                    {l.max_budget && (
                      <span className="flex items-center gap-1">
                        <DollarSign className="w-3 h-3" />
                        Budget: ${l.max_budget.toLocaleString()}
                      </span>
                    )}
                    <span className="text-[color:var(--muted)]">
                      Added {formatDistanceToNow(new Date(l.created_at + 'Z'), { addSuffix: true })}
                    </span>
                  </div>
                  {l.notes && (
                    <p className="text-xs text-[color:var(--muted)] mt-1.5 truncate">{l.notes}</p>
                  )}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1 flex-shrink-0">
                  {/* Quick status change */}
                  <select
                    className="text-xs bg-[color:var(--card)] border border-[color:var(--hairline-2)] text-[color:var(--ink-2)] rounded-lg px-2 py-1 cursor-pointer"
                    value={l.status}
                    onChange={e => handleStatusChange(l, e.target.value)}
                    onClick={e => e.stopPropagation()}
                  >
                    {STATUSES.map(s => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
                  </select>
                  <button onClick={() => openEdit(l)} className="btn-ghost p-1.5">
                    <Edit2 className="w-3.5 h-3.5" />
                  </button>
                  <button onClick={() => toggleExpand(l.id)} className="btn-ghost p-1.5" title="Show matching cars">
                    <ChevronRight className={`w-3.5 h-3.5 transition-transform ${expanded === l.id ? 'rotate-90' : ''}`} />
                  </button>
                  <DeleteButton onConfirm={() => handleDelete(l.id)} />
                </div>
              </div>

              {/* Matching Inventory */}
              {expanded === l.id && (
                <div className="border-t border-[color:var(--hairline-2)] bg-[color:var(--card)] p-4">
                  <p className="text-xs font-semibold text-[color:var(--muted)] mb-3">
                    Matching inventory for this lead:
                  </p>
                  {!matches[l.id] ? (
                    <p className="text-xs text-[color:var(--muted)] animate-pulse">Loading...</p>
                  ) : matches[l.id].length === 0 ? (
                    <p className="text-xs text-[color:var(--muted)]">No matching vehicles currently in inventory.</p>
                  ) : (
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
                      {matches[l.id].map(v => (
                        <a
                          key={v.id}
                          href={v.listing_url || '#'}
                          target="_blank"
                          rel="noreferrer"
                          className="flex items-center gap-3 bg-[color:var(--bg-2)] rounded-lg p-3 hover:bg-[color:var(--hairline)] transition-colors group"
                        >
                          {v.image_url && (
                            <img src={v.image_url} alt="" className="w-14 h-10 object-cover rounded flex-shrink-0" />
                          )}
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-semibold text-[color:var(--ink)] truncate">
                              {v.year} {v.make} {v.model}
                            </p>
                            <p className="text-xs text-[color:var(--positive)] font-semibold">
                              {v.price ? `$${v.price.toLocaleString()}` : 'N/A'}
                            </p>
                            <p className="text-[11px] text-[color:var(--muted)]">
                              {v.mileage ? `${v.mileage.toLocaleString()} mi` : ''} · Stock #{v.stock_number}
                            </p>
                          </div>
                          <ExternalLink className="w-3 h-3 text-[color:var(--muted)] group-hover:text-[color:var(--muted)] flex-shrink-0" />
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
