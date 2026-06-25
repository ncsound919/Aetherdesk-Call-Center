import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { voiceQualityApi } from '../services/api'
import {
  Activity, Wifi, Phone, TrendingUp, AlertTriangle,
  CheckCircle2, XCircle
} from 'lucide-react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts'

const QUALITY_COLORS = {
  excellent: '#22c55e',
  good: '#86efac',
  fair: '#f59e0b',
  poor: '#f97316',
  bad: '#ef4444',
}

function getMosColor(mos) {
  if (mos >= 4.0) return 'text-call-green'
  if (mos >= 3.5) return 'text-yellow-500'
  return 'text-red-500'
}

function getMosBg(mos) {
  if (mos >= 4.0) return 'bg-call-green-soft'
  if (mos >= 3.5) return 'bg-yellow-50'
  return 'bg-red-50'
}

function formatDt(ts) {
  if (!ts) return '—'
  return new Date(ts).toLocaleString()
}

export default function VoiceQualityDashboard() {
  const { tenant } = useAuth()
  const [metrics, setMetrics] = useState([])
  const [summary, setSummary] = useState(null)
  const [trends, setTrends] = useState([])
  const [loading, setLoading] = useState(false)

  const fetchMetrics = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await voiceQualityApi.listMetrics({ tenant_id: tenant.id, limit: 100 })
      setMetrics(Array.isArray(res.data) ? res.data : [])
    } catch { setMetrics([]) }
  }, [tenant])

  const fetchSummary = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await voiceQualityApi.getSummary({ tenant_id: tenant.id })
      setSummary(res.data)
    } catch { setSummary(null) }
  }, [tenant])

  const fetchTrends = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await voiceQualityApi.getTrends({ tenant_id: tenant.id, granularity: 'hour' })
      setTrends(Array.isArray(res.data) ? res.data : [])
    } catch { setTrends([]) }
  }, [tenant])

  useEffect(() => {
    setLoading(true)
    Promise.all([fetchMetrics(), fetchSummary(), fetchTrends()])
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [fetchMetrics, fetchSummary, fetchTrends])

  const qualityPieData = summary
    ? Object.entries(summary.quality_distribution || {}).map(([name, value]) => ({ name, value }))
    : []

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-ink tracking-tight">Voice Quality Monitoring</h1>
        <p className="text-sm text-ink-muted mt-0.5">Real-time MOS, jitter, packet loss, and latency metrics</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="card p-5 flex items-center gap-4">
          <div className={`p-3 rounded-xl ${getMosBg(summary?.avg_mos || 0)}`}>
            <Activity className={`h-5 w-5 ${getMosColor(summary?.avg_mos || 0)}`} />
          </div>
          <div>
            <p className="text-xs text-ink-muted font-medium uppercase tracking-wider">Avg MOS</p>
            <p className={`text-xl font-semibold ${getMosColor(summary?.avg_mos || 0)}`}>
              {summary?.avg_mos ? summary.avg_mos.toFixed(2) : '0.00'}
            </p>
          </div>
        </div>
        <div className="card p-5 flex items-center gap-4">
          <div className="p-3 rounded-xl bg-accent-soft">
            <Phone className="h-5 w-5 text-accent" />
          </div>
          <div>
            <p className="text-xs text-ink-muted font-medium uppercase tracking-wider">Total Calls</p>
            <p className="text-xl font-semibold text-ink">{summary?.total_calls || 0}</p>
          </div>
        </div>
        <div className="card p-5 flex items-center gap-4">
          <div className="p-3 rounded-xl bg-call-amber-soft">
            <Wifi className="h-5 w-5 text-telecom-amber" />
          </div>
          <div>
            <p className="text-xs text-ink-muted font-medium uppercase tracking-wider">P95 Jitter</p>
            <p className="text-xl font-semibold text-ink">{summary?.p95_jitter_ms?.toFixed(1) || '0.0'}ms</p>
          </div>
        </div>
        <div className="card p-5 flex items-center gap-4">
          <div className={`p-3 rounded-xl ${(summary?.p95_packet_loss_pct || 0) > 3 ? 'bg-red-50' : 'bg-call-green-soft'}`}>
            <AlertTriangle className={`h-5 w-5 ${(summary?.p95_packet_loss_pct || 0) > 3 ? 'text-red-500' : 'text-call-green'}`} />
          </div>
          <div>
            <p className="text-xs text-ink-muted font-medium uppercase tracking-wider">P95 Packet Loss</p>
            <p className="text-xl font-semibold text-ink">{summary?.p95_packet_loss_pct?.toFixed(1) || '0.0'}%</p>
          </div>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        {/* MOS Trends */}
        <div className="card p-6">
          <h3 className="text-sm font-medium text-ink mb-4 flex items-center gap-2">
            <TrendingUp className="h-4 w-4 text-accent" /> MOS Trends
          </h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={trends}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="bucket" tick={{ fontSize: 10 }} tickFormatter={v => v ? new Date(v).toLocaleTimeString([], { hour: '2-digit' }) : ''} />
              <YAxis domain={[1, 5]} tick={{ fontSize: 11 }} />
              <Tooltip labelFormatter={v => formatDt(v)} />
              <Line type="monotone" dataKey="avg_mos" stroke="#6366f1" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Jitter Trends */}
        <div className="card p-6">
          <h3 className="text-sm font-medium text-ink mb-4 flex items-center gap-2">
            <Wifi className="h-4 w-4 text-telecom-amber" /> Jitter Trends
          </h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={trends}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="bucket" tick={{ fontSize: 10 }} tickFormatter={v => v ? new Date(v).toLocaleTimeString([], { hour: '2-digit' }) : ''} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip labelFormatter={v => formatDt(v)} />
              <Line type="monotone" dataKey="avg_jitter" stroke="#f59e0b" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Quality Distribution Pie */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className="card p-6 lg:col-span-1">
          <h3 className="text-sm font-medium text-ink mb-4">Quality Distribution</h3>
          {qualityPieData.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={qualityPieData} cx="50%" cy="50%" innerRadius={50} outerRadius={80} dataKey="value" nameKey="name" label={({ name, value }) => `${name}: ${value}`}>
                  {qualityPieData.map((entry, i) => (
                    <Cell key={i} fill={QUALITY_COLORS[entry.name] || '#94a3b8'} />
                  ))}
                </Pie>
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-ink-muted text-center py-12">No quality data yet</p>
          )}
        </div>

        {/* Recent Calls Table */}
        <div className="card overflow-hidden lg:col-span-2">
          <div className="px-6 py-4 border-b border-hairline">
            <h3 className="text-sm font-medium text-ink">Recent Calls</h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hairline bg-surface-subtle">
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">MOS</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Jitter</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Packet Loss</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Latency</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Codec</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Rating</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Time</th>
                </tr>
              </thead>
              <tbody>
                {metrics.length === 0 && (
                  <tr>
                    <td colSpan="7" className="px-4 py-12 text-center text-ink-muted">
                      No quality metrics recorded yet.
                    </td>
                  </tr>
                )}
                {metrics.map(m => {
                  const color = m.mos >= 4.0 ? 'text-call-green' : m.mos >= 3.5 ? 'text-yellow-500' : 'text-red-500'
                  const RatingIcon = m.quality_rating === 'excellent' || m.quality_rating === 'good' ? CheckCircle2 : XCircle
                  return (
                    <tr key={m.id} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                      <td className={`px-4 py-3 font-medium ${color}`}>{m.mos?.toFixed(2)}</td>
                      <td className="px-4 py-3 text-ink-muted">{m.jitter_ms?.toFixed(1)}ms</td>
                      <td className="px-4 py-3 text-ink-muted">{m.packet_loss_pct?.toFixed(1)}%</td>
                      <td className="px-4 py-3 text-ink-muted">{m.latency_ms?.toFixed(0)}ms</td>
                      <td className="px-4 py-3">
                        <span className="text-xs font-mono bg-surface-subtle px-2 py-0.5 rounded">{m.codec || 'opus'}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 text-xs font-medium ${m.quality_rating === 'excellent' || m.quality_rating === 'good' ? 'text-call-green' : 'text-red-500'}`}>
                          <RatingIcon className="h-3 w-3" />
                          {m.quality_rating}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-ink-muted text-xs">{formatDt(m.created_at)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
