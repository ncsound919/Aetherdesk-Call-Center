import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { reliabilityApi } from '../services/api'
import {
  Activity, Shield, Zap, Database, RefreshCw, BarChart3,
  AlertCircle, Wifi, Loader2, ToggleLeft, ToggleRight
} from 'lucide-react'
import { toast } from 'sonner'

export default function ReliabilityDashboard() {
  const { tenant } = useAuth()
  const [activeTab, setActiveTab] = useState('breakers')
  const [loading, setLoading] = useState(false)
  const [breakers, setBreakers] = useState([])
  const [rateLimits, setRateLimits] = useState([])
  const [drStatus, setDrStatus] = useState(null)
  const [cacheStats, setCacheStats] = useState(null)
  const [configForm, setConfigForm] = useState({ tenant_id: '', route_key: '', max_requests: 100, window_seconds: 60 })

  const fetchBreakers = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await reliabilityApi.getCircuitBreakers(tenant.id)
      setBreakers(Array.isArray(res.data) ? res.data : [])
    } catch { setBreakers([]) }
  }, [tenant])

  const fetchRateLimits = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await reliabilityApi.getRateLimits(tenant.id)
      setRateLimits(Array.isArray(res.data) ? res.data : [])
    } catch { setRateLimits([]) }
  }, [tenant])

  const fetchDrStatus = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await reliabilityApi.getDrStatus(tenant.id)
      setDrStatus(res.data)
    } catch { setDrStatus(null) }
  }, [tenant])

  const fetchCacheStats = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await reliabilityApi.getCacheStats(tenant.id)
      setCacheStats(res.data)
    } catch { setCacheStats(null) }
  }, [tenant])

  useEffect(() => {
    if (activeTab === 'breakers') fetchBreakers()
    if (activeTab === 'ratelimits') fetchRateLimits()
    if (activeTab === 'dr') fetchDrStatus()
    if (activeTab === 'cache') fetchCacheStats()
  }, [activeTab, fetchBreakers, fetchRateLimits, fetchDrStatus, fetchCacheStats])

  async function handleResetBreaker(name) {
    try {
      await reliabilityApi.resetCircuitBreaker(tenant.id, name)
      toast.success(`Circuit breaker '${name}' reset`)
      fetchBreakers()
    } catch { toast.error('Failed to reset breaker') }
  }

  async function handleSetRateLimit(e) {
    e.preventDefault()
    try {
      await reliabilityApi.setRateLimit(tenant.id, configForm.tenant_id, configForm.route_key, configForm.max_requests, configForm.window_seconds)
      toast.success('Rate limit configured')
      fetchRateLimits()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to set rate limit')
    }
  }

  async function handleRunDrTest(testType) {
    setLoading(true)
    try {
      const res = await reliabilityApi.runDrTest(tenant.id, testType)
      toast.success('DR test completed')
      fetchDrStatus()
    } catch (err) {
      toast.error('DR test failed')
    } finally { setLoading(false) }
  }

  const tabs = [
    { key: 'breakers', label: 'Circuit Breakers', icon: Activity },
    { key: 'ratelimits', label: 'Rate Limiting', icon: Shield },
    { key: 'dr', label: 'DR Testing', icon: Wifi },
    { key: 'cache', label: 'Cache', icon: Database },
  ]

  function breakerColor(state) {
    if (state === 'CLOSED') return 'border-green-500 bg-green-50'
    if (state === 'OPEN') return 'border-red-500 bg-red-50'
    if (state === 'HALF_OPEN') return 'border-yellow-500 bg-yellow-50'
    return 'border-gray-300 bg-gray-50'
  }

  function breakerBadge(state) {
    const colors = { CLOSED: 'bg-green-100 text-green-700', OPEN: 'bg-red-100 text-red-700', HALF_OPEN: 'bg-yellow-100 text-yellow-700' }
    return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${colors[state] || 'bg-gray-100 text-gray-700'}`}>{state}</span>
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Reliability & Performance</h1>
          <p className="text-sm text-ink-muted mt-0.5">Circuit breakers, rate limiting, DR testing, and cache monitoring</p>
        </div>
      </div>

      <div className="flex gap-1 mb-6 border-b border-hairline overflow-x-auto">
        {tabs.map(tab => {
          const Icon = tab.icon
          return (
            <button key={tab.key} onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab.key ? 'border-accent text-accent' : 'border-transparent text-ink-muted hover:text-ink'
              }`}>
              <Icon className="h-4 w-4" /> {tab.label}
            </button>
          )
        })}
      </div>

      {activeTab === 'breakers' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {breakers.length === 0 && (
              <div className="card p-12 col-span-2 text-center text-ink-muted">No circuit breakers registered.</div>
            )}
            {breakers.map(cb => (
              <div key={cb.name} className={`card p-5 border-l-4 ${breakerColor(cb.state)}`}>
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-ink">{cb.name}</h3>
                    {breakerBadge(cb.state)}
                  </div>
                  {cb.is_open && (
                    <button onClick={() => handleResetBreaker(cb.name)} className="text-xs text-accent hover:underline font-medium flex items-center gap-1">
                      <RefreshCw className="h-3 w-3" /> Reset
                    </button>
                  )}
                </div>
                <div className="grid grid-cols-3 gap-3 text-xs">
                  <div><span className="text-ink-muted">Failures:</span> <span className="font-medium text-ink">{cb.failure_count}/{cb.threshold}</span></div>
                  <div><span className="text-ink-muted">Success:</span> <span className="font-medium text-ink">{cb.success_count}</span></div>
                  <div><span className="text-ink-muted">Total:</span> <span className="font-medium text-ink">{cb.total_calls}</span></div>
                  <div><span className="text-ink-muted">Timeout:</span> <span className="font-medium text-ink">{cb.recovery_timeout}s</span></div>
                  <div><span className="text-ink-muted">Probes:</span> <span className="font-medium text-ink">{cb.half_open_max_calls}</span></div>
                  <div><span className="text-ink-muted">Last:</span> <span className="font-medium text-ink">{cb.last_failure_time ? new Date(cb.last_failure_time * 1000).toLocaleTimeString() : '—'}</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {activeTab === 'ratelimits' && (
        <div className="space-y-6">
          <form onSubmit={handleSetRateLimit} className="card p-4">
            <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
              <input type="text" placeholder="Tenant ID" value={configForm.tenant_id}
                onChange={e => setConfigForm({ ...configForm, tenant_id: e.target.value })}
                className="input-field" required />
              <input type="text" placeholder="Route key" value={configForm.route_key}
                onChange={e => setConfigForm({ ...configForm, route_key: e.target.value })}
                className="input-field" required />
              <input type="number" placeholder="Max requests" value={configForm.max_requests}
                onChange={e => setConfigForm({ ...configForm, max_requests: parseInt(e.target.value) })}
                className="input-field" required />
              <input type="number" placeholder="Window (sec)" value={configForm.window_seconds}
                onChange={e => setConfigForm({ ...configForm, window_seconds: parseInt(e.target.value) })}
                className="input-field" required />
              <button type="submit" className="btn-primary"><Shield className="h-4 w-4" /> Set Limit</button>
            </div>
          </form>
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hairline bg-surface-subtle">
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Tenant</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Route</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Max Requests</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Window</th>
                  </tr>
                </thead>
                <tbody>
                  {rateLimits.length === 0 && (
                    <tr><td colSpan="4" className="px-4 py-12 text-center text-ink-muted">No rate limits configured.</td></tr>
                  )}
                  {rateLimits.map(rl => (
                    <tr key={rl.id} className="border-b border-hairline">
                      <td className="px-4 py-3 text-ink font-mono text-xs">{rl.tenant_id}</td>
                      <td className="px-4 py-3 text-ink">{rl.route_key}</td>
                      <td className="px-4 py-3 text-ink-muted">{rl.max_requests}</td>
                      <td className="px-4 py-3 text-ink-muted">{rl.window_seconds}s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'dr' && (
        <div className="space-y-6">
          {drStatus && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="card p-6 flex flex-col items-center">
                <p className="text-sm text-ink-muted mb-1">DR Ready</p>
                {drStatus.dr_ready ? <CheckCircleIcon /> : <XIcon />}
                <p className={`text-lg font-semibold ${drStatus.dr_ready ? 'text-green-500' : 'text-red-500'}`}>{drStatus.dr_ready ? 'Yes' : 'No'}</p>
              </div>
              <div className="card p-6 flex flex-col items-center">
                <p className="text-sm text-ink-muted mb-1">RTO</p>
                <p className="text-2xl font-semibold text-ink">{drStatus.rto_seconds}s</p>
              </div>
              <div className="card p-6 flex flex-col items-center">
                <p className="text-sm text-ink-muted mb-1">RPO</p>
                <p className="text-2xl font-semibold text-ink">{drStatus.rpo_seconds}s</p>
              </div>
              <div className="card p-6 flex flex-col items-center">
                <p className="text-sm text-ink-muted mb-1">Backup</p>
                <p className="text-lg font-semibold text-green-500">{drStatus.backup_enabled ? 'Enabled' : 'Disabled'}</p>
              </div>
            </div>
          )}
          <div className="card p-4 flex items-center justify-between">
            <p className="text-sm text-ink-muted">Run disaster recovery drill to test system resilience</p>
            <div className="flex gap-2">
              <button onClick={() => handleRunDrTest('database_failover')} className="btn-secondary text-xs" disabled={loading}>
                {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : null} DB Failover
              </button>
              <button onClick={() => handleRunDrTest('service_restart')} className="btn-secondary text-xs" disabled={loading}>
                Service Restart
              </button>
              <button onClick={() => handleRunDrTest('full')} className="btn-primary text-xs" disabled={loading}>
                {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : null} Full Drill
              </button>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'cache' && (
        <div className="space-y-6">
          {cacheStats && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="card p-6 flex flex-col items-center">
                  <p className="text-sm text-ink-muted mb-1">Hit Rate</p>
                  <div className="relative w-20 h-20">
                    <svg className="w-20 h-20 transform -rotate-90" viewBox="0 0 100 100">
                      <circle cx="50" cy="50" r="40" fill="none" stroke="#e5e7eb" strokeWidth="8" />
                      <circle cx="50" cy="50" r="40" fill="none" stroke={cacheStats.hit_rate_pct >= 80 ? '#22c55e' : '#f59e0b'} strokeWidth="8"
                        strokeDasharray={`${cacheStats.hit_rate_pct * 2.51} 251`} strokeLinecap="round" />
                    </svg>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <span className="text-sm font-semibold text-ink">{cacheStats.hit_rate_pct}%</span>
                    </div>
                  </div>
                </div>
                <div className="card p-6 flex flex-col items-center">
                  <p className="text-sm text-ink-muted mb-1">Hits</p>
                  <p className="text-2xl font-semibold text-ink">{cacheStats.hits}</p>
                </div>
                <div className="card p-6 flex flex-col items-center">
                  <p className="text-sm text-ink-muted mb-1">Misses</p>
                  <p className="text-2xl font-semibold text-ink">{cacheStats.misses}</p>
                </div>
                <div className="card p-6 flex flex-col items-center">
                  <p className="text-sm text-ink-muted mb-1">Local Items</p>
                  <p className="text-2xl font-semibold text-ink">{cacheStats.local_cache_size}</p>
                </div>
              </div>
              <div className="card p-6">
                <h3 className="text-sm font-semibold text-ink mb-4">Cache Details</h3>
                <pre className="text-xs text-ink-muted bg-surface-subtle p-4 rounded-lg overflow-x-auto">{JSON.stringify(cacheStats, null, 2)}</pre>
              </div>
            </>
          )}
          {!cacheStats && (
            <div className="card p-12 text-center text-ink-muted">No cache statistics available.</div>
          )}
        </div>
      )}
    </div>
  )
}

function CheckCircleIcon() {
  return (
    <svg className="h-6 w-6 text-green-500 mb-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  )
}

function XIcon() {
  return (
    <svg className="h-6 w-6 text-red-500 mb-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
  )
}
