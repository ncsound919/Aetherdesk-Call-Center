import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { dataGovernanceApi } from '../services/api'
import {
  GitBranch, Database, Search, Activity, TrendingUp, CheckCircle2, AlertTriangle
} from 'lucide-react'
import { toast } from 'sonner'

export default function DataGovernanceDashboard() {
  const { tenant } = useAuth()
  const [healthScore, setHealthScore] = useState(null)
  const [healthLoading, setHealthLoading] = useState(false)
  const [lineageSearch, setLineageSearch] = useState({ table: '', record_id: '' })
  const [lineageResult, setLineageResult] = useState(null)
  const [lineageLoading, setLineageLoading] = useState(false)
  const [graphData, setGraphData] = useState(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [columnSearch, setColumnSearch] = useState({ table: '', column: '' })
  const [columnResult, setColumnResult] = useState(null)
  const [columnLoading, setColumnLoading] = useState(false)

  const fetchHealthScore = useCallback(async () => {
    if (!tenant) return
    setHealthLoading(true)
    try {
      const res = await dataGovernanceApi.getHealthScore()
      setHealthScore(res.data?.data || null)
    } catch { setHealthScore(null) }
    finally { setHealthLoading(false) }
  }, [tenant])

  useEffect(() => {
    fetchHealthScore()
  }, [fetchHealthScore])

  useEffect(() => {
    if (!tenant) return
    ;(async () => {
      try {
        const res = await dataGovernanceApi.getLineageGraph({})
        setGraphData(res.data?.data || null)
      } catch { setGraphData(null) }
    })()
  }, [tenant])

  async function handleLineageSearch(e) {
    e.preventDefault()
    if (!lineageSearch.table || !lineageSearch.record_id) return
    setLineageLoading(true)
    try {
      const res = await dataGovernanceApi.getRecordLineage(lineageSearch)
      setLineageResult(res.data?.data || null)
    } catch {
      setLineageResult(null)
      toast.error('No lineage found for this record')
    }
    finally { setLineageLoading(false) }
  }

  async function handleColumnSearch(e) {
    e.preventDefault()
    if (!columnSearch.table || !columnSearch.column) return
    setColumnLoading(true)
    try {
      const res = await dataGovernanceApi.getColumnLineage(columnSearch)
      setColumnResult(res.data?.data || null)
    } catch {
      setColumnResult(null)
      toast.error('No column lineage found')
    }
    finally { setColumnLoading(false) }
  }

  const score = healthScore?.overall || 0
  const scoreColor = score >= 90 ? 'text-green-600' : score >= 70 ? 'text-amber-500' : 'text-red-500'
  const scoreBg = score >= 90 ? 'bg-green-50 border-green-200' : score >= 70 ? 'bg-amber-50 border-amber-200' : 'bg-red-50 border-red-200'

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Data Governance</h1>
          <p className="text-sm text-ink-muted mt-0.5">Data lineage tracking, column-level tracing, and health monitoring</p>
        </div>
      </div>

      <div className={`card p-6 border ${scoreBg}`}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-ink flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Data Health Score
          </h2>
          {healthLoading && <span className="text-sm text-ink-muted animate-pulse">Refreshing...</span>}
        </div>
        <div className="flex items-center gap-6">
          <div className="relative w-28 h-28">
            <svg className="w-28 h-28 transform -rotate-90" viewBox="0 0 100 100">
              <circle cx="50" cy="50" r="40" fill="none" stroke="#e5e7eb" strokeWidth="8" />
              <circle cx="50" cy="50" r="40" fill="none" stroke={score >= 90 ? '#22c55e' : score >= 70 ? '#f59e0b' : '#ef4444'} strokeWidth="8"
                strokeDasharray={`${score * 2.51} 251`} strokeLinecap="round" />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className={`text-2xl font-bold ${scoreColor}`}>{score}%</span>
            </div>
          </div>
          <div className="grid grid-cols-3 gap-6 flex-1">
            <div>
              <p className="text-sm text-ink-muted flex items-center gap-1">
                <CheckCircle2 className="h-3.5 w-3.5 text-green-500" /> Completeness
              </p>
              <p className="text-xl font-semibold text-ink">{healthScore?.completeness || 0}%</p>
            </div>
            <div>
              <p className="text-sm text-ink-muted flex items-center gap-1">
                <GitBranch className="h-3.5 w-3.5 text-blue-500" /> Consistency
              </p>
              <p className="text-xl font-semibold text-ink">{healthScore?.consistency || 0}%</p>
            </div>
            <div>
              <p className="text-sm text-ink-muted flex items-center gap-1">
                <TrendingUp className="h-3.5 w-3.5 text-purple-500" /> Freshness
              </p>
              <p className="text-xl font-semibold text-ink">{healthScore?.freshness || 0}%</p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card p-6">
          <h2 className="text-lg font-semibold text-ink flex items-center gap-2 mb-4">
            <Search className="h-5 w-5" />
            Lineage Search
          </h2>
          <form onSubmit={handleLineageSearch} className="flex gap-2 mb-4">
            <input
              type="text" placeholder="Table name (e.g. call_sessions)"
              value={lineageSearch.table}
              onChange={e => setLineageSearch({ ...lineageSearch, table: e.target.value })}
              className="input-field flex-1" required
            />
            <input
              type="text" placeholder="Record ID"
              value={lineageSearch.record_id}
              onChange={e => setLineageSearch({ ...lineageSearch, record_id: e.target.value })}
              className="input-field flex-1" required
            />
            <button type="submit" className="btn-primary" disabled={lineageLoading}>
              {lineageLoading ? '...' : 'Search'}
            </button>
          </form>
          {lineageResult && (
            <div className="space-y-2">
              <p className="text-sm text-ink-muted">
                Found {lineageResult.total || 0} lineage entries for <strong>{lineageResult.record?.table}:{lineageResult.record?.id}</strong>
              </p>
              {lineageResult.lineage?.length > 0 && (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {lineageResult.lineage.map((entry, i) => (
                    <div key={i} className="flex items-center gap-2 p-2 bg-surface-subtle rounded-lg text-sm">
                      <Database className="h-3.5 w-3.5 text-ink-muted shrink-0" />
                      <span className="font-mono text-xs text-ink truncate">{entry.source_table}:{entry.source_id}</span>
                      <span className="text-ink-muted mx-1">→</span>
                      <span className="font-mono text-xs text-ink truncate">{entry.target_table}:{entry.target_id}</span>
                      <span className="ml-auto text-xs text-ink-muted">{entry.operation}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="card p-6">
          <h2 className="text-lg font-semibold text-ink flex items-center gap-2 mb-4">
            <GitBranch className="h-5 w-5" />
            Column Lineage
          </h2>
          <form onSubmit={handleColumnSearch} className="flex gap-2 mb-4">
            <input
              type="text" placeholder="Table name"
              value={columnSearch.table}
              onChange={e => setColumnSearch({ ...columnSearch, table: e.target.value })}
              className="input-field flex-1" required
            />
            <input
              type="text" placeholder="Column name"
              value={columnSearch.column}
              onChange={e => setColumnSearch({ ...columnSearch, column: e.target.value })}
              className="input-field flex-1" required
            />
            <button type="submit" className="btn-primary" disabled={columnLoading}>
              {columnLoading ? '...' : 'Trace'}
            </button>
          </form>
          {columnResult && (
            <div className="space-y-2">
              <p className="text-sm text-ink-muted">
                Found {columnResult.total || 0} lineage entries for <strong>{columnResult.table}.{columnResult.column}</strong>
              </p>
              {columnResult.lineage?.length > 0 && (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {columnResult.lineage.map((entry, i) => (
                    <div key={i} className="flex items-center gap-2 p-2 bg-surface-subtle rounded-lg text-sm">
                      <span className="font-mono text-xs text-ink truncate">{entry.source_table}:{entry.source_id}</span>
                      <span className="text-ink-muted mx-1">→</span>
                      <span className="font-mono text-xs text-ink truncate">{entry.target_table}:{entry.target_id}</span>
                      <span className="ml-auto text-xs text-ink-muted">{entry.operation}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="card p-6">
        <h2 className="text-lg font-semibold text-ink flex items-center gap-2 mb-4">
          <GitBranch className="h-5 w-5" />
          Lineage Graph
        </h2>
        {graphLoading && <p className="text-sm text-ink-muted animate-pulse">Loading graph...</p>}
        {graphData && (
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {graphData.nodes?.length === 0 && (
              <p className="text-sm text-ink-muted py-8 text-center">No lineage data recorded yet.</p>
            )}
            <div className="flex flex-wrap gap-2 mb-3">
              {graphData.nodes?.map((node, i) => (
                <span key={i} className="inline-flex items-center gap-1 px-2.5 py-1 bg-surface-subtle rounded-full text-xs font-medium text-ink">
                  <Database className="h-3 w-3" />
                  {node.table}
                </span>
              ))}
            </div>
            {graphData.edges?.map((edge, i) => (
              <div key={i} className="flex items-center gap-2 p-3 bg-surface-subtle rounded-lg text-sm border border-hairline">
                <div className="flex items-center gap-2 min-w-0 flex-1">
                  <span className="font-mono text-xs bg-white px-2 py-1 rounded border text-ink truncate">{edge.source}</span>
                  <span className="text-ink-muted text-lg">→</span>
                  <span className="font-mono text-xs bg-white px-2 py-1 rounded border text-ink truncate">{edge.target}</span>
                </div>
                <span className="text-xs text-ink-muted shrink-0">{edge.operation}</span>
                {edge.column && <span className="text-xs text-accent shrink-0">col: {edge.column}</span>}
              </div>
            ))}
          </div>
        )}
        {!graphData && !graphLoading && (
          <p className="text-sm text-ink-muted py-8 text-center">Loading lineage graph data...</p>
        )}
      </div>
    </div>
  )
}
