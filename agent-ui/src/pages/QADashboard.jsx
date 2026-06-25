import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { qaApi, agentApi } from '../services/api'
import {
  ClipboardCheck, Star, TrendingUp, Plus, X, Loader2
} from 'lucide-react'
import { toast } from 'sonner'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, Cell
} from 'recharts'

export default function QADashboard() {
  const { tenant } = useAuth()
  const [activeTab, setActiveTab] = useState('reviews')
  const [scores, setScores] = useState([])
  const [rubrics, setRubrics] = useState([])
  const [agents, setAgents] = useState([])
  const [selectedAgent, setSelectedAgent] = useState('')
  const [agentSummary, setAgentSummary] = useState(null)
  const [loading, setLoading] = useState(false)
  const [showScoreModal, setShowScoreModal] = useState(false)
  const [showRubricModal, setShowRubricModal] = useState(false)
  const [scoreForm, setScoreForm] = useState({ call_id: '', agent_id: '', rubric_id: '', scores_per_criterion: {}, notes: '' })
  const [rubricForm, setRubricForm] = useState({ name: '', description: '', criteria: '' })

  const fetchScores = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await qaApi.listScores(tenant.id)
      setScores(Array.isArray(res.data) ? res.data : [])
    } catch { setScores([]) }
  }, [tenant])

  const fetchRubrics = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await qaApi.listRubrics(tenant.id)
      setRubrics(Array.isArray(res.data) ? res.data : [])
    } catch { setRubrics([]) }
  }, [tenant])

  const fetchAgents = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await agentApi.list(tenant.id)
      setAgents(Array.isArray(res.data) ? res.data : [])
    } catch { setAgents([]) }
  }, [tenant])

  const fetchAgentSummary = useCallback(async (agentId) => {
    if (!agentId) { setAgentSummary(null); return }
    setLoading(true)
    try {
      const res = await qaApi.getAgentSummary(agentId)
      setAgentSummary(res.data)
    } catch { setAgentSummary(null) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchScores(); fetchRubrics(); fetchAgents() }, [fetchScores, fetchRubrics, fetchAgents])
  useEffect(() => { if (selectedAgent) fetchAgentSummary(selectedAgent) }, [selectedAgent, fetchAgentSummary])

  async function handleScoreCall(e) {
    e.preventDefault()
    try {
      await qaApi.createScore(scoreForm)
      toast.success('QA score recorded')
      setShowScoreModal(false)
      setScoreForm({ call_id: '', agent_id: '', rubric_id: '', scores_per_criterion: {}, notes: '' })
      fetchScores()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to record score')
    }
  }

  async function handleCreateRubric(e) {
    e.preventDefault()
    try {
      let criteria = []
      try { criteria = JSON.parse(rubricForm.criteria) } catch { toast.error('Invalid criteria JSON'); return }
      await qaApi.createRubric({ name: rubricForm.name, description: rubricForm.description, criteria })
      toast.success('Rubric created')
      setShowRubricModal(false)
      setRubricForm({ name: '', description: '', criteria: '' })
      fetchRubrics()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create rubric')
    }
  }

  function getActiveRubricCriteria() {
    const rubric = rubrics.find(r => r.id === scoreForm.rubric_id)
    if (!rubric) return []
    let criteria = rubric.criteria
    if (typeof criteria === 'string') {
      try { criteria = JSON.parse(criteria) } catch { criteria = [] }
    }
    return Array.isArray(criteria) ? criteria : []
  }

  function updateCriterionScore(name, value) {
    const num = Math.min(5, Math.max(1, parseInt(value) || 1))
    setScoreForm(prev => ({
      ...prev,
      scores_per_criterion: { ...prev.scores_per_criterion, [name]: num }
    }))
  }

  const tabs = [
    { key: 'reviews', label: 'Reviews', icon: ClipboardCheck },
    { key: 'rubrics', label: 'Rubrics', icon: Star },
    { key: 'agent-scores', label: 'Agent Scores', icon: TrendingUp },
  ]

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Quality Assurance</h1>
          <p className="text-sm text-ink-muted mt-0.5">Call evaluations and scoring</p>
        </div>
        {activeTab === 'reviews' && (
          <button onClick={() => setShowScoreModal(true)} className="btn-primary">
            <Plus className="h-4 w-4" /> Score a Call
          </button>
        )}
        {activeTab === 'rubrics' && (
          <button onClick={() => setShowRubricModal(true)} className="btn-primary">
            <Plus className="h-4 w-4" /> New Rubric
          </button>
        )}
      </div>

      {/* Tabs */}
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

      {/* Reviews Tab */}
      {activeTab === 'reviews' && (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hairline bg-surface-subtle">
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Call ID</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Agent</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Score</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Reviewer</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Date</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Notes</th>
                </tr>
              </thead>
              <tbody>
                {scores.length === 0 && (
                  <tr>
                    <td colSpan="6" className="px-4 py-12 text-center text-ink-muted">
                      No QA evaluations yet. Score a call to get started.
                    </td>
                  </tr>
                )}
                {scores.map(score => (
                  <tr key={score.id} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                    <td className="px-4 py-3 font-mono text-xs text-ink-muted">{String(score.call_id).slice(0, 8)}...</td>
                    <td className="px-4 py-3 text-ink font-medium">{score.agent_name || score.agent_id}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold ${
                        (score.total_score / score.max_score * 100) >= 80 ? 'bg-call-green-soft text-call-green' :
                        (score.total_score / score.max_score * 100) >= 60 ? 'bg-call-amber-soft text-telecom-amber' :
                        'bg-red-50 text-red-600'
                      }`}>
                        {score.total_score.toFixed(1)} / {score.max_score}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-ink-muted">{score.reviewer_id}</td>
                    <td className="px-4 py-3 text-ink-muted text-xs">{new Date(score.reviewed_at).toLocaleDateString()}</td>
                    <td className="px-4 py-3 text-ink-muted text-xs max-w-[200px] truncate">{score.notes || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Rubrics Tab */}
      {activeTab === 'rubrics' && (
        <div className="space-y-4">
          {rubrics.length === 0 && (
            <div className="card p-12 text-center text-ink-muted">
              No rubrics created yet. Create one to define scoring criteria.
            </div>
          )}
          {rubrics.map(rubric => {
            let criteria = rubric.criteria
            if (typeof criteria === 'string') {
              try { criteria = JSON.parse(criteria) } catch { criteria = [] }
            }
            return (
              <div key={rubric.id} className="card p-5">
                <div className="flex items-center justify-between mb-3">
                  <h3 className="font-medium text-ink">{rubric.name}</h3>
                  <span className="text-xs text-ink-muted">Created {new Date(rubric.created_at).toLocaleDateString()}</span>
                </div>
                {rubric.description && <p className="text-sm text-ink-muted mb-3">{rubric.description}</p>}
                <div className="flex flex-wrap gap-2">
                  {(Array.isArray(criteria) ? criteria : []).map((c, i) => (
                    <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-surface-subtle text-xs text-ink">
                      {c.name} <span className="text-ink-muted">({c.weight}%)</span>
                    </span>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Agent Scores Tab */}
      {activeTab === 'agent-scores' && (
        <div className="space-y-6">
          <div className="card p-4">
            <label className="block text-sm font-medium text-ink mb-2">Select Agent</label>
            <select value={selectedAgent} onChange={e => setSelectedAgent(e.target.value)} className="input-field max-w-xs">
              <option value="">Choose an agent...</option>
              {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>

          {loading && (
            <div className="card p-12 flex items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-accent" />
            </div>
          )}

          {!loading && agentSummary && (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="card p-6 text-center">
                <p className="text-sm text-ink-muted mb-1">Average Score</p>
                <p className="text-3xl font-semibold text-ink">{agentSummary.avg_score?.toFixed(1) || 0}</p>
              </div>
              <div className="card p-6 text-center">
                <p className="text-sm text-ink-muted mb-1">Total Reviewed</p>
                <p className="text-3xl font-semibold text-ink">{agentSummary.total_reviewed || 0}</p>
              </div>
              <div className="card p-6 text-center">
                <p className="text-sm text-ink-muted mb-1">Trend (30d)</p>
                <p className={`text-3xl font-semibold ${(agentSummary.trend || 0) >= 0 ? 'text-call-green' : 'text-red-500'}`}>
                  {(agentSummary.trend || 0) >= 0 ? '+' : ''}{agentSummary.trend?.toFixed(1) || 0}
                </p>
              </div>
              {agentSummary.criteria_breakdown && Object.keys(agentSummary.criteria_breakdown).length > 0 && (
                <div className="card p-6 md:col-span-3">
                  <p className="text-sm font-medium text-ink mb-4">Criteria Breakdown (Last Score)</p>
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={Object.entries(agentSummary.criteria_breakdown).map(([k, v]) => ({ name: k, score: v }))}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                      <YAxis domain={[0, 5]} tick={{ fontSize: 11 }} />
                      <Tooltip />
                      <Bar dataKey="score" radius={[4, 4, 0, 0]}>
                        {(Object.entries(agentSummary.criteria_breakdown) || []).map(([k], i) => (
                          <Cell key={k} fill={['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4'][i % 6]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          )}

          {!loading && selectedAgent && !agentSummary && (
            <div className="card p-12 text-center text-ink-muted">No QA data for this agent.</div>
          )}
        </div>
      )}

      {/* Score Call Modal */}
      {showScoreModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-lg mx-4 p-6 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">Score a Call</h2>
              <button onClick={() => setShowScoreModal(false)} className="p-1.5 rounded-lg hover:bg-surface-hover">
                <X className="h-5 w-5 text-ink-muted" />
              </button>
            </div>
            <form onSubmit={handleScoreCall} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Call ID</label>
                <input type="text" value={scoreForm.call_id} onChange={e => setScoreForm({ ...scoreForm, call_id: e.target.value })} className="input-field" required placeholder="Enter call session ID" />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Agent</label>
                <select value={scoreForm.agent_id} onChange={e => setScoreForm({ ...scoreForm, agent_id: e.target.value })} className="input-field" required>
                  <option value="">Select agent...</option>
                  {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Rubric</label>
                <select value={scoreForm.rubric_id} onChange={e => setScoreForm({ ...scoreForm, rubric_id: e.target.value, scores_per_criterion: {} })} className="input-field" required>
                  <option value="">Select rubric...</option>
                  {rubrics.map(r => <option key={r.id} value={r.id}>{r.name}</option>)}
                </select>
              </div>
              {getActiveRubricCriteria().length > 0 && (
                <div className="space-y-3">
                  <p className="text-sm font-medium text-ink">Criterion Scores (1-5)</p>
                  {getActiveRubricCriteria().map(c => (
                    <div key={c.name} className="flex items-center gap-3">
                      <span className="flex-1 text-sm text-ink">{c.name} <span className="text-ink-muted">({c.weight}%)</span></span>
                      <input type="number" min="1" max="5" value={scoreForm.scores_per_criterion[c.name] || ''} onChange={e => updateCriterionScore(c.name, e.target.value)} className="input-field w-20 text-center" required />
                    </div>
                  ))}
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Notes</label>
                <textarea value={scoreForm.notes} onChange={e => setScoreForm({ ...scoreForm, notes: e.target.value })} className="input-field" rows={3} placeholder="Optional evaluation notes" />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowScoreModal(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" className="btn-primary flex-1">
                  <ClipboardCheck className="h-4 w-4" /> Submit Score
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Create Rubric Modal */}
      {showRubricModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">Create Rubric</h2>
              <button onClick={() => setShowRubricModal(false)} className="p-1.5 rounded-lg hover:bg-surface-hover">
                <X className="h-5 w-5 text-ink-muted" />
              </button>
            </div>
            <form onSubmit={handleCreateRubric} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Name</label>
                <input type="text" value={rubricForm.name} onChange={e => setRubricForm({ ...rubricForm, name: e.target.value })} className="input-field" required placeholder="e.g. Standard QA Rubric" />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Description</label>
                <input type="text" value={rubricForm.description} onChange={e => setRubricForm({ ...rubricForm, description: e.target.value })} className="input-field" placeholder="Optional description" />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Criteria (JSON)</label>
                <textarea value={rubricForm.criteria} onChange={e => setRubricForm({ ...rubricForm, criteria: e.target.value })} className="input-field font-mono text-xs" rows={6} required placeholder='[{"name":"greeting","description":"Professional greeting","weight":15}]' />
                <p className="text-xs text-ink-subtle mt-1">Array of objects with name, description, and weight (should total 100)</p>
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowRubricModal(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" className="btn-primary flex-1">
                  <Plus className="h-4 w-4" /> Create Rubric
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
