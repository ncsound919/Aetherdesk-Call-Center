import React, { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'
import { toast } from 'sonner'

export default function ScriptsPage() {
  const { tenant } = useAuth()
  const [scripts, setScripts] = useState([])
  const [loading, setLoading] = useState(true)
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
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

  const handleCreate = async () => {
    if (!newName.trim()) return
    setCreating(true)
    try {
      const res = await api.post('/scripts', { tenant_id: tenant.id, name: newName, content: '' })
      setNewName('')
      navigate(`/scripts/${res.data.id}`)
    } catch {
      toast.error('Failed to create script')
    } finally {
      setCreating(false)
    }
  }

  const handleDelete = async (scriptId) => {
    if (!window.confirm('Delete this script?')) return
    try {
      await api.delete(`/scripts/${scriptId}`)
      setScripts((prev) => prev.filter((s) => s.id !== scriptId))
      toast.success('Script deleted')
    } catch {
      toast.error('Failed to delete script')
    }
  }

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-gray-900 mb-4">Scripts</h1>
      <div className="flex gap-2 mb-6">
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="New script name"
          className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
        />
        <button
          onClick={handleCreate}
          disabled={creating}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm font-medium disabled:opacity-50"
        >
          {creating ? 'Creating...' : 'New Script'}
        </button>
      </div>
      {loading ? (
        <p className="text-gray-500">Loading...</p>
      ) : scripts.length === 0 ? (
        <p className="text-gray-500">No scripts yet. Create one above.</p>
      ) : (
        <div className="space-y-3">
          {scripts.map((script) => (
            <div key={script.id} className="bg-white shadow rounded-lg p-4 flex items-center justify-between">
              <button
                onClick={() => navigate(`/scripts/${script.id}`)}
                className="text-left flex-1"
              >
                <p className="font-medium text-gray-900">{script.name}</p>
                <p className="text-sm text-gray-500 truncate">{script.content?.substring(0, 100) || 'Empty script'}</p>
              </button>
              <button
                onClick={() => handleDelete(script.id)}
                className="ml-4 text-red-600 hover:text-red-800 text-sm"
              >
                Delete
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
