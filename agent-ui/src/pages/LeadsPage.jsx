import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'
import {
  Users, Plus, Search, Download, Loader2, Phone, Mail,
  User, Filter, ArrowUpDown, Trash2, MoreHorizontal, Upload,
  Star, StarOff, Target, CheckCircle2, XCircle, Clock,
  TrendingUp, BarChart3
} from 'lucide-react'
import { toast } from 'sonner'

const STATUSES = ['new', 'contacted', 'qualified', 'converted', 'lost']
const STATUS_COLORS = {
  new: 'badge-slate', contacted: 'badge-amber',
  qualified: 'badge-green', converted: 'bg-call-green-soft text-call-green font-medium px-2 py-0.5 text-xs rounded-full',
  lost: 'badge-red',
}

export default function LeadsPage() {
  const { tenant } = useAuth()
  const navigate = useNavigate()
  const [leads, setLeads] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const [sortField, setSortField] = useState('created_at')
  const [sortDir, setSortDir] = useState('desc')
  const [selected, setSelected] = useState([])
  const [page, setPage] = useState(0)
  const pageSize = 25

  const fetchLeads = useCallback(async () => {
    if (!tenant) return
    setLoading(true)
    try {
      const params = { tenant_id: tenant.id, limit: pageSize, offset: page * pageSize }
      if (statusFilter !== 'all') params.status = statusFilter
      if (search) params.search = search
      const res = await api.get('/leads', { params })
      setLeads(Array.isArray(res.data) ? res.data : [])
    } catch { setLeads([]) }
    finally { setLoading(false) }
  }, [tenant, page, statusFilter, search])

  useEffect(() => { fetchLeads() }, [fetchLeads])

  const filtered = leads.filter(l => {
    if (search) {
      const q = search.toLowerCase()
      if (!(l.name?.toLowerCase().includes(q) || l.phone?.includes(q) || l.email?.toLowerCase().includes(q))) return false
    }
    if (statusFilter !== 'all' && l.status !== statusFilter) return false
    return true
  })

  const toggleSort = (field) => {
    if (sortField === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortField(field); setSortDir('asc') }
  }

  const sorted = [...filtered].sort((a, b) => {
    const aVal = a[sortField] || '', bVal = b[sortField] || ''
    return sortDir === 'asc' ? String(aVal).localeCompare(String(bVal)) : String(bVal).localeCompare(String(aVal))
  })

  const toggleSelect = (id) => {
    setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }

  const toggleAll = () => {
    if (selected.length === sorted.length) setSelected([])
    else setSelected(sorted.map(l => l.id))
  }

  const updateStatus = async (leadId, status) => {
    try {
      await api.put(`/leads/${leadId}`, { status })
      toast.success(`Lead marked as ${status}`)
      fetchLeads()
    } catch { toast.error('Failed to update') }
  }

  const deleteSelected = async () => {
    if (!window.confirm(`Delete ${selected.length} leads?`)) return
    try {
      await Promise.all(selected.map(id => api.delete(`/leads/${id}`)))
      toast.success(`${selected.length} leads deleted`)
      setSelected([])
      fetchLeads()
    } catch { toast.error('Failed to delete') }
  }

  const formatPhone = (phone) => {
    if (!phone) return '-'
    const c = phone.replace(/\D/g, '')
    if (c.length === 11) return `+1 (${c.slice(1,4)}) ${c.slice(4,7)}-${c.slice(7)}`
    if (c.length === 10) return `(${c.slice(0,3)}) ${c.slice(3,6)}-${c.slice(6)}`
    return phone
  }

  const scoreToStars = (score) => {
    if (!score) return []
    const stars = []
    for (let i = 0; i < 5; i++) stars.push(i < score / 20)
    return stars
  }

  const stats = {
    total: leads.length,
    converted: leads.filter(l => l.status === 'converted').length,
    qualified: leads.filter(l => l.status === 'qualified').length,
    new: leads.filter(l => l.status === 'new' || !l.status).length,
  }

  return (
    <div className="p-6 max-w-7xl mx-auto animate-slide-up">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Leads</h1>
          <p className="text-sm text-ink-muted mt-0.5">Manage your leads and track conversion</p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => navigate('/leads/import')} className="btn-secondary">
            <Upload className="h-4 w-4" />
            Import
          </button>
          <button onClick={() => navigate('/leads/import')} className="btn-primary">
            <Plus className="h-4 w-4" />
            Add Lead
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-ink tabular-nums">{stats.total}</p>
          <p className="text-xs text-ink-muted">Total Leads</p>
        </div>
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-call-green tabular-nums">{stats.converted}</p>
          <p className="text-xs text-ink-muted">Converted</p>
        </div>
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-accent tabular-nums">{stats.qualified}</p>
          <p className="text-xs text-ink-muted">Qualified</p>
        </div>
        <div className="card p-4 text-center">
          <p className="text-2xl font-bold text-call-amber tabular-nums">{stats.new}</p>
          <p className="text-xs text-ink-muted">New</p>
        </div>
      </div>

      {/* Filters */}
      <div className="card p-4 mb-4">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-subtle" />
            <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
              className="input-field pl-9" placeholder="Search by name, phone, email..." />
          </div>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}
            className="input-field w-auto min-w-[140px]">
            <option value="all">All Statuses</option>
            {STATUSES.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
          </select>
          {selected.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-sm text-ink-muted">{selected.length} selected</span>
              <button onClick={deleteSelected} className="btn-ghost text-call-red">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="card p-12 text-center"><Loader2 className="h-6 w-6 animate-spin mx-auto text-ink-subtle" /></div>
      ) : sorted.length === 0 ? (
        <div className="card p-12 text-center">
          <Users className="h-10 w-10 mx-auto text-ink-subtle mb-3" />
          <p className="text-sm text-ink-muted">No leads found</p>
          <button onClick={() => navigate('/leads/import')} className="btn-primary mt-4">
            <Upload className="h-4 w-4" /> Import Leads
          </button>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-hairline bg-surface-hover">
                  <th className="w-10 px-4 py-3">
                    <input type="checkbox" checked={selected.length === sorted.length && sorted.length > 0}
                      onChange={toggleAll} className="rounded border-hairline" />
                  </th>
                  <th className="text-left px-4 py-3 cursor-pointer" onClick={() => toggleSort('name')}>
                    <div className="flex items-center gap-1 text-xs font-semibold text-ink-muted uppercase tracking-wider">
                      Name <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-ink-muted uppercase tracking-wider">Contact</th>
                  <th className="text-left px-4 py-3 cursor-pointer" onClick={() => toggleSort('status')}>
                    <div className="flex items-center gap-1 text-xs font-semibold text-ink-muted uppercase tracking-wider">
                      Status <ArrowUpDown className="h-3 w-3" />
                    </div>
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-semibold text-ink-muted uppercase tracking-wider">Score</th>
                  <th className="text-right px-4 py-3 text-xs font-semibold text-ink-muted uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {sorted.map((lead) => (
                  <tr key={lead.id} className={`hover:bg-surface-hover transition-colors ${selected.includes(lead.id) ? 'bg-accent-soft/50' : ''}`}>
                    <td className="px-4 py-3">
                      <input type="checkbox" checked={selected.includes(lead.id)}
                        onChange={() => toggleSelect(lead.id)} className="rounded border-hairline" />
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-full bg-accent-soft flex items-center justify-center">
                          <span className="text-accent text-xs font-semibold">{lead.name?.[0] || '?'}</span>
                        </div>
                        <span className="text-sm font-medium text-ink">{lead.name || 'Unnamed'}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="space-y-0.5">
                        <p className="text-sm text-ink-muted flex items-center gap-1">
                          <Phone className="h-3 w-3" /> {formatPhone(lead.phone)}
                        </p>
                        {lead.email && <p className="text-xs text-ink-subtle flex items-center gap-1">
                          <Mail className="h-3 w-3" /> {lead.email}
                        </p>}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <select value={lead.status || 'new'} onChange={(e) => updateStatus(lead.id, e.target.value)}
                        className={`text-xs font-medium rounded-full px-2 py-0.5 border-0 ${STATUS_COLORS[lead.status] || 'badge-slate'}`}>
                        {STATUSES.map(s => <option key={s} value={s}>{s.charAt(0).toUpperCase() + s.slice(1)}</option>)}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-0.5">
                        {scoreToStars(lead.score || 0).map((filled, i) => (
                          filled ? <Star key={i} className="h-3.5 w-3.5 text-call-amber fill-call-amber" />
                            : <StarOff key={i} className="h-3.5 w-3.5 text-ink-subtle" />
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => navigator.clipboard.writeText(lead.phone || '')}
                          className="btn-ghost p-1.5" title="Copy phone">
                          <Phone className="h-3.5 w-3.5" />
                        </button>
                        <button onClick={() => updateStatus(lead.id, lead.status === 'converted' ? 'new' : 'converted')}
                          className="btn-ghost p-1.5" title="Toggle converted">
                          {lead.status === 'converted' ? <XCircle className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Pagination */}
          <div className="px-4 py-3 border-t border-hairline flex items-center justify-between">
            <span className="text-xs text-ink-muted">{sorted.length} leads</span>
            <div className="flex items-center gap-2">
              <button onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}
                className="btn-ghost text-xs px-3 py-1.5">Previous</button>
              <span className="text-xs text-ink-muted">Page {page + 1}</span>
              <button onClick={() => setPage(p => p + 1)} disabled={sorted.length < pageSize}
                className="btn-ghost text-xs px-3 py-1.5">Next</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
