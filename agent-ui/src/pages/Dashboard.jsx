import React, { useEffect, useState, useCallback, useRef } from 'react'
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
  Activity, TrendingUp, AlertTriangle, RefreshCw
} from 'lucide-react'
import { toast } from 'sonner'

// ── Skeleton helpers ─────────────────────────────────────────────────────────

function SkeletonStatCard() {
  return (
    <div className="card p-5 animate-pulse" aria-hidden="true">
      <div className="flex items-center justify-between mb-3">
        <div className="h-9 w-9 rounded-xl bg-slate-100" />
        <div className="h-4 w-16 rounded bg-slate-100" />
      </div>
      <div className="h-8 w-24 rounded bg-slate-100 mb-1" />
      <div className="h-3 w-20 rounded bg-slate-100" />
    </div>
  )
}

function SkeletonCallRow() {
  return (
    <div className="flex items-center gap-3 p-4 animate-pulse" aria-hidden="true">
      <div className="h-10 w-10 rounded-xl bg-slate-100 shrink-0" />
      <div className="flex-1 space-y-2">
        <div className="h-3.5 w-32 rounded bg-slate-100" />
        <div className="h-3 w-20 rounded bg-slate-100" />
      </div>
      <div className="h-3 w-12 rounded bg-slate-100" />
    </div>
  )
}

// ── Section error fallback ────────────────────────────────────────────────────

