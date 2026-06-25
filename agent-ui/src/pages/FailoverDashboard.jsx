import React, { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { failoverApi } from '../services/api'
import {
  Radio, Activity, CheckCircle2, XCircle, RefreshCw, Clock
} from 'lucide-react'
import { toast } from 'sonner'

export default function FailoverDashboard() {
  const { tenant } = useAuth()
  const [status, setStatus] = useState(null)
  const [history, setHistory] = useState([])
  const [config, setConfig] = useState(null)
  const [testing, setTesting] = useState(false)

  const fetchData = async () => {
    if (!tenant) return
    try {
      const [statusRes, historyRes, configRes] = await Promise.all([
        failoverApi.getStatus({ tenant_id: tenant.id }),
        failoverApi.getHistory({ tenant_id: tenant.id }),
        failoverApi.getConfig({ tenant_id: tenant.id }),
      ])
      setStatus(statusRes.data)
      setHistory(Array.isArray(historyRes.data) ? historyRes.data : [])
      setConfig(configRes.data)
    } catch { }
  }

  useEffect(() => { fetchData() }, [tenant])

  async function handleRunTest() {
    setTesting(true)
    try {
      const res = await failoverApi.runTest({ tenant_id: tenant.id })
      toast.success(res.data.failover_success ? 'Failover test passed' : 'Failover test failed')
      fetchData()
    } catch { toast.error('Failed to run failover test') }
    finally { setTesting(false) }
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Telephony Failover Testing</h1>
          <p className="text-sm text-ink-muted mt-0.5">Test and monitor provider failover resilience</p>
        </div>
        <button onClick={handleRunTest} disabled={testing} className="btn-primary">
          {testing ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Activity className="h-4 w-4" />}
          {testing ? ' Testing...' : ' Run Failover Test'}
        </button>
      </div>

      {/* Current Status */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <div className="card p-6 flex items-center gap-4">
          <div className={`p-3 rounded-xl ${status?.primary_healthy ? 'bg-call-green-soft' : 'bg-red-50'}`}>
            <Radio className={`h-6 w-6 ${status?.primary_healthy ? 'text-call-green' : 'text-red-500'}`} />
          </div>
          <div>
            <p className="text-sm text-ink-muted">Primary Provider</p>
            <p className="text-lg font-semibold text-ink capitalize">{status?.primary_provider || 'twilio'}</p>
            <div className="flex items-center gap-1 mt-0.5">
              {status?.primary_healthy ? (
                <><CheckCircle2 className="h-3.5 w-3.5 text-call-green" /><span className="text-xs text-call-green">Healthy</span></>
              ) : (
                <><XCircle className="h-3.5 w-3.5 text-red-500" /><span className="text-xs text-red-500">Unhealthy</span></>
              )}
            </div>
          </div>
        </div>
        <div className="card p-6 flex items-center gap-4">
          <div className={`p-3 rounded-xl ${status?.secondary_healthy ? 'bg-call-green-soft' : 'bg-red-50'}`}>
            <Radio className={`h-6 w-6 ${status?.secondary_healthy ? 'text-call-green' : 'text-red-500'}`} />
          </div>
          <div>
            <p className="text-sm text-ink-muted">Secondary Provider</p>
            <p className="text-lg font-semibold text-ink capitalize">{status?.secondary_provider || 'fonster'}</p>
            <div className="flex items-center gap-1 mt-0.5">
              {status?.secondary_healthy ? (
                <><CheckCircle2 className="h-3.5 w-3.5 text-call-green" /><span className="text-xs text-call-green">Healthy</span></>
              ) : (
                <><XCircle className="h-3.5 w-3.5 text-red-500" /><span className="text-xs text-red-500">Unhealthy</span></>
              )}
            </div>
          </div>
        </div>
        <div className="card p-6 flex items-center gap-4">
          <div className="p-3 rounded-xl bg-surface-subtle">
            <Clock className="h-6 w-6 text-ink-muted" />
          </div>
          <div>
            <p className="text-sm text-ink-muted">Last Test</p>
            <p className="text-lg font-semibold text-ink">
              {status?.last_test_at ? new Date(status.last_test_at).toLocaleString() : 'Never'}
            </p>
            <p className="text-xs text-ink-muted mt-0.5">
              Auto-test: {config?.auto_test_interval_hours ? `Every ${config.auto_test_interval_hours}h` : 'Disabled'}
            </p>
          </div>
        </div>
      </div>

      {/* Test History */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b border-hairline">
          <h3 className="text-sm font-medium text-ink">Test History</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-hairline bg-surface-subtle">
                <th className="text-left px-4 py-3 font-medium text-ink-muted">Date</th>
                <th className="text-left px-4 py-3 font-medium text-ink-muted">Result</th>
                <th className="text-left px-4 py-3 font-medium text-ink-muted">Failover Time (ms)</th>
                <th className="text-left px-4 py-3 font-medium text-ink-muted">Fallback</th>
              </tr>
            </thead>
            <tbody>
              {history.length === 0 && (
                <tr>
                  <td colSpan="4" className="px-4 py-12 text-center text-ink-muted">
                    No test history yet. Run a failover test to populate.
                  </td>
                </tr>
              )}
              {history.map((test, i) => (
                <tr key={test.id || i} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                  <td className="px-4 py-3 text-ink-muted">
                    {test.timestamp ? new Date(test.timestamp).toLocaleString() : '-'}
                  </td>
                  <td className="px-4 py-3">
                    {test.failover_success ? (
                      <span className="inline-flex items-center gap-1 text-call-green">
                        <CheckCircle2 className="h-4 w-4" /> Success
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-red-500">
                        <XCircle className="h-4 w-4" /> Failed
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-ink-muted">{test.failover_time_ms}</td>
                  <td className="px-4 py-3">
                    {test.fallback_success ? (
                      <span className="text-call-green">Success</span>
                    ) : (
                      <span className="text-red-500">Failed</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Config */}
      {config && (
        <div className="card p-6 mt-6">
          <h3 className="text-sm font-medium text-ink mb-3">Configuration</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-xs text-ink-muted">Auto-test Interval</p>
              <p className="text-sm font-medium text-ink">{config.auto_test_interval_hours}h</p>
            </div>
            <div>
              <p className="text-xs text-ink-muted">Notifications</p>
              <p className="text-sm font-medium text-ink">{config.notifications_enabled ? 'Enabled' : 'Disabled'}</p>
            </div>
            <div>
              <p className="text-xs text-ink-muted">Primary</p>
              <p className="text-sm font-medium text-ink capitalize">{config.primary_provider}</p>
            </div>
            <div>
              <p className="text-xs text-ink-muted">Secondary</p>
              <p className="text-sm font-medium text-ink capitalize">{config.secondary_provider}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
