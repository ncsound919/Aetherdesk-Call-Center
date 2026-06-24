import React, { useState, useEffect } from 'react'
import { useAuth } from '../context/AuthContext'
import { settingsApi } from '../services/api'
import {
  Building2, Globe, Clock, PhoneCall, Shield, Lock, CreditCard,
  Plug, Key, Bell, Save, Loader2, CheckCircle2, XCircle, Headphones,
  ShoppingCart, Wrench, DollarSign, BookOpen, Sliders
} from 'lucide-react'
import { toast } from 'sonner'

const BUSINESS_TYPES = [
  { id: 'sales', label: 'Sales Center', icon: ShoppingCart, desc: 'Lead generation, outbound campaigns, conversion optimization' },
  { id: 'support', label: 'Support Center', icon: Headphones, desc: 'Customer service, issue resolution, CSAT optimization' },
  { id: 'billing', label: 'Billing Center', icon: DollarSign, desc: 'Payment processing, dispute resolution, account management' },
  { id: 'technical', label: 'Technical Support', icon: Wrench, desc: 'Troubleshooting, escalation management, fix rate optimization' },
]

const LANGUAGES = [
  { value: 'en-US', label: 'English (US)' },
  { value: 'es-US', label: 'Spanish (US)' },
  { value: 'fr-FR', label: 'French' },
  { value: 'de-DE', label: 'German' },
  { value: 'ja-JP', label: 'Japanese' },
]

const TIMEZONES = [
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'America/Anchorage', 'Pacific/Honolulu', 'Europe/London', 'Europe/Berlin',
  'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Kolkata', 'Australia/Sydney',
]

