import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { cdpApi } from '../services/api'
import {
  Users, Search, Tag, BarChart3, TrendingUp, Activity,
  Heart, Target, Clock, UserCheck, Loader2, Plus, X
} from 'lucide-react'
import { toast } from 'sonner'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell
} from 'recharts'

export default function CDPDashboard() {
  const { tenant } = useAuth()
  const [activeTab, setActiveTab] = useState('profiles')
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState([])
  const [selectedProfile, setSelectedProfile] = useState(null)
  const [profileData, setProfileData] = useState(null)
  const [segments, setSegments] = useState([])
  const [segmentForm, setSegmentForm] = useState({ name: '', criteria: '{}' })
  const [cohortData, setCohortData] = useState(null)
  const [overview, setOverview] = useState(null)
  const [loading, setLoading] = useState(false)
  const [newTag, setNewTag] = useState('')

  const fetchSegments = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await cdpApi.listSegments({ tenant_id: tenant.id })
      setSegments(Array.isArray(res.data) ? res.data : [])
    } catch { setSegments([]) }
  }, [tenant])

  const fetchOverview = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await cdpApi.getOverview({ tenant_id: tenant.id })
      setOverview(res.data)
    } catch { setOverview(null) }
  }, [tenant])

  const fetchCohort = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await cdpApi.getCohort({ tenant_id: tenant.id })
      setCohortData(res.data)
    } catch { setCohortData(null) }
  }, [tenant])

  useEffect(() => {
    fetchSegments()
    fetchOverview()
  }, [fetchSegments, fetchOverview])

  useEffect(() => {
    if (activeTab === 'analytics') fetchCohort()
  }, [activeTab, fetchCohort])

  async function handleSearch(e) {
    e.preventDefault()
    if (!tenant || !searchQuery.trim()) return
    setLoading(true)
    try {
      const res = await cdpApi.search({ q: searchQuery, tenant_id: tenant.id })
      setSearchResults(Array.isArray(res.data) ? res.data : [])
      setSelectedProfile(null)
      setProfileData(null)
    } catch { setSearchResults([]) }
    finally { setLoading(false) }
  }

  async function handleSelectProfile(profile) {
    setSelectedProfile(profile)
    setLoading(true)
    try {
      const res = await cdpApi.getProfile(profile.id, { params: { tenant_id: tenant.id } })
      setProfileData(res.data)
    } catch { setProfileData(null) }
    finally { setLoading(false) }
  }

  async function handleAddTag() {
    if (!newTag.trim() || !profileData) return
    try {
      const res = await cdpApi.addTags(profileData.profile.id, { tags: [newTag.trim()] })
      setProfileData(prev => ({ ...prev, profile: { ...prev.profile, tags: res.data.tags } }))
      setNewTag('')
      toast.success('Tag added')
    } catch { toast.error('Failed to add tag') }
  }

  async function handleCreateSegment(e) {
    e.preventDefault()
    if (!tenant) return
    let criteria
    try {
      criteria = JSON.parse(segmentForm.criteria)
    } catch {
      toast.error('Invalid JSON in criteria')
      return
    }
    try {
      await cdpApi.createSegment({ name: segmentForm.name, criteria, tenant_id: tenant.id })
      toast.success('Segment created')
      setSegmentForm({ name: '', criteria: '{}' })
      fetchSegments()
    } catch { toast.error('Failed to create segment') }
  }

  async function handleEvaluateSegment(segmentId) {
    try {
      const res = await cdpApi.evaluateSegment(segmentId, { params: { tenant_id: tenant.id } })
      toast.success(`Segment evaluated: ${res.data.length} customers`)
    } catch { toast.error('Failed to evaluate segment') }
  }

  const tabs = [
    { key: 'profiles', label: 'Profiles', icon: Users },
    { key: 'segments', label: 'Segments', icon: Target },
    { key: 'analytics', label: 'Analytics', icon: BarChart3 },
  ]

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Customer Data Platform</h1>
          <p className="text-sm text-ink-muted mt-0.5">Unified customer profiles, segments, and analytics</p>
        </div>
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

      {activeTab === 'profiles' && (
        <div className="space-y-6">
          <form onSubmit={handleSearch} className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-ink-muted" />
              <input
                type="text" value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search by name, phone, or email..."
                className="input-field pl-9"
              />
            </div>
            <button type="submit" className="btn-primary">
              <Search className="h-4 w-4" /> Search
            </button>
          </form>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-1">
              <div className="card overflow-hidden">
                <div className="p-3 border-b border-hairline bg-surface-subtle">
                  <span className="text-sm font-medium text-ink">Results ({searchResults.length})</span>
                </div>
                {searchResults.length === 0 && (
                  <div className="p-6 text-center text-sm text-ink-muted">
                    {searchQuery ? 'No customers found' : 'Search for a customer above'}
                  </div>
                )}
                {searchResults.map(p => (
                  <button
                    key={p.id}
                    onClick={() => handleSelectProfile(p)}
                    className={`w-full text-left p-3 border-b border-hairline hover:bg-surface-hover transition-colors ${
                      selectedProfile?.id === p.id ? 'bg-accent-soft' : ''
                    }`}
                  >
                    <p className="text-sm font-medium text-ink">{p.name || 'Unnamed'}</p>
                    <p className="text-xs text-ink-muted">{p.phone || p.email || p.id}</p>
                  </button>
                ))}
              </div>
            </div>

            <div className="lg:col-span-2">
              {loading && !profileData && (
                <div className="card p-12 flex items-center justify-center">
                  <Loader2 className="h-6 w-6 animate-spin text-accent" />
                </div>
              )}
              {profileData && (
                <div className="space-y-4">
                  <div className="card p-6">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-sm font-medium text-ink">{profileData.profile.name || 'Customer'}</h3>
                      <div className="flex items-center gap-2">
                        {profileData.rfm && (
                          <span className="text-xs bg-accent-soft text-accent px-2 py-0.5 rounded-full font-medium">
                            RFM: {profileData.rfm.rfm_segment}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3 text-sm">
                      <div><span className="text-ink-muted">Phone:</span> {profileData.profile.phone || '—'}</div>
                      <div><span className="text-ink-muted">Email:</span> {profileData.profile.email || '—'}</div>
                      <div><span className="text-ink-muted">External ID:</span> {profileData.profile.external_id || '—'}</div>
                      <div><span className="text-ink-muted">First Seen:</span> {profileData.profile.first_seen_at ? new Date(profileData.profile.first_seen_at).toLocaleDateString() : '—'}</div>
                    </div>
                  </div>

                  <div className="card p-6">
                    <h3 className="text-sm font-medium text-ink mb-3 flex items-center gap-2"><Tag className="h-4 w-4" /> Tags</h3>
                    <div className="flex flex-wrap gap-2 mb-3">
                      {(profileData.profile.tags || []).map((t, i) => (
                        <span key={i} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-accent-soft text-accent">{t}</span>
                      ))}
                      {(profileData.profile.tags || []).length === 0 && <span className="text-xs text-ink-muted">No tags</span>}
                    </div>
                    <div className="flex gap-2">
                      <input type="text" value={newTag} onChange={e => setNewTag(e.target.value)} placeholder="Add tag..." className="input-field text-sm flex-1" />
                      <button onClick={handleAddTag} className="btn-primary text-sm"><Plus className="h-3 w-3" /> Add</button>
                    </div>
                  </div>

                  {profileData.rfm && (
                    <div className="card p-6">
                      <h3 className="text-sm font-medium text-ink mb-3 flex items-center gap-2"><Activity className="h-4 w-4" /> RFM Scores</h3>
                      <div className="grid grid-cols-3 gap-4 text-center">
                        <div className="bg-surface-subtle rounded-lg p-3">
                          <p className="text-xs text-ink-muted">Recency</p>
                          <p className="text-lg font-semibold text-ink">{profileData.rfm.r_score}/5</p>
                          <p className="text-xs text-ink-muted">{profileData.rfm.recency_days}d ago</p>
                        </div>
                        <div className="bg-surface-subtle rounded-lg p-3">
                          <p className="text-xs text-ink-muted">Frequency</p>
                          <p className="text-lg font-semibold text-ink">{profileData.rfm.f_score}/5</p>
                          <p className="text-xs text-ink-muted">{profileData.rfm.frequency} interactions</p>
                        </div>
                        <div className="bg-surface-subtle rounded-lg p-3">
                          <p className="text-xs text-ink-muted">Monetary</p>
                          <p className="text-lg font-semibold text-ink">{profileData.rfm.m_score}/5</p>
                          <p className="text-xs text-ink-muted">{Math.round(profileData.rfm.monetary_seconds / 60)} min</p>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="card p-6">
                    <h3 className="text-sm font-medium text-ink mb-3 flex items-center gap-2"><Clock className="h-4 w-4" /> Interaction Timeline</h3>
                    <div className="space-y-2 max-h-80 overflow-y-auto">
                      {(!profileData.calls || profileData.calls.length === 0) && (
                        <p className="text-sm text-ink-muted">No interactions recorded</p>
                      )}
                      {(profileData.calls || []).slice(0, 20).map((c, i) => (
                        <div key={i} className="flex items-center gap-3 p-2 rounded-lg bg-surface-subtle text-sm">
                          <span className={`h-2 w-2 rounded-full ${
                            c.sentiment === 'positive' ? 'bg-call-green' :
                            c.sentiment === 'negative' ? 'bg-red-400' : 'bg-ink-muted'
                          }`} />
                          <span className="text-ink-muted flex-1">{c.interaction_type || 'call'}</span>
                          <span className="text-ink-muted text-xs">{c.created_at ? new Date(c.created_at).toLocaleString() : ''}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {profileData.csat_surveys && profileData.csat_surveys.length > 0 && (
                    <div className="card p-6">
                      <h3 className="text-sm font-medium text-ink mb-3 flex items-center gap-2"><Heart className="h-4 w-4" /> CSAT Scores</h3>
                      <div className="space-y-2">
                        {profileData.csat_surveys.map((s, i) => (
                          <div key={i} className="flex items-center gap-3 p-2 rounded-lg bg-surface-subtle text-sm">
                            <span className="text-lg">{'★'.repeat(s.rating)}{'☆'.repeat(5 - s.rating)}</span>
                            <span className="text-ink-muted text-xs">{s.created_at ? new Date(s.created_at).toLocaleString() : ''}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'segments' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="card p-6">
            <h3 className="text-sm font-medium text-ink mb-4">Create Segment</h3>
            <form onSubmit={handleCreateSegment} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Name</label>
                <input type="text" value={segmentForm.name} onChange={e => setSegmentForm({ ...segmentForm, name: e.target.value })} className="input-field" placeholder="e.g. High Value Customers" required />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Criteria (JSON)</label>
                <textarea value={segmentForm.criteria} onChange={e => setSegmentForm({ ...segmentForm, criteria: e.target.value })} className="input-field font-mono text-xs" rows={6}
                  placeholder='{"min_calls": 10, "min_csat": 4, "max_recency_days": 30}' />
              </div>
              <button type="submit" className="btn-primary"><Plus className="h-4 w-4" /> Create Segment</button>
            </form>
          </div>

          <div>
            <h3 className="text-sm font-medium text-ink mb-3">Saved Segments ({segments.length})</h3>
            <div className="space-y-3">
              {segments.length === 0 && <div className="card p-6 text-center text-sm text-ink-muted">No segments created yet</div>}
              {segments.map(s => (
                <div key={s.id} className="card p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-sm font-medium text-ink">{s.name}</h4>
                    <span className="text-xs bg-surface-subtle text-ink-muted px-2 py-0.5 rounded-full">{s.member_count || 0} members</span>
                  </div>
                  <pre className="text-xs text-ink-muted bg-surface-subtle p-2 rounded mb-3 overflow-x-auto">{JSON.stringify(s.criteria || {}, null, 1)}</pre>
                  <button onClick={() => handleEvaluateSegment(s.id)} className="btn-secondary text-sm"><UserCheck className="h-3 w-3" /> Evaluate</button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === 'analytics' && (
        <div className="space-y-6">
          {overview && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="card p-4 text-center">
                <p className="text-xs text-ink-muted mb-1">Total Customers</p>
                <p className="text-xl font-semibold text-ink">{overview.total_customers}</p>
              </div>
              <div className="card p-4 text-center">
                <p className="text-xs text-ink-muted mb-1">Active</p>
                <p className="text-xl font-semibold text-call-green">{overview.active_customers}</p>
              </div>
              <div className="card p-4 text-center">
                <p className="text-xs text-ink-muted mb-1">New</p>
                <p className="text-xl font-semibold text-accent">{overview.new_customers}</p>
              </div>
              <div className="card p-4 text-center">
                <p className="text-xs text-ink-muted mb-1">Avg Lifetime Calls</p>
                <p className="text-xl font-semibold text-ink">{overview.avg_lifetime_calls}</p>
              </div>
            </div>
          )}

          <div className="card p-6">
            <h3 className="text-sm font-medium text-ink mb-4 flex items-center gap-2"><BarChart3 className="h-4 w-4" /> Cohort Analysis</h3>
            {cohortData && cohortData.cohorts ? (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={cohortData.cohorts}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="cohort" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="retention_pct" fill="#6366f1" radius={[4, 4, 0, 0]}>
                    {cohortData.cohorts.map((entry, idx) => (
                      <Cell key={idx} fill={entry.retention_pct > 50 ? '#22c55e' : entry.retention_pct > 20 ? '#f59e0b' : '#ef4444'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-sm text-ink-muted">Loading cohort data...</p>
            )}
          </div>

          <div className="card p-6">
            <h3 className="text-sm font-medium text-ink mb-4 flex items-center gap-2"><TrendingUp className="h-4 w-4" /> Churn Risk & LTV</h3>
            <p className="text-sm text-ink-muted">Select a customer profile from the Profiles tab to view churn risk and LTV estimates.</p>
          </div>
        </div>
      )}
    </div>
  )
}
