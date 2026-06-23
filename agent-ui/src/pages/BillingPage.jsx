import React, { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import api from '../services/api'
import { toast } from 'sonner'

export default function BillingPage() {
  const { tenant } = useAuth()
  const [summary, setSummary] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!tenant) return
    setLoading(true)
    api.get('/billing', { params: { tenant_id: tenant.id } })
      .then((res) => setSummary(res.data))
      .catch(() => toast.error('Failed to load billing info'))
      .finally(() => setLoading(false))
  }, [tenant])

  if (loading) {
    return <div className="p-6"><p className="text-gray-500">Loading billing...</p></div>
  }

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-gray-900 mb-4">Billing</h1>
      {summary ? (
        <div className="bg-white shadow rounded-lg p-6 space-y-4">
          <div className="flex justify-between">
            <span className="text-gray-600">Plan</span>
            <span className="font-medium">{summary.plan || 'Free'}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">Calls this month</span>
            <span className="font-medium">{summary.calls_this_month ?? 0}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">Minutes used</span>
            <span className="font-medium">{summary.minutes_used ?? 0}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">Estimated cost</span>
            <span className="font-medium">${summary.estimated_cost?.toFixed(2) ?? '0.00'}</span>
          </div>
        </div>
      ) : (
        <p className="text-gray-500">No billing information available.</p>
      )}
    </div>
  )
}
