import React, { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { agentApi } from '../services/api'
import { Plus, Pencil, Trash2, X, Loader2, Users } from 'lucide-react'
import { toast } from 'sonner'

const SKILLS = ['sales', 'support', 'technical', 'billing', 'accounting']

export default function AgentManagement() {
  const { tenant } = useAuth()
  const [agents, setAgents] = useState([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ name: '', type: 'ai', skills: [], config: {} })
  const [saving, setSaving] = useState(false)

  useEffect(() => { if (tenant) fetchAgents() }, [tenant])

  const fetchAgents = async () => {
    try {
      const res = await agentApi.list(tenant.id)
      setAgents(Array.isArray(res.data) ? res.data : [])
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }

  const openNew = () => { setEditing(null); setForm({ name: '', type: 'ai', skills: [], config: {} }); setShowModal(true) }
  const openEdit = (a) => { setEditing(a); setForm({ name: a.name, type: a.agent_type, skills: a.skills || [], config: {} }); setShowModal(true) }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) { toast.error('Agent name is required'); return }
    setSaving(true)
    try {
      if (editing) {
        await agentApi.update(tenant.id, editing.id, form)
        toast.success('Agent updated')
      } else {
        await agentApi.create(tenant.id, form)
        toast.success('Agent created')
      }
      setShowModal(false); setEditing(null); fetchAgents()
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to save') }
    finally { setSaving(false) }
  }

  const handleDelete = async (id, name) => {
    if (!window.confirm(`Delete agent "${name}"?`)) return
    try {
      await agentApi.delete(tenant.id, id)
      toast.success('Agent deleted')
      fetchAgents()
    } catch (err) { toast.error('Failed to delete') }
  }

  const toggleStatus = async (agent) => {
    const newStatus = agent.status === 'available' ? 'offline' : 'available'
    try {
      await agentApi.updateStatus(agent.id, newStatus)
      fetchAgents()
    } catch (err) { toast.error('Failed to update status') }
  }

  const toggleSkill = (skill) => {
    setForm((prev) => ({
      ...prev,
      skills: prev.skills.includes(skill) ? prev.skills.filter((s) => s !== skill) : [...prev.skills, skill],
    }))
  }

  const getTypeBadge = (type) => {
    switch (type) {
      case 'ai': return <span className="badge-green">AI</span>
      case 'human': return <span className="badge-amber">Human</span>
      case 'hybrid': return <span className="badge-slate">Hybrid</span>
      default: return <span className="badge-slate">{type}</span>
    }
  }

  const getStatusBadge = (status) => {
    switch (status) {
      case 'available': case 'online': return <span className="badge-green">{status}</span>
      case 'offline': return <span className="badge-slate">{status}</span>
      case 'busy': case 'on_call': return <span className="badge-amber">{status}</span>
      default: return <span className="badge-slate">{status || 'unknown'}</span>
    }
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Agent Management</h1>
          <p className="text-sm text-ink-muted mt-0.5">Manage your AI and human agents</p>
        </div>
        <button onClick={openNew} className="btn-primary">
          <Plus className="h-4 w-4" />
          Add Agent
        </button>
      </div>

      {loading ? (
        <div className="card p-12 text-center">
          <Loader2 className="h-6 w-6 animate-spin mx-auto text-ink-subtle mb-2" />
          <p className="text-sm text-ink-muted">Loading agents...</p>
        </div>
      ) : agents.length === 0 ? (
        <div className="card p-12 text-center">
          <Users className="h-10 w-10 mx-auto text-ink-subtle mb-3" />
          <p className="text-sm text-ink-muted">No agents yet</p>
          <button onClick={openNew} className="btn-primary mt-4">
            <Plus className="h-4 w-4" />
            Create your first agent
          </button>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-hairline bg-surface-hover">
                  <th className="text-left px-5 py-3 text-xs font-semibold text-ink-muted uppercase tracking-wider">Agent</th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-ink-muted uppercase tracking-wider">Type</th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-ink-muted uppercase tracking-wider">Status</th>
                  <th className="text-left px-5 py-3 text-xs font-semibold text-ink-muted uppercase tracking-wider">Skills</th>
                  <th className="text-right px-5 py-3 text-xs font-semibold text-ink-muted uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {agents.map((agent) => (
                  <tr key={agent.id} className="hover:bg-surface-hover transition-colors">
                    <td className="px-5 py-4">
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-full bg-accent-soft flex items-center justify-center">
                          <span className="text-accent text-xs font-semibold">{agent.name?.[0]?.toUpperCase() || '?'}</span>
                        </div>
                        <div>
                          <p className="text-sm font-medium text-ink">{agent.name}</p>
                          <p className="text-xs text-ink-muted">{agent.email || agent.id?.slice(0, 8)}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-5 py-4">{getTypeBadge(agent.agent_type)}</td>
                    <td className="px-5 py-4">
                      <button onClick={() => toggleStatus(agent)} className="hover:opacity-80 transition-opacity">
                        {getStatusBadge(agent.status)}
                      </button>
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex gap-1 flex-wrap">
                        {(agent.skills || []).map((s) => (
                          <span key={s} className="badge-slate text-[11px]">{s}</span>
                        ))}
                      </div>
                    </td>
                    <td className="px-5 py-4 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => openEdit(agent)} className="btn-ghost p-2">
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button onClick={() => handleDelete(agent.id, agent.name)} className="btn-ghost p-2 text-call-red hover:bg-call-red-soft">
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-lg mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">{editing ? 'Edit Agent' : 'Add Agent'}</h2>
              <button onClick={() => setShowModal(false)} className="p-1.5 rounded-lg hover:bg-surface-hover">
                <X className="h-5 w-5 text-ink-muted" />
              </button>
            </div>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Name</label>
                <input type="text" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="input-field" placeholder="e.g. Sarah Sales" required />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Type</label>
                <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}
                  className="input-field">
                  <option value="ai">AI Agent</option>
                  <option value="human">Human Agent</option>
                  <option value="hybrid">Hybrid Agent</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-2">Skills</label>
                <div className="flex flex-wrap gap-2">
                  {SKILLS.map((s) => (
                    <button key={s} type="button" onClick={() => toggleSkill(s)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                        form.skills.includes(s)
                          ? 'bg-accent text-white border-accent'
                          : 'bg-white text-ink-muted border-hairline hover:border-ink-subtle'
                      }`}>
                      {s}
                    </button>
                  ))}
                </div>
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowModal(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" disabled={saving} className="btn-primary flex-1">
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  {editing ? 'Update Agent' : 'Create Agent'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
