import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { aiOpsApi } from '../services/api'
import {
  BrainCircuit, Target, FlaskConical, TrendingUp, AlertTriangle,
  CheckCircle2, XCircle, BarChart3, Plus, Loader2, X
} from 'lucide-react'
import { toast } from 'sonner'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell
} from 'recharts'

export default function AIOpsDashboard() {
  const { tenant } = useAuth()
  const [activeTab, setActiveTab] = useState('overview')
  const [accuracy, setAccuracy] = useState(null)
  const [experiments, setExperiments] = useState([])
  const [distribution, setDistribution] = useState(null)
  const [thresholds, setThresholds] = useState({ proceed: 0.8, review: 0.5, escalate: 0.0 })
  const [loading, setLoading] = useState(false)
  const [showExpModal, setShowExpModal] = useState(false)
  const [expForm, setExpForm] = useState({ name: '', description: '', model_a: '', model_b: '', traffic_split: 0.5 })
  const [selectedExp, setSelectedExp] = useState(null)
  const [recentEvals, setRecentEvals] = useState([])

  const fetchAccuracy = useCallback(async () => {
    if (!tenant) return
    setLoading(true)
    try {
      const res = await aiOpsApi.getAccuracy({ tenant_id: tenant.id })
      setAccuracy(res.data)
    } catch { setAccuracy(null) }
    finally { setLoading(false) }
  }, [tenant])

  const fetchExperiments = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await aiOpsApi.listExperiments({ tenant_id: tenant.id })
      setExperiments(Array.isArray(res.data) ? res.data : [])
    } catch { setExperiments([]) }
  }, [tenant])

  const fetchDistribution = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await aiOpsApi.getConfidenceDistribution({ tenant_id: tenant.id })
      setDistribution(res.data)
    } catch { setDistribution(null) }
  }, [tenant])

  const fetchThresholds = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await aiOpsApi.getConfidenceThresholds()
      setThresholds(res.data)
    } catch { /* keep defaults */ }
  }, [tenant])

  const fetchRecentEvals = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await aiOpsApi.getAccuracy({ tenant_id: tenant.id })
      // Use accuracy data for recent evaluations display
      setRecentEvals([])
    } catch { setRecentEvals([]) }
  }, [tenant])

  useEffect(() => {
    fetchAccuracy()
    fetchExperiments()
    fetchDistribution()
    fetchThresholds()
    fetchRecentEvals()
  }, [fetchAccuracy, fetchExperiments, fetchDistribution, fetchThresholds, fetchRecentEvals])

  useEffect(() => {
    if (activeTab === 'accuracy') fetchAccuracy()
    if (activeTab === 'experiments') fetchExperiments()
    if (activeTab === 'confidence') { fetchDistribution(); fetchThresholds() }
  }, [activeTab, fetchAccuracy, fetchExperiments, fetchDistribution, fetchThresholds])

  async function handleCreateExperiment(e) {
    e.preventDefault()
    try {
      await aiOpsApi.createExperiment(expForm)
      toast.success('Experiment created')
      setShowExpModal(false)
      setExpForm({ name: '', description: '', model_a: '', model_b: '', traffic_split: 0.5 })
      fetchExperiments()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create experiment')
    }
  }

  async function handleStopExperiment(expId) {
    try {
      await aiOpsApi.stopExperiment(expId)
      toast.success('Experiment stopped')
      fetchExperiments()
      setSelectedExp(null)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to stop experiment')
    }
  }

  async function handleSaveThresholds() {
    try {
      await aiOpsApi.setConfidenceThresholds(thresholds)
      toast.success('Thresholds saved')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save thresholds')
    }
  }

  const tabs = [
    { key: 'overview', label: 'Overview', icon: BrainCircuit },
    { key: 'accuracy', label: 'Accuracy', icon: Target },
    { key: 'experiments', label: 'Experiments', icon: FlaskConical },
    { key: 'confidence', label: 'Confidence', icon: BarChart3 },
  ]

  const distData = distribution?.buckets?.map(b => ({ name: b.label, count: b.count })) || []
  const intentData = accuracy?.intents ? Object.entries(accuracy.intents).map(([k, v]) => ({ name: k, accuracy: v.correct / v.total || 0, f1: v.f1 })) : []

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">AI Operations</h1>
          <p className="text-sm text-ink-muted mt-0.5">Intent accuracy, A/B experiments, and confidence monitoring</p>
        </div>
        {activeTab === 'experiments' && (
          <button onClick={() => setShowExpModal(true)} className="btn-primary">
            <Plus className="h-4 w-4" /> New Experiment
          </button>
        )}
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
        <div className="card p-5">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-accent-soft">
              <Target className="h-5 w-5 text-accent" />
            </div>
            <div>
              <p className="text-sm text-ink-muted">Intent Accuracy</p>
              <p className="text-2xl font-semibold text-ink">{accuracy?.accuracy != null ? `${(accuracy.accuracy * 100).toFixed(1)}%` : 'N/A'}</p>
            </div>
          </div>
        </div>
        <div className="card p-5">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-purple-50">
              <BrainCircuit className="h-5 w-5 text-purple-600" />
            </div>
            <div>
              <p className="text-sm text-ink-muted">Total Evaluations</p>
              <p className="text-2xl font-semibold text-ink">{accuracy?.total_evaluations || 0}</p>
            </div>
          </div>
        </div>
        <div className="card p-5">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-call-amber-soft">
              <FlaskConical className="h-5 w-5 text-telecom-amber" />
            </div>
            <div>
              <p className="text-sm text-ink-muted">Active Experiments</p>
              <p className="text-2xl font-semibold text-ink">{experiments.filter(e => e.status === 'active').length}</p>
            </div>
          </div>
        </div>
        <div className="card p-5">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-call-green-soft">
              <TrendingUp className="h-5 w-5 text-call-green" />
            </div>
            <div>
              <p className="text-sm text-ink-muted">Avg Confidence</p>
              <p className="text-2xl font-semibold text-ink">{accuracy?.avg_confidence != null ? `${(accuracy.avg_confidence * 100).toFixed(1)}%` : 'N/A'}</p>
            </div>
          </div>
        </div>
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

      {/* Overview Tab */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="card p-6">
              <h3 className="text-sm font-medium text-ink mb-4">Intent Accuracy by Type</h3>
              {intentData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={intentData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} domain={[0, 1]} />
                    <Tooltip formatter={(v) => `${(v * 100).toFixed(1)}%`} />
                    <Bar dataKey="accuracy" fill="#6366f1" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[300px] flex items-center justify-center text-ink-muted text-sm">
                  No evaluation data yet
                </div>
              )}
            </div>
            <div className="card p-6">
              <h3 className="text-sm font-medium text-ink mb-4">Confidence Distribution</h3>
              {distData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={distData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#22c55e" radius={[4, 4, 0, 0]}>
                      {distData.map((entry, idx) => (
                        <Cell key={idx} fill={idx < 2 ? '#ef4444' : idx < 4 ? '#f59e0b' : '#22c55e'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[300px] flex items-center justify-center text-ink-muted text-sm">
                  No confidence data yet
                </div>
              )}
            </div>
          </div>
          <div className="card p-6">
            <h3 className="text-sm font-medium text-ink mb-4">Active Experiments</h3>
            {experiments.filter(e => e.status === 'active').length === 0 ? (
              <p className="text-sm text-ink-muted">No active experiments</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-hairline bg-surface-subtle">
                      <th className="text-left px-4 py-3 font-medium text-ink-muted">Name</th>
                      <th className="text-left px-4 py-3 font-medium text-ink-muted">Model A</th>
                      <th className="text-left px-4 py-3 font-medium text-ink-muted">Model B</th>
                      <th className="text-left px-4 py-3 font-medium text-ink-muted">Split</th>
                      <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {experiments.filter(e => e.status === 'active').slice(0, 5).map(exp => (
                      <tr key={exp.id} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                        <td className="px-4 py-3 text-ink font-medium">{exp.name}</td>
                        <td className="px-4 py-3 text-ink-muted">{exp.model_a}</td>
                        <td className="px-4 py-3 text-ink-muted">{exp.model_b}</td>
                        <td className="px-4 py-3 text-ink-muted">{(exp.traffic_split * 100).toFixed(0)}%</td>
                        <td className="px-4 py-3">
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-call-green-soft text-call-green">
                            {exp.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Accuracy Tab */}
      {activeTab === 'accuracy' && (
        <div className="space-y-6">
          {loading && (
            <div className="card p-12 flex items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-accent" />
              <span className="ml-2 text-ink-muted">Loading accuracy data...</span>
            </div>
          )}
          {!loading && accuracy && (
            <>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="card p-6">
                  <p className="text-sm text-ink-muted mb-1">Overall Accuracy</p>
                  <p className="text-2xl font-semibold text-ink">{(accuracy.accuracy * 100).toFixed(1)}%</p>
                </div>
                <div className="card p-6">
                  <p className="text-sm text-ink-muted mb-1">Total Evaluations</p>
                  <p className="text-2xl font-semibold text-ink">{accuracy.total_evaluations}</p>
                </div>
                <div className="card p-6">
                  <p className="text-sm text-ink-muted mb-1">Avg Confidence</p>
                  <p className="text-2xl font-semibold text-ink">{(accuracy.avg_confidence * 100).toFixed(1)}%</p>
                </div>
              </div>
              <div className="card p-6">
                <h3 className="text-sm font-medium text-ink mb-4">Per-Intent Metrics</h3>
                {accuracy.intents && Object.keys(accuracy.intents).length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-hairline bg-surface-subtle">
                          <th className="text-left px-4 py-3 font-medium text-ink-muted">Intent</th>
                          <th className="text-left px-4 py-3 font-medium text-ink-muted">Precision</th>
                          <th className="text-left px-4 py-3 font-medium text-ink-muted">Recall</th>
                          <th className="text-left px-4 py-3 font-medium text-ink-muted">F1</th>
                          <th className="text-left px-4 py-3 font-medium text-ink-muted">Total</th>
                          <th className="text-left px-4 py-3 font-medium text-ink-muted">Correct</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(accuracy.intents).map(([intent, m]) => (
                          <tr key={intent} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                            <td className="px-4 py-3 text-ink font-medium">{intent}</td>
                            <td className="px-4 py-3 text-ink-muted">{(m.precision * 100).toFixed(1)}%</td>
                            <td className="px-4 py-3 text-ink-muted">{(m.recall * 100).toFixed(1)}%</td>
                            <td className="px-4 py-3 text-ink-muted">{(m.f1 * 100).toFixed(1)}%</td>
                            <td className="px-4 py-3 text-ink-muted">{m.total}</td>
                            <td className="px-4 py-3 text-ink-muted">{m.correct}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-sm text-ink-muted">No intent data yet</p>
                )}
              </div>
              <div className="card p-6">
                <h3 className="text-sm font-medium text-ink mb-4">Accuracy by Intent</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={intentData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} domain={[0, 1]} />
                    <Tooltip formatter={(v) => `${(v * 100).toFixed(1)}%`} />
                    <Bar dataKey="f1" fill="#6366f1" radius={[4, 4, 0, 0]} name="F1 Score" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </>
          )}
        </div>
      )}

      {/* Experiments Tab */}
      {activeTab === 'experiments' && (
        <div className="space-y-6">
          {selectedExp ? (
            <div className="card p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-medium text-ink">{selectedExp.name}</h3>
                <button onClick={() => setSelectedExp(null)} className="text-sm text-accent hover:underline">Back to list</button>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
                <div className="card p-4">
                  <p className="text-sm text-ink-muted mb-1">Model A</p>
                  <p className="font-medium text-ink">{selectedExp.model_a}</p>
                </div>
                <div className="card p-4">
                  <p className="text-sm text-ink-muted mb-1">Model B</p>
                  <p className="font-medium text-ink">{selectedExp.model_b}</p>
                </div>
                <div className="card p-4">
                  <p className="text-sm text-ink-muted mb-1">Traffic Split</p>
                  <p className="font-medium text-ink">{(selectedExp.traffic_split * 100).toFixed(0)}%</p>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="card p-4">
                  <p className="text-sm text-ink-muted mb-1">Status</p>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                    selectedExp.status === 'active' ? 'bg-call-green-soft text-call-green' : 'bg-surface-subtle text-ink-muted'
                  }`}>
                    {selectedExp.status}
                  </span>
                </div>
                <div className="card p-4">
                  <p className="text-sm text-ink-muted mb-1">Created</p>
                  <p className="font-medium text-ink">{new Date(selectedExp.created_at).toLocaleDateString()}</p>
                </div>
              </div>
              {selectedExp.status === 'active' && (
                <div className="mt-4">
                  <button onClick={() => handleStopExperiment(selectedExp.id)} className="btn-primary bg-red-500 hover:bg-red-600">
                    Stop Experiment
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div className="card overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-hairline bg-surface-subtle">
                      <th className="text-left px-4 py-3 font-medium text-ink-muted">Name</th>
                      <th className="text-left px-4 py-3 font-medium text-ink-muted">Model A</th>
                      <th className="text-left px-4 py-3 font-medium text-ink-muted">Model B</th>
                      <th className="text-left px-4 py-3 font-medium text-ink-muted">Split</th>
                      <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                      <th className="text-left px-4 py-3 font-medium text-ink-muted">Created</th>
                      <th className="text-right px-4 py-3 font-medium text-ink-muted">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {experiments.length === 0 && (
                      <tr>
                        <td colSpan="7" className="px-4 py-12 text-center text-ink-muted">
                          No experiments yet. Create one to start A/B testing.
                        </td>
                      </tr>
                    )}
                    {experiments.map(exp => (
                      <tr key={exp.id} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                        <td className="px-4 py-3 text-ink font-medium">{exp.name}</td>
                        <td className="px-4 py-3 text-ink-muted">{exp.model_a}</td>
                        <td className="px-4 py-3 text-ink-muted">{exp.model_b}</td>
                        <td className="px-4 py-3 text-ink-muted">{(exp.traffic_split * 100).toFixed(0)}%</td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                            exp.status === 'active' ? 'bg-call-green-soft text-call-green' :
                            exp.status === 'stopped' ? 'bg-surface-subtle text-ink-muted' :
                            'bg-accent-soft text-accent'
                          }`}>
                            {exp.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-ink-muted">{new Date(exp.created_at).toLocaleDateString()}</td>
                        <td className="px-4 py-3 text-right">
                          <button onClick={() => setSelectedExp(exp)} className="text-sm text-accent hover:underline mr-3">View</button>
                          {exp.status === 'active' && (
                            <button onClick={() => handleStopExperiment(exp.id)} className="text-sm text-red-500 hover:underline">Stop</button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Confidence Tab */}
      {activeTab === 'confidence' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="card p-6">
              <h3 className="text-sm font-medium text-ink mb-4">Confidence Distribution</h3>
              {distData.length > 0 ? (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={distData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]}>
                      {distData.map((entry, idx) => (
                        <Cell key={idx} fill={idx < 2 ? '#ef4444' : idx < 4 ? '#f59e0b' : '#22c55e'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-[300px] flex items-center justify-center text-ink-muted text-sm">
                  No confidence data yet
                </div>
              )}
            </div>
            <div className="card p-6">
              <h3 className="text-sm font-medium text-ink mb-4">Threshold Settings</h3>
              <div className="space-y-4">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-sm text-ink">Proceed Threshold</label>
                    <span className="text-sm text-ink-muted">{(thresholds.proceed * 100).toFixed(0)}%</span>
                  </div>
                  <input
                    type="range"
                    min="0" max="100"
                    value={thresholds.proceed * 100}
                    onChange={e => setThresholds({ ...thresholds, proceed: e.target.value / 100 })}
                    className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-green-500"
                  />
                  <p className="text-xs text-ink-muted mt-1">Confidence above this auto-proceeds</p>
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-sm text-ink">Review Threshold</label>
                    <span className="text-sm text-ink-muted">{(thresholds.review * 100).toFixed(0)}%</span>
                  </div>
                  <input
                    type="range"
                    min="0" max="100"
                    value={thresholds.review * 100}
                    onChange={e => setThresholds({ ...thresholds, review: e.target.value / 100 })}
                    className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-yellow-500"
                  />
                  <p className="text-xs text-ink-muted mt-1">Confidence in this range requires review</p>
                </div>
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-sm text-ink">Escalate Threshold</label>
                    <span className="text-sm text-ink-muted">{(thresholds.escalate * 100).toFixed(0)}%</span>
                  </div>
                  <input
                    type="range"
                    min="0" max="100"
                    value={thresholds.escalate * 100}
                    onChange={e => setThresholds({ ...thresholds, escalate: e.target.value / 100 })}
                    className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-red-500"
                  />
                  <p className="text-xs text-ink-muted mt-1">Confidence below this is escalated to human</p>
                </div>
                <button onClick={handleSaveThresholds} className="btn-primary w-full mt-4">
                  Save Thresholds
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Create Experiment Modal */}
      {showExpModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">Create A/B Experiment</h2>
              <button onClick={() => setShowExpModal(false)} className="p-1.5 rounded-lg hover:bg-surface-hover">
                <X className="h-5 w-5 text-ink-muted" />
              </button>
            </div>
            <form onSubmit={handleCreateExperiment} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Experiment Name</label>
                <input type="text" value={expForm.name} onChange={e => setExpForm({ ...expForm, name: e.target.value })} className="input-field" required placeholder="e.g. Intent Model Comparison" />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Description</label>
                <input type="text" value={expForm.description} onChange={e => setExpForm({ ...expForm, description: e.target.value })} className="input-field" placeholder="Optional description" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-ink mb-1.5">Model A</label>
                  <input type="text" value={expForm.model_a} onChange={e => setExpForm({ ...expForm, model_a: e.target.value })} className="input-field" required placeholder="e.g. gpt-4" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-ink mb-1.5">Model B</label>
                  <input type="text" value={expForm.model_b} onChange={e => setExpForm({ ...expForm, model_b: e.target.value })} className="input-field" required placeholder="e.g. gpt-3.5" />
                </div>
              </div>
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-sm font-medium text-ink">Traffic Split</label>
                  <span className="text-sm text-ink-muted">{(expForm.traffic_split * 100).toFixed(0)}% / {(100 - expForm.traffic_split * 100).toFixed(0)}%</span>
                </div>
                <input
                  type="range"
                  min="10" max="90"
                  value={expForm.traffic_split * 100}
                  onChange={e => setExpForm({ ...expForm, traffic_split: e.target.value / 100 })}
                  className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-accent"
                />
                <div className="flex justify-between text-xs text-ink-muted mt-1">
                  <span>Model A: {(expForm.traffic_split * 100).toFixed(0)}%</span>
                  <span>Model B: {(100 - expForm.traffic_split * 100).toFixed(0)}%</span>
                </div>
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowExpModal(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" className="btn-primary flex-1">
                  <FlaskConical className="h-4 w-4" /> Create Experiment
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
