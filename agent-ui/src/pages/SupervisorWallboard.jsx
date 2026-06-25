import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { supervisorApi } from '../services/api'
import {
  Tv, Users, Clock, PhoneCall, AlertTriangle, TrendingUp, BarChart3, Loader2
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer
} from 'recharts'

export default function SupervisorWallboard() {
  const { tenant } = useAuth()
  const [wallboard, setWallboard] = useState(null)
  const [agents, setAgents] = useState([])
  const [team, setTeam] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [loading, setLoading] = useState(false)

  const fetchAll = useCallback(async () => {
    if (!tenant) return
    setLoading(true)
    try {
      const [wbRes, agRes, tmRes, alRes] = await Promise.all([
        supervisorApi.getWallboard(tenant.id),
        supervisorApi.getAgents(tenant.id),
        supervisorApi.getTeam(tenant.id),
        supervisorApi.getAlerts(tenant.id),
      ])
      setWallboard(wbRes.data)
      setAgents(Array.isArray(agRes.data) ? agRes.data : [])
      setTeam(tmRes.data)
      setAlerts(Array.isArray(alRes.data) ? alRes.data : [])
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [tenant])

  useEffect(() => { fetchAll(); const i = setInterval(fetchAll, 15000); return () => clearInterval(i) }, [fetchAll])

  const stats = [
    { label: 'Active Calls', value: wallboard?.active_calls || 0, icon: PhoneCall, color: 'text-call-green' },
    { label: 'Waiting', value: wallboard?.waiting_queue || 0, icon: Clock, color: 'text-telecom-amber' },
    { label: 'Agents Online', value: wallboard?.agents_online || 0, icon: Users, color: 'text-accent' },
    { label: 'Avg Wait', value: `${wallboard?.avg_wait_seconds || 0}s`, icon: TrendingUp, color: 'text-ink-muted' },
    { label: 'Longest Wait', value: `${wallboard?.longest_wait_seconds || 0}s`, icon: AlertTriangle, color: 'text-red-500' },
  ]

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Supervisor Wallboard</h1>
          <p className="text-sm text-ink-muted mt-0.5">Real-time contact center overview</p>
        </div>
        {loading && <Loader2 className="h-5 w-5 animate-spin text-accent" />}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        {stats.map((s) => {
          const Icon = s.icon
          return (
            <div key={s.label} className="card p-4 flex items-center gap-3">
              <div className={`p-2.5 rounded-lg bg-surface-subtle ${s.color}`}>
                <Icon className="h-5 w-5" />
              </div>
              <div>
                <p className="text-xs text-ink-muted">{s.label}</p>
                <p className="text-xl font-semibold text-ink">{s.value}</p>
              </div>
            </div>
          )
        })}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className="lg:col-span-2 card p-6">
          <h3 className="text-sm font-medium text-ink mb-4 flex items-center gap-2"><BarChart3 className="h-4 w-4" /> Team Performance</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={team?.agents || []}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="calls_handled" fill="#6366f1" name="Calls Handled" radius={[4, 4, 0, 0]} />
              <Bar dataKey="avg_aht" fill="#22c55e" name="Avg AHT (s)" radius={[4, 4, 0, 0]} />
              <Bar dataKey="csat" fill="#f59e0b" name="CSAT" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="card p-6">
          <h3 className="text-sm font-medium text-ink mb-4 flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> Recent Alerts</h3>
          {alerts.length === 0 && <p className="text-sm text-ink-muted">No active alerts</p>}
          <div className="space-y-3">
            {alerts.map((a, i) => (
              <div key={i} className={`p-3 rounded-lg text-sm ${
                a.severity === 'critical' ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-amber-50 text-amber-700 border border-amber-200'
              }`}>
                <p className="font-medium">{a.type.replace(/_/g, ' ')}</p>
                <p className="text-xs mt-0.5">{a.message}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b border-hairline">
          <h3 className="text-sm font-medium text-ink flex items-center gap-2"><Users className="h-4 w-4" /> Agent Status</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-hairline bg-surface-subtle">
                <th className="text-left px-4 py-3 font-medium text-ink-muted">Name</th>
                <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                <th className="text-left px-4 py-3 font-medium text-ink-muted">Call Duration</th>
                <th className="text-left px-4 py-3 font-medium text-ink-muted">Calls Today</th>
                <th className="text-left px-4 py-3 font-medium text-ink-muted">Adherence %</th>
              </tr>
            </thead>
            <tbody>
              {agents.map((a) => (
                <tr key={a.id} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                  <td className="px-4 py-3 font-medium text-ink">{a.name}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                      a.status === 'available' ? 'bg-call-green-soft text-call-green' :
                      a.status === 'busy' ? 'bg-call-amber-soft text-telecom-amber' :
                      'bg-surface-subtle text-ink-muted'
                    }`}>{a.status}</span>
                  </td>
                  <td className="px-4 py-3 text-ink-muted">{a.current_call_duration}s</td>
                  <td className="px-4 py-3 text-ink-muted">{a.calls_today}</td>
                  <td className="px-4 py-3 text-ink-muted">{a.adherence_pct}%</td>
                </tr>
              ))}
              {agents.length === 0 && (
                <tr><td colSpan="5" className="px-4 py-12 text-center text-ink-muted">No agents found</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
