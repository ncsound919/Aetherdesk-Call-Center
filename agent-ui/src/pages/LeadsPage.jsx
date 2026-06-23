import React, { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useNavigate } from 'react-router-dom'
import api from '../services/api'
import { toast } from 'sonner'

export default function LeadsPage() {
  const { tenant } = useAuth()
  const [leads, setLeads] = useState([])
  const [loading, setLoading] = useState(true)
  const navigate = useNavigate()

  useEffect(() => {
    if (!tenant) return
    setLoading(true)
    api.get('/leads', { params: { tenant_id: tenant.id } })
      .then((res) => setLeads(Array.isArray(res.data) ? res.data : []))
      .catch(() => toast.error('Failed to load leads'))
      .finally(() => setLoading(false))
  }, [tenant])

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Leads</h1>
          <p className="text-gray-600">Manage your lead database</p>
        </div>
        <button
          onClick={() => navigate('/leads/import')}
          className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 text-sm font-medium"
        >
          Import CSV
        </button>
      </div>
      {loading ? (
        <p className="text-gray-500">Loading...</p>
      ) : leads.length === 0 ? (
        <p className="text-gray-500">No leads yet. Import a CSV to get started.</p>
      ) : (
        <div className="bg-white shadow rounded-lg overflow-hidden">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Phone</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {leads.map((lead, i) => (
                <tr key={lead.id || i}>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{lead.name || '—'}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{lead.phone || '—'}</td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">{lead.email || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
