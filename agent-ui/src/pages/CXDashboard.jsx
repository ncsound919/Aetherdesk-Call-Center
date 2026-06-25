import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { cxApi } from '../services/api'
import {
  Heart, Star, TrendingUp, Users, MessageSquare,
  ThumbsUp, ThumbsDown, Minus, Search, Loader2
} from 'lucide-react'
import { toast } from 'sonner'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, LineChart, Line, PieChart, Pie, Cell
} from 'recharts'

const COLORS = ['#22c55e', '#f59e0b', '#ef4444']
const SENTIMENT_COLORS = { positive: '#22c55e', neutral: '#94a3b8', negative: '#ef4444' }

export default function CXDashboard() {
  const { tenant } = useAuth()
  const [summary, setSummary] = useState(null)
  const [csatScore, setCsatScore] = useState(null)
  const [nps, setNps] = useState(null)
  const [responseRate, setResponseRate] = useState(null)
  const [surveys, setSurveys] = useState([])
  const [sentimentTrends, setSentimentTrends] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchCustomerId, setSearchCustomerId] = useState('')
  const [customer360, setCustomer360] = useState(null)
  const [searchingCustomer, setSearchingCustomer] = useState(false)

  const fetchAll = useCallback(async () => {
    if (!tenant) return
    setLoading(true)
    try {
      const [summaryRes, csatRes, npsRes, rrRes, surveysRes, trendsRes] = await Promise.all([
        cxApi.getSummary({ tenant_id: tenant.id }),
        cxApi.getCSATScore({ tenant_id: tenant.id }),
        cxApi.getNPS({ tenant_id: tenant.id }),
        cxApi.getResponseRate({ tenant_id: tenant.id }),
        cxApi.listSurveys({ tenant_id: tenant.id, limit: 20 }),
        cxApi.getSentimentTrends({ tenant_id: tenant.id, granularity: 'day' }),
      ])
      setSummary(summaryRes.data)
      setCsatScore(csatRes.data)
      setNps(npsRes.data)
      setResponseRate(rrRes.data)
      setSurveys(Array.isArray(surveysRes.data) ? surveysRes.data : [])

      const grouped = {}
      ;(Array.isArray(trendsRes.data) ? trendsRes.data : []).forEach(row => {
        const period = row.period?.split('T')?.[0] || row.period
        if (!grouped[period]) grouped[period] = { date: period, positive: 0, neutral: 0, negative: 0 }
        grouped[period][row.sentiment || 'neutral'] += row.count || 0
      })
      setSentimentTrends(Object.values(grouped).slice(-14))
    } catch {
      toast.error('Failed to load CX data')
    } finally {
      setLoading(false)
    }
  }, [tenant])

  useEffect(() => { fetchAll() }, [fetchAll])

  async function handleSearchCustomer() {
    if (!searchCustomerId.trim()) return
    setSearchingCustomer(true)
    try {
      const res = await cxApi.getCustomer360(searchCustomerId.trim())
      setCustomer360(res.data)
    } catch {
      toast.error('Customer not found')
      setCustomer360(null)
    } finally {
      setSearchingCustomer(false)
    }
  }

  const csatDistribution = [1, 2, 3, 4, 5].map(r => ({
    rating: `${r} Star${r > 1 ? 's' : ''}`,
    count: surveys.filter(s => s.rating === r).length,
  }))

  const npsBreakdown = nps ? [
    { name: 'Promoters', value: nps.promoters || 0, color: '#22c55e' },
    { name: 'Passives', value: nps.passives || 0, color: '#f59e0b' },
    { name: 'Detractors', value: nps.detractors || 0, color: '#ef4444' },
  ] : []

  const avgRating = csatScore?.avg_rating || 0
  const npsScore = nps?.nps || 0
  const rr = responseRate?.response_rate || 0

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Customer Experience</h1>
          <p className="text-sm text-ink-muted mt-0.5">CSAT scores, NPS, sentiment analysis, and customer insights</p>
        </div>
      </div>

      {loading && (
        <div className="card p-12 flex items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin text-accent" />
          <span className="ml-2 text-ink-muted">Loading CX data...</span>
        </div>
      )}

      {!loading && (
        <>
          {/* Stat Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <div className="card p-5 flex items-center gap-4">
              <div className={`p-3 rounded-xl ${avgRating >= 4 ? 'bg-call-green-soft' : avgRating >= 3 ? 'bg-call-amber-soft' : 'bg-red-50'}`}>
                <Heart className={`h-5 w-5 ${avgRating >= 4 ? 'text-call-green' : avgRating >= 3 ? 'text-telecom-amber' : 'text-red-500'}`} />
              </div>
              <div>
                <p className="text-sm text-ink-muted">CSAT Score</p>
                <p className="text-2xl font-semibold text-ink">{avgRating.toFixed(1)}<span className="text-sm text-ink-muted font-normal">/5</span></p>
              </div>
            </div>
            <div className="card p-5 flex items-center gap-4">
              <div className={`p-3 rounded-xl ${npsScore >= 50 ? 'bg-call-green-soft' : npsScore >= 0 ? 'bg-call-amber-soft' : 'bg-red-50'}`}>
                <TrendingUp className={`h-5 w-5 ${npsScore >= 50 ? 'text-call-green' : npsScore >= 0 ? 'text-telecom-amber' : 'text-red-500'}`} />
              </div>
              <div>
                <p className="text-sm text-ink-muted">NPS Score</p>
                <p className="text-2xl font-semibold text-ink">{npsScore}</p>
              </div>
            </div>
            <div className="card p-5 flex items-center gap-4">
              <div className="p-3 rounded-xl bg-accent-soft">
                <Users className="h-5 w-5 text-accent" />
              </div>
              <div>
                <p className="text-sm text-ink-muted">Response Rate</p>
                <p className="text-2xl font-semibold text-ink">{rr.toFixed(1)}%</p>
              </div>
            </div>
            <div className="card p-5 flex items-center gap-4">
              <div className="p-3 rounded-xl bg-purple-50">
                <MessageSquare className="h-5 w-5 text-purple-500" />
              </div>
              <div>
                <p className="text-sm text-ink-muted">Total Surveys</p>
                <p className="text-2xl font-semibold text-ink">{csatScore?.total_surveys || 0}</p>
              </div>
            </div>
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            {/* CSAT Distribution */}
            <div className="card p-6">
              <h3 className="text-sm font-medium text-ink mb-4">CSAT Distribution</h3>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={csatDistribution}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="rating" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Sentiment Trends */}
            <div className="card p-6">
              <h3 className="text-sm font-medium text-ink mb-4">Sentiment Trends</h3>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={sentimentTrends}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={v => v?.split('-').slice(1).join('/')} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="positive" stroke="#22c55e" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="neutral" stroke="#94a3b8" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="negative" stroke="#ef4444" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* NPS + Customer 360 */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            {/* NPS Breakdown */}
            <div className="card p-6">
              <h3 className="text-sm font-medium text-ink mb-4">NPS Breakdown</h3>
              {npsBreakdown.length > 0 && npsBreakdown.some(s => s.value > 0) ? (
                <div className="flex items-center gap-6">
                  <ResponsiveContainer width={180} height={180}>
                    <PieChart>
                      <Pie data={npsBreakdown} cx="50%" cy="50%" innerRadius={40} outerRadius={70} paddingAngle={3} dataKey="value">
                        {npsBreakdown.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                      </Pie>
                      <Tooltip />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="flex flex-col gap-2">
                    {npsBreakdown.map(s => (
                      <div key={s.name} className="flex items-center gap-2 text-sm">
                        <div className="w-3 h-3 rounded-full" style={{ backgroundColor: s.color }} />
                        <span className="text-ink-muted">{s.name}:</span>
                        <span className="font-medium text-ink">{s.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-ink-muted text-center py-8">No NPS data yet</p>
              )}
            </div>

            {/* Customer 360 Search */}
            <div className="card p-6">
              <h3 className="text-sm font-medium text-ink mb-4">Customer 360 Search</h3>
              <div className="flex gap-2 mb-4">
                <input
                  type="text"
                  value={searchCustomerId}
                  onChange={e => setSearchCustomerId(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSearchCustomer()}
                  placeholder="Enter customer ID or phone..."
                  className="input-field flex-1"
                />
                <button onClick={handleSearchCustomer} className="btn-primary" disabled={searchingCustomer}>
                  {searchingCustomer ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                </button>
              </div>
              {customer360 && (
                <div className="space-y-3 max-h-60 overflow-y-auto">
                  <div className="flex gap-4 text-sm">
                    <div>
                      <span className="text-ink-muted">Interactions:</span>
                      <span className="ml-1 font-medium text-ink">{customer360.summary?.total_interactions || 0}</span>
                    </div>
                    <div>
                      <span className="text-ink-muted">Avg CSAT:</span>
                      <span className="ml-1 font-medium text-ink">{(customer360.summary?.avg_csat || 0).toFixed(1)}</span>
                    </div>
                  </div>
                  {customer360.interactions?.slice(0, 5).map((int, i) => (
                    <div key={i} className="flex items-center justify-between py-1.5 border-b border-hairline text-xs">
                      <span className="text-ink">{int.interaction_type}</span>
                      <span className={`px-1.5 py-0.5 rounded-full ${
                        int.sentiment === 'positive' ? 'bg-call-green-soft text-call-green' :
                        int.sentiment === 'negative' ? 'bg-red-50 text-red-500' :
                        'bg-surface-subtle text-ink-muted'
                      }`}>{int.sentiment}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Recent Surveys */}
          <div className="card overflow-hidden">
            <div className="px-6 py-4 border-b border-hairline">
              <h3 className="text-sm font-medium text-ink">Recent Surveys</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hairline bg-surface-subtle">
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Customer</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Rating</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Feedback</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Channel</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {surveys.length === 0 && (
                    <tr>
                      <td colSpan="5" className="px-4 py-12 text-center text-ink-muted">
                        No surveys yet. Create one to get started.
                      </td>
                    </tr>
                  )}
                  {surveys.map(s => (
                    <tr key={s.id} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                      <td className="px-4 py-3 text-ink font-medium">{s.customer_id || 'Anonymous'}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          {[1, 2, 3, 4, 5].map(star => (
                            <Star key={star} className={`h-3.5 w-3.5 ${star <= s.rating ? 'text-telecom-amber fill-telecom-amber' : 'text-gray-200'}`} />
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-ink-muted max-w-[200px] truncate">{s.feedback || '—'}</td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-accent-soft text-accent">
                          {s.channel}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-ink-muted">{new Date(s.created_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
