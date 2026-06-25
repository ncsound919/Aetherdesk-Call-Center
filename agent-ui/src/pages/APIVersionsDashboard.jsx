import React, { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { versionsApi } from '../services/api'
import {
  GitBranch, Code, Clock, AlertTriangle, BarChart3, FileText
} from 'lucide-react'
import { toast } from 'sonner'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

export default function APIVersionsDashboard() {
  const { tenant } = useAuth()
  const [versions, setVersions] = useState([])
  const [usageStats, setUsageStats] = useState(null)
  const [changelog, setChangelog] = useState(null)
  const [migrationGuide, setMigrationGuide] = useState(null)
  const [activeTab, setActiveTab] = useState('versions')
  const [deprecateVersion, setDeprecateVersion] = useState('')
  const [sunsetDate, setSunsetDate] = useState('')
  const [fromVersion, setFromVersion] = useState('v1')
  const [toVersion, setToVersion] = useState('v4')

  const tabs = [
    { key: 'versions', label: 'Versions', icon: GitBranch },
    { key: 'deprecate', label: 'Deprecate', icon: Clock },
    { key: 'changelog', label: 'Changelog', icon: FileText },
    { key: 'usage', label: 'Usage Stats', icon: BarChart3 },
    { key: 'migration', label: 'Migration Guide', icon: Code },
  ]

  async function fetchVersions() {
    if (!tenant) return
    try {
      const res = await versionsApi.list({ tenant_id: tenant.id })
      setVersions(Array.isArray(res.data) ? res.data : [])
    } catch { setVersions([]) }
  }

  async function fetchUsage() {
    if (!tenant) return
    try {
      const res = await versionsApi.getUsageStats({ tenant_id: tenant.id })
      setUsageStats(res.data)
    } catch { setUsageStats(null) }
  }

  async function fetchChangelog(version) {
    if (!tenant) return
    try {
      const res = await versionsApi.getChangelog({ tenant_id: tenant.id, version })
      setChangelog(Array.isArray(res.data) ? res.data : [])
    } catch { setChangelog(null) }
  }

  async function handleDeprecate() {
    if (!deprecateVersion || !sunsetDate) return
    try {
      const res = await versionsApi.deprecate(deprecateVersion, { sunset_date: sunsetDate, tenant_id: tenant.id })
      if (res.data.success) {
        toast.success(`Version ${deprecateVersion} deprecated until ${sunsetDate}`)
        fetchVersions()
      } else {
        toast.error(res.data.error || 'Failed to deprecate')
      }
    } catch { toast.error('Failed to deprecate version') }
  }

  async function handleMigration() {
    if (!tenant) return
    try {
      const res = await versionsApi.getMigrationGuide({ from_version: fromVersion, to_version: toVersion, tenant_id: tenant.id })
      setMigrationGuide(res.data)
    } catch { setMigrationGuide(null) }
  }

  useEffect(() => { fetchVersions() }, [tenant])
  useEffect(() => {
    if (activeTab === 'usage') fetchUsage()
    if (activeTab === 'changelog') fetchChangelog(null)
  }, [activeTab, tenant])

  const statusColors = {
    active: 'bg-call-green-soft text-call-green',
    deprecated: 'bg-call-amber-soft text-call-amber',
    sunset: 'bg-red-50 text-red-500',
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-ink tracking-tight">API Versioning</h1>
        <p className="text-sm text-ink-muted mt-0.5">Manage API versions, deprecations, and migrations</p>
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

      {activeTab === 'versions' && (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hairline bg-surface-subtle">
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Version</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Release Date</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Sunset Date</th>
                </tr>
              </thead>
              <tbody>
                {versions.map((v, i) => (
                  <tr key={v.version || i} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                    <td className="px-4 py-3 font-mono font-medium text-ink">{v.version}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${statusColors[v.status] || 'bg-surface-subtle text-ink-muted'}`}>
                        {v.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-ink-muted">{v.release_date}</td>
                    <td className="px-4 py-3 text-ink-muted">{v.sunset_date || 'N/A'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'deprecate' && (
        <div className="card p-6 max-w-md">
          <h3 className="text-sm font-medium text-ink mb-4">Deprecate API Version</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1.5">Version</label>
              <select value={deprecateVersion} onChange={e => setDeprecateVersion(e.target.value)} className="input-field w-full">
                <option value="">Select version...</option>
                {versions.filter(v => v.status === 'active').map(v => (
                  <option key={v.version} value={v.version}>{v.version}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1.5">Sunset Date</label>
              <input type="date" value={sunsetDate} onChange={e => setSunsetDate(e.target.value)} className="input-field w-full" />
            </div>
            <button onClick={handleDeprecate} disabled={!deprecateVersion || !sunsetDate} className="btn-primary">
              <AlertTriangle className="h-4 w-4" /> Deprecate Version
            </button>
          </div>
        </div>
      )}

      {activeTab === 'changelog' && (
        <div className="space-y-4">
          {!changelog && <div className="card p-12 text-center text-ink-muted">Loading changelog...</div>}
          {changelog?.length === 0 && <div className="card p-12 text-center text-ink-muted">No changelog entries.</div>}
          {changelog?.map((v, i) => (
            <div key={i} className="card p-6">
              <div className="flex items-center gap-3 mb-2">
                <span className="font-mono font-semibold text-ink">{v.version}</span>
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${statusColors[v.status]}`}>{v.status}</span>
              </div>
              <p className="text-sm text-ink-muted mb-2">{v.changelog}</p>
              {v.migration_notes && (
                <div className="mt-2 p-3 rounded-lg bg-surface-subtle">
                  <p className="text-xs font-medium text-ink-muted mb-1">Migration Notes</p>
                  <p className="text-sm text-ink">{v.migration_notes}</p>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {activeTab === 'usage' && (
        <div className="card p-6">
          <h3 className="text-sm font-medium text-ink mb-4">Requests per Version</h3>
          {usageStats ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={Object.entries(usageStats).map(([v, d]) => ({ version: v, requests: d.total_requests || 0, tenants: d.active_tenants || 0 }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                <XAxis dataKey="version" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="requests" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <p className="text-sm text-ink-muted text-center py-12">No usage data available.</p>
          )}
        </div>
      )}

      {activeTab === 'migration' && (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-sm font-medium text-ink mb-4">Migration Guide</h3>
            <div className="flex items-end gap-4 mb-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">From</label>
                <select value={fromVersion} onChange={e => setFromVersion(e.target.value)} className="input-field">
                  {versions.map(v => <option key={v.version} value={v.version}>{v.version}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">To</label>
                <select value={toVersion} onChange={e => setToVersion(e.target.value)} className="input-field">
                  {versions.map(v => <option key={v.version} value={v.version}>{v.version}</option>)}
                </select>
              </div>
              <button onClick={handleMigration} className="btn-primary">
                <Code className="h-4 w-4" /> Get Guide
              </button>
            </div>
          </div>

          {migrationGuide && (
            <div className="card p-6">
              <h3 className="text-sm font-medium text-ink mb-3">
                {migrationGuide.from_version} → {migrationGuide.to_version}
              </h3>
              <p className="text-sm text-ink-muted mb-4">{migrationGuide.migration_notes}</p>
              {migrationGuide.breaking_changes?.length > 0 && (
                <div>
                  <p className="text-sm font-medium text-ink mb-2">Breaking Changes</p>
                  <ul className="space-y-1">
                    {migrationGuide.breaking_changes.map((change, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-ink-muted">
                        <AlertTriangle className="h-4 w-4 text-call-amber mt-0.5 shrink-0" />
                        {change}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
