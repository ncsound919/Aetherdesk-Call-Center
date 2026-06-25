import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { bcApi } from '../services/api'
import {
  Shield, Activity, AlertTriangle, FileText, RefreshCw, Database, Globe,
  Plus, Loader2, CheckCircle2, X
} from 'lucide-react'
import { toast } from 'sonner'

export default function BusinessContinuityDashboard() {
  const { tenant } = useAuth()
  const [activeTab, setActiveTab] = useState('failover')
  const [failoverTests, setFailoverTests] = useState([])
  const [multiRegion, setMultiRegion] = useState(null)
  const [chaosExps, setChaosExps] = useState([])
  const [contracts, setContracts] = useState([])
  const [contractAlerts, setContractAlerts] = useState([])
  const [channels, setChannels] = useState([])
  const [loading, setLoading] = useState(false)
  const [runningTest, setRunningTest] = useState(false)
  const [showContractModal, setShowContractModal] = useState(false)
  const [contractForm, setContractForm] = useState({ vendor: '', terms: '', renewal_date: '', cost: '' })
  const [showChannelModal, setShowChannelModal] = useState(false)
  const [channelForm, setChannelForm] = useState({ channel_type: 'sms', config: '' })
  const [chaosForm, setChaosForm] = useState({ target: '', fault_type: '', duration_seconds: 30 })

  const fetchFailoverData = useCallback(async () => {
    if (!tenant) return
    try {
      const [ftRes, mrRes] = await Promise.all([
        bcApi.listFailoverTests(tenant.id),
        bcApi.getMultiRegionStatus(tenant.id),
      ])
      setFailoverTests(Array.isArray(ftRes.data) ? ftRes.data : [])
      setMultiRegion(mrRes.data)
    } catch { /* ignore */ }
  }, [tenant])

  const fetchChaosData = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await bcApi.listChaosExperiments(tenant.id)
      setChaosExps(Array.isArray(res.data) ? res.data : [])
    } catch { setChaosExps([]) }
  }, [tenant])

  const fetchContractData = useCallback(async () => {
    if (!tenant) return
    try {
      const [cRes, aRes] = await Promise.all([
        bcApi.listContracts(tenant.id),
        bcApi.getContractAlerts(tenant.id),
      ])
      setContracts(Array.isArray(cRes.data) ? cRes.data : [])
      setContractAlerts(Array.isArray(aRes.data) ? aRes.data : [])
    } catch { /* ignore */ }
  }, [tenant])

  const fetchChannelData = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await bcApi.listBackupChannels(tenant.id)
      setChannels(Array.isArray(res.data) ? res.data : [])
    } catch { setChannels([]) }
  }, [tenant])

  useEffect(() => { if (activeTab === 'failover') { setLoading(true); fetchFailoverData().finally(() => setLoading(false)) } }, [activeTab, fetchFailoverData])
  useEffect(() => { if (activeTab === 'chaos') fetchChaosData() }, [activeTab, fetchChaosData])
  useEffect(() => { if (activeTab === 'contracts') fetchContractData() }, [activeTab, fetchContractData])
  useEffect(() => { if (activeTab === 'channels') fetchChannelData() }, [activeTab, fetchChannelData])

  async function handleRunTest(service) {
    setRunningTest(true)
    try {
      const res = await bcApi.runFailoverTest({ service })
      toast.success(`Failover test for ${service}: ${res.data.status}`)
      fetchFailoverData()
    } catch (err) { toast.error(err.response?.data?.detail || 'Test failed') }
    finally { setRunningTest(false) }
  }

  async function handleRunChaos(e) {
    e.preventDefault()
    try {
      await bcApi.runChaos(chaosForm)
      toast.success('Chaos experiment started')
      setChaosForm({ target: '', fault_type: '', duration_seconds: 30 })
      fetchChaosData()
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
  }

  async function handleCreateContract(e) {
    e.preventDefault()
    try {
      await bcApi.createContract({ ...contractForm, cost: parseFloat(contractForm.cost) || null })
      toast.success('Contract created')
      setShowContractModal(false)
      setContractForm({ vendor: '', terms: '', renewal_date: '', cost: '' })
      fetchContractData()
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
  }

  async function handleConfigureChannel(e) {
    e.preventDefault()
    try {
      let config = {}
      try { config = JSON.parse(channelForm.config) } catch { config = { endpoint: channelForm.config } }
      await bcApi.configureBackupChannel({ channel_type: channelForm.channel_type, config })
      toast.success('Backup channel configured')
      setShowChannelModal(false)
      setChannelForm({ channel_type: 'sms', config: '' })
      fetchChannelData()
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
  }

  async function handleTestChannel(channelType) {
    try {
      const res = await bcApi.testBackupChannel(channelType)
      toast.success(res.data.message || 'Test sent')
      fetchChannelData()
    } catch (err) { toast.error('Test failed') }
  }

  const tabs = [
    { key: 'failover', label: 'Failover', icon: Shield },
    { key: 'chaos', label: 'Chaos Engineering', icon: Activity },
    { key: 'contracts', label: 'Contracts', icon: FileText },
    { key: 'channels', label: 'Backup Channels', icon: RefreshCw },
  ]

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Business Continuity</h1>
          <p className="text-sm text-ink-muted mt-0.5">Disaster recovery, failover testing, and vendor contracts</p>
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

      {loading && <div className="card p-12 flex items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-accent" /></div>}

      {!loading && activeTab === 'failover' && (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-sm font-medium text-ink mb-4 flex items-center gap-2"><Database className="h-4 w-4" /> Run Failover Test</h3>
            <div className="flex gap-3 flex-wrap">
              {['telephony', 'database', 'llm'].map(service => (
                <button key={service} onClick={() => handleRunTest(service)} disabled={runningTest}
                  className="btn-secondary flex items-center gap-2">
                  {runningTest ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                  Test {service}
                </button>
              ))}
            </div>
          </div>

          {multiRegion && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {['primary', 'standby'].map(region => {
                const r = multiRegion[region] || {}
                return (
                  <div key={region} className="card p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Globe className="h-4 w-4 text-accent" />
                      <span className="text-sm font-medium text-ink capitalize">{region} — {r.region}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                        r.status === 'healthy' ? 'bg-call-green-soft text-call-green' : 'bg-red-50 text-red-600'
                      }`}>{r.status}</span>
                      <span className="text-xs text-ink-muted">{r.latency_ms}ms</span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          <div className="card overflow-hidden">
            <div className="px-4 py-3 border-b border-hairline"><h3 className="text-sm font-medium text-ink">Test History</h3></div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hairline bg-surface-subtle">
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Service</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Duration</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {failoverTests.map(t => (
                    <tr key={t.id} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                      <td className="px-4 py-3 font-medium text-ink">{t.service}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          t.status === 'passed' ? 'bg-call-green-soft text-call-green' :
                          t.status === 'failed' ? 'bg-red-50 text-red-600' : 'bg-amber-50 text-amber-600'
                        }`}>{t.status}</span>
                      </td>
                      <td className="px-4 py-3 text-ink-muted">{t.duration_seconds}s</td>
                      <td className="px-4 py-3 text-ink-muted">{t.created_at ? new Date(t.created_at).toLocaleString() : ''}</td>
                    </tr>
                  ))}
                  {failoverTests.length === 0 && (
                    <tr><td colSpan="4" className="px-4 py-12 text-center text-ink-muted">No tests run yet</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {!loading && activeTab === 'chaos' && (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-sm font-medium text-ink mb-4 flex items-center gap-2"><AlertTriangle className="h-4 w-4" /> Run Chaos Experiment</h3>
            <form onSubmit={handleRunChaos} className="flex gap-3 items-end flex-wrap">
              <div>
                <label className="block text-xs font-medium text-ink mb-1">Target</label>
                <input type="text" value={chaosForm.target} onChange={e => setChaosForm({ ...chaosForm, target: e.target.value })} className="input-field text-sm" placeholder="e.g. telephony, database" required />
              </div>
              <div>
                <label className="block text-xs font-medium text-ink mb-1">Fault Type</label>
                <input type="text" value={chaosForm.fault_type} onChange={e => setChaosForm({ ...chaosForm, fault_type: e.target.value })} className="input-field text-sm" placeholder="e.g. latency, timeout" required />
              </div>
              <div>
                <label className="block text-xs font-medium text-ink mb-1">Duration (s)</label>
                <input type="number" value={chaosForm.duration_seconds} onChange={e => setChaosForm({ ...chaosForm, duration_seconds: parseInt(e.target.value) })} className="input-field text-sm w-24" min={5} />
              </div>
              <button type="submit" className="btn-primary"><Activity className="h-4 w-4" /> Start</button>
            </form>
          </div>

          <div className="card overflow-hidden">
            <div className="px-4 py-3 border-b border-hairline"><h3 className="text-sm font-medium text-ink">Experiment History</h3></div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hairline bg-surface-subtle">
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Target</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Fault Type</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Duration</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {chaosExps.map(e => (
                    <tr key={e.id} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                      <td className="px-4 py-3 font-medium text-ink">{e.target}</td>
                      <td className="px-4 py-3 text-ink-muted">{e.fault_type}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          e.status === 'completed' ? 'bg-call-green-soft text-call-green' :
                          e.status === 'running' ? 'bg-accent-soft text-accent' : 'bg-amber-50 text-amber-600'
                        }`}>{e.status}</span>
                      </td>
                      <td className="px-4 py-3 text-ink-muted">{e.duration_seconds}s</td>
                      <td className="px-4 py-3 text-ink-muted">{e.created_at ? new Date(e.created_at).toLocaleString() : ''}</td>
                    </tr>
                  ))}
                  {chaosExps.length === 0 && (
                    <tr><td colSpan="5" className="px-4 py-12 text-center text-ink-muted">No experiments yet</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {!loading && activeTab === 'contracts' && (
        <div className="space-y-6">
          <div className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-medium text-ink">Vendor Contracts</h3>
              <button onClick={() => setShowContractModal(true)} className="btn-primary"><Plus className="h-4 w-4" /> Add Contract</button>
            </div>
            {contractAlerts.length > 0 && (
              <div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg">
                <p className="text-xs font-medium text-amber-700 flex items-center gap-2"><AlertTriangle className="h-3 w-3" /> {contractAlerts.length} upcoming renewal{contractAlerts.length > 1 ? 's' : ''}</p>
                {contractAlerts.map(a => (
                  <p key={a.id} className="text-xs text-amber-600 mt-1">{a.vendor} — renews {a.renewal_date}</p>
                ))}
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hairline bg-surface-subtle">
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Vendor</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Renewal</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {contracts.map(c => (
                    <tr key={c.id} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                      <td className="px-4 py-3 font-medium text-ink">{c.vendor}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          c.status === 'active' ? 'bg-call-green-soft text-call-green' : 'bg-surface-subtle text-ink-muted'
                        }`}>{c.status}</span>
                      </td>
                      <td className="px-4 py-3 text-ink-muted">{c.renewal_date || '—'}</td>
                      <td className="px-4 py-3 text-ink-muted">{c.cost ? `$${c.cost}` : '—'}</td>
                    </tr>
                  ))}
                  {contracts.length === 0 && (
                    <tr><td colSpan="4" className="px-4 py-12 text-center text-ink-muted">No contracts</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {!loading && activeTab === 'channels' && (
        <div className="space-y-6">
          <div className="card p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-medium text-ink">Backup Channels</h3>
              <button onClick={() => setShowChannelModal(true)} className="btn-primary"><Plus className="h-4 w-4" /> Configure</button>
            </div>
            <div className="space-y-3">
              {channels.map(ch => (
                <div key={ch.id} className="flex items-center justify-between p-3 border border-hairline rounded-lg">
                  <div className="flex items-center gap-3">
                    <RefreshCw className="h-4 w-4 text-accent" />
                    <div>
                      <p className="text-sm font-medium text-ink capitalize">{ch.channel_type}</p>
                      <p className="text-xs text-ink-muted">Last test: {ch.last_test_at ? new Date(ch.last_test_at).toLocaleString() : 'Never'}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                      ch.status === 'active' ? 'bg-call-green-soft text-call-green' : 'bg-surface-subtle text-ink-muted'
                    }`}>{ch.status}</span>
                    <button onClick={() => handleTestChannel(ch.channel_type)} className="btn-secondary text-xs py-1.5">
                      <RefreshCw className="h-3 w-3" /> Test
                    </button>
                  </div>
                </div>
              ))}
              {channels.length === 0 && <p className="text-sm text-ink-muted">No backup channels configured</p>}
            </div>
          </div>
        </div>
      )}

      {showContractModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">Add Contract</h2>
              <button onClick={() => setShowContractModal(false)} className="p-1.5 rounded-lg hover:bg-surface-hover"><X className="h-5 w-5 text-ink-muted" /></button>
            </div>
            <form onSubmit={handleCreateContract} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Vendor</label>
                <input type="text" value={contractForm.vendor} onChange={e => setContractForm({ ...contractForm, vendor: e.target.value })} className="input-field" required />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Terms</label>
                <textarea value={contractForm.terms} onChange={e => setContractForm({ ...contractForm, terms: e.target.value })} className="input-field" rows={3} />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Renewal Date</label>
                <input type="date" value={contractForm.renewal_date} onChange={e => setContractForm({ ...contractForm, renewal_date: e.target.value })} className="input-field" />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Cost ($)</label>
                <input type="number" step="0.01" value={contractForm.cost} onChange={e => setContractForm({ ...contractForm, cost: e.target.value })} className="input-field" />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowContractModal(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" className="btn-primary flex-1"><Plus className="h-4 w-4" /> Create</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showChannelModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">Configure Backup Channel</h2>
              <button onClick={() => setShowChannelModal(false)} className="p-1.5 rounded-lg hover:bg-surface-hover"><X className="h-5 w-5 text-ink-muted" /></button>
            </div>
            <form onSubmit={handleConfigureChannel} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Channel Type</label>
                <select value={channelForm.channel_type} onChange={e => setChannelForm({ ...channelForm, channel_type: e.target.value })} className="input-field">
                  <option value="sms">SMS</option>
                  <option value="email">Email</option>
                  <option value="slack">Slack</option>
                  <option value="pagerduty">PagerDuty</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Config (JSON or endpoint)</label>
                <input type="text" value={channelForm.config} onChange={e => setChannelForm({ ...channelForm, config: e.target.value })} className="input-field" placeholder='{"webhook": "https://..."}' />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowChannelModal(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" className="btn-primary flex-1"><Plus className="h-4 w-4" /> Configure</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
