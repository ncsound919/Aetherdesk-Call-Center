import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { trainingApi, agentApi } from '../services/api'
import {
  BookOpen, GraduationCap, Target, Users, Plus, Clock, Loader2, X, CheckCircle2
} from 'lucide-react'
import { toast } from 'sonner'

export default function TrainingDashboard() {
  const { tenant } = useAuth()
  const [activeTab, setActiveTab] = useState('courses')
  const [courses, setCourses] = useState([])
  const [agents, setAgents] = useState([])
  const [certifications, setCertifications] = useState([])
  const [coaching, setCoaching] = useState([])
  const [loading, setLoading] = useState(false)
  const [showCourseModal, setShowCourseModal] = useState(false)
  const [courseForm, setCourseForm] = useState({ title: '', description: '', modules: '', duration_hours: '' })
  const [showCoachingModal, setShowCoachingModal] = useState(false)
  const [coachingForm, setCoachingForm] = useState({ agent_id: '', coach_id: '', focus_area: '', notes: '' })
  const [enrollForm, setEnrollForm] = useState({ agent_id: '', course_id: '' })
  const [selectedAgent, setSelectedAgent] = useState('')

  const fetchData = useCallback(async () => {
    if (!tenant) return
    setLoading(true)
    try {
      const [coRes, agRes] = await Promise.all([
        trainingApi.listCourses(tenant.id),
        agentApi.list(tenant.id),
      ])
      setCourses(Array.isArray(coRes.data) ? coRes.data : [])
      setAgents(Array.isArray(agRes.data) ? agRes.data : [])
    } catch { /* ignore */ }
    setLoading(false)
  }, [tenant])

  const fetchCertifications = useCallback(async (agentId) => {
    if (!tenant || !agentId) return
    try {
      const res = await trainingApi.getCertifications(agentId, tenant.id)
      setCertifications(Array.isArray(res.data) ? res.data : [])
    } catch { setCertifications([]) }
  }, [tenant])

  const fetchCoaching = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await trainingApi.listCoaching(tenant.id)
      setCoaching(Array.isArray(res.data) ? res.data : [])
    } catch { setCoaching([]) }
  }, [tenant])

  useEffect(() => { fetchData() }, [fetchData])
  useEffect(() => { if (activeTab === 'certifications') fetchCertifications(selectedAgent) }, [activeTab, selectedAgent, fetchCertifications])
  useEffect(() => { if (activeTab === 'coaching') fetchCoaching() }, [activeTab, fetchCoaching])

  async function handleCreateCourse(e) {
    e.preventDefault()
    try {
      const modules = courseForm.modules ? courseForm.modules.split(',').map(m => ({ title: m.trim() })) : []
      await trainingApi.createCourse({ ...courseForm, modules, duration_hours: parseFloat(courseForm.duration_hours) || 0 })
      toast.success('Course created')
      setShowCourseModal(false)
      setCourseForm({ title: '', description: '', modules: '', duration_hours: '' })
      fetchData()
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
  }

  async function handleEnroll(e) {
    e.preventDefault()
    try {
      await trainingApi.enrollAgent(enrollForm)
      toast.success('Agent enrolled')
      setEnrollForm({ agent_id: '', course_id: '' })
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
  }

  async function handleCreateCoaching(e) {
    e.preventDefault()
    try {
      await trainingApi.createCoaching(coachingForm)
      toast.success('Coaching session created')
      setShowCoachingModal(false)
      setCoachingForm({ agent_id: '', coach_id: '', focus_area: '', notes: '' })
      fetchCoaching()
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
  }

  const tabs = [
    { key: 'courses', label: 'Courses', icon: BookOpen },
    { key: 'certifications', label: 'Certifications', icon: GraduationCap },
    { key: 'coaching', label: 'Coaching', icon: Target },
  ]

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Training & Coaching</h1>
          <p className="text-sm text-ink-muted mt-0.5">Courses, certifications, and agent coaching</p>
        </div>
        {activeTab === 'courses' && (
          <button onClick={() => setShowCourseModal(true)} className="btn-primary">
            <Plus className="h-4 w-4" /> New Course
          </button>
        )}
        {activeTab === 'coaching' && (
          <button onClick={() => setShowCoachingModal(true)} className="btn-primary">
            <Plus className="h-4 w-4" /> New Session
          </button>
        )}
      </div>

      <div className="flex gap-1 mb-6 border-b border-hairline">
        {tabs.map(tab => {
          const Icon = tab.icon
          return (
            <button key={tab.key} onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key ? 'border-accent text-accent' : 'border-transparent text-ink-muted hover:text-ink'
              }`}>
              <Icon className="h-4 w-4" /> {tab.label}
            </button>
          )
        })}
      </div>

      {loading && <div className="card p-12 flex items-center justify-center"><Loader2 className="h-6 w-6 animate-spin text-accent" /></div>}

      {!loading && activeTab === 'courses' && (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-sm font-medium text-ink mb-4">Available Courses</h3>
            {courses.length === 0 && <p className="text-sm text-ink-muted">No courses yet. Create one to get started.</p>}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {courses.map(c => (
                <div key={c.id} className="border border-hairline rounded-lg p-4 hover:shadow-sm transition-shadow">
                  <div className="flex items-center gap-2 mb-2">
                    <BookOpen className="h-4 w-4 text-accent" />
                    <h4 className="font-medium text-ink text-sm">{c.title}</h4>
                  </div>
                  <p className="text-xs text-ink-muted mb-3">{c.description || 'No description'}</p>
                  <div className="flex items-center gap-3 text-xs text-ink-muted">
                    <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {c.duration_hours}h</span>
                    <span className="flex items-center gap-1"><Target className="h-3 w-3" /> {Array.isArray(c.modules_json) ? c.modules_json.length : 0} modules</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card p-6">
            <h3 className="text-sm font-medium text-ink mb-4">Enroll Agent</h3>
            <form onSubmit={handleEnroll} className="flex gap-3 items-end">
              <div className="flex-1">
                <label className="block text-xs font-medium text-ink mb-1">Agent</label>
                <select value={enrollForm.agent_id} onChange={e => setEnrollForm({ ...enrollForm, agent_id: e.target.value })} className="input-field text-sm" required>
                  <option value="">Select agent...</option>
                  {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </div>
              <div className="flex-1">
                <label className="block text-xs font-medium text-ink mb-1">Course</label>
                <select value={enrollForm.course_id} onChange={e => setEnrollForm({ ...enrollForm, course_id: e.target.value })} className="input-field text-sm" required>
                  <option value="">Select course...</option>
                  {courses.map(c => <option key={c.id} value={c.id}>{c.title}</option>)}
                </select>
              </div>
              <button type="submit" className="btn-primary"><Plus className="h-4 w-4" /> Enroll</button>
            </form>
          </div>
        </div>
      )}

      {!loading && activeTab === 'certifications' && (
        <div className="card p-6">
          <h3 className="text-sm font-medium text-ink mb-4">Agent Certifications</h3>
          <div className="mb-4">
            <label className="block text-xs font-medium text-ink mb-1">Select Agent</label>
            <select value={selectedAgent} onChange={e => { setSelectedAgent(e.target.value); fetchCertifications(e.target.value) }} className="input-field text-sm max-w-xs">
              <option value="">Choose agent...</option>
              {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
            </select>
          </div>
          {!selectedAgent && <p className="text-sm text-ink-muted">Select an agent to view certifications</p>}
          {selectedAgent && certifications.length === 0 && <p className="text-sm text-ink-muted">No completed certifications</p>}
          <div className="space-y-3">
            {certifications.map(c => (
              <div key={c.id} className="flex items-center gap-3 p-3 border border-hairline rounded-lg">
                <CheckCircle2 className="h-5 w-5 text-call-green" />
                <div className="flex-1">
                  <p className="text-sm font-medium text-ink">{c.title}</p>
                  <p className="text-xs text-ink-muted">Completed: {c.completed_at ? new Date(c.completed_at).toLocaleDateString() : 'N/A'}</p>
                </div>
                <span className="text-xs text-ink-muted">{c.duration_hours}h</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {!loading && activeTab === 'coaching' && (
        <div className="card p-6">
          <h3 className="text-sm font-medium text-ink mb-4">Coaching Sessions</h3>
          {coaching.length === 0 && <p className="text-sm text-ink-muted">No coaching sessions yet</p>}
          <div className="space-y-3">
            {coaching.map(s => (
              <div key={s.id} className="border border-hairline rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Target className="h-4 w-4 text-accent" />
                    <span className="font-medium text-ink text-sm">{s.focus_area}</span>
                  </div>
                  <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                    s.status === 'completed' ? 'bg-call-green-soft text-call-green' : 'bg-accent-soft text-accent'
                  }`}>{s.status}</span>
                </div>
                {s.notes && <p className="text-xs text-ink-muted">{s.notes}</p>}
              </div>
            ))}
          </div>
        </div>
      )}

      {showCourseModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">Create Course</h2>
              <button onClick={() => setShowCourseModal(false)} className="p-1.5 rounded-lg hover:bg-surface-hover"><X className="h-5 w-5 text-ink-muted" /></button>
            </div>
            <form onSubmit={handleCreateCourse} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Title</label>
                <input type="text" value={courseForm.title} onChange={e => setCourseForm({ ...courseForm, title: e.target.value })} className="input-field" required />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Description</label>
                <textarea value={courseForm.description} onChange={e => setCourseForm({ ...courseForm, description: e.target.value })} className="input-field" rows={3} />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Modules (comma-separated)</label>
                <input type="text" value={courseForm.modules} onChange={e => setCourseForm({ ...courseForm, modules: e.target.value })} className="input-field" placeholder="Module 1, Module 2" />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Duration (hours)</label>
                <input type="number" step="0.5" value={courseForm.duration_hours} onChange={e => setCourseForm({ ...courseForm, duration_hours: e.target.value })} className="input-field" />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowCourseModal(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" className="btn-primary flex-1"><Plus className="h-4 w-4" /> Create</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showCoachingModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">New Coaching Session</h2>
              <button onClick={() => setShowCoachingModal(false)} className="p-1.5 rounded-lg hover:bg-surface-hover"><X className="h-5 w-5 text-ink-muted" /></button>
            </div>
            <form onSubmit={handleCreateCoaching} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Agent</label>
                <select value={coachingForm.agent_id} onChange={e => setCoachingForm({ ...coachingForm, agent_id: e.target.value })} className="input-field" required>
                  <option value="">Select agent...</option>
                  {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Coach</label>
                <input type="text" value={coachingForm.coach_id} onChange={e => setCoachingForm({ ...coachingForm, coach_id: e.target.value })} className="input-field" placeholder="Coach name or ID" required />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Focus Area</label>
                <input type="text" value={coachingForm.focus_area} onChange={e => setCoachingForm({ ...coachingForm, focus_area: e.target.value })} className="input-field" placeholder="e.g. Call handling, Soft skills" required />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Notes</label>
                <textarea value={coachingForm.notes} onChange={e => setCoachingForm({ ...coachingForm, notes: e.target.value })} className="input-field" rows={3} />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowCoachingModal(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" className="btn-primary flex-1"><Plus className="h-4 w-4" /> Create</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
