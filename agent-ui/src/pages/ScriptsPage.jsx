import React, { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'
import { FileText, Plus, Trash2, Loader2, BookOpen, Search } from 'lucide-react'
import { toast } from 'sonner'

export default function ScriptsPage() {
  const { tenant } = useAuth()
  const [scripts, setScripts] = useState([])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const navigate = useNavigate()

  const fetchScripts = () => {
    if (!tenant) return
    setLoading(true)
    api.get('/scripts', { params: { tenant_id: tenant.id } })
      .then((res) => setScripts(Array.isArray(res.data) ? res.data : []))
      .catch(() => toast.error('Failed to load scripts'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchScripts() }, [tenant])

  const handleDelete = async (scriptId, name) => {
    if (!window.confirm(`Delete "${name}"?`)) return
    try {
      await api.delete(`/scripts/${scriptId}`)
      setScripts((prev) => prev.filter((s) => s.id !== scriptId))
      toast.success('Script deleted')
    } catch { toast.error('Failed to delete script') }
  }

  const filtered = scripts.filter(s => s.name?.toLowerCase().includes(search.toLowerCase()))

  return (
    <div className="p-6 max-w-5xl mx-auto animate-slide-up">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Scripts</h1>
          <p className="text-sm text-ink-muted mt-0.5">Create and manage your call scripts</p>
        </div>
        <button onClick={() => navigate('/scripts/new')} className="btn-primary">
          <Plus className="h-4 w-4" />
          New Script
        </button>
      </div>

      {/* Search */}
      {scripts.length > 0 && (
        <div className="relative mb-6">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-subtle" />
          <input type="text" value={search} onChange={(e) => setSearch(e.target.value)}
            className="input-field pl-9" placeholder="Search scripts..." />
        </div>
      )}

      {loading ? (
        <div className="card p-12 text-center">
          <Loader2 className="h-6 w-6 animate-spin mx-auto text-ink-subtle mb-2" />
          <p className="text-sm text-ink-muted">Loading scripts...</p>
        </div>
      ) : scripts.length === 0 ? (
        <div className="card p-12 text-center">
          <FileText className="h-10 w-10 mx-auto text-ink-subtle mb-3" />
          <p className="text-sm text-ink-muted">No scripts yet</p>
          <p className="text-xs text-ink-subtle mt-1">Create a script to guide your agents through calls</p>
          <button onClick={() => navigate('/scripts/new')} className="btn-primary mt-4">
            <Plus className="h-4 w-4" />
            Create your first script
          </button>
          <div className="mt-6 pt-6 border-t border-hairline">
            <div className="flex items-center gap-2 justify-center text-xs text-ink-muted mb-3">
              <BookOpen className="h-4 w-4" />
              <span>Start with a template</span>
            </div>
            <p className="text-xs text-ink-muted">Templates available for Sales, Support, Billing, and Technical scripts</p>
          </div>
        </div>
      ) : (
        <div className="space-y-2">
          {filtered.map((script) => (
            <div key={script.id}
              className="card p-4 flex items-center justify-between group hover:border-accent/20 transition-colors cursor-pointer"
              onClick={() => navigate(`/scripts/${script.id}`)}>
              <div className="flex items-center gap-3 min-w-0">
                <div className="p-2 rounded-lg bg-accent-soft shrink-0">
                  <FileText className="h-4 w-4 text-accent" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-ink truncate">{script.name}</p>
                  <p className="text-xs text-ink-muted truncate mt-0.5">
                    {script.content ? script.content.substring(0, 120).replace(/\n/g, ' ') : 'Empty script'}
                  </p>
                </div>
              </div>
              <button onClick={(e) => { e.stopPropagation(); handleDelete(script.id, script.name) }}
                className="btn-ghost p-2 text-call-red opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
          {filtered.length === 0 && search && (
            <div className="card p-8 text-center">
              <p className="text-sm text-ink-muted">No scripts matching "{search}"</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
