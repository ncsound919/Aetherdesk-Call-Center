import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import api from '../services/api'
import { toast } from 'sonner'

export default function ScriptEditorPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get(`/scripts/${id}`)
      .then((res) => {
        setName(res.data.name || '')
        setContent(res.data.content || '')
      })
      .catch(() => {
        toast.error('Failed to load script')
        navigate('/scripts')
      })
      .finally(() => setLoading(false))
  }, [id])

  const handleSave = async () => {
    setSaving(true)
    try {
      await api.put(`/scripts/${id}`, { name, content })
      toast.success('Script saved')
    } catch {
      toast.error('Failed to save script')
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <div className="p-6"><p className="text-gray-500">Loading...</p></div>

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-semibold text-gray-900">Edit Script</h1>
        <div className="flex gap-2">
          <button onClick={() => navigate('/scripts')} className="px-4 py-2 border border-gray-300 rounded-md text-sm text-gray-700 hover:bg-gray-50">
            Back
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm font-medium disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>
      <input
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="w-full px-3 py-2 border border-gray-300 rounded-md mb-4 text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500"
        placeholder="Script name"
      />
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        rows={20}
        className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm font-mono focus:outline-none focus:ring-blue-500 focus:border-blue-500"
        placeholder="Write your script content here..."
      />
    </div>
  )
}
