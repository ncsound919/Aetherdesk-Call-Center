import React, { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { qualityApi } from '../services/api'
import {
  MessageSquare, Star, Target, TrendingUp, Users, Lightbulb
} from 'lucide-react'
import { toast } from 'sonner'

export default function ConversationQualityDashboard() {
  const { tenant } = useAuth()
  const [activeTab, setActiveTab] = useState('score')
  const [transcript, setTranscript] = useState('')
  const [rubricName, setRubricName] = useState('standard')
  const [scoringResult, setScoringResult] = useState(null)
  const [scores, setScores] = useState([])
  const [trends, setTrends] = useState(null)
  const [coaching, setCoaching] = useState([])
  const [scoring, setScoring] = useState(false)

  const tabs = [
    { key: 'score', label: 'Score Conversation', icon: Star },
    { key: 'scores', label: 'Quality Scores', icon: Target },
    { key: 'trends', label: 'Trends', icon: TrendingUp },
    { key: 'coaching', label: 'Coaching', icon: Lightbulb },
  ]

  async function handleScore() {
    if (!transcript.trim()) return
    setScoring(true)
    try {
      const res = await qualityApi.scoreConversation({
        transcript,
        rubric_name: rubricName,
        tenant_id: tenant.id,
      })
      setScoringResult(res.data)
      toast.success('Conversation scored')
    } catch { toast.error('Failed to score conversation') }
    finally { setScoring(false) }
  }

  async function fetchScores() {
    if (!tenant) return
    try {
      const res = await qualityApi.getScores({ tenant_id: tenant.id })
      setScores(Array.isArray(res.data) ? res.data : [])
    } catch { setScores([]) }
  }

  async function fetchTrends() {
    if (!tenant) return
    try {
      const res = await qualityApi.getTrends({ tenant_id: tenant.id })
      setTrends(res.data)
    } catch { setTrends(null) }
  }

  async function fetchCoaching() {
    if (!tenant) return
    try {
      const res = await qualityApi.getCoaching('agent-1', { tenant_id: tenant.id })
      setCoaching(Array.isArray(res.data) ? res.data : [])
    } catch { setCoaching([]) }
  }

  useEffect(() => {
    if (activeTab === 'scores') fetchScores()
    if (activeTab === 'trends') fetchTrends()
    if (activeTab === 'coaching') fetchCoaching()
  }, [activeTab, tenant])

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-ink tracking-tight">Conversation Quality Scoring</h1>
        <p className="text-sm text-ink-muted mt-0.5">Score transcripts, track agent quality, identify coaching needs</p>
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

      {activeTab === 'score' && (
        <div className="space-y-6">
          <div className="card p-6">
            <h3 className="text-sm font-medium text-ink mb-3">Paste Transcript</h3>
            <textarea
              value={transcript}
              onChange={e => setTranscript(e.target.value)}
              className="input-field w-full h-40 resize-y"
              placeholder="Paste the full conversation transcript here..."
            />
            <div className="flex items-center gap-4 mt-3">
              <select value={rubricName} onChange={e => setRubricName(e.target.value)} className="input-field w-48">
                <option value="standard">Standard Rubric</option>
              </select>
              <button onClick={handleScore} disabled={scoring} className="btn-primary">
                <Star className="h-4 w-4" /> {scoring ? 'Scoring...' : 'Score'}
              </button>
            </div>
          </div>

          {scoringResult && (
            <div className="card p-6">
              <h3 className="text-sm font-medium text-ink mb-3">Scoring Result</h3>
              <div className="grid grid-cols-5 gap-4 mb-4">
                {Object.entries(scoringResult.criteria_scores || {}).map(([criterion, score]) => (
                  <div key={criterion} className="text-center p-3 rounded-lg bg-surface-subtle">
                    <p className="text-xs text-ink-muted capitalize mb-1">{criterion}</p>
                    <p className={`text-xl font-semibold ${
                      score >= 8 ? 'text-call-green' : score >= 5 ? 'text-call-amber' : 'text-red-500'
                    }`}>{score}/10</p>
                  </div>
                ))}
              </div>
              <div className="flex items-center gap-6 p-4 rounded-lg bg-accent-soft">
                <div>
                  <p className="text-xs text-ink-muted">Total Score</p>
                  <p className="text-2xl font-semibold text-accent">{scoringResult.total_score}/{scoringResult.max_possible}</p>
                </div>
                <div>
                  <p className="text-xs text-ink-muted">Percentage</p>
                  <p className="text-2xl font-semibold text-accent">{scoringResult.percentage}%</p>
                </div>
                <div>
                  <p className="text-xs text-ink-muted">Rating</p>
                  <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-sm font-medium ${
                    scoringResult.rating === 'excellent' ? 'bg-call-green-soft text-call-green' :
                    scoringResult.rating === 'good' ? 'bg-blue-50 text-blue-600' :
                    scoringResult.rating === 'average' ? 'bg-call-amber-soft text-call-amber' :
                    'bg-red-50 text-red-500'
                  }`}>
                    {scoringResult.rating.replace('_', ' ')}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'scores' && (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hairline bg-surface-subtle">
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Agent</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Avg Score</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Greeting</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Clarity</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Empathy</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Resolution</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Professionalism</th>
                </tr>
              </thead>
              <tbody>
                {scores.length === 0 && (
                  <tr>
                    <td colSpan="7" className="px-4 py-12 text-center text-ink-muted">
                      No quality scores yet. Score a conversation to get started.
                    </td>
                  </tr>
                )}
                {scores.map((s, i) => (
                  <tr key={s.id || i} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                    <td className="px-4 py-3 text-ink font-medium">{s.agent_id || s.agent_name || 'Unknown'}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                        (s.percentage || 0) >= 80 ? 'bg-call-green-soft text-call-green' :
                        (s.percentage || 0) >= 50 ? 'bg-call-amber-soft text-call-amber' :
                        'bg-red-50 text-red-500'
                      }`}>
                        {s.percentage || s.total_score || 0}%
                      </span>
                    </td>
                    {['greeting', 'clarity', 'empathy', 'resolution', 'professionalism'].map(c => (
                      <td key={c} className="px-4 py-3 text-ink-muted">
                        {s.criteria_scores?.[c] != null ? `${s.criteria_scores[c]}/10` : '-'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'trends' && (
        <div className="card p-6">
          <h3 className="text-sm font-medium text-ink mb-4">Quality Trends</h3>
          {trends?.trend?.length > 0 ? (
            <div className="space-y-2">
              {trends.trend.map((point, i) => (
                <div key={i} className="flex items-center justify-between py-1.5 border-b border-hairline last:border-0">
                  <span className="text-sm text-ink-muted">{new Date(point.date).toLocaleDateString()}</span>
                  <span className={`text-sm font-medium ${
                    point.percentage >= 80 ? 'text-call-green' : point.percentage >= 50 ? 'text-call-amber' : 'text-red-500'
                  }`}>{point.percentage}%</span>
                </div>
              ))}
              <p className="text-sm text-ink-muted pt-2">Average: {trends.avg_percentage}%</p>
            </div>
          ) : (
            <p className="text-sm text-ink-muted text-center py-8">No trend data available yet.</p>
          )}
        </div>
      )}

      {activeTab === 'coaching' && (
        <div className="space-y-4">
          <div className="card p-4 flex items-center gap-3 bg-call-amber-soft">
            <Lightbulb className="h-5 w-5 text-call-amber" />
            <p className="text-sm text-ink-muted">
              Coaching opportunities identified based on lowest-scoring criteria per agent.
            </p>
          </div>
          {coaching.length === 0 && (
            <div className="card p-12 text-center text-ink-muted">
              No coaching data available. Score some conversations first.
            </div>
          )}
          {coaching.map((item, i) => (
            <div key={i} className="card p-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-ink capitalize">{item.criterion}</p>
                <p className="text-xs text-ink-muted">Avg: {item.average_score}/10 — Gap: {item.gap} pts</p>
              </div>
              <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                item.priority === 'high' ? 'bg-red-50 text-red-500' :
                item.priority === 'medium' ? 'bg-call-amber-soft text-call-amber' :
                'bg-call-green-soft text-call-green'
              }`}>
                {item.priority} priority
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