export default function Settings() {
  const { tenant, user, logout } = useAuth()
  const [activeTab, setActiveTab] = useState('general')
  const [saving, setSaving] = useState(false)
  const [formData, setFormData] = useState({
    companyName: 'AetherDesk',
    businessType: 'sales',
    timezone: 'America/New_York',
    language: 'en-US',
    maxConcurrentCalls: 10,
    recordingRetention: 365,
    afterHoursMessage: 'Our office is currently closed. Please call back during business hours.',
    holidayRouting: 'voicemail',
    autoAttendant: true,
    scriptRequirement: 'encouraged',
    qualityMonitoring: true,
    callRecording: true,
    gdprConsent: true,
    hipaaConsent: true,
    notificationEmail: '',
  })

  useEffect(() => {
    if (tenant?.id) {
      settingsApi.getTenant(tenant.id).then(res => {
        if (res.data?.settings) {
          setFormData(prev => ({ ...prev, ...res.data.settings }))
        }
        if (res.data?.name) setFormData(prev => ({ ...prev, companyName: res.data.name }))
      }).catch(() => {})
    }
  }, [tenant])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!tenant?.id) return
    setSaving(true)
    try {
      await settingsApi.updateTenant(tenant.id, {
        name: formData.companyName,
        settings: {
          timezone: formData.timezone,
          language: formData.language,
          business_type: formData.businessType,
          max_concurrent_calls: parseInt(formData.maxConcurrentCalls),
          recording_retention: parseInt(formData.recordingRetention),
          after_hours_message: formData.afterHoursMessage,
          holiday_routing: formData.holidayRouting,
          auto_attendant: formData.autoAttendant,
          script_requirement: formData.scriptRequirement,
          quality_monitoring: formData.qualityMonitoring,
          call_recording: formData.callRecording,
        }
      })
      toast.success('Settings saved successfully')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to save settings')
    } finally { setSaving(false) }
  }

  const tabs = [
    { id: 'general', label: 'General', icon: Sliders },
    { id: 'compliance', label: 'Compliance', icon: Shield },
    { id: 'billing', label: 'Billing', icon: CreditCard },
    { id: 'integrations', label: 'Integrations', icon: Plug },
    { id: 'security', label: 'Security', icon: Lock },
  ]

  return (
    <div className="p-6 max-w-5xl mx-auto animate-slide-up">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Settings</h1>
          <p className="text-sm text-ink-muted mt-0.5">Manage your platform configuration and business profile</p>
        </div>
      </div>

      <div className="card overflow-hidden">
        {/* Tabs */}
        <div className="border-b border-hairline bg-surface-hover/50">
          <nav className="flex overflow-x-auto px-4" aria-label="Tabs">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <button key={tab.id} onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center gap-2 py-3.5 px-4 border-b-2 font-medium text-sm whitespace-nowrap transition-colors ${
                    activeTab === tab.id
                      ? 'border-accent text-accent'
                      : 'border-transparent text-ink-muted hover:text-ink hover:border-hairline'
                  }`}>
                  <Icon className="h-4 w-4" />
                  {tab.label}
                </button>
              )
            })}
          </nav>
        </div>

        <div className="p-6">
          {/* General Tab */}
          {activeTab === 'general' && (
            <form onSubmit={handleSubmit} className="space-y-8">
              {/* Business Profile */}
              <section>
                <div className="flex items-center gap-2 mb-4">
                  <Building2 className="h-5 w-5 text-accent" />
                  <h2 className="text-base font-semibold text-ink">Business Profile</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5">Company Name</label>
                    <input type="text" value={formData.companyName}
                      onChange={(e) => setFormData({ ...formData, companyName: e.target.value })}
                      className="input-field" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5">Business Type</label>
                    <select value={formData.businessType}
                      onChange={(e) => setFormData({ ...formData, businessType: e.target.value })}
                      className="input-field">
                      {BUSINESS_TYPES.map(bt => <option key={bt.id} value={bt.id}>{bt.label}</option>)}
                    </select>
                    <p className="text-xs text-ink-muted mt-1">{BUSINESS_TYPES.find(b => b.id === formData.businessType)?.desc}</p>
                  </div>
                </div>
              </section>

              {/* Region & Language */}
              <section>
                <div className="flex items-center gap-2 mb-4">
                  <Globe className="h-5 w-5 text-accent" />
                  <h2 className="text-base font-semibold text-ink">Region & Language</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5">Timezone</label>
                    <select value={formData.timezone}
                      onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                      className="input-field">
                      {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5">Language</label>
                    <select value={formData.language}
                      onChange={(e) => setFormData({ ...formData, language: e.target.value })}
                      className="input-field">
                      {LANGUAGES.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
                    </select>
                  </div>
                </div>
              </section>

              {/* Call Handling */}
              <section>
                <div className="flex items-center gap-2 mb-4">
                  <PhoneCall className="h-5 w-5 text-accent" />
                  <h2 className="text-base font-semibold text-ink">Call Handling</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5">Max Concurrent Calls</label>
                    <input type="number" value={formData.maxConcurrentCalls}
                      onChange={(e) => setFormData({ ...formData, maxConcurrentCalls: e.target.value })}
                      className="input-field" min="1" max="100" />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5">Script Requirement</label>
                    <select value={formData.scriptRequirement}
                      onChange={(e) => setFormData({ ...formData, scriptRequirement: e.target.value })}
                      className="input-field">
                      <option value="required">Required — agents must use scripts</option>
                      <option value="encouraged">Encouraged — suggested but optional</option>
                      <option value="optional">Optional — agents choose</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5">Holiday Routing</label>
                    <select value={formData.holidayRouting}
                      onChange={(e) => setFormData({ ...formData, holidayRouting: e.target.value })}
                      className="input-field">
                      <option value="voicemail">Send to voicemail</option>
                      <option value="message">Play holiday message then disconnect</option>
                      <option value="alternate">Route to alternate number</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5">Call Recording Retention</label>
                    <select value={formData.recordingRetention}
                      onChange={(e) => setFormData({ ...formData, recordingRetention: parseInt(e.target.value) })}
                      className="input-field">
                      <option value={30}>30 days</option>
                      <option value={90}>90 days</option>
                      <option value={180}>180 days</option>
                      <option value={365}>365 days (recommended)</option>
                    </select>
                  </div>
                </div>
              </section>

              {/* Toggles */}
              <section>
                <div className="flex items-center gap-2 mb-4">
                  <Sliders className="h-5 w-5 text-accent" />
                  <h2 className="text-base font-semibold text-ink">Features</h2>
                </div>
                <div className="space-y-3">
                  {[
                    { key: 'autoAttendant', label: 'Auto Attendant', desc: 'Automated greeting and menu system for incoming calls' },
                    { key: 'qualityMonitoring', label: 'Quality Monitoring', desc: 'Record and review calls for quality assurance and training' },
                    { key: 'callRecording', label: 'Call Recording', desc: 'Record all calls for compliance and dispute resolution' },
                  ].map((f) => (
                    <label key={f.key} className="flex items-center justify-between p-3 rounded-lg border border-hairline hover:bg-surface-hover cursor-pointer transition-colors">
                      <div>
                        <p className="text-sm font-medium text-ink">{f.label}</p>
                        <p className="text-xs text-ink-muted">{f.desc}</p>
                      </div>
                      <div className={`relative w-10 h-6 rounded-full transition-colors ${formData[f.key] ? 'bg-accent' : 'bg-hairline'}`}
                        onClick={() => setFormData({ ...formData, [f.key]: !formData[f.key] })}>
                        <div className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow-sm transition-transform ${formData[f.key] ? 'translate-x-4' : ''}`} />
                      </div>
                    </label>
                  ))}
                </div>
              </section>

              {/* Save */}
              <div className="flex justify-end pt-4 border-t border-hairline">
                <button type="submit" disabled={saving} className="btn-primary">
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  {saving ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          )}

          {/* Compliance Tab */}
          {activeTab === 'compliance' && (
            <div className="space-y-6">
              <div className="flex items-center gap-2 mb-4">
                <Shield className="h-5 w-5 text-call-green" />
                <h2 className="text-base font-semibold text-ink">Compliance Status</h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[
                  { label: 'GDPR Compliant', status: true, desc: 'Data protection and privacy for EU customers' },
                  { label: 'HIPAA Compliant', status: true, desc: 'Healthcare data protection (US) — enabled' },
                  { label: 'PCI Compliant', status: true, desc: 'Payment card industry data security' },
                  { label: 'Data Encryption at Rest', status: true, desc: 'AES-256-GCM encryption for stored call data' },
                  { label: 'Data Encryption in Transit', status: true, desc: 'TLS 1.3 for all API and media traffic' },
                  { label: 'Call Recording', status: formData.callRecording, desc: 'Call recording — configurable in General settings' },
                ].map((item, i) => (
                  <div key={i} className="flex items-start gap-3 p-4 rounded-xl border border-hairline">
                    {item.status ? <CheckCircle2 className="h-5 w-5 text-call-green shrink-0 mt-0.5" /> : <XCircle className="h-5 w-5 text-call-red shrink-0 mt-0.5" />}
                    <div>
                      <p className="text-sm font-medium text-ink">{item.label}</p>
                      <p className="text-xs text-ink-muted mt-0.5">{item.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Billing Tab */}
          {activeTab === 'billing' && (
            <div className="text-center py-12">
              <CreditCard className="h-10 w-10 mx-auto text-ink-subtle mb-3" />
              <p className="text-sm text-ink-muted">Billing information managed through your subscription portal.</p>
            </div>
          )}

          {/* Integrations Tab */}
          {activeTab === 'integrations' && (
            <div className="space-y-4">
              <div className="flex items-center gap-2 mb-4">
                <Plug className="h-5 w-5 text-accent" />
                <h2 className="text-base font-semibold text-ink">Connected Services</h2>
              </div>
              {[
                { name: 'Twilio Voice', status: 'connected', desc: 'Primary telephony provider for outbound calls' },
                { name: 'Fonoster + FreeSWITCH', status: 'available', desc: 'Self-hosted voice infrastructure (optional)' },
                { name: 'Gemma 4 E2B (Ollama)', status: 'connected', desc: 'Local LLM for intent classification and agent intelligence' },
                { name: 'Deepgram STT', status: 'configurable', desc: 'Speech-to-text for transcription' },
                { name: 'Chatterbox TTS', status: 'configurable', desc: 'Text-to-speech for voice responses' },
              ].map((int, i) => (
                <div key={i} className="flex items-center justify-between p-4 rounded-xl border border-hairline hover:bg-surface-hover transition-colors">
                  <div className="flex items-center gap-3">
                    <div className={`h-2.5 w-2.5 rounded-full ${
                      int.status === 'connected' ? 'bg-call-green' : int.status === 'available' ? 'bg-call-amber' : 'bg-ink-subtle'
                    }`} />
                    <div>
                      <p className="text-sm font-medium text-ink">{int.name}</p>
                      <p className="text-xs text-ink-muted">{int.desc}</p>
                    </div>
                  </div>
                  <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${
                    int.status === 'connected' ? 'bg-call-green-soft text-call-green' : int.status === 'available' ? 'bg-call-amber-soft text-call-amber' : 'bg-hairline text-ink-muted'
                  }`}>{int.status}</span>
                </div>
              ))}
            </div>
          )}

          {/* Security Tab */}
          {activeTab === 'security' && (
            <div className="space-y-6">
              <div className="flex items-center gap-2 mb-4">
                <Lock className="h-5 w-5 text-accent" />
                <h2 className="text-base font-semibold text-ink">Security Settings</h2>
              </div>
              <div className="bg-call-amber-soft border border-call-amber/20 rounded-xl p-4">
                <p className="text-sm text-call-amber">Password management and session controls are managed through your account profile.</p>
              </div>
              <div className="flex items-center justify-between p-4 rounded-xl border border-hairline">
                <div>
                  <p className="text-sm font-medium text-ink">Active Sessions</p>
                  <p className="text-xs text-ink-muted mt-0.5">You have 1 active session</p>
                </div>
              </div>
              <div className="flex items-center justify-between p-4 rounded-xl border border-hairline">
                <div>
                  <p className="text-sm font-medium text-ink">API Keys</p>
                  <p className="text-xs text-ink-muted mt-0.5">Manage API keys for programmatic access</p>
                </div>
                <span className="text-xs text-ink-subtle">Coming soon</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
