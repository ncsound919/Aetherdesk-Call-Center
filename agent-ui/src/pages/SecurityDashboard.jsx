import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { securityApi } from '../services/api'
import {
  Shield, Lock, AlertTriangle, CheckCircle2, Search,
  Users, Key, Database, Loader2, Activity, X, ToggleLeft, ToggleRight
} from 'lucide-react'
import { toast } from 'sonner'

export default function SecurityDashboard() {
  const { tenant } = useAuth()
  const [activeTab, setActiveTab] = useState('pentest')
  const [loading, setLoading] = useState(false)
  const [scans, setScans] = useState([])
  const [selectedScan, setSelectedScan] = useState(null)
  const [wafRules, setWafRules] = useState([])
  const [wafEvents, setWafEvents] = useState([])
  const [classifications, setClassifications] = useState([])
  const [rbacResults, setRbacResults] = useState([])
  const [credAudit, setCredAudit] = useState(null)
  const [targetUrl, setTargetUrl] = useState('')
  const [classifyForm, setClassifyForm] = useState({ table: '', column: '', sensitivity: 'internal' })

  const fetchScans = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await securityApi.listScans(tenant.id)
      setScans(Array.isArray(res.data) ? res.data : [])
    } catch { setScans([]) }
  }, [tenant])

  const fetchWafRules = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await securityApi.getWafRules(tenant.id)
      setWafRules(Array.isArray(res.data) ? res.data : [])
    } catch { setWafRules([]) }
  }, [tenant])

  const fetchWafEvents = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await securityApi.getWafEvents(tenant.id)
      setWafEvents(Array.isArray(res.data) ? res.data : [])
    } catch { setWafEvents([]) }
  }, [tenant])

  const fetchClassifications = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await securityApi.getDataClassification(tenant.id)
      setClassifications(Array.isArray(res.data) ? res.data : [])
    } catch { setClassifications([]) }
  }, [tenant])

  const fetchCredAudit = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await securityApi.getCredentialAudit(tenant.id)
      setCredAudit(res.data)
    } catch { setCredAudit(null) }
  }, [tenant])

  useEffect(() => {
    fetchScans()
    fetchWafRules()
    fetchWafEvents()
  }, [fetchScans, fetchWafRules, fetchWafEvents])

  useEffect(() => {
    if (activeTab === 'classification') fetchClassifications()
    if (activeTab === 'rbac') fetchRbacResults()
    if (activeTab === 'credentials') fetchCredAudit()
  }, [activeTab, fetchClassifications, fetchCredAudit])

  async function handleRunScan(e) {
    e.preventDefault()
    if (!targetUrl) return
    setLoading(true)
    try {
      await securityApi.runScan(tenant.id, targetUrl)
      toast.success('Pen test scan started')
      setTargetUrl('')
      fetchScans()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Scan failed')
    } finally { setLoading(false) }
  }

  async function handleToggleRule(ruleId, enabled) {
    try {
      await securityApi.updateWafRule(ruleId, enabled ? 'disable' : 'enable')
      toast.success(`Rule ${enabled ? 'disabled' : 'enabled'}`)
      fetchWafRules()
    } catch { toast.error('Failed to update rule') }
  }

  async function handleClassify(e) {
    e.preventDefault()
    try {
      await securityApi.classifyField(tenant.id, classifyForm.table, classifyForm.column, classifyForm.sensitivity)
      toast.success('Field classified')
      fetchClassifications()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Classification failed')
    }
  }

  async function handleRunRbacAudit() {
    setLoading(true)
    try {
      const res = await securityApi.runRbacAudit(tenant.id)
      setRbacResults(res.data?.results || [])
      toast.success(`RBAC audit complete: ${res.data?.total_tests || 0} tests`)
    } catch (err) {
      toast.error('RBAC audit failed')
    } finally { setLoading(false) }
  }

  async function handleForceReset(userId) {
    try {
      await securityApi.forcePasswordReset(tenant.id, userId)
      toast.success('Password reset forced')
      fetchCredAudit()
    } catch { toast.error('Failed to force reset') }
  }

  async function fetchRbacResults() {
    if (!tenant) return
    try {
      const res = await securityApi.getRbacAuditResults(tenant.id)
      setRbacResults(Array.isArray(res.data) ? res.data : [])
    } catch { setRbacResults([]) }
  }

  async function handleViewScan(scan) {
    try {
      const res = await securityApi.getScan(scan.id)
      setSelectedScan(res.data)
    } catch { toast.error('Failed to load scan') }
  }

  const tabs = [
    { key: 'pentest', label: 'Pen Testing', icon: Search },
    { key: 'waf', label: 'WAF', icon: Shield },
    { key: 'classification', label: 'Data Classification', icon: Database },
    { key: 'rbac', label: 'RBAC', icon: Users },
    { key: 'credentials', label: 'Credentials', icon: Key },
  ]

  function renderSeverityBadge(severity) {
    const colors = { high: 'bg-red-100 text-red-700', medium: 'bg-amber-100 text-amber-700', low: 'bg-blue-100 text-blue-700' }
    return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${colors[severity] || 'bg-gray-100 text-gray-700'}`}>{severity}</span>
  }

  function renderStateBadge(state) {
    const colors = { completed: 'bg-green-100 text-green-700', running: 'bg-blue-100 text-blue-700', failed: 'bg-red-100 text-red-700' }
    return <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${colors[state] || 'bg-gray-100 text-gray-700'}`}>{state}</span>
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Security Hardening</h1>
          <p className="text-sm text-ink-muted mt-0.5">Pen testing, WAF, data classification, RBAC, and credential management</p>
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

      {activeTab === 'pentest' && (
        <div className="space-y-6">
          <form onSubmit={handleRunScan} className="card p-4 flex gap-3">
            <input type="url" value={targetUrl} onChange={e => setTargetUrl(e.target.value)}
              className="input-field flex-1" placeholder="https://example.com" required />
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
              Run Scan
            </button>
          </form>
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hairline bg-surface-subtle">
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Target</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Severity</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Started</th>
                    <th className="text-right px-4 py-3 font-medium text-ink-muted">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {scans.length === 0 && (
                    <tr><td colSpan="5" className="px-4 py-12 text-center text-ink-muted">No scans run yet.</td></tr>
                  )}
                  {scans.map(scan => (
                    <tr key={scan.id} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                      <td className="px-4 py-3 text-ink font-medium">{scan.target_url}</td>
                      <td className="px-4 py-3">{renderSeverityBadge(scan.severity)}</td>
                      <td className="px-4 py-3">{renderStateBadge(scan.status)}</td>
                      <td className="px-4 py-3 text-ink-muted">{new Date(scan.started_at).toLocaleString()}</td>
                      <td className="px-4 py-3 text-right">
                        <button onClick={() => handleViewScan(scan)} className="text-accent hover:underline text-xs font-medium">View Findings</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          {selectedScan && (
            <div className="card p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-ink">Findings — {selectedScan.target_url}</h3>
                <button onClick={() => setSelectedScan(null)} className="p-1 rounded hover:bg-surface-hover"><X className="h-4 w-4" /></button>
              </div>
              {Array.isArray(selectedScan.findings_json) ? selectedScan.findings_json.map((f, i) => (
                <div key={f.id || i} className="border border-hairline rounded-lg p-4 mb-3">
                  <div className="flex items-center gap-2 mb-1">
                    {renderSeverityBadge(f.severity)}
                    <span className="text-sm font-medium text-ink">{f.type.toUpperCase()}</span>
                    <span className="text-xs text-ink-muted">CVSS: {f.cvss_score}</span>
                  </div>
                  <p className="text-sm text-ink-muted mb-1">{f.description}</p>
                  <p className="text-xs text-ink-muted"><span className="font-medium">Endpoint:</span> {f.endpoint}</p>
                  <p className="text-xs text-ink-muted"><span className="font-medium">Remediation:</span> {f.remediation}</p>
                </div>
              )) : <p className="text-sm text-ink-muted">No structured findings</p>}
            </div>
          )}
        </div>
      )}

      {activeTab === 'waf' && (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-sm font-semibold text-ink mb-4">WAF Rules</h3>
            <div className="space-y-2">
              {wafRules.map(rule => (
                <div key={rule.id} className="flex items-center justify-between p-3 border border-hairline rounded-lg">
                  <div className="flex items-center gap-3">
                    <button onClick={() => handleToggleRule(rule.id, rule.enabled)} className="text-ink-muted hover:text-accent">
                      {rule.enabled ? <ToggleRight className="h-5 w-5 text-green-500" /> : <ToggleLeft className="h-5 w-5" />}
                    </button>
                    <div>
                      <p className="text-sm font-medium text-ink">{rule.name}</p>
                      <p className="text-xs text-ink-muted">Action: {rule.action} | Priority: {rule.priority}</p>
                    </div>
                  </div>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                    rule.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
                  }`}>{rule.enabled ? 'Enabled' : 'Disabled'}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="card overflow-hidden">
            <div className="px-4 py-3 border-b border-hairline">
              <h3 className="text-sm font-semibold text-ink">Blocked Events</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hairline bg-surface-subtle">
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Rule</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Action</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Source IP</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Path</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Time</th>
                  </tr>
                </thead>
                <tbody>
                  {wafEvents.length === 0 && (
                    <tr><td colSpan="5" className="px-4 py-12 text-center text-ink-muted">No blocked events.</td></tr>
                  )}
                  {wafEvents.map(evt => (
                    <tr key={evt.id} className="border-b border-hairline">
                      <td className="px-4 py-3 text-ink">{evt.rule_id}</td>
                      <td className="px-4 py-3"><span className="text-red-600 text-xs font-medium">{evt.action}</span></td>
                      <td className="px-4 py-3 text-ink-muted font-mono text-xs">{evt.source_ip}</td>
                      <td className="px-4 py-3 text-ink-muted text-xs">{evt.request_path}</td>
                      <td className="px-4 py-3 text-ink-muted text-xs">{new Date(evt.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'classification' && (
        <div className="space-y-6">
          <form onSubmit={handleClassify} className="card p-4">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
              <input type="text" placeholder="Table name" value={classifyForm.table}
                onChange={e => setClassifyForm({ ...classifyForm, table: e.target.value })}
                className="input-field" required />
              <input type="text" placeholder="Column name" value={classifyForm.column}
                onChange={e => setClassifyForm({ ...classifyForm, column: e.target.value })}
                className="input-field" required />
              <select value={classifyForm.sensitivity}
                onChange={e => setClassifyForm({ ...classifyForm, sensitivity: e.target.value })}
                className="input-field">
                <option value="public">Public</option>
                <option value="internal">Internal</option>
                <option value="confidential">Confidential</option>
                <option value="restricted">Restricted</option>
              </select>
              <button type="submit" className="btn-primary"><Database className="h-4 w-4" /> Classify</button>
            </div>
          </form>
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hairline bg-surface-subtle">
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Schema</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Table</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Column</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Sensitivity</th>
                  </tr>
                </thead>
                <tbody>
                  {classifications.length === 0 && (
                    <tr><td colSpan="4" className="px-4 py-12 text-center text-ink-muted">No fields classified yet.</td></tr>
                  )}
                  {classifications.map(c => (
                    <tr key={c.id} className="border-b border-hairline">
                      <td className="px-4 py-3 text-ink-muted text-xs">{c.schema_name}</td>
                      <td className="px-4 py-3 text-ink font-medium">{c.table_name}</td>
                      <td className="px-4 py-3 text-ink-muted font-mono text-xs">{c.column_name}</td>
                      <td className="px-4 py-3">{renderSeverityBadge(c.sensitivity)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'rbac' && (
        <div className="space-y-6">
          <div className="card p-4 flex items-center justify-between">
            <p className="text-sm text-ink-muted">Test all role/resource/action combinations against Casbin policies</p>
            <button onClick={handleRunRbacAudit} className="btn-primary" disabled={loading}>
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Activity className="h-4 w-4" />}
              Run Audit
            </button>
          </div>
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hairline bg-surface-subtle">
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Role</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Resource</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Action</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Expected</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Actual</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {rbacResults.length === 0 && (
                    <tr><td colSpan="6" className="px-4 py-12 text-center text-ink-muted">Click "Run Audit" to test RBAC policies.</td></tr>
                  )}
                  {rbacResults.map((r, i) => (
                    <tr key={r.id || i} className="border-b border-hairline">
                      <td className="px-4 py-3 text-ink font-medium">{r.role}</td>
                      <td className="px-4 py-3 text-ink-muted">{r.resource}</td>
                      <td className="px-4 py-3 text-ink-muted">{r.action}</td>
                      <td className="px-4 py-3">{r.expected ? <CheckCircle2 className="h-4 w-4 text-green-500" /> : <X className="h-4 w-4 text-red-400" />}</td>
                      <td className="px-4 py-3">{r.actual ? <CheckCircle2 className="h-4 w-4 text-green-500" /> : <X className="h-4 w-4 text-red-400" />}</td>
                      <td className="px-4 py-3">{r.passed ? <span className="text-green-600 text-xs font-medium">PASS</span> : <span className="text-red-600 text-xs font-medium">FAIL</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'credentials' && (
        <div className="space-y-6">
          {credAudit && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="card p-6 flex flex-col items-center">
                <p className="text-sm text-ink-muted mb-1">Total Users</p>
                <p className="text-2xl font-semibold text-ink">{credAudit.total_users}</p>
              </div>
              <div className="card p-6 flex flex-col items-center">
                <p className="text-sm text-ink-muted mb-1">Critical</p>
                <p className="text-2xl font-semibold text-red-500">{credAudit.critical}</p>
              </div>
              <div className="card p-6 flex flex-col items-center">
                <p className="text-sm text-ink-muted mb-1">OK</p>
                <p className="text-2xl font-semibold text-green-500">{credAudit.ok}</p>
              </div>
            </div>
          )}
          <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hairline bg-surface-subtle">
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">User ID</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Email</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                    <th className="text-right px-4 py-3 font-medium text-ink-muted">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {credAudit?.users?.map(u => (
                    <tr key={u.user_id} className="border-b border-hairline">
                      <td className="px-4 py-3 text-ink-muted font-mono text-xs">{u.user_id}</td>
                      <td className="px-4 py-3 text-ink">{u.email}</td>
                      <td className="px-4 py-3">{u.status === 'critical' ? <span className="text-red-600 text-xs font-medium flex items-center gap-1"><AlertTriangle className="h-3 w-3" /> Critical</span> : <span className="text-green-600 text-xs font-medium flex items-center gap-1"><CheckCircle2 className="h-3 w-3" /> OK</span>}</td>
                      <td className="px-4 py-3 text-right">
                        <button onClick={() => handleForceReset(u.user_id)} className="text-xs text-accent hover:underline font-medium">Force Reset</button>
                      </td>
                    </tr>
                  ))}
                  {(!credAudit?.users || credAudit.users.length === 0) && (
                    <tr><td colSpan="4" className="px-4 py-12 text-center text-ink-muted">No credential data.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
