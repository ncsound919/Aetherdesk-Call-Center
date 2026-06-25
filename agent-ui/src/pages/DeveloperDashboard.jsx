import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { developerApi } from '../services/api'
import {
  Key, Webhook, Code, FileText, Activity, RefreshCw,
  Copy, CheckCircle2, XCircle, Plus, X, Loader2, Trash2
} from 'lucide-react'
import { toast } from 'sonner'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer
} from 'recharts'

const ALL_SCOPES = ['all', 'calls:read', 'calls:write', 'agents:read', 'agents:write', 'analytics:read', 'webhooks:manage']
const ALL_EVENTS = ['call.completed', 'call.failed', 'agent.status_changed', 'intent.classified', 'qa.score_created', 'csat.submitted', 'transcription.ready']

export default function DeveloperDashboard() {
  const { tenant } = useAuth()
  const [activeTab, setActiveTab] = useState('api-keys')
  const [apiKeys, setApiKeys] = useState([])
  const [webhooks, setWebhooks] = useState([])
  const [eventCatalog, setEventCatalog] = useState({})
  const [loading, setLoading] = useState(false)
  const [showCreateKeyModal, setShowCreateKeyModal] = useState(false)
  const [showRegisterWebhookModal, setShowRegisterWebhookModal] = useState(false)
  const [showNewKeyModal, setShowNewKeyModal] = useState(false)
  const [newKeyData, setNewKeyData] = useState(null)
  const [copied, setCopied] = useState(false)
  const [selectedWebhookLogs, setSelectedWebhookLogs] = useState(null)
  const [webhookLogs, setWebhookLogs] = useState([])
  const [loadingLogs, setLoadingLogs] = useState(false)
  const [keyUsage, setKeyUsage] = useState(null)
  const [showKeyUsage, setShowKeyUsage] = useState(null)

  const [keyForm, setKeyForm] = useState({ name: '', scopes: ['all'], expires_in_days: 365 })
  const [webhookForm, setWebhookForm] = useState({ url: '', events: [], secret: '' })

  const fetchKeys = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await developerApi.listAPIKeys()
      setApiKeys(Array.isArray(res.data) ? res.data : [])
    } catch { setApiKeys([]) }
  }, [tenant])

  const fetchWebhooks = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await developerApi.listWebhooks()
      setWebhooks(Array.isArray(res.data) ? res.data : [])
    } catch { setWebhooks([]) }
  }, [tenant])

  const fetchEventCatalog = useCallback(async () => {
    try {
      const res = await developerApi.getEventCatalog()
      setEventCatalog(res.data?.events || {})
    } catch { setEventCatalog({}) }
  }, [])

  useEffect(() => {
    fetchKeys()
    fetchWebhooks()
    fetchEventCatalog()
  }, [fetchKeys, fetchWebhooks, fetchEventCatalog])

  async function handleCreateKey(e) {
    e.preventDefault()
    try {
      const res = await developerApi.createAPIKey(keyForm)
      setNewKeyData(res.data)
      setShowNewKeyModal(true)
      setShowCreateKeyModal(false)
      setKeyForm({ name: '', scopes: ['all'], expires_in_days: 365 })
      toast.success('API key created')
      fetchKeys()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create key')
    }
  }

  async function handleRevokeKey(keyId) {
    try {
      await developerApi.revokeAPIKey(keyId)
      toast.success('Key revoked')
      fetchKeys()
    } catch { toast.error('Failed to revoke key') }
  }

  async function handleRotateKey(keyId) {
    try {
      const res = await developerApi.rotateAPIKey(keyId)
      setNewKeyData(res.data)
      setShowNewKeyModal(true)
      toast.success('Key rotated')
      fetchKeys()
    } catch { toast.error('Failed to rotate key') }
  }

  async function handleFetchKeyUsage(keyId) {
    try {
      const res = await developerApi.getAPIKeyUsage(keyId, { period: '30d' })
      setKeyUsage(res.data)
      setShowKeyUsage(keyId)
    } catch { toast.error('Failed to load usage') }
  }

  async function handleRegisterWebhook(e) {
    e.preventDefault()
    try {
      await developerApi.registerWebhook(webhookForm)
      toast.success('Webhook registered')
      setShowRegisterWebhookModal(false)
      setWebhookForm({ url: '', events: [], secret: '' })
      fetchWebhooks()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to register webhook')
    }
  }

  async function handleUnregisterWebhook(webhookId) {
    try {
      await developerApi.unregisterWebhook(webhookId)
      toast.success('Webhook removed')
      fetchWebhooks()
    } catch { toast.error('Failed to remove webhook') }
  }

  async function handleTestWebhook(webhookId) {
    try {
      const res = await developerApi.testWebhook(webhookId)
      if (res.data?.success) toast.success('Test event sent')
      else toast.error('Test delivery failed')
    } catch { toast.error('Test failed') }
  }

  async function handleFetchLogs(webhookId) {
    setSelectedWebhookLogs(webhookId)
    setLoadingLogs(true)
    try {
      const res = await developerApi.getWebhookLogs(webhookId, { limit: 20 })
      setWebhookLogs(Array.isArray(res.data) ? res.data : [])
    } catch { setWebhookLogs([]) }
    finally { setLoadingLogs(false) }
  }

  async function handleRetry(logId) {
    try {
      await developerApi.retryWebhookDelivery(logId)
      toast.success('Retry queued')
      if (selectedWebhookLogs) handleFetchLogs(selectedWebhookLogs)
    } catch { toast.error('Retry failed') }
  }

  function copyToClipboard(text) {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function toggleScope(scope) {
    const scopes = keyForm.scopes.includes(scope)
      ? keyForm.scopes.filter(s => s !== scope)
      : [...keyForm.scopes, scope]
    setKeyForm({ ...keyForm, scopes })
  }

  function toggleEvent(event) {
    const events = webhookForm.events.includes(event)
      ? webhookForm.events.filter(e => e !== event)
      : [...webhookForm.events, event]
    setWebhookForm({ ...webhookForm, events })
  }

  const tabs = [
    { key: 'api-keys', label: 'API Keys', icon: Key },
    { key: 'webhooks', label: 'Webhooks', icon: Webhook },
    { key: 'events', label: 'Events', icon: Code },
  ]

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Developer Platform</h1>
          <p className="text-sm text-ink-muted mt-0.5">API keys, webhooks, and event management</p>
        </div>
        {activeTab === 'api-keys' && (
          <button onClick={() => setShowCreateKeyModal(true)} className="btn-primary">
            <Plus className="h-4 w-4" /> Create Key
          </button>
        )}
        {activeTab === 'webhooks' && (
          <button onClick={() => setShowRegisterWebhookModal(true)} className="btn-primary">
            <Plus className="h-4 w-4" /> Register Webhook
          </button>
        )}
      </div>

      <div className="flex gap-1 mb-6 border-b border-hairline">
        {tabs.map(tab => {
          const Icon = tab.icon
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-accent text-accent'
                  : 'border-transparent text-ink-muted hover:text-ink'
              }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* API Keys Tab */}
      {activeTab === 'api-keys' && (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hairline bg-surface-subtle">
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Name</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Key</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Scopes</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Created</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Last Used</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                  <th className="text-right px-4 py-3 font-medium text-ink-muted">Actions</th>
                </tr>
              </thead>
              <tbody>
                {apiKeys.length === 0 && (
                  <tr>
                    <td colSpan="7" className="px-4 py-12 text-center text-ink-muted">
                      No API keys. Create one to get started.
                    </td>
                  </tr>
                )}
                {apiKeys.map(key => (
                  <tr key={key.id} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                    <td className="px-4 py-3 text-ink font-medium">{key.name}</td>
                    <td className="px-4 py-3">
                      <code className="text-xs bg-surface-subtle px-2 py-0.5 rounded text-ink-muted font-mono">
                        {key.masked_key}
                      </code>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1 flex-wrap">
                        {key.scopes?.map(s => (
                          <span key={s} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-accent-soft text-accent">
                            {s}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-ink-muted text-xs">
                      {key.created_at ? new Date(key.created_at).toLocaleDateString() : '-'}
                    </td>
                    <td className="px-4 py-3 text-ink-muted text-xs">
                      {key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'Never'}
                    </td>
                    <td className="px-4 py-3">
                      {key.is_active ? (
                        <span className="inline-flex items-center gap-1 text-xs font-medium text-call-green">
                          <CheckCircle2 className="h-3 w-3" /> Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs font-medium text-ink-muted">
                          <XCircle className="h-3 w-3" /> Revoked
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => handleFetchKeyUsage(key.id)} className="p-1.5 rounded-lg text-ink-muted hover:text-accent hover:bg-accent-soft transition-colors" title="Usage">
                          <Activity className="h-4 w-4" />
                        </button>
                        <button onClick={() => handleRotateKey(key.id)} className="p-1.5 rounded-lg text-ink-muted hover:text-accent hover:bg-accent-soft transition-colors" title="Rotate">
                          <RefreshCw className="h-4 w-4" />
                        </button>
                        {key.is_active && (
                          <button onClick={() => handleRevokeKey(key.id)} className="p-1.5 rounded-lg text-ink-muted hover:text-red-500 hover:bg-red-50 transition-colors" title="Revoke">
                            <Trash2 className="h-4 w-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {showKeyUsage && keyUsage && (
            <div className="border-t border-hairline p-4 bg-surface-subtle">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium text-ink">Usage: {keyUsage.name}</h3>
                <button onClick={() => { setShowKeyUsage(null); setKeyUsage(null) }} className="text-ink-muted hover:text-ink">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-white rounded-lg p-3">
                  <p className="text-xs text-ink-muted">Call Count</p>
                  <p className="text-lg font-semibold text-ink">{keyUsage.call_count}</p>
                </div>
                <div className="bg-white rounded-lg p-3">
                  <p className="text-xs text-ink-muted">Last Used</p>
                  <p className="text-lg font-semibold text-ink">{keyUsage.last_used_at ? new Date(keyUsage.last_used_at).toLocaleDateString() : 'Never'}</p>
                </div>
                <div className="bg-white rounded-lg p-3">
                  <p className="text-xs text-ink-muted">Period</p>
                  <p className="text-lg font-semibold text-ink">{keyUsage.period}</p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Webhooks Tab */}
      {activeTab === 'webhooks' && (
        <div className="space-y-4">
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hairline bg-surface-subtle">
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">URL</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Events</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                    <th className="text-right px-4 py-3 font-medium text-ink-muted">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {webhooks.length === 0 && (
                    <tr>
                      <td colSpan="4" className="px-4 py-12 text-center text-ink-muted">
                        No webhooks configured. Register one to receive event notifications.
                      </td>
                    </tr>
                  )}
                  {webhooks.map(wh => (
                    <React.Fragment key={wh.id}>
                      <tr className="border-b border-hairline hover:bg-surface-hover transition-colors">
                        <td className="px-4 py-3">
                          <code className="text-xs bg-surface-subtle px-2 py-0.5 rounded text-ink-muted font-mono max-w-[300px] truncate inline-block">
                            {wh.url}
                          </code>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-1 flex-wrap max-w-[300px]">
                            {wh.events?.slice(0, 3).map(e => (
                              <span key={e} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-surface-subtle text-ink-muted">
                                {e}
                              </span>
                            ))}
                            {(wh.events?.length || 0) > 3 && (
                              <span className="text-xs text-ink-muted">+{wh.events.length - 3}</span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          {wh.is_active ? (
                            <span className="inline-flex items-center gap-1 text-xs font-medium text-call-green">
                              <CheckCircle2 className="h-3 w-3" /> Active
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 text-xs font-medium text-ink-muted">
                              <XCircle className="h-3 w-3" /> Inactive
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center justify-end gap-1">
                            <button onClick={() => handleTestWebhook(wh.id)} className="p-1.5 rounded-lg text-ink-muted hover:text-accent hover:bg-accent-soft transition-colors" title="Test">
                              <Activity className="h-4 w-4" />
                            </button>
                            <button onClick={() => handleFetchLogs(wh.id)} className="p-1.5 rounded-lg text-ink-muted hover:text-accent hover:bg-accent-soft transition-colors" title="Logs">
                              <FileText className="h-4 w-4" />
                            </button>
                            <button onClick={() => handleUnregisterWebhook(wh.id)} className="p-1.5 rounded-lg text-ink-muted hover:text-red-500 hover:bg-red-50 transition-colors" title="Remove">
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                      {selectedWebhookLogs === wh.id && (
                        <tr>
                          <td colSpan="4" className="px-4 py-3 bg-surface-subtle">
                            <div className="flex items-center justify-between mb-2">
                              <h4 className="text-xs font-medium text-ink-muted uppercase tracking-wider">Delivery Logs</h4>
                              <button onClick={() => setSelectedWebhookLogs(null)} className="text-ink-muted hover:text-ink">
                                <X className="h-4 w-4" />
                              </button>
                            </div>
                            {loadingLogs ? (
                              <div className="flex items-center gap-2 text-ink-muted text-sm py-4">
                                <Loader2 className="h-4 w-4 animate-spin" /> Loading...
                              </div>
                            ) : webhookLogs.length === 0 ? (
                              <p className="text-sm text-ink-muted py-4">No delivery logs yet.</p>
                            ) : (
                              <div className="space-y-2 max-h-64 overflow-y-auto">
                                {webhookLogs.map(log => (
                                  <div key={log.id} className="flex items-center justify-between bg-white rounded-lg px-3 py-2 text-xs">
                                    <div className="flex items-center gap-3">
                                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full font-medium ${
                                        log.status === 'delivered' ? 'bg-call-green-soft text-call-green' :
                                        log.status === 'dead_letter' ? 'bg-red-50 text-red-500' :
                                        log.status === 'retrying' ? 'bg-call-amber-soft text-telecom-amber' :
                                        'bg-surface-subtle text-ink-muted'
                                      }`}>
                                        {log.status === 'delivered' ? <CheckCircle2 className="h-3 w-3" /> :
                                         log.status === 'dead_letter' ? <XCircle className="h-3 w-3" /> : null}
                                        {log.status}
                                      </span>
                                      <span className="text-ink-muted">{log.event_type}</span>
                                      <span className="text-ink-muted">{log.response_status ? `HTTP ${log.response_status}` : '-'}</span>
                                      <span className="text-ink-muted">{log.created_at ? new Date(log.created_at).toLocaleString() : ''}</span>
                                    </div>
                                    <div className="flex items-center gap-1">
                                      {log.status === 'dead_letter' || log.status === 'failed' ? (
                                        <button onClick={() => handleRetry(log.id)} className="p-1 rounded text-ink-muted hover:text-accent">
                                          <RefreshCw className="h-3 w-3" />
                                        </button>
                                      ) : null}
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Events Tab */}
      {activeTab === 'events' && (
        <div className="space-y-4">
          <p className="text-sm text-ink-muted">Available event types and their payload schemas for webhook subscriptions.</p>
          {Object.keys(eventCatalog).length === 0 && (
            <div className="card p-12 text-center text-ink-muted">
              No events available.
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {Object.entries(eventCatalog).map(([key, ev]) => (
              <div key={key} className="card p-5">
                <div className="flex items-center gap-2 mb-2">
                  <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-accent-soft text-accent">
                    {key}
                  </span>
                </div>
                <p className="text-sm text-ink-muted mb-3">{ev.description}</p>
                <div className="bg-surface-subtle rounded-lg p-3">
                  <pre className="text-xs font-mono text-ink leading-relaxed overflow-x-auto">
{JSON.stringify(ev.schema, null, 2)}</pre>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Create Key Modal */}
      {showCreateKeyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">Create API Key</h2>
              <button onClick={() => setShowCreateKeyModal(false)} className="p-1.5 rounded-lg hover:bg-surface-hover">
                <X className="h-5 w-5 text-ink-muted" />
              </button>
            </div>
            <form onSubmit={handleCreateKey} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Key Name</label>
                <input type="text" value={keyForm.name} onChange={e => setKeyForm({ ...keyForm, name: e.target.value })} className="input-field" placeholder="e.g., Production API Key" required />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Scopes</label>
                <div className="space-y-2 max-h-40 overflow-y-auto">
                  {ALL_SCOPES.map(scope => (
                    <label key={scope} className="flex items-center gap-2 cursor-pointer">
                      <input type="checkbox" checked={keyForm.scopes.includes(scope)} onChange={() => toggleScope(scope)} className="rounded border-hairline text-accent focus:ring-accent" />
                      <span className="text-sm text-ink">{scope}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Expires In (days)</label>
                <input type="number" value={keyForm.expires_in_days} onChange={e => setKeyForm({ ...keyForm, expires_in_days: parseInt(e.target.value) || 365 })} className="input-field" min="1" max="3650" />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowCreateKeyModal(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" className="btn-primary flex-1">
                  <Plus className="h-4 w-4" /> Create Key
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Show New Key Modal */}
      {showNewKeyModal && newKeyData && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-lg mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">API Key Created</h2>
              <button onClick={() => { setShowNewKeyModal(false); setNewKeyData(null) }} className="p-1.5 rounded-lg hover:bg-surface-hover">
                <X className="h-5 w-5 text-ink-muted" />
              </button>
            </div>
            <p className="text-sm text-ink-muted mb-4">Copy this key now. You won't be able to see it again.</p>
            <div className="bg-surface-subtle rounded-lg p-4 mb-4">
              <code className="text-sm font-mono text-ink break-all">{newKeyData.full_key}</code>
            </div>
            <div className="flex gap-3">
              <button onClick={() => copyToClipboard(newKeyData.full_key)} className="btn-primary flex-1">
                {copied ? <><CheckCircle2 className="h-4 w-4" /> Copied</> : <><Copy className="h-4 w-4" /> Copy</>}
              </button>
              <button onClick={() => { setShowNewKeyModal(false); setNewKeyData(null) }} className="btn-secondary flex-1">Done</button>
            </div>
          </div>
        </div>
      )}

      {/* Register Webhook Modal */}
      {showRegisterWebhookModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">Register Webhook</h2>
              <button onClick={() => setShowRegisterWebhookModal(false)} className="p-1.5 rounded-lg hover:bg-surface-hover">
                <X className="h-5 w-5 text-ink-muted" />
              </button>
            </div>
            <form onSubmit={handleRegisterWebhook} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Endpoint URL</label>
                <input type="url" value={webhookForm.url} onChange={e => setWebhookForm({ ...webhookForm, url: e.target.value })} className="input-field" placeholder="https://example.com/webhooks" required />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Events</label>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {ALL_EVENTS.map(ev => (
                    <label key={ev} className="flex items-center gap-2 cursor-pointer">
                      <input type="checkbox" checked={webhookForm.events.includes(ev)} onChange={() => toggleEvent(ev)} className="rounded border-hairline text-accent focus:ring-accent" />
                      <span className="text-sm text-ink">{ev}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Secret (optional)</label>
                <input type="text" value={webhookForm.secret} onChange={e => setWebhookForm({ ...webhookForm, secret: e.target.value })} className="input-field" placeholder="Leave blank to auto-generate" />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowRegisterWebhookModal(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" className="btn-primary flex-1">
                  <Plus className="h-4 w-4" /> Register
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
