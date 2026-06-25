import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { wfmApi } from '../services/api'
import { agentApi } from '../services/api'
import {
  CalendarClock, Users, TrendingUp, BarChart3, CheckCircle2,
  Plus, Loader2, X, Trash2, Clock
} from 'lucide-react'
import { toast } from 'sonner'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, Cell
} from 'recharts'

export default function WFMDashboard() {
  const { tenant } = useAuth()
  const [activeTab, setActiveTab] = useState('schedule')
  const [shifts, setShifts] = useState([])
  const [schedules, setSchedules] = useState([])
  const [agents, setAgents] = useState([])
  const [forecast, setForecast] = useState(null)
  const [adherence, setAdherence] = useState(null)
  const [loading, setLoading] = useState(false)
  const [showShiftModal, setShowShiftModal] = useState(false)
  const [shiftForm, setShiftForm] = useState({ agent_id: '', start_time: '', end_time: '', shift_type: 'regular', notes: '' })

  const fetchShifts = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await wfmApi.listShifts(tenant.id)
      setShifts(Array.isArray(res.data) ? res.data : [])
    } catch { setShifts([]) }
  }, [tenant])

  const fetchSchedules = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await wfmApi.getSchedule(tenant.id)
      setSchedules(Array.isArray(res.data) ? res.data : [])
    } catch { setSchedules([]) }
  }, [tenant])

  const fetchAgents = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await agentApi.list(tenant.id)
      setAgents(Array.isArray(res.data) ? res.data : [])
    } catch { setAgents([]) }
  }, [tenant])

  const fetchForecast = useCallback(async () => {
    if (!tenant) return
    setLoading(true)
    try {
      const res = await wfmApi.getForecast(tenant.id, { hours_ahead: 48 })
      setForecast(res.data)
    } catch { setForecast(null) }
    finally { setLoading(false) }
  }, [tenant])

  const fetchAdherence = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await wfmApi.getAdherence(tenant.id)
      setAdherence(res.data)
    } catch { setAdherence(null) }
  }, [tenant])

  useEffect(() => {
    fetchShifts()
    fetchSchedules()
    fetchAgents()
  }, [fetchShifts, fetchSchedules, fetchAgents])

  useEffect(() => {
    if (activeTab === 'forecast') fetchForecast()
    if (activeTab === 'adherence') fetchAdherence()
  }, [activeTab, fetchForecast, fetchAdherence])

  async function handleCreateShift(e) {
    e.preventDefault()
    try {
      await wfmApi.createShift(shiftForm)
      toast.success('Shift created')
      setShowShiftModal(false)
      setShiftForm({ agent_id: '', start_time: '', end_time: '', shift_type: 'regular', notes: '' })
      fetchShifts()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create shift')
    }
  }

  async function handleDeleteShift(shiftId) {
    try {
      await wfmApi.deleteShift(shiftId)
      toast.success('Shift deleted')
      fetchShifts()
    } catch { toast.error('Failed to delete shift') }
  }

  const tabs = [
    { key: 'schedule', label: 'Schedule', icon: CalendarClock },
    { key: 'adherence', label: 'Adherence', icon: CheckCircle2 },
    { key: 'forecast', label: 'Forecast', icon: TrendingUp },
  ]

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Workforce Management</h1>
          <p className="text-sm text-ink-muted mt-0.5">Shifts, scheduling, and demand forecasting</p>
        </div>
        {activeTab === 'schedule' && (
          <button onClick={() => setShowShiftModal(true)} className="btn-primary">
            <Plus className="h-4 w-4" /> New Shift
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

      {/* Schedule Tab */}
      {activeTab === 'schedule' && (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hairline bg-surface-subtle">
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Agent</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Start</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">End</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Type</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                  <th className="text-right px-4 py-3 font-medium text-ink-muted">Actions</th>
                </tr>
              </thead>
              <tbody>
                {shifts.length === 0 && (
                  <tr>
                    <td colSpan="6" className="px-4 py-12 text-center text-ink-muted">
                      No shifts scheduled. Create one to get started.
                    </td>
                  </tr>
                )}
                {shifts.map(shift => (
                  <tr key={shift.id} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                    <td className="px-4 py-3 text-ink font-medium">{shift.agent_name || shift.agent_id}</td>
                    <td className="px-4 py-3 text-ink-muted">
                      {new Date(shift.start_time).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-ink-muted">
                      {new Date(shift.end_time).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                        shift.shift_type === 'overtime' ? 'bg-call-amber-soft text-telecom-amber' :
                        shift.shift_type === 'training' ? 'bg-purple-50 text-purple-600' :
                        'bg-call-green-soft text-call-green'
                      }`}>
                        {shift.shift_type}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                        shift.status === 'active' ? 'bg-call-green-soft text-call-green' :
                        shift.status === 'completed' ? 'bg-surface-subtle text-ink-muted' :
                        'bg-accent-soft text-accent'
                      }`}>
                        {shift.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button onClick={() => handleDeleteShift(shift.id)} className="p-1.5 rounded-lg text-ink-muted hover:text-red-500 hover:bg-red-50 transition-colors">
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Adherence Tab */}
      {activeTab === 'adherence' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="card p-6 flex flex-col items-center justify-center">
              <p className="text-sm text-ink-muted mb-2">Overall Adherence</p>
              <div className="relative w-24 h-24">
                <svg className="w-24 h-24 transform -rotate-90" viewBox="0 0 100 100">
                  <circle cx="50" cy="50" r="40" fill="none" stroke="#e5e7eb" strokeWidth="8" />
                  <circle cx="50" cy="50" r="40" fill="none" stroke={adherence?.overall_adherence_pct >= 80 ? '#22c55e' : '#f59e0b'} strokeWidth="8"
                    strokeDasharray={`${(adherence?.overall_adherence_pct || 0) * 2.51} 251`} strokeLinecap="round" />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-xl font-semibold text-ink">{adherence?.overall_adherence_pct || 0}%</span>
                </div>
              </div>
            </div>
            <div className="card p-6">
              <p className="text-sm text-ink-muted mb-1">Forecasted Volume</p>
              <p className="text-2xl font-semibold text-ink">{adherence?.schedule_summary?.forecasted_volume || 0}</p>
            </div>
            <div className="card p-6">
              <p className="text-sm text-ink-muted mb-1">Forecasted Agents</p>
              <p className="text-2xl font-semibold text-ink">{adherence?.schedule_summary?.forecasted_agents || 0}</p>
            </div>
          </div>
          <div className="card p-6">
            <h3 className="text-sm font-medium text-ink mb-4">Schedule Summary</h3>
            <p className="text-sm text-ink-muted">Adherence data will populate as shifts are tracked against actual activity.</p>
          </div>
        </div>
      )}

      {/* Forecast Tab */}
      {activeTab === 'forecast' && (
        <div className="space-y-6">
          {loading && (
            <div className="card p-12 flex items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-accent" />
              <span className="ml-2 text-ink-muted">Generating forecast...</span>
            </div>
          )}
          {!loading && forecast && (
            <>
              <div className="card p-6">
                <h3 className="text-sm font-medium text-ink mb-4">Call Volume Forecast (48h)</h3>
                <ResponsiveContainer width="100%" height={300}>
                  <AreaChart data={forecast.forecast || []}>
                    <defs>
                      <linearGradient id="colorPredicted" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3}/>
                        <stop offset="95%" stopColor="#6366f1" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="hour" tick={{ fontSize: 11 }} tickFormatter={v => new Date(v).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} />
                    <YAxis tick={{ fontSize: 11 }} />
                    <Tooltip labelFormatter={v => new Date(v).toLocaleString()} />
                    <Area type="monotone" dataKey="confidence_high" stroke="none" fill="#6366f1" fillOpacity={0.1} />
                    <Area type="monotone" dataKey="predicted_volume" stroke="#6366f1" fill="url(#colorPredicted)" strokeWidth={2} />
                    <Area type="monotone" dataKey="confidence_low" stroke="none" fill="#6366f1" fillOpacity={0.05} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="card p-6">
                  <p className="text-sm text-ink-muted mb-1">Peak Volume</p>
                  <p className="text-2xl font-semibold text-ink">{forecast.staffing_recommendation?.peak_volume || 0}</p>
                </div>
                <div className="card p-6">
                  <p className="text-sm text-ink-muted mb-1">Recommended Agents</p>
                  <p className="text-2xl font-semibold text-accent">{forecast.staffing_recommendation?.recommended_agents || 0}</p>
                </div>
                <div className="card p-6">
                  <p className="text-sm text-ink-muted mb-1">Model Accuracy (MAPE)</p>
                  <p className="text-2xl font-semibold text-ink">{forecast.model_accuracy_mape != null ? `${forecast.model_accuracy_mape}%` : 'N/A'}</p>
                </div>
              </div>
            </>
          )}
          {!loading && !forecast && (
            <div className="card p-12 text-center text-ink-muted">
              Click Forecast tab to generate demand predictions.
            </div>
          )}
        </div>
      )}

      {/* Create Shift Modal */}
      {showShiftModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">Create Shift</h2>
              <button onClick={() => setShowShiftModal(false)} className="p-1.5 rounded-lg hover:bg-surface-hover">
                <X className="h-5 w-5 text-ink-muted" />
              </button>
            </div>
            <form onSubmit={handleCreateShift} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Agent</label>
                <select value={shiftForm.agent_id} onChange={e => setShiftForm({ ...shiftForm, agent_id: e.target.value })} className="input-field" required>
                  <option value="">Select agent...</option>
                  {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-ink mb-1.5">Start Time</label>
                  <input type="datetime-local" value={shiftForm.start_time} onChange={e => setShiftForm({ ...shiftForm, start_time: e.target.value })} className="input-field" required />
                </div>
                <div>
                  <label className="block text-sm font-medium text-ink mb-1.5">End Time</label>
                  <input type="datetime-local" value={shiftForm.end_time} onChange={e => setShiftForm({ ...shiftForm, end_time: e.target.value })} className="input-field" required />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Shift Type</label>
                <select value={shiftForm.shift_type} onChange={e => setShiftForm({ ...shiftForm, shift_type: e.target.value })} className="input-field">
                  <option value="regular">Regular</option>
                  <option value="overtime">Overtime</option>
                  <option value="training">Training</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Notes</label>
                <input type="text" value={shiftForm.notes} onChange={e => setShiftForm({ ...shiftForm, notes: e.target.value })} className="input-field" placeholder="Optional notes" />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowShiftModal(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" className="btn-primary flex-1">
                  <Plus className="h-4 w-4" /> Create Shift
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