function SectionError({ message, onRetry }) {
  return (
    <div className="flex flex-col items-center gap-3 py-10 text-center">
      <div className="h-10 w-10 rounded-full bg-rose-50 flex items-center justify-center">
        <AlertTriangle className="h-5 w-5 text-rose-500" aria-hidden="true" />
      </div>
      <p className="text-sm text-slate-600 font-medium max-w-xs">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="flex items-center gap-1.5 text-xs font-bold text-slate-700 hover:text-slate-900 underline underline-offset-2"
        >
          <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
          Retry
        </button>
      )}
    </div>
  )
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

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

  // Granular loading + error state per section (Issue 1, 7)
  const [statsLoading, setStatsLoading]       = useState(true)
  const [callsLoading, setCallsLoading]       = useState(true)
  const [agentsLoading, setAgentsLoading]     = useState(true)
  const [statsError, setStatsError]           = useState(null)
  const [callsError, setCallsError]           = useState(null)

  const [showCallModal, setShowCallModal] = useState(false)
  const [callForm, setCallForm] = useState({ number: '', agentId: '' })
  const [calling, setCalling] = useState(false)
  const socket = useSocket()

  // AbortController refs so we can cancel on unmount / re-fetch (Issue 3)
  const statsAbort  = useRef(null)
  const callsAbort  = useRef(null)

  function formatDuration(m) {
    const h = Math.floor(m / 60)
    const mins = Math.round(m % 60)
    return h > 0 ? `${h}h ${mins}m` : `${mins}m`
  }

  // ── fetchStats ──────────────────────────────────────────────────────────────
  const fetchStats = useCallback(async () => {
    if (!tenant) return
    // Cancel any in-flight request before starting a new one (Issue 3)
    statsAbort.current?.abort()
    statsAbort.current = new AbortController()
    setStatsLoading(true)
    setStatsError(null)
    try {
      const today = new Date().toISOString().split('T')[0]
      const res = await api.get(
        `/usage?tenant_id=${tenant.id}&period_start=${today}T00:00:00&period_end=${new Date().toISOString()}`,
        { signal: statsAbort.current.signal }
      )
      const d = res.data
      setStats({
        activeCalls:       d.active_calls       || 0,
        totalCallsToday:   d.total_calls        || 0,
        avgCallDuration:   formatDuration(d.avg_call_duration || 0),
        availableAgents:   d.active_agents      || 0,
        totalAgents:       d.total_agents       || 0,
      })
    } catch (e) {
      if (e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED') return
      const msg = e?.response?.data?.error || e?.message || 'Failed to load stats'
      setStatsError(msg)                       // (Issue 1)
      toast.error(msg)
    } finally {
      setStatsLoading(false)
    }
  }, [tenant])

  // ── fetchRecentCalls ─────────────────────────────────────────────────────────
  const fetchRecentCalls = useCallback(async () => {
    if (!tenant) return
    callsAbort.current?.abort()
    callsAbort.current = new AbortController()
    setCallsLoading(true)
    setCallsError(null)
    try {
      const res = await api.get(
        `/calls?tenant_id=${tenant.id}&status=completed`,
        { signal: callsAbort.current.signal }
      )
      setRecentCalls(Array.isArray(res.data) ? res.data.slice(0, 10) : [])
    } catch (e) {
      if (e?.name === 'CanceledError' || e?.code === 'ERR_CANCELED') return
      const msg = e?.response?.data?.error || e?.message || 'Failed to load recent calls'
      setCallsError(msg)                       // (Issue 1)
      toast.error(msg)
      setRecentCalls([])
    } finally {
      setCallsLoading(false)
    }
  }, [tenant])

  // ── fetchAgents ──────────────────────────────────────────────────────────────
  const fetchAgents = useCallback(async () => {
    if (!tenant) return
    setAgentsLoading(true)
    try {
      const res = await agentApi.list(tenant.id)
      setAgents(Array.isArray(res.data) ? res.data : [])
    } catch {
      setAgents([])
    } finally {
      setAgentsLoading(false)
    }
  }, [tenant])

  // ── Mount / unmount ──────────────────────────────────────────────────────────
  useEffect(() => {
    fetchStats()
    fetchRecentCalls()
    fetchAgents()
    // Cleanup: abort any in-flight requests on unmount (Issue 3)
    return () => {
      statsAbort.current?.abort()
      callsAbort.current?.abort()
    }
  }, [fetchStats, fetchRecentCalls, fetchAgents])

  // ── Live socket updates ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!socket?.tenantSocket) return
    const h = () => { fetchStats(); fetchRecentCalls() }
    window.addEventListener('call:status', h)
    window.addEventListener('call:assigned', h)
    return () => {
      window.removeEventListener('call:status', h)
      window.removeEventListener('call:assigned', h)
    }
  }, [socket, fetchStats, fetchRecentCalls])

  const hasAgents = agents.length > 0
  const hasCalls  = recentCalls.length > 0

  // ── Make call handler ────────────────────────────────────────────────────────
  async function handleMakeCall(e) {
    e.preventDefault()
    if (!callForm.number || !callForm.agentId) {
      toast.error(t('dashboard.fillInRequired', 'Fill in number and agent'))
      return
    }
    setCalling(true)
    try {
      const num = callForm.number.startsWith('+')
        ? callForm.number
        : `+1${callForm.number.replace(/\D/g, '')}`
      await api.post(
        '/calls',
        { agent_id: callForm.agentId, caller_number: num, call_direction: 'inbound', intent: 'generalInquiry' },
        { params: { tenant_id: tenant.id } }
      )
      toast.success(`Call initiated to ${callForm.number}`)
      setShowCallModal(false)
      setCallForm({ number: '', agentId: '' })
      fetchStats()
      fetchRecentCalls()
    } catch (err) {
      toast.error(err.response?.data?.detail || err.message || 'Call failed')
    } finally {
      setCalling(false)
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="p-6 max-w-7xl mx-auto">

      {/* ── Header ── */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">{t('dashboard.title')}</h1>
          <p className="text-sm text-ink-muted mt-0.5">{t('dashboard.subtitle')}</p>
        </div>
        <button
          onClick={() => setShowCallModal(true)}
          className="btn-primary"
          aria-label={t('dashboard.makeACall')}
        >
          <PhoneCall className="h-4 w-4" aria-hidden="true" />
          {t('dashboard.makeACall')}
        </button>
      </div>

      {/* ── Quick-Start onboarding checklist ── */}
      {!hasCalls && !callsLoading && (
        <div className="mb-6 card overflow-hidden">
          <div className="bg-gradient-to-r from-primary-dark to-primary p-5 text-white">
            <h2 className="text-lg font-semibold">{t('dashboard.welcomeTitle')}</h2>
            <p className="text-sm text-white/60 mt-1">{t('dashboard.welcomeDesc')}</p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-hairline">
            {[
              { done: hasAgents,  label: t('dashboard.createAgent'),        desc: t('dashboard.createAgentDesc'),        action: () => navigate('/agents'),   btn: t('dashboard.addAgent') },
              { done: false,      label: t('dashboard.makeTestCall'),        desc: t('dashboard.makeTestCallDesc'),        action: () => setShowCallModal(true), btn: t('dashboard.callNow') },
              { done: false,      label: t('dashboard.configureSettings'),   desc: t('dashboard.configureSettingsDesc'),   action: () => navigate('/settings'), btn: t('dashboard.openSettings') },
            ].map((step, i) => (
              <div key={i} className="flex items-start gap-3 p-5">
                {step.done
                  ? <CheckCircle2 className="h-5 w-5 text-call-green mt-0.5 shrink-0" aria-hidden="true" />
                  : <Circle       className="h-5 w-5 text-ink-subtle   mt-0.5 shrink-0" aria-hidden="true" />}
                <div className="flex-1">
                  <p className="font-medium text-ink text-sm">{step.label}</p>
                  <p className="text-xs text-ink-muted mt-0.5">{step.desc}</p>
                  <button
                    type="button"
                    onClick={step.action}
                    className="mt-2 text-xs text-accent hover:text-accent-strong font-medium flex items-center gap-1"
                  >
                    {step.btn} <ArrowRight className="h-3 w-3" aria-hidden="true" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Stats grid — skeleton while loading, error fallback, or data ── */}
      <div
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-6"
        role="region"
        aria-label={t('dashboard.title')}
        aria-busy={statsLoading}    // (Issue 7)
      >
        {statsLoading ? (
          // Per-section skeleton (Issue 7)
          Array.from({ length: 4 }).map((_, i) => <SkeletonStatCard key={i} />)
        ) : statsError ? (
          // Per-section error fallback (Issue 1)
          <div className="sm:col-span-2 lg:col-span-4 card">
            <SectionError message={statsError} onRetry={fetchStats} />
          </div>
        ) : (
          <>
            <StatCard title={t('dashboard.activeCalls')}      value={stats.activeCalls}                       icon={<PhoneIncoming className="h-5 w-5" />} color="text-call-green"    bgColor="bg-call-green-soft" />
            <StatCard title={t('dashboard.totalCallsToday')}  value={stats.totalCallsToday}                   icon={<BarChart3      className="h-5 w-5" />} color="text-accent"       bgColor="bg-accent-soft"    />
            <StatCard title={t('dashboard.avgCallDuration')}  value={stats.avgCallDuration}                   icon={<Clock         className="h-5 w-5" />} color="text-purple-600"  bgColor="bg-purple-50"      />
            <StatCard title={t('dashboard.availableAgents')}  value={`${stats.availableAgents} / ${stats.totalAgents}`} icon={<Users className="h-5 w-5" />} color="text-telecom-amber" bgColor="bg-call-amber-soft" />
          </>
        )}
      </div>

      {/* ── Activity Feed — skeleton, error, or data ── */}
      <section aria-label={t('dashboard.recentActivity', 'Recent Activity')} aria-live="polite">
        {callsLoading ? (
          // Per-section skeleton rows (Issue 7)
          <div className="card divide-y divide-hairline">
            {Array.from({ length: 5 }).map((_, i) => <SkeletonCallRow key={i} />)}
          </div>
        ) : callsError ? (
          <div className="card">
            <SectionError message={callsError} onRetry={fetchRecentCalls} />
          </div>
        ) : (
          <RecentCalls calls={recentCalls} />
        )}
      </section>

      {/* ── Make a Call Modal ── */}
      {showCallModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
          role="dialog"
          aria-modal="true"
          aria-labelledby="call-modal-title"
          aria-live="assertive"   // (Issue 2 — modal state change is announced)
        >
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-3">
                <div className="h-9 w-9 rounded-xl bg-accent-soft flex items-center justify-center">
                  <PhoneCall className="h-4 w-4 text-accent" aria-hidden="true" />
                </div>
                <h2 id="call-modal-title" className="text-lg font-semibold text-ink">
                  {t('dashboard.callModalTitle')}
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setShowCallModal(false)}
                className="p-1.5 rounded-lg hover:bg-surface-hover"
                aria-label={t('dashboard.cancel', 'Close dialog')}  // (Issue 2)
              >
                <X className="h-5 w-5 text-ink-muted" aria-hidden="true" />
              </button>
            </div>

            <form
              onSubmit={handleMakeCall}
              className="space-y-4"
              aria-label={t('dashboard.callModalTitle')}
            >
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5" htmlFor="call-number">
                  {t('dashboard.phoneNumber')}
                </label>
                <input
                  id="call-number"
                  type="tel"
                  placeholder={t('dashboard.phonePlaceholder')}
                  value={callForm.number}
                  onChange={(e) => setCallForm({ ...callForm, number: e.target.value })}
                  className="input-field"
                  required
                />
                <p className="text-xs text-ink-subtle mt-1">{t('dashboard.phoneHint')}</p>
              </div>

              <div>
                <label className="block text-sm font-medium text-ink mb-1.5" htmlFor="call-agent">
                  {t('dashboard.assignTo')}
                </label>
                <select
                  id="call-agent"
                  value={callForm.agentId}
                  onChange={(e) => setCallForm({ ...callForm, agentId: e.target.value })}
                  className="input-field"
                  required
                >
                  <option value="">{t('dashboard.selectAgent')}</option>
                  {agents.map((a) => (
                    <option key={a.id} value={a.id}>{a.name} ({a.status})</option>
                  ))}
                </select>
                {agentsLoading && (
                  <p className="text-xs text-ink-subtle mt-1 flex items-center gap-1">
                    <Loader2 className="h-3 w-3 animate-spin" aria-hidden="true" />
                    Loading agents…
                  </p>
                )}
                {!agentsLoading && agents.length === 0 && (
                  <p className="text-xs text-call-amber mt-1">{t('dashboard.noAgents')}</p>
                )}
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCallModal(false)}
                  className="btn-secondary flex-1"
                >
                  {t('dashboard.cancel')}
                </button>
                <button
                  type="submit"
                  disabled={calling || agents.length === 0}
                  className="btn-primary flex-1"
                  aria-label={calling ? t('dashboard.calling') : t('dashboard.startCall')}
                >
                  {calling
                    ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                    : <PhoneCall className="h-4 w-4" aria-hidden="true" />}
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
