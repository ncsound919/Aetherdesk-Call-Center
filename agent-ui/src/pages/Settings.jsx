import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { settingsApi } from '../services/api'
import api from '../services/api'
import {
  Building2, Globe, Clock, PhoneCall, Shield, Lock, CreditCard,
  Plug, Key, Bell, Save, Loader2, CheckCircle2, XCircle, Headphones,
  ShoppingCart, Wrench, DollarSign, BookOpen, Sliders
} from 'lucide-react'
import { toast } from 'sonner'

const BUSINESS_TYPES = (t) => [
  { id: 'sales', label: t('settings.salesCenter'), icon: ShoppingCart, desc: t('settings.salesCenterDesc') },
  { id: 'support', label: t('settings.supportCenter'), icon: Headphones, desc: t('settings.supportCenterDesc') },
  { id: 'billing', label: t('settings.billingCenter'), icon: DollarSign, desc: t('settings.billingCenterDesc') },
  { id: 'technical', label: t('settings.technicalSupport'), icon: Wrench, desc: t('settings.technicalSupportDesc') },
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
  const { t } = useTranslation()
  const { tenant, user, logout } = useAuth()
  const [activeTab, setActiveTab] = useState('general')
  const [saving, setSaving] = useState(false)
  const [mfaStatus, setMfaStatus] = useState({ enrolled: false, enabled: false })
  const [mfaSetup, setMfaSetup] = useState(null) // {secret, otpauth_url, backup_codes}
  const [showMFAModal, setShowMFAModal] = useState(false)
  const [mfaCode, setMfaCode] = useState('')
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

  useEffect(() => {
    if (activeTab === 'security' && tenant?.id) {
      api.get('/auth/mfa/status').then(res => setMfaStatus(res.data)).catch(() => {})
    }
  }, [activeTab, tenant])

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
      toast.success(t('settings.savedSuccess'))
    } catch (err) {
      toast.error(err.response?.data?.detail || t('common.error'))
    } finally { setSaving(false) }
  }

  async function handleMFASetup() {
    try {
      const res = await api.post('/auth/mfa/setup')
      setMfaSetup(res.data)
      setShowMFAModal(true)
    } catch (err) {       toast.error(t('common.error')) }
  }

  async function handleMFAVerify() {
    try {
      await api.post('/auth/mfa/verify', { code: mfaCode })
      toast.success(t('settings.mfaEnabled'))
      setShowMFAModal(false)
      setMfaStatus({ enrolled: true, enabled: true })
    } catch (err) {       toast.error(t('settings.invalidCode')) }
  }

  async function handleMFADisable() {
    try {
      await api.post('/auth/mfa/disable')
      toast.success(t('settings.mfaDisabled'))
      setMfaStatus({ enrolled: false, enabled: false })
    } catch (err) { toast.error('Failed to disable MFA') }
  }

  const tabs = [
    { id: 'general', label: t('settings.general'), icon: Sliders },
    { id: 'compliance', label: t('settings.compliance'), icon: Shield },
    { id: 'billing', label: t('settings.billing'), icon: CreditCard },
    { id: 'integrations', label: t('settings.integrations'), icon: Plug },
    { id: 'security', label: t('settings.security'), icon: Lock },
  ]

  return (
    <div className="p-6 max-w-5xl mx-auto animate-slide-up">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">{t('settings.title')}</h1>
          <p className="text-sm text-ink-muted mt-0.5">{t('settings.subtitle')}</p>
        </div>
      </div>

      <div className="card overflow-hidden">
        {/* Tabs */}
        <div className="border-b border-hairline bg-surface-hover/50">
          <nav className="flex overflow-x-auto px-4" aria-label="Tabs">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <button key={tab.id} onClick={() => setActiveTab(tab.id)} role="tab" aria-selected={activeTab === tab.id} aria-controls={`tabpanel-${tab.id}`}
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
            <form onSubmit={handleSubmit} className="space-y-8" role="tabpanel" id="tabpanel-general" aria-labelledby="tab-general">
              {/* Business Profile */}
              <section>
                <div className="flex items-center gap-2 mb-4">
                  <Building2 className="h-5 w-5 text-accent" />
                  <h2 className="text-base font-semibold text-ink">{t('settings.businessProfile')}</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5" htmlFor="company-name">{t('settings.companyName')}</label>
                    <input id="company-name" type="text" value={formData.companyName}
                      onChange={(e) => setFormData({ ...formData, companyName: e.target.value })}
                      className="input-field" aria-label={t('settings.companyName')} />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5" htmlFor="business-type">{t('settings.businessType')}</label>
                    <select id="business-type" value={formData.businessType}
                      onChange={(e) => setFormData({ ...formData, businessType: e.target.value })}
                      className="input-field" aria-label={t('settings.businessType')}>
                      {BUSINESS_TYPES(t).map(bt => <option key={bt.id} value={bt.id}>{bt.label}</option>)}
                    </select>
                    <p className="text-xs text-ink-muted mt-1">{BUSINESS_TYPES(t).find(b => b.id === formData.businessType)?.desc}</p>
                  </div>
                </div>
              </section>

              {/* Region & Language */}
              <section>
                <div className="flex items-center gap-2 mb-4">
                  <Globe className="h-5 w-5 text-accent" />
                  <h2 className="text-base font-semibold text-ink">{t('settings.regionLanguage')}</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5" htmlFor="timezone">{t('settings.timezone')}</label>
                    <select id="timezone" value={formData.timezone}
                      onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                      className="input-field" aria-label={t('settings.timezone')}>
                      {TIMEZONES.map(tz => <option key={tz} value={tz}>{tz}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5" htmlFor="language-setting">{t('settings.language')}</label>
                    <select id="language-setting" value={formData.language}
                      onChange={(e) => setFormData({ ...formData, language: e.target.value })}
                      className="input-field" aria-label={t('settings.language')}>
                      {LANGUAGES.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
                    </select>
                  </div>
                </div>
              </section>

              {/* Call Handling */}
              <section>
                <div className="flex items-center gap-2 mb-4">
                  <PhoneCall className="h-5 w-5 text-accent" />
                  <h2 className="text-base font-semibold text-ink">{t('settings.callHandling')}</h2>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5" htmlFor="max-calls">{t('settings.maxConcurrentCalls')}</label>
                    <input id="max-calls" type="number" value={formData.maxConcurrentCalls}
                      onChange={(e) => setFormData({ ...formData, maxConcurrentCalls: e.target.value })}
                      className="input-field" min="1" max="100" aria-label={t('settings.maxConcurrentCalls')} />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5" htmlFor="script-req">{t('settings.scriptRequirement')}</label>
                    <select id="script-req" value={formData.scriptRequirement}
                      onChange={(e) => setFormData({ ...formData, scriptRequirement: e.target.value })}
                      className="input-field" aria-label={t('settings.scriptRequirement')}>
                      <option value="required">{t('settings.scriptRequired')}</option>
                      <option value="encouraged">{t('settings.scriptEncouraged')}</option>
                      <option value="optional">{t('settings.scriptOptional')}</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5" htmlFor="holiday-routing">{t('settings.holidayRouting')}</label>
                    <select id="holiday-routing" value={formData.holidayRouting}
                      onChange={(e) => setFormData({ ...formData, holidayRouting: e.target.value })}
                      className="input-field" aria-label={t('settings.holidayRouting')}>
                      <option value="voicemail">{t('settings.holidayVoicemail')}</option>
                      <option value="message">{t('settings.holidayMessage')}</option>
                      <option value="alternate">{t('settings.holidayAlternate')}</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5" htmlFor="recording-retention">{t('settings.callRecordingRetention')}</label>
                    <select id="recording-retention" value={formData.recordingRetention}
                      onChange={(e) => setFormData({ ...formData, recordingRetention: parseInt(e.target.value) })}
                      className="input-field" aria-label={t('settings.callRecordingRetention')}>
                      <option value={30}>{t('settings.days30')}</option>
                      <option value={90}>{t('settings.days90')}</option>
                      <option value={180}>{t('settings.days180')}</option>
                      <option value={365}>{t('settings.days365')}</option>
                    </select>
                  </div>
                </div>
              </section>

              {/* Toggles */}
              <section>
                <div className="flex items-center gap-2 mb-4">
                  <Sliders className="h-5 w-5 text-accent" />
                  <h2 className="text-base font-semibold text-ink">{t('settings.features')}</h2>
                </div>
                <div className="space-y-3">
                  {[
                    { key: 'autoAttendant', label: t('settings.autoAttendant'), desc: t('settings.autoAttendantDesc') },
                    { key: 'qualityMonitoring', label: t('settings.qualityMonitoring'), desc: t('settings.qualityMonitoringDesc') },
                    { key: 'callRecording', label: t('settings.callRecording'), desc: t('settings.callRecordingDesc') },
                  ].map((f) => (
                    <label key={f.key} className="flex items-center justify-between p-3 rounded-lg border border-hairline hover:bg-surface-hover cursor-pointer transition-colors">
                      <div>
                        <p className="text-sm font-medium text-ink">{f.label}</p>
                        <p className="text-xs text-ink-muted">{f.desc}</p>
                      </div>
                      <div className={`relative w-10 h-6 rounded-full transition-colors ${formData[f.key] ? 'bg-accent' : 'bg-hairline'}`}
                        onClick={() => setFormData({ ...formData, [f.key]: !formData[f.key] })}
                        role="switch" aria-checked={formData[f.key]} tabIndex={0}
                        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setFormData({ ...formData, [f.key]: !formData[f.key] }) } }}>
                        <div className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow-sm transition-transform ${formData[f.key] ? 'translate-x-4' : ''}`} />
                      </div>
                    </label>
                  ))}
                </div>
              </section>

              {/* Save */}
              <div className="flex justify-end pt-4 border-t border-hairline">
                <button type="submit" disabled={saving} className="btn-primary" aria-label={saving ? t('settings.saving') : t('settings.saveChanges')}>
                  {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  {saving ? t('settings.saving') : t('settings.saveChanges')}
                </button>
              </div>
            </form>
          )}

          {/* Compliance Tab */}
          {activeTab === 'compliance' && (
            <div className="space-y-6" role="tabpanel" id="tabpanel-compliance" aria-labelledby="tab-compliance">
              <div className="flex items-center gap-2 mb-4">
                <Shield className="h-5 w-5 text-call-green" />
                <h2 className="text-base font-semibold text-ink">{t('settings.complianceStatus')}</h2>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {[
                  { label: t('settings.gdpr'), status: true, desc: t('settings.gdprDesc') },
                  { label: t('settings.hipaa'), status: true, desc: t('settings.hipaaDesc') },
                  { label: t('settings.pci'), status: true, desc: t('settings.pciDesc') },
                  { label: t('settings.encryptionAtRest'), status: true, desc: t('settings.encryptionAtRestDesc') },
                  { label: t('settings.encryptionInTransit'), status: true, desc: t('settings.encryptionInTransitDesc') },
                  { label: t('settings.callRecording'), status: formData.callRecording, desc: t('settings.callRecordingDesc') },
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
            <div className="text-center py-12" role="tabpanel" id="tabpanel-billing" aria-labelledby="tab-billing">
              <CreditCard className="h-10 w-10 mx-auto text-ink-subtle mb-3" />
              <p className="text-sm text-ink-muted">{t('settings.billingInfo')}</p>
            </div>
          )}

          {/* Integrations Tab */}
          {activeTab === 'integrations' && (
            <div className="space-y-4" role="tabpanel" id="tabpanel-integrations" aria-labelledby="tab-integrations">
              <div className="flex items-center gap-2 mb-4">
                <Plug className="h-5 w-5 text-accent" />
                <h2 className="text-base font-semibold text-ink">{t('settings.connectedServices')}</h2>
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
            <div className="space-y-6" role="tabpanel" id="tabpanel-security" aria-labelledby="tab-security">
              <div className="flex items-center gap-2 mb-4">
                <Lock className="h-5 w-5 text-accent" />
                <h2 className="text-base font-semibold text-ink">{t('settings.securitySettings')}</h2>
              </div>
              <div className="bg-call-amber-soft border border-call-amber/20 rounded-xl p-4">
                <p className="text-sm text-call-amber">{t('settings.passwordManagement')}</p>
              </div>

              {/* MFA Section */}
              <div className="flex items-center justify-between p-4 rounded-xl border border-hairline">
                <div>
                  <p className="text-sm font-medium text-ink">{t('settings.mfa')}</p>
                  <p className="text-xs text-ink-muted mt-0.5">{t('settings.mfaDesc')}</p>
                </div>
                {mfaStatus.enrolled ? (
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${mfaStatus.enabled ? 'bg-call-green-soft text-call-green' : 'bg-call-amber-soft text-call-amber'}`}>
                      {mfaStatus.enabled ? t('settings.enabled') : t('settings.setupPending')}
                    </span>
                    {mfaStatus.enabled ? (
                      <button onClick={handleMFADisable} className="btn-secondary text-xs text-call-red hover:text-call-red">{t('settings.disable')}</button>
                    ) : (
                      <button onClick={handleMFASetup} className="btn-secondary text-xs">{t('settings.completeSetup')}</button>
                    )}
                  </div>
                ) : (
                  <button onClick={handleMFASetup} className="btn-secondary text-xs">{t('settings.enableMFA')}</button>
                )}
              </div>

              <div className="flex items-center justify-between p-4 rounded-xl border border-hairline">
                <div>
                  <p className="text-sm font-medium text-ink">{t('settings.activeSessions')}</p>
                  <p className="text-xs text-ink-muted mt-0.5">{t('settings.activeSessionDesc')}</p>
                </div>
              </div>
              <div className="flex items-center justify-between p-4 rounded-xl border border-hairline">
                <div>
                  <p className="text-sm font-medium text-ink">{t('settings.apiKeys')}</p>
                  <p className="text-xs text-ink-muted mt-0.5">{t('settings.apiKeysDesc')}</p>
                </div>
                <span className="text-xs text-ink-subtle">{t('settings.comingSoon')}</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* MFA Setup Modal */}
      {showMFAModal && mfaSetup && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-md mx-4 p-6">
            <h3 className="text-lg font-semibold text-ink mb-4">{t('settings.setUpMFA')}</h3>
            <div className="space-y-4">
              <div>
                <p className="text-sm text-ink-muted mb-2">{t('settings.scanQR')}</p>
                <div className="bg-hairline rounded-lg p-4 text-center">
                  <p className="text-xs font-mono break-all">{mfaSetup.otpauth_url}</p>
                </div>
              </div>
              <div>
                <p className="text-sm text-ink-muted mb-2">{t('settings.enterSecret')}</p>
                <p className="text-sm font-mono bg-surface p-2 rounded">{mfaSetup.secret}</p>
              </div>
              <div>
                <p className="text-sm text-ink-muted mb-2">{t('settings.backupCodes')}</p>
                <div className="grid grid-cols-2 gap-1">
                  {mfaSetup.backup_codes.map((code, i) => (
                    <p key={i} className="text-xs font-mono bg-surface p-1 rounded text-center">{code}</p>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5" htmlFor="mfa-verify-code">{t('settings.verificationCode')}</label>
                <input id="mfa-verify-code" type="text" value={mfaCode} onChange={(e) => setMfaCode(e.target.value)}
                  placeholder="000000" maxLength={6} className="input-field" aria-label={t('settings.verificationCode')} />
              </div>
              <div className="flex gap-3">
                <button onClick={() => { setShowMFAModal(false); setMfaCode('') }} className="btn-secondary flex-1">{t('common.cancel')}</button>
                <button onClick={handleMFAVerify} disabled={mfaCode.length !== 6} className="btn-primary flex-1">{t('settings.verifyAndEnable')}</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
