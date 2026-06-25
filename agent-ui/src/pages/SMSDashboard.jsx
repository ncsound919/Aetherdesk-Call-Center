import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { omnichannelApi } from '../services/api'
import {
  MessageSquare, Send, Users, FileText, Clock,
  Plus, Loader2, X
} from 'lucide-react'
import { toast } from 'sonner'

export default function SMSDashboard() {
  const { tenant } = useAuth()
  const [activeTab, setActiveTab] = useState('send')
  const [loading, setLoading] = useState(false)
  const [templates, setTemplates] = useState([])
  const [smsLog, setSmsLog] = useState([])

  const [sendForm, setSendForm] = useState({ to_number: '', message: '', template_id: '' })
  const [bulkForm, setBulkForm] = useState({ recipients: '', message: '' })
  const [templateForm, setTemplateForm] = useState({ name: '', body: '' })
  const [showTemplateModal, setShowTemplateModal] = useState(false)

  const fetchTemplates = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await omnichannelApi.listSMSTemplates()
      setTemplates(Array.isArray(res.data) ? res.data : [])
    } catch { setTemplates([]) }
  }, [tenant])

  const fetchLog = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await omnichannelApi.getSMSLog({ limit: 100, offset: 0 })
      setSmsLog(Array.isArray(res.data) ? res.data : [])
    } catch { setSmsLog([]) }
  }, [tenant])

  useEffect(() => { fetchTemplates(); fetchLog() }, [fetchTemplates, fetchLog])

  async function handleSendSMS(e) {
    e.preventDefault()
    try {
      await omnichannelApi.sendSMS(sendForm)
      toast.success('SMS sent')
      setSendForm({ to_number: '', message: '', template_id: '' })
      fetchLog()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to send SMS')
    }
  }

  async function handleBulkSend(e) {
    e.preventDefault()
    const recipients = bulkForm.recipients.split('\n').map(r => r.trim()).filter(Boolean)
    if (!recipients.length) { toast.error('Enter at least one recipient'); return }
    try {
      await omnichannelApi.sendBulkSMS({ recipients, message: bulkForm.message })
      toast.success(`Bulk SMS sent to ${recipients.length} recipients`)
      setBulkForm({ recipients: '', message: '' })
      fetchLog()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to send bulk SMS')
    }
  }

  async function handleCreateTemplate(e) {
    e.preventDefault()
    try {
      await omnichannelApi.createSMSTemplate(templateForm)
      toast.success('Template created')
      setShowTemplateModal(false)
      setTemplateForm({ name: '', body: '' })
      fetchTemplates()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create template')
    }
  }

  const tabs = [
    { key: 'send', label: 'Send SMS', icon: Send },
    { key: 'bulk', label: 'Bulk Send', icon: Users },
    { key: 'templates', label: 'Templates', icon: FileText },
    { key: 'log', label: 'SMS Log', icon: Clock },
  ]

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">SMS Messages</h1>
          <p className="text-sm text-ink-muted mt-0.5">Send, manage, and track SMS communications</p>
        </div>
        {activeTab === 'templates' && (
          <button onClick={() => setShowTemplateModal(true)} className="btn-primary">
            <Plus className="h-4 w-4" /> New Template
          </button>
        )}
      </div>

      <div className="flex gap-1 mb-6 border-b border-hairline">
        {tabs.map(tab => {
          const Icon = tab.icon
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-accent text-accent'
                  : 'border-transparent text-ink-muted hover:text-ink'
              }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {activeTab === 'send' && (
        <div className="card p-6 max-w-lg">
          <form onSubmit={handleSendSMS} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1.5">To Number</label>
              <input
                type="text" value={sendForm.to_number}
                onChange={e => setSendForm({ ...sendForm, to_number: e.target.value })}
                className="input-field" placeholder="+1234567890" required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1.5">Template (optional)</label>
              <select
                value={sendForm.template_id}
                onChange={e => {
                  const tpl = templates.find(t => t.id === e.target.value)
                  setSendForm({ ...sendForm, template_id: e.target.value, message: tpl ? tpl.body : sendForm.message })
                }}
                className="input-field"
              >
                <option value="">No template</option>
                {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1.5">Message</label>
              <textarea
                value={sendForm.message}
                onChange={e => setSendForm({ ...sendForm, message: e.target.value })}
                className="input-field min-h-[100px]" placeholder="Type your message..." required
              />
            </div>
            <button type="submit" className="btn-primary">
              <Send className="h-4 w-4" /> Send SMS
            </button>
          </form>
        </div>
      )}

      {activeTab === 'bulk' && (
        <div className="card p-6 max-w-lg">
          <form onSubmit={handleBulkSend} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1.5">Recipients (one per line)</label>
              <textarea
                value={bulkForm.recipients}
                onChange={e => setBulkForm({ ...bulkForm, recipients: e.target.value })}
                className="input-field min-h-[120px]" placeholder="+1234567890&#10;+0987654321" required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-ink mb-1.5">Message</label>
              <textarea
                value={bulkForm.message}
                onChange={e => setBulkForm({ ...bulkForm, message: e.target.value })}
                className="input-field min-h-[100px]" placeholder="Type your message..." required
              />
            </div>
            <button type="submit" className="btn-primary">
              <Users className="h-4 w-4" /> Send Bulk SMS
            </button>
          </form>
        </div>
      )}

      {activeTab === 'templates' && (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hairline bg-surface-subtle">
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Name</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Body</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Created</th>
                </tr>
              </thead>
              <tbody>
                {templates.length === 0 && (
                  <tr>
                    <td colSpan="3" className="px-4 py-12 text-center text-ink-muted">No templates yet.</td>
                  </tr>
                )}
                {templates.map(t => (
                  <tr key={t.id} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                    <td className="px-4 py-3 text-ink font-medium">{t.name}</td>
                    <td className="px-4 py-3 text-ink-muted max-w-md truncate">{t.body}</td>
                    <td className="px-4 py-3 text-ink-muted">{new Date(t.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {activeTab === 'log' && (
        <div className="card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-hairline bg-surface-subtle">
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">To</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Message</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Status</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Direction</th>
                  <th className="text-left px-4 py-3 font-medium text-ink-muted">Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {smsLog.length === 0 && (
                  <tr>
                    <td colSpan="5" className="px-4 py-12 text-center text-ink-muted">No SMS logs yet.</td>
                  </tr>
                )}
                {smsLog.map(entry => (
                  <tr key={entry.id} className="border-b border-hairline hover:bg-surface-hover transition-colors">
                    <td className="px-4 py-3 text-ink font-medium">{entry.to_number}</td>
                    <td className="px-4 py-3 text-ink-muted max-w-md truncate">{entry.body}</td>
                    <td className="px-4 py-3">
                      <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                        entry.status === 'sent' ? 'bg-call-green-soft text-call-green' :
                        entry.status === 'received' ? 'bg-accent-soft text-accent' :
                        'bg-surface-subtle text-ink-muted'
                      }`}>
                        {entry.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-ink-muted">{entry.direction}</td>
                    <td className="px-4 py-3 text-ink-muted">{new Date(entry.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {showTemplateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">Create SMS Template</h2>
              <button onClick={() => setShowTemplateModal(false)} className="p-1.5 rounded-lg hover:bg-surface-hover">
                <X className="h-5 w-5 text-ink-muted" />
              </button>
            </div>
            <form onSubmit={handleCreateTemplate} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Name</label>
                <input type="text" value={templateForm.name} onChange={e => setTemplateForm({ ...templateForm, name: e.target.value })} className="input-field" placeholder="Order Confirmation" required />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Body</label>
                <textarea value={templateForm.body} onChange={e => setTemplateForm({ ...templateForm, body: e.target.value })} className="input-field min-h-[100px]" placeholder="Your order {{order_id}} has been confirmed." required />
              </div>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowTemplateModal(false)} className="btn-secondary flex-1">Cancel</button>
                <button type="submit" className="btn-primary flex-1"><Plus className="h-4 w-4" /> Create</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
