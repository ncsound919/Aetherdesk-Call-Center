import React, { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { useSocket } from '../context/SocketContext'
import { useNavigate } from 'react-router-dom'
import api, { agentApi } from '../services/api'
import StatCard from '../components/StatCard'
import RecentCalls from '../components/RecentCalls'
import {
  PhoneIncoming, PhoneOutgoing, Clock, Users, PhoneCall,
  CheckCircle2, Circle, Loader2, X, ArrowRight, BarChart3,
  Activity, TrendingUp
} from 'lucide-react'
import { toast } from 'sonner'

export default function Dashboard() {
  const { t } = useTranslation()
  const { tenant } = useAuth()
  const navigate = useNavigate()
  const [stats, setStats] = useState({
    activeCalls: 0, totalCallsToday: 0, avgCallDuration: '0:00',
    availableAgents: 0, totalAgents: 0,
  })
  const [recentCalls, setRecentCalls] = useState([])
  const [agents, setAgents] = useState([])
  const [showCallModal, setShowCallModal] = useState(false)
  const [callForm, setCallForm] = useState({ number: '', agentId: '' })
  const [calling, setCalling] = useState(false)
  const socket = useSocket()

  const fetchStats = useCallback(async () => {
    if (!tenant) return
    try {
      const today = new Date().toISOString().split('T')[0]
      const res = await api.get(`/usage?tenant_id=${tenant.id}&period_start=${today}T00:00:00&period_end=${new Date().toISOString()}`)
      const d = res.data
      setStats({
        activeCalls: d.active_calls || 0,
        totalCallsToday: d.total_calls || 0,
        avgCallDuration: formatDuration(d.avg_call_duration || 0),
        availableAgents: d.active_agents || 0,
        totalAgents: d.total_agents || 0,
      })
    } catch (e) { console.error('fetchStats', e) }
  }, [tenant])

  const fetchRecentCalls = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await api.get(`/calls?tenant_id=${tenant.id}&status=completed`)
      setRecentCalls(Array.isArray(res.data) ? res.data.slice(0, 10) : [])
    } catch (e) { setRecentCalls([]) }
  }, [tenant])

  const fetchAgents = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await agentApi.list(tenant.id)
      setAgents(Array.isArray(res.data) ? res.data : [])
    } catch { setAgents([]) }
  }, [tenant])

  useEffect(() => { fetchStats(); fetchRecentCalls(); fetchAgents() }, [fetchStats, fetchRecentCalls, fetchAgents])
  useEffect(() => {
    if (!socket?.tenantSocket) return
    const h = () => { fetchStats(); fetchRecentCalls() }
    window.addEventListener('call:status', h); window.addEventListener('call:assigned', h)
    return () => { window.removeEventListener('call:status', h); window.removeEventListener('call:assigned', h) }
  }, [socket, fetchStats, fetchRecentCalls])

  function formatDuration(m) { const h = Math.floor(m / 60); const mins = Math.round(m % 60); return h > 0 ? `${h}h ${mins}m` : `${mins}m` }

  const hasAgents = agents.length > 0
  const hasCalls = recentCalls.length > 0

  async function handleMakeCall(e) {
    e.preventDefault()
    if (!callForm.number || !callForm.agentId) { toast.error(t('dashboard.fillInRequired', 'Fill in number and agent')); return }
    setCalling(true)
    try {
      const num = callForm.number.startsWith('+') ? callForm.number : `+1${callForm.number.replace(/\D/g, '')}`
      await api.post('/calls', { agent_id: callForm.agentId, caller_number: num, call_direction: 'inbound', intent: 'generalInquiry' }, { params: { tenant_id: tenant.id } })
      toast.success(`Call initiated to ${callForm.number}`)
      setShowCallModal(false); setCallForm({ number: '', agentId: '' })
      fetchStats(); fetchRecentCalls()
    } catch (err) { toast.error(err.response?.data?.detail || err.message || 'Call failed') }
    finally { setCalling(false) }
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">{t('dashboard.title')}</h1>
          <p className="text-sm text-ink-muted mt-0.5">{t('dashboard.subtitle')}</p>
        </div>
        <button onClick={() => setShowCallModal(true)} className="btn-primary" aria-label={t('dashboard.makeACall')}>
          <PhoneCall className="h-4 w-4" />
          {t('dashboard.makeACall')}
        </button>
      </div>

      {/* Quick Start */}
      {!hasCalls && (
        <div className="mb-6 card overflow-hidden">
          <div className="bg-gradient-to-r from-primary-dark to-primary p-5 text-white">
            <h2 className="text-lg font-semibold">{t('dashboard.welcomeTitle')}</h2>
            <p className="text-sm text-white/60 mt-1">{t('dashboard.welcomeDesc')}</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-hairline">
            {[
              { done: hasAgents, label: t('dashboard.createAgent'), desc: t('dashboard.createAgentDesc'), action: () => navigate('/agents'), btn: t('dashboard.addAgent') },
              { done: false, label: t('dashboard.makeTestCall'), desc: t('dashboard.makeTestCallDesc'), action: () => setShowCallModal(true), btn: t('dashboard.callNow') },
              { done: false, label: t('dashboard.configureSettings'), desc: t('dashboard.configureSettingsDesc'), action: () => navigate('/settings'), btn: t('dashboard.openSettings') },
            ].map((step, i) => (
              <div key={i} className="flex items-start gap-3 p-5">
                {step.done ? <CheckCircle2 className="h-5 w-5 text-call-green mt-0.5 shrink-0" /> : <Circle className="h-5 w-5 text-ink-subtle mt-0.5 shrink-0" />}
                <div className="flex-1">
                  <p className="font-medium text-ink text-sm">{step.label}</p>
                  <p className="text-xs text-ink-muted mt-0.5">{step.desc}</p>
                  <button onClick={step.action} className="mt-2 text-xs text-accent hover:text-accent-strong font-medium flex items-center gap-1">
                    {step.btn} <ArrowRight className="h-3 w-3" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-6" role="region" aria-label={t('dashboard.title')}>
        <StatCard title={t('dashboard.activeCalls')} value={stats.activeCalls} icon={<PhoneIncoming className="h-5 w-5" />} color="text-call-green" bgColor="bg-call-green-soft" />
        <StatCard title={t('dashboard.totalCallsToday')} value={stats.totalCallsToday} icon={<BarChart3 className="h-5 w-5" />} color="text-accent" bgColor="bg-accent-soft" />
        <StatCard title={t('dashboard.avgCallDuration')} value={stats.avgCallDuration} icon={<Clock className="h-5 w-5" />} color="text-purple-600" bgColor="bg-purple-50" />
        <StatCard title={t('dashboard.availableAgents')} value={`${stats.availableAgents} / ${stats.totalAgents}`} icon={<Users className="h-5 w-5" />} color="text-telecom-amber" bgColor="bg-call-amber-soft" />
      </div>

      {/* Activity Feed */}
      <div aria-live="polite">
        <RecentCalls calls={recentCalls} />
      </div>

      {/* Make a Call Modal */}
      {showCallModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-3">
                <div className="h-9 w-9 rounded-xl bg-accent-soft flex items-center justify-center">
                  <PhoneCall className="h-4 w-4 text-accent" />
                </div>
                <h2 className="text-lg font-semibold text-ink">{t('dashboard.callModalTitle')}</h2>
              </div>
              <button onClick={() => setShowCallModal(false)} className="p-1.5 rounded-lg hover:bg-surface-hover">
                <X className="h-5 w-5 text-ink-muted" />
              </button>
            </div>
            <form onSubmit={handleMakeCall} className="space-y-4" role="form" aria-label={t('dashboard.callModalTitle')}>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5" htmlFor="call-number">{t('dashboard.phoneNumber')}</label>
                <input id="call-number" type="tel" placeholder={t('dashboard.phonePlaceholder')} value={callForm.number}
                  onChange={(e) => setCallForm({ ...callForm, number: e.target.value })}
                  className="input-field" required aria-label={t('dashboard.phoneNumber')} />
                <p className="text-xs text-ink-subtle mt-1">{t('dashboard.phoneHint')}</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5" htmlFor="call-agent">{t('dashboard.assignTo')}</label>
                <select id="call-agent" value={callForm.agentId} onChange={(e) => setCallForm({ ...callForm, agentId: e.target.value })}
                  className="input-field" required aria-label={t('dashboard.assignTo')}>
                  <option value="">{t('dashboard.selectAgent')}</option>
                  {agents.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.status})</option>)}
                </select>
                {agents.length === 0 && <p className="text-xs text-call-amber mt-1">{t('dashboard.noAgents')}</p>}
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowCallModal(false)} className="btn-secondary flex-1">{t('dashboard.cancel')}</button>
                <button type="submit" disabled={calling || agents.length === 0} className="btn-primary flex-1" aria-label={calling ? t('dashboard.calling') : t('dashboard.startCall')}>
                  {calling ? <Loader2 className="h-4 w-4 animate-spin" /> : <PhoneCall className="h-4 w-4" />}
                  {calling ? t('dashboard.calling') : t('dashboard.startCall')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
