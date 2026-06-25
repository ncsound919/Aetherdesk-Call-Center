import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { portalApi } from '../services/api'
import {
  User, Phone, CreditCard, MessageSquare, Calendar, Clock, Settings
} from 'lucide-react'
import { toast } from 'sonner'

export default function CustomerPortalPreview() {
  const { tenant } = useAuth()
  const [searchTerm, setSearchTerm] = useState('')
  const [portalData, setPortalData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [showComplaintForm, setShowComplaintForm] = useState(false)
  const [showCallbackForm, setShowCallbackForm] = useState(false)
  const [complaintForm, setComplaintForm] = useState({ subject: '', description: '' })
  const [callbackForm, setCallbackForm] = useState({ preferred_time: '', reason: '' })
  const [preferences, setPreferences] = useState(null)

  async function handleSearch() {
    if (!searchTerm.trim() || !tenant) return
    setLoading(true)
    try {
      const res = await portalApi.getPortalData(searchTerm.trim(), { tenant_id: tenant.id })
      setPortalData(res.data)
      setPreferences(res.data.preferences)
    } catch { toast.error('Customer not found'); setPortalData(null) }
    finally { setLoading(false) }
  }

  async function handleSubmitComplaint(e) {
    e.preventDefault()
    try {
      await portalApi.submitComplaint({
        customer_id: portalData.customer_id,
        ...complaintForm,
        tenant_id: tenant.id,
      })
      toast.success('Complaint submitted')
      setShowComplaintForm(false)
      setComplaintForm({ subject: '', description: '' })
    } catch { toast.error('Failed to submit complaint') }
  }

  async function handleScheduleCallback(e) {
    e.preventDefault()
    try {
      await portalApi.scheduleCallback({
        customer_id: portalData.customer_id,
        ...callbackForm,
        tenant_id: tenant.id,
      })
      toast.success('Callback scheduled')
      setShowCallbackForm(false)
      setCallbackForm({ preferred_time: '', reason: '' })
    } catch { toast.error('Failed to schedule callback') }
  }

  async function handleTogglePreference(key) {
    const updated = { ...preferences, [key]: !preferences[key] }
    try {
      await portalApi.updatePreferences(portalData.customer_id, { ...updated, tenant_id: tenant.id })
      setPreferences(updated)
      toast.success('Preferences updated')
    } catch { toast.error('Failed to update preferences') }
  }

  const inputClass = "w-full rounded-lg border border-hairline bg-white px-3 py-2 text-sm text-ink placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-accent/20 focus:border-accent transition-colors"

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-ink tracking-tight">Customer Self-Service Portal</h1>
        <p className="text-sm text-ink-muted mt-0.5">Customer 360 view, call history, billing, and preferences</p>
      </div>

      {/* Search */}
      <div className="card p-4 mb-6">
        <div className="flex gap-3">
          <input
            type="text"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSearch()}
            placeholder="Search by customer ID or phone number..."
            className={inputClass}
          />
          <button onClick={handleSearch} disabled={loading} className="btn-primary whitespace-nowrap">
            <User className="h-4 w-4" /> {loading ? 'Searching...' : 'Search'}
          </button>
        </div>
      </div>

      {!portalData && !loading && (
        <div className="card p-12 text-center text-ink-muted">
          <User className="h-12 w-12 mx-auto mb-3 opacity-40" />
          <p>Search for a customer to view their portal data.</p>
        </div>
      )}

      {loading && (
        <div className="card p-12 text-center text-ink-muted">Loading customer data...</div>
      )}

      {portalData && (
        <div className="space-y-6">
          {/* Customer Header */}
          <div className="card p-6 flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="p-3 rounded-xl bg-accent-soft">
                <User className="h-6 w-6 text-accent" />
              </div>
              <div>
                <p className="text-lg font-semibold text-ink">{portalData.customer_id}</p>
                <p className="text-sm text-ink-muted">Avg CSAT: {portalData.average_csat}/5</p>
              </div>
            </div>
            <div className="flex gap-2">
              <button onClick={() => setShowComplaintForm(true)} className="btn-secondary text-sm">
                <MessageSquare className="h-4 w-4" /> Complaint
              </button>
              <button onClick={() => setShowCallbackForm(true)} className="btn-primary text-sm">
                <Phone className="h-4 w-4" /> Call Back
              </button>
            </div>
          </div>

          {/* Call History */}
          <div className="card overflow-hidden">
            <div className="px-4 py-3 border-b border-hairline flex items-center gap-2">
              <Phone className="h-4 w-4 text-ink-muted" />
              <h3 className="text-sm font-medium text-ink">Call History</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hairline bg-surface-subtle">
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Call ID</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Date</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Direction</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Duration</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Agent</th>
                  </tr>
                </thead>
                <tbody>
                  {portalData.call_history?.map((call, i) => (
                    <tr key={i} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                      <td className="px-4 py-3 font-mono text-xs text-ink">{call.call_id}</td>
                      <td className="px-4 py-3 text-ink-muted">{new Date(call.date).toLocaleString()}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          call.direction === 'inbound' ? 'bg-blue-50 text-blue-600' : 'bg-purple-50 text-purple-600'
                        }`}>{call.direction}</span>
                      </td>
                      <td className="px-4 py-3 text-ink-muted">{call.duration_seconds}s</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          call.status === 'completed' ? 'bg-call-green-soft text-call-green' : 'bg-red-50 text-red-500'
                        }`}>{call.status}</span>
                      </td>
                      <td className="px-4 py-3 text-ink-muted">{call.agent || '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Invoices */}
          <div className="card overflow-hidden">
            <div className="px-4 py-3 border-b border-hairline flex items-center gap-2">
              <CreditCard className="h-4 w-4 text-ink-muted" />
              <h3 className="text-sm font-medium text-ink">Invoices</h3>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-hairline bg-surface-subtle">
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">ID</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Date</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Amount</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                    <th className="text-left px-4 py-3 font-medium text-ink-muted">Description</th>
                  </tr>
                </thead>
                <tbody>
                  {portalData.invoices?.map((inv, i) => (
                    <tr key={i} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                      <td className="px-4 py-3 font-mono text-xs text-ink">{inv.id}</td>
                      <td className="px-4 py-3 text-ink-muted">{inv.date}</td>
                      <td className="px-4 py-3 text-ink font-medium">${inv.amount.toFixed(2)}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          inv.status === 'paid' ? 'bg-call-green-soft text-call-green' : 'bg-call-amber-soft text-call-amber'
                        }`}>{inv.status}</span>
                      </td>
                      <td className="px-4 py-3 text-ink-muted">{inv.description}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Preferences */}
          <div className="card p-6">
            <div className="flex items-center gap-2 mb-4">
              <Settings className="h-4 w-4 text-ink-muted" />
              <h3 className="text-sm font-medium text-ink">Communication Preferences</h3>
            </div>
            {preferences && (
              <div className="space-y-3">
                {['communication_email', 'communication_sms', 'communication_phone', 'marketing_emails'].map(key => (
                  <label key={key} className="flex items-center justify-between py-2 border-b border-hairline last:border-0">
                    <span className="text-sm text-ink">{key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}</span>
                    <button
                      onClick={() => handleTogglePreference(key)}
                      className={`relative w-10 h-6 rounded-full transition-colors ${preferences[key] ? 'bg-accent' : 'bg-gray-200'}`}
                    >
                      <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow-sm transition-transform ${preferences[key] ? 'translate-x-4' : ''}`} />
                    </button>
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Complaint Modal */}
      {showComplaintForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-semibold text-ink mb-4">Submit Complaint</h2>
            <form onSubmit={handleSubmitComplaint} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Subject</label>
                <input type="text" value={complaintForm.subject} onChange={e => setComplaintForm({ ...complaintForm, subject: e.target.value })} className={inputClass} required />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Description</label>
                <textarea value={complaintForm.description} onChange={e => setComplaintForm({ ...complaintForm, description: e.target.value })} className={`${inputClass} h-24 resize-y`} required />
              </div>
              <div className="flex gap-3">
                <button type="button" onClick={() => setShowComplaintForm(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" className="btn-primary flex-1">Submit</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Callback Modal */}
      {showCallbackForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <h2 className="text-lg font-semibold text-ink mb-4">Schedule Call Back</h2>
            <form onSubmit={handleScheduleCallback} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Preferred Time</label>
                <input type="datetime-local" value={callbackForm.preferred_time} onChange={e => setCallbackForm({ ...callbackForm, preferred_time: e.target.value })} className={inputClass} required />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Reason</label>
                <input type="text" value={callbackForm.reason} onChange={e => setCallbackForm({ ...callbackForm, reason: e.target.value })} className={inputClass} placeholder="Why does the customer need a callback?" required />
              </div>
              <div className="flex gap-3">
                <button type="button" onClick={() => setShowCallbackForm(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" className="btn-primary flex-1">Schedule</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
