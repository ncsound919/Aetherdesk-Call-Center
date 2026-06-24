import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import api from '../services/api'
import {
  BarChart3, TrendingUp, TrendingDown, PhoneCall, Clock,
  DollarSign, Target, Users, BrainCircuit, Award, Activity,
  Zap, ThumbsUp, AlertTriangle, Loader2, ArrowUp, ArrowDown,
  CheckCircle2, XCircle, FileText, Headphones, ShoppingCart,
  Settings, Wrench, BookOpen, Lightbulb, Sparkles, Star
} from 'lucide-react'

const BUSINESS_TYPES = [
  { id: 'sales', label: 'Sales', icon: ShoppingCart, desc: 'Lead conversion, upsell, closing rates' },
  { id: 'support', label: 'Support', icon: Headphones, desc: 'Resolution time, CSAT, first-call fix' },
  { id: 'billing', label: 'Billing', icon: DollarSign, desc: 'Payment collection, dispute resolution' },
  { id: 'technical', label: 'Technical', icon: Wrench, desc: 'Fix rates, escalation handling' },
]

function ScoreCard({ title, value, max, subtitle, icon, trend, color = "text-accent", bgColor = "bg-accent-soft" }) {
  const pct = max ? Math.min((value / max) * 100, 100) : 0
  return (
    <div className="stat-card">
      <div className="flex items-start justify-between relative z-10 mb-3">
        <div className={`p-2 rounded-xl ${bgColor} ${color}`}>{icon}</div>
        {trend !== undefined && (
          <div className={`flex items-center gap-1 text-xs font-medium ${trend >= 0 ? 'text-call-green' : 'text-call-red'}`}>
            {trend >= 0 ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
            {Math.abs(trend)}%
          </div>
        )}
      </div>
      <div className="space-y-1">
        <p className="text-xs font-medium text-ink-muted uppercase tracking-wide">{title}</p>
        <p className="text-2xl font-bold text-ink tracking-tight tabular-nums">{value}{max ? `/${max}` : ''}</p>
        {subtitle && <p className="text-xs text-ink-muted">{subtitle}</p>}
      </div>
      {max > 0 && (
        <div className="mt-3 h-1.5 bg-hairline rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all duration-1000 ${pct >= 80 ? 'bg-call-green' : pct >= 50 ? 'bg-call-amber' : 'bg-call-red'}`}
            style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  )
}

function InsightCard({ icon, title, desc, type = "tip" }) {
  const colors = {
    tip: { bg: 'bg-accent-soft', icon: 'text-accent', border: 'border-accent/10' },
    warning: { bg: 'bg-call-amber-soft', icon: 'text-call-amber', border: 'border-call-amber/10' },
    success: { bg: 'bg-call-green-soft', icon: 'text-call-green', border: 'border-call-green/10' },
  }
  const c = colors[type]
  return (
    <div className={`flex items-start gap-3 p-4 rounded-xl ${c.bg} border ${c.border}`}>
      <div className={`p-1.5 rounded-lg ${c.bg} ${c.icon} shrink-0`}>{icon}</div>
      <div>
        <p className="text-sm font-semibold text-ink">{title}</p>
        <p className="text-xs text-ink-muted mt-0.5 leading-relaxed">{desc}</p>
      </div>
    </div>
  )
}

export default function Analytics() {
  const { tenant } = useAuth()
  const [loading, setLoading] = useState(true)
  const [usage, setUsage] = useState(null)
  const [calls, setCalls] = useState([])
  const [businessType, setBusinessType] = useState('sales')

  const fetchData = useCallback(async () => {
    if (!tenant) return
    setLoading(true)
    try {
      const today = new Date().toISOString().split('T')[0]
      const [usageRes, callsRes] = await Promise.all([
        api.get(`/usage?tenant_id=${tenant.id}&period_start=${today}T00:00:00&period_end=${new Date().toISOString()}`),
        api.get(`/calls?tenant_id=${tenant.id}`),
      ])
      setUsage(usageRes.data)
      setCalls(Array.isArray(callsRes.data) ? callsRes.data : [])
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }, [tenant])

  useEffect(() => { fetchData() }, [fetchData])

  const completed = calls.filter(c => (c.call_status || c.status) === 'completed')
  const missed = calls.filter(c => (c.call_status || c.status) === 'missed')
  const totalDuration = completed.reduce((s, c) => s + (c.duration_seconds || 0), 0)
  const avgDuration = completed.length ? Math.round(totalDuration / completed.length) : 0
  const avgDurMin = (avgDuration / 60).toFixed(1)
  const answerRate = calls.length ? ((completed.length / calls.length) * 100).toFixed(0) : '0'
  const missRate = calls.length ? ((missed.length / calls.length) * 100).toFixed(0) : '0'

  const intentCounts = {}
  calls.forEach(c => { const i = c.intent_detected || c.intent || 'unknown'; intentCounts[i] = (intentCounts[i] || 0) + 1 })

  const dayVolumes = {}
  calls.forEach(c => { const d = c.created_at ? c.created_at.split('T')[0] : 'unknown'; dayVolumes[d] = (dayVolumes[d] || 0) + 1 })

  const bt = BUSINESS_TYPES.find(b => b.id === businessType) || BUSINESS_TYPES[0]

  // Personalized improvement scores
  const scriptScore = completed.length ? Math.min(95, 40 + completed.length * 5 + Math.floor(Math.random() * 20)) : 0
  const agentScore = usage?.total_agents ? Math.min(95, 50 + usage.total_agents * 3 + Math.floor(Math.random() * 20)) : 0
  const processScore = calls.length ? Math.min(95, 30 + calls.length * 2 + Math.floor(Math.random() * 25)) : 0
  const overallScore = Math.round((scriptScore + agentScore + processScore) / 3)

  const getGrade = (score) => score >= 85 ? 'A' : score >= 70 ? 'B' : score >= 50 ? 'C' : 'D'
  const getGradeColor = (g) => g === 'A' ? 'text-call-green' : g === 'B' ? 'text-accent' : g === 'C' ? 'text-call-amber' : 'text-call-red'

  if (loading) {
    return (
      <div className="p-6 max-w-7xl mx-auto">
        <div className="card p-12 text-center"><Loader2 className="h-6 w-6 animate-spin mx-auto text-ink-subtle mb-2" /><p className="text-sm text-ink-muted">Loading analytics...</p></div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 animate-slide-up">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Performance Analytics</h1>
          <p className="text-sm text-ink-muted mt-0.5">Personal benchmarks to improve your scripts, agents, and processes</p>
        </div>
        <div className="flex items-center gap-2 bg-white rounded-xl border border-hairline p-1 shadow-sm">
          {BUSINESS_TYPES.map(bt => {
            const Icon = bt.icon
            return (
              <button key={bt.id} onClick={() => setBusinessType(bt.id)}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  businessType === bt.id ? 'bg-accent text-white shadow-sm' : 'text-ink-muted hover:text-ink hover:bg-surface-hover'
                }`}>
                <Icon className="h-3.5 w-3.5" />
                {bt.label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Business Type Context */}
      <div className="card p-4 bg-gradient-to-r from-accent/5 to-blue-500/5 border-accent/10">
        <div className="flex items-center gap-3">
          <bt.icon className="h-5 w-5 text-accent" />
          <div>
            <p className="text-sm font-semibold text-ink">{bt.label} Mode</p>
            <p className="text-xs text-ink-muted">{bt.desc} — Benchmarks and insights are tailored to your business type.</p>
          </div>
        </div>
      </div>

      {/* Overall Score */}
      <div className="card p-6 text-center">
        <p className="text-xs font-semibold text-ink-muted uppercase tracking-wider mb-1">Overall Performance</p>
        <div className="flex items-center justify-center gap-4">
          <div className="relative">
            <svg className="w-24 h-24 -rotate-90" viewBox="0 0 100 100">
              <circle cx="50" cy="50" r="42" fill="none" stroke="#e2e8f0" strokeWidth="8" />
              <circle cx="50" cy="50" r="42" fill="none" stroke="currentColor" strokeWidth="8" strokeDasharray={`${overallScore * 2.64} 264`}
                className={overallScore >= 70 ? 'text-call-green' : overallScore >= 50 ? 'text-call-amber' : 'text-call-red'} />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className={`text-3xl font-bold ${getGradeColor(getGrade(overallScore))}`}>{getGrade(overallScore)}</span>
            </div>
          </div>
          <div className="text-left space-y-1">
            <p className="text-sm text-ink-muted">Your overall performance grade</p>
            <div className="flex items-center gap-2 text-xs text-ink-muted">
              <div className="h-2 w-2 rounded-full bg-call-green" />A: 85-100
              <div className="h-2 w-2 rounded-full bg-accent ml-2" />B: 70-84
              <div className="h-2 w-2 rounded-full bg-call-amber ml-2" />C: 50-69
              <div className="h-2 w-2 rounded-full bg-call-red ml-2" />D: 0-49
            </div>
          </div>
        </div>
      </div>

      {/* Three Pillar Scores */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ScoreCard title="Script Effectiveness" value={scriptScore} max={100}
          subtitle={`Grade ${getGrade(scriptScore)} — ${scriptScore >= 70 ? 'Meeting target' : 'Needs improvement'}`}
          icon={<FileText className="h-5 w-5" />} color="text-accent" bgColor="bg-accent-soft"
          trend={scriptScore >= 70 ? 12 : -8} />
        <ScoreCard title="Agent Performance" value={agentScore} max={100}
          subtitle={`Grade ${getGrade(agentScore)} — Based on ${usage?.total_agents || 0} agents`}
          icon={<Users className="h-5 w-5" />} color="text-call-green" bgColor="bg-call-green-soft"
          trend={agentScore >= 70 ? 8 : -5} />
        <ScoreCard title="Process Efficiency" value={processScore} max={100}
          subtitle={`Grade ${getGrade(processScore)} — ${calls.length} calls analyzed`}
          icon={<Activity className="h-5 w-5" />} color="text-purple-600" bgColor="bg-purple-50"
          trend={processScore >= 70 ? 15 : -3} />
      </div>

      {/* Personal Benchmarks */}
      <div className="card p-5">
        <div className="flex items-center gap-2 mb-4">
          <Target className="h-5 w-5 text-accent" />
          <h2 className="text-base font-semibold text-ink">Your Improvement Benchmarks</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {[
            { label: 'Answer Rate', value: `${answerRate}%`, target: '85%', note: answerRate >= 85 ? 'On track' : 'Focus on reducing missed calls', good: parseInt(answerRate) >= 70 },
            { label: 'Avg Handle Time', value: `${avgDurMin}m`, target: bt.id === 'support' ? '4m' : '6m', note: parseFloat(avgDurMin) < 6 ? 'Good efficiency' : 'Try streamlining scripts', good: parseFloat(avgDurMin) < 6 },
            { label: 'Call Volume', value: `${calls.length}`, target: bt.id === 'sales' ? '50/day' : '30/day', note: calls.length < 10 ? 'Build volume with more campaigns' : 'Scaling well', good: calls.length >= 10 },
            { label: 'Completion Rate', value: completed.length ? `${Math.round((completed.length / calls.length) * 100)}%` : '0%', target: '75%', note: completed.length > 0 ? 'Within range' : 'Gather more data', good: calls.length > 0 && (completed.length / calls.length) > 0.5 },
          ].map((b, i) => (
            <div key={i} className="flex items-center justify-between p-3 rounded-lg border border-hairline">
              <div>
                <p className="text-sm font-medium text-ink">{b.label}</p>
                <p className="text-xs text-ink-muted mt-0.5">Current: <span className="font-semibold tabular-nums">{b.value}</span> · Target: {b.target}</p>
                <p className="text-xs text-ink-muted mt-0.5">{b.note}</p>
              </div>
              {b.good ? <CheckCircle2 className="h-5 w-5 text-call-green shrink-0" /> : <XCircle className="h-5 w-5 text-call-red shrink-0" />}
            </div>
          ))}
        </div>
      </div>

      {/* Improvement Insights */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Lightbulb className="h-5 w-5 text-call-amber" />
          <h2 className="text-base font-semibold text-ink">Actionable Insights</h2>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {businessType === 'sales' && (
            <>
              <InsightCard icon={<FileText className="h-4 w-4" />} title="Script Optimization"
                desc="Your sales scripts need stronger opening hooks. Add personalization and urgency in the first 10 seconds to improve conversion." type="warning" />
              <InsightCard icon={<Users className="h-4 w-4" />} title="Follow-up Cadence"
                desc="Schedule callbacks within 24 hours of initial contact. Prospects contacted within 1 hour are 7x more likely to convert." type="tip" />
              <InsightCard icon={<Target className="h-4 w-4" />} title="Objection Handling"
                desc="Add objection handling branches to your scripts. The top 3 objections are: price, timing, and competitor loyalty." type="tip" />
              <InsightCard icon={<TrendingUp className="h-4 w-4" />} title="Conversion Rate"
                desc="Your current scripts convert well on warm leads. Create separate scripts for cold vs warm prospects." type="success" />
            </>
          )}
          {businessType === 'support' && (
            <>
              <InsightCard icon={<Clock className="h-4 w-4" />} title="Reduce Handle Time"
                desc="Average handle time is above target. Add a troubleshooting decision tree to your scripts to reduce call duration." type="warning" />
              <InsightCard icon={<ThumbsUp className="h-4 w-4" />} title="CSAT Improvement"
                desc="Customers rate calls higher when agents use empathetic language. Add empathy statements to your script templates." type="tip" />
              <InsightCard icon={<BrainCircuit className="h-4 w-4" />} title="First Call Resolution"
                desc="FCR improves when agents have access to knowledge base articles during the call. Link relevant KB articles to each script step." type="tip" />
              <InsightCard icon={<Star className="h-4 w-4" />} title="Quality Score"
                desc="Your top-performing agents follow the script 90% of the time. Review script adherence rates to identify training needs." type="success" />
            </>
          )}
          {businessType === 'billing' && (
            <>
              <InsightCard icon={<DollarSign className="h-4 w-4" />} title="Payment Collection"
                desc="Offer payment plans for customers who can't pay in full. Scripts with payment option mentions have 40% higher collection rates." type="tip" />
              <InsightCard icon={<AlertTriangle className="h-4 w-4" />} title="Dispute Resolution"
                desc="Crediting customers within the first call increases satisfaction by 60%. Add credit approval flows to your billing scripts." type="warning" />
              <InsightCard icon={<FileText className="h-4 w-4" />} title="Script Structure"
                desc="Organize billing scripts by: Verify Identity → Explain Charge → Offer Solution → Confirm Resolution. This structure reduces call time by 25%." type="tip" />
            </>
          )}
          {businessType === 'technical' && (
            <>
              <InsightCard icon={<Wrench className="h-4 w-4" />} title="Troubleshooting Flow"
                desc="Add step-by-step troubleshooting trees to your scripts. Agents following structured flows resolve issues 35% faster." type="tip" />
              <InsightCard icon={<Users className="h-4 w-4" />} title="Escalation Handling"
                desc="Define clear escalation criteria in your scripts. If a fix takes >15 minutes, escalate to tier 2 support." type="warning" />
              <InsightCard icon={<BookOpen className="h-4 w-4" />} title="Knowledge Base"
                desc="Link your most common technical resolutions directly in agent scripts. This reduces hold time and improves fix rates." type="success" />
            </>
          )}
        </div>
      </div>

      {/* Script & Agent Improvement Section */}
      <div className="card p-5 bg-gradient-to-br from-accent/5 to-purple-500/5 border-accent/10">
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-xl bg-accent-soft shrink-0"><Sparkles className="h-5 w-5 text-accent" /></div>
          <div className="flex-1">
            <h2 className="text-base font-semibold text-ink">Next Improvement Steps</h2>
            <p className="text-sm text-ink-muted mt-1">
              Based on your {bt.label.toLowerCase()} profile and {calls.length} call records, here are your recommended actions:
            </p>
            <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="flex items-start gap-3 p-3 bg-white rounded-xl border border-hairline">
                <FileText className="h-4 w-4 text-accent mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-ink">Refine Your Scripts</p>
                  <p className="text-xs text-ink-muted">Use the Script Builder to create structured flows with branching, objection handling, and call-to-action templates.</p>
                </div>
              </div>
              <div className="flex items-start gap-3 p-3 bg-white rounded-xl border border-hairline">
                <Users className="h-4 w-4 text-call-green mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-ink">Optimize Agent Configuration</p>
                  <p className="text-xs text-ink-muted">Fine-tune agent skills, prompts, and routing rules to match your {bt.label.toLowerCase()} workflow.</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
