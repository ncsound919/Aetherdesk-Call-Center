import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { wfmMetricsApi } from '../services/api'
import {
  Clock, Target, Star, ThumbsUp, BarChart3, TrendingUp, Loader2
} from 'lucide-react'
import {
  LineChart, Line, BarChart as ReBarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from 'recharts'

const PIE_COLORS = ['#22c55e', '#f59e0b', '#ef4444']

export default function WFMMetricsDashboard() {
  const { tenant } = useAuth()
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(false)

  const fetchSummary = useCallback(async () => {
    if (!tenant) return
    setLoading(true)
    try {
      const res = await wfmMetricsApi.getSummary(tenant.id, { period: '7d' })
      setSummary(res.data)
    } catch { setSummary(null) }
    finally { setLoading(false) }
  }, [tenant])

  useEffect(() => { fetchSummary() }, [fetchSummary])

  const aht = summary?.aht || {}
  const fcr = summary?.fcr || {}
  const nps = summary?.nps || {}
  const csatTrend = summary?.csat_trend || []

  const npsData = [
    { name: 'Promoters', value: nps.promoters || 0 },
    { name: 'Passives', value: nps.passives || 0 },
    { name: 'Detractors', value: nps.detractors || 0 },
  ]

  const ahtDistData = [
    { name: 'Avg', value: aht.avg || 0 },
    { name: 'P50', value: aht.p50 || 0 },
    { name: 'P90', value: aht.p90 || 0 },
    { name: 'P99', value: aht.p99 || 0 },
  ]

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">WFM Metrics</h1>
          <p className="text-sm text-ink-muted mt-0.5">Average Handle Time, FCR, CSAT, and NPS</p>
        </div>
        {loading && <Loader2 className="h-5 w-5 animate-spin text-accent" />}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="card p-4">
          <div className="flex items-center gap-2 text-ink-muted mb-2">
            <Clock className="h-4 w-4" />
            <span className="text-xs font-medium">Avg AHT</span>
          </div>
          <p className="text-2xl font-semibold text-ink">{aht.avg || 0}s</p>
          <p className="text-xs text-ink-muted mt-1">{aht.count || 0} calls</p>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-2 text-ink-muted mb-2">
            <Target className="h-4 w-4" />
            <span className="text-xs font-medium">FCR Rate</span>
          </div>
          <p className="text-2xl font-semibold text-call-green">{fcr.fcr_rate || 0}%</p>
          <p className="text-xs text-ink-muted mt-1">{fcr.resolved || 0}/{fcr.total || 0} resolved</p>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-2 text-ink-muted mb-2">
            <Star className="h-4 w-4" />
            <span className="text-xs font-medium">CSAT</span>
          </div>
          <p className="text-2xl font-semibold text-telecom-amber">
            {csatTrend.length > 0 ? csatTrend[csatTrend.length - 1].avg_rating.toFixed(1) : '—'}
          </p>
          <p className="text-xs text-ink-muted mt-1">/ 5.0</p>
        </div>
        <div className="card p-4">
          <div className="flex items-center gap-2 text-ink-muted mb-2">
            <ThumbsUp className="h-4 w-4" />
            <span className="text-xs font-medium">NPS Score</span>
          </div>
          <p className={`text-2xl font-semibold ${nps.nps_score >= 0 ? 'text-call-green' : 'text-red-500'}`}>
            {nps.nps_score || 0}
          </p>
          <p className="text-xs text-ink-muted mt-1">{nps.total || 0} responses</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <div className="card p-6">
          <h3 className="text-sm font-medium text-ink mb-4 flex items-center gap-2"><TrendingUp className="h-4 w-4" /> CSAT Trend</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={csatTrend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis domain={[0, 5]} tick={{ fontSize: 11 }} />
              <Tooltip />
              <Line type="monotone" dataKey="avg_rating" stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} name="CSAT" />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="card p-6">
          <h3 className="text-sm font-medium text-ink mb-4 flex items-center gap-2"><BarChart3 className="h-4 w-4" /> AHT Distribution</h3>
          <ResponsiveContainer width="100%" height={250}>
            <ReBarChart data={ahtDistData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip />
              <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} name="Seconds" />
            </ReBarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-6">
          <h3 className="text-sm font-medium text-ink mb-4 flex items-center gap-2"><ThumbsUp className="h-4 w-4" /> NPS Breakdown</h3>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie data={npsData} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, value }) => `${name}: ${value}`}>
                {npsData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i]} />)}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="card p-6">
          <h3 className="text-sm font-medium text-ink mb-4 flex items-center gap-2"><Clock className="h-4 w-4" /> Recent Metrics</h3>
          <div className="text-sm text-ink-muted">
            <p>AHT entries tracked: {aht.count || 0}</p>
            <p>FCR events: {fcr.total || 0}</p>
            <p>CSAT ratings: {csatTrend.reduce((s, d) => s + d.count, 0)}</p>
            <p>NPS responses: {nps.total || 0}</p>
            <p className="mt-3 text-xs">Metrics auto-populate as calls are tracked via the WFM Metrics API endpoints.</p>
          </div>
        </div>
      </div>
    </div>
  )
}
