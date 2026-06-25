import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import {
  Plug, RefreshCw, CheckCircle2, AlertTriangle,
  Database, Ticket, Users, ExternalLink, Loader2, Plus, X
} from 'lucide-react'
import { toast } from 'sonner'
import { integrationsApi } from '../services/api'

export default function IntegrationsDashboard() {
  const { tenant } = useAuth()
  const [configs, setConfigs] = useState([])
  const [crmHealth, setCrmHealth] = useState(null)
  const [ticketingHealth, setTicketingHealth] = useState(null)
  const [activityLog, setActivityLog] = useState([])
  const [loading, setLoading] = useState(false)
  const [showConfigModal, setShowConfigModal] = useState(false)
  const [configForm, setConfigForm] = useState({ provider: '', integration_type: 'crm', config: '{}', status: 'active' })

  const fetchConfigs = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await integrationsApi.getConfigs()
      setConfigs(Array.isArray(res.data?.configs) ? res.data.configs : [])
    } catch { setConfigs([]) }
  }, [tenant])

  const fetchHealth = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await integrationsApi.getCRMHealth()
      setCrmHealth(res.data)
    } catch { setCrmHealth(null) }
    try {
      const res = await integrationsApi.getTicketingHealth()
      setTicketingHealth(res.data)
    } catch { setTicketingHealth(null) }
  }, [tenant])

  useEffect(() => {
    fetchConfigs()
    fetchHealth()
  }, [fetchConfigs, fetchHealth])

  function getHealthStatus(health) {
    if (!health) return { label: 'Not configured', color: 'bg-gray-100 text-gray-500', icon: AlertTriangle }
    const status = health?.data?.status
    if (status === 'healthy') return { label: 'Connected', color: 'bg-call-green-soft text-call-green', icon: CheckCircle2 }
    if (status === 'not_configured') return { label: 'Not configured', color: 'bg-gray-100 text-gray-500', icon: AlertTriangle }
    return { label: 'Error', color: 'bg-red-50 text-red-600', icon: AlertTriangle }
  }

  async function handleSync() {
    setLoading(true)
    try {
      const res = await integrationsApi.syncCRMContacts()
      toast.success('CRM sync completed')
      setActivityLog(prev => [{ type: 'crm_sync', message: 'CRM contacts synced', timestamp: new Date().toISOString() }, ...prev])
    } catch { toast.error('CRM sync failed') }
    finally { setLoading(false) }
  }

  async function handleCreateConfig(e) {
    e.preventDefault()
    try {
      let parsedConfig = {}
      try { parsedConfig = JSON.parse(configForm.config) } catch { parsedConfig = {} }
      await integrationsApi.createConfig({
        provider: configForm.provider,
        integration_type: configForm.integration_type,
        config: parsedConfig,
        status: configForm.status,
      })
      toast.success('Integration configured')
      setShowConfigModal(false)
      setConfigForm({ provider: '', integration_type: 'crm', config: '{}', status: 'active' })
      fetchConfigs()
      fetchHealth()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to configure integration')
    }
  }

  const HealthCard = ({ title, health, provider }) => {
    const status = getHealthStatus(health)
    const Icon = status.icon
    return (
      <div className="card p-5">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            {provider === 'crm' ? <Users className="h-5 w-5 text-accent" /> : <Ticket className="h-5 w-5 text-accent" />}
            <h3 className="font-medium text-ink">{title}</h3>
          </div>
          <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ${status.color}`}>
            <Icon className="h-3.5 w-3.5" />
            {status.label}
          </span>
        </div>
        {health?.data?.details && (
          <p className="text-xs text-ink-muted">{health.data.details}</p>
        )}
      </div>
    )
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Integrations</h1>
          <p className="text-sm text-ink-muted mt-0.5">Connect CRM and ticketing providers</p>
        </div>
        <button onClick={() => setShowConfigModal(true)} className="btn-primary">
          <Plug className="h-4 w-4" /> Add Integration
        </button>
      </div>

      {/* Health Summary */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
        <HealthCard title="CRM" health={crmHealth} provider="crm" />
        <HealthCard title="Ticketing" health={ticketingHealth} provider="ticketing" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* CRM Section */}
        <div className="card overflow-hidden">
          <div className="px-5 py-4 border-b border-hairline flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4 text-accent" />
              <h2 className="text-sm font-medium text-ink">CRM Contacts</h2>
            </div>
            <button onClick={handleSync} disabled={loading} className="btn-secondary text-xs px-3 py-1.5">
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
              Sync
            </button>
          </div>
          <div className="p-5 text-center text-sm text-ink-muted">
            Configure a CRM integration to manage contacts.
          </div>
        </div>

        {/* Ticketing Section */}
        <div className="card overflow-hidden">
          <div className="px-5 py-4 border-b border-hairline flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Ticket className="h-4 w-4 text-accent" />
              <h2 className="text-sm font-medium text-ink">Tickets</h2>
            </div>
          </div>
          <div className="p-5 text-center text-sm text-ink-muted">
            Configure a ticketing integration to manage tickets.
          </div>
        </div>
      </div>

      {/* Integration Configs */}
      <div className="mt-6">
        <h2 className="text-sm font-medium text-ink mb-3 flex items-center gap-2">
          <Database className="h-4 w-4 text-ink-muted" />
          Configured Integrations
        </h2>
        {configs.length === 0 && (
          <div className="card p-6 text-center text-sm text-ink-muted">
            No integrations configured yet. Click "Add Integration" to get started.
          </div>
        )}
        {configs.length > 0 && (
          <div className="card overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hairline bg-surface-subtle">
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Provider</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Type</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Last Sync</th>
                </tr>
              </thead>
              <tbody>
                {configs.map((cfg, i) => (
                  <tr key={cfg.id || i} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                    <td className="px-4 py-3 text-ink font-medium capitalize">{cfg.provider}</td>
                    <td className="px-4 py-3 text-ink-muted uppercase text-xs">{cfg.integration_type}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                        cfg.status === 'active' ? 'bg-call-green-soft text-call-green' : 'bg-red-50 text-red-600'
                      }`}>
                        {cfg.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-ink-muted text-xs">
                      {cfg.last_sync_at ? new Date(cfg.last_sync_at).toLocaleString() : 'Never'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Activity Log */}
      <div className="mt-6">
        <h2 className="text-sm font-medium text-ink mb-3 flex items-center gap-2">
          <ExternalLink className="h-4 w-4 text-ink-muted" />
          Integration Activity
        </h2>
        <div className="card p-5">
          {activityLog.length === 0 && (
            <p className="text-sm text-ink-muted text-center">No activity yet. Sync or create tickets to see logs.</p>
          )}
          {activityLog.length > 0 && (
            <div className="space-y-2">
              {activityLog.map((log, i) => (
                <div key={i} className="flex items-center gap-3 text-sm py-1.5 border-b border-hairline last:border-0">
                  {log.type === 'crm_sync' ? (
                    <RefreshCw className="h-3.5 w-3.5 text-accent" />
                  ) : (
                    <Ticket className="h-3.5 w-3.5 text-accent" />
                  )}
                  <span className="text-ink flex-1">{log.message}</span>
                  <span className="text-xs text-ink-muted">{new Date(log.timestamp).toLocaleTimeString()}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Add Integration Modal */}
      {showConfigModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">Add Integration</h2>
              <button onClick={() => setShowConfigModal(false)} className="p-1.5 rounded-lg hover:bg-surface-hover">
                <X className="h-5 w-5 text-ink-muted" />
              </button>
            </div>
            <form onSubmit={handleCreateConfig} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Provider</label>
                <select value={configForm.provider} onChange={e => setConfigForm({ ...configForm, provider: e.target.value })} className="input-field" required>
                  <option value="">Select provider...</option>
                  <option value="salesforce">Salesforce</option>
                  <option value="hubspot">HubSpot</option>
                  <option value="zendesk">Zendesk</option>
                  <option value="servicenow">ServiceNow</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Type</label>
                <select value={configForm.integration_type} onChange={e => setConfigForm({ ...configForm, integration_type: e.target.value })} className="input-field">
                  <option value="crm">CRM</option>
                  <option value="ticketing">Ticketing</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Config (JSON)</label>
                <textarea value={configForm.config} onChange={e => setConfigForm({ ...configForm, config: e.target.value })} className="input-field" rows={3} placeholder='{"api_key": "..."}' />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowConfigModal(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" className="btn-primary flex-1">
                  <Plus className="h-4 w-4" /> Save
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
