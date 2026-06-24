import React, { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import api from '../services/api'
import { PhoneIncoming, PhoneOutgoing, Clock, Filter, Loader2, PhoneMissed } from 'lucide-react'

export default function CallLogs() {
  const { tenant } = useAuth()
  const [calls, setCalls] = useState([])
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState({ status: 'all', dateFrom: '', dateTo: '' })

  useEffect(() => { if (tenant) fetchCalls() }, [tenant, filters])

  const fetchCalls = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ tenant_id: tenant.id })
      if (filters.status !== 'all') params.append('status', filters.status)
      const res = await api.get(`/calls?${params}`)
      setCalls(Array.isArray(res.data) ? res.data : [])
    } catch (e) { console.error(e); setCalls([]) }
    finally { setLoading(false) }
  }

  const getIcon = (dir) => {
    if (dir === 'inbound') return <PhoneIncoming className="h-4 w-4 text-call-green" />
    if (dir === 'outbound') return <PhoneOutgoing className="h-4 w-4 text-accent" />
    return <PhoneMissed className="h-4 w-4 text-call-red" />
  }
  const getBg = (dir) => {
    if (dir === 'inbound') return 'bg-call-green-soft'
    if (dir === 'outbound') return 'bg-accent-soft'
    return 'bg-call-red-soft'
  }

  const statusOptions = ['all', 'completed', 'active', 'missed', 'failed', 'voicemail', 'initiated']

  const statusBadge = (status) => {
    switch (status) {
      case 'completed': return <span className="badge-green">Completed</span>
      case 'active': case 'ringing': case 'initiated': return <span className="badge-amber">{status}</span>
      case 'missed': return <span className="badge-red">Missed</span>
      case 'failed': return <span className="badge-red">Failed</span>
      case 'voicemail': return <span className="badge-slate">Voicemail</span>
      default: return <span className="badge-slate">{status || 'Unknown'}</span>
    }
  }

  const fmtNum = (num) => {
    if (!num) return '-'
    const c = num.replace(/\D/g, '')
    if (c.length === 11) return `+1 (${c.slice(1,4)}) ${c.slice(4,7)}-${c.slice(7)}`
    if (c.length === 10) return `(${c.slice(0,3)}) ${c.slice(3,6)}-${c.slice(6)}`
    return num
  }

  const fmtDur = (s) => {
    if (!s || s === 0) return '-'
    const m = Math.floor(s / 60); const sec = Math.floor(s % 60)
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Call Logs</h1>
          <p className="text-sm text-ink-muted mt-0.5">View and manage all call records</p>
        </div>
      </div>

      {/* Filters */}
      <div className="card p-4 mb-6">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-ink-muted" />
            <span className="text-sm text-ink-muted font-medium">Filters</span>
          </div>
          <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}
            className="input-field w-auto min-w-[140px] text-sm">
            {statusOptions.map((s) => (
              <option key={s} value={s}>{s === 'all' ? 'All Statuses' : s.charAt(0).toUpperCase() + s.slice(1)}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="card p-12 text-center">
          <Loader2 className="h-6 w-6 animate-spin mx-auto text-ink-subtle mb-2" />
          <p className="text-sm text-ink-muted">Loading calls...</p>
        </div>
      ) : calls.length === 0 ? (
        <div className="card p-12 text-center">
          <PhoneIncoming className="h-10 w-10 mx-auto text-ink-subtle mb-3" />
          <p className="text-sm text-ink-muted">No calls found</p>
          <p className="text-xs text-ink-subtle mt-1">Try adjusting your filters</p>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-hairline bg-surface-hover">
                  <th className="text-left px-5 py-3 text-xs font-semibold text-ink-muted uppercase tracking-wider">Direction</th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-ink-muted uppercase tracking-wider">From</th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-ink-muted uppercase tracking-wider">To</th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-ink-muted uppercase tracking-wider">Agent</th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-ink-muted uppercase tracking-wider">Duration</th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-ink-muted uppercase tracking-wider">Intent</th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-ink-muted uppercase tracking-wider">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {calls.map((call, idx) => (
                  <tr key={call.id || idx} className="hover:bg-surface-hover transition-colors">
                    <td className="px-5 py-4">
                      <div className={`p-2 rounded-lg ${getBg(call.call_direction || call.direction)} inline-flex`}>
                        {getIcon(call.call_direction || call.direction)}
                      </div>
                    </td>
                    <td className="px-5 py-4 text-sm font-medium text-ink">{fmtNum(call.caller_number || call.from)}</td>
                    <td className="px-5 py-4 text-sm text-ink-muted">{fmtNum(call.called_number || call.to)}</td>
                    <td className="px-5 py-4 text-sm text-ink-muted">
                      {call.agent_id ? `Agent ${call.agent_id.slice(0, 6)}` : '-'}
                    </td>
                    <td className="px-5 py-4 text-sm text-ink-muted flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {fmtDur(call.duration_seconds || call.duration)}
                    </td>
                    <td className="px-5 py-4">
                      <span className="badge-slate text-[11px]">{call.intent_detected || call.intent || 'N/A'}</span>
                    </td>
                    <td className="px-5 py-4">{statusBadge(call.call_status || call.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
