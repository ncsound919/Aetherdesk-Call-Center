import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { platformOpsApi } from '../services/api'
import {
  Palette, Globe, CheckCircle2, AlertTriangle, Image, Eye, Save, Loader2
} from 'lucide-react'
import { toast } from 'sonner'

export default function WhiteLabelDashboard() {
  const { tenant } = useAuth()
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [branding, setBranding] = useState({
    company_name: '',
    logo_url: '',
    primary_color: '#2563eb',
    secondary_color: '#7c3aed',
    favicon_url: '',
  })
  const [domain, setDomain] = useState({ domain: '', ssl_status: null, verified: false })
  const [domainInput, setDomainInput] = useState('')
  const [verifying, setVerifying] = useState(false)

  const fetchBranding = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await platformOpsApi.getBranding(tenant.id)
      if (res.data) {
        setBranding({
          company_name: res.data.company_name || '',
          logo_url: res.data.logo_url || '',
          primary_color: res.data.primary_color || '#2563eb',
          secondary_color: res.data.secondary_color || '#7c3aed',
          favicon_url: res.data.favicon_url || '',
        })
      }
    } catch { /* ignore */ }
  }, [tenant])

  const fetchDomain = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await platformOpsApi.getDomain(tenant.id)
      setDomain(res.data)
      if (res.data?.domain) setDomainInput(res.data.domain)
    } catch { /* ignore */ }
  }, [tenant])

  useEffect(() => {
    fetchBranding()
    fetchDomain()
  }, [fetchBranding, fetchDomain])

  async function handleSaveBranding() {
    if (!tenant) return
    setSaving(true)
    try {
      await platformOpsApi.updateBranding(tenant.id, branding)
      toast.success('Branding updated')
    } catch {
      toast.error('Failed to update branding')
    } finally {
      setSaving(false)
    }
  }

  async function handleSetDomain() {
    if (!tenant || !domainInput.trim()) return
    setLoading(true)
    try {
      await platformOpsApi.setDomain(tenant.id, domainInput)
      toast.success('Custom domain configured')
      fetchDomain()
    } catch {
      toast.error('Failed to set domain')
    } finally {
      setLoading(false)
    }
  }

  async function handleVerifyDomain() {
    if (!tenant || !domainInput.trim()) return
    setVerifying(true)
    try {
      const res = await platformOpsApi.verifyDomain(tenant.id, domainInput)
      if (res.data?.verified) {
        toast.success('Domain verified successfully')
        setDomain(prev => ({ ...prev, verified: true, ssl_status: 'active' }))
      } else {
        toast.error('DNS verification failed. Check your DNS records.')
      }
    } catch {
      toast.error('Verification failed')
    } finally {
      setVerifying(false)
    }
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-ink tracking-tight">White Label & Branding</h1>
        <p className="text-sm text-ink-muted mt-0.5">Customize your tenant's look and feel</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Branding Section */}
        <div className="card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Palette className="h-5 w-5 text-accent" />
            <h2 className="text-lg font-semibold text-ink">Branding</h2>
          </div>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-ink mb-1.5">Company Name</label>
              <input
                type="text"
                value={branding.company_name}
                onChange={e => setBranding({ ...branding, company_name: e.target.value })}
                className="input-field"
                placeholder="Acme Corp"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-ink mb-1.5">Logo URL</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={branding.logo_url}
                  onChange={e => setBranding({ ...branding, logo_url: e.target.value })}
                  className="input-field flex-1"
                  placeholder="https://example.com/logo.png"
                />
                {branding.logo_url && (
                  <div className="w-10 h-10 rounded-lg border border-hairline flex items-center justify-center overflow-hidden bg-surface-subtle shrink-0">
                    <img src={branding.logo_url} alt="preview" className="max-w-full max-h-full object-contain" onError={e => { e.target.style.display = 'none' }} />
                  </div>
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Primary Color</label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={branding.primary_color}
                    onChange={e => setBranding({ ...branding, primary_color: e.target.value })}
                    className="w-10 h-10 rounded-lg border border-hairline cursor-pointer bg-transparent"
                  />
                  <span className="text-sm text-ink-muted font-mono">{branding.primary_color}</span>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Secondary Color</label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={branding.secondary_color}
                    onChange={e => setBranding({ ...branding, secondary_color: e.target.value })}
                    className="w-10 h-10 rounded-lg border border-hairline cursor-pointer bg-transparent"
                  />
                  <span className="text-sm text-ink-muted font-mono">{branding.secondary_color}</span>
                </div>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-ink mb-1.5">Favicon URL</label>
              <input
                type="text"
                value={branding.favicon_url}
                onChange={e => setBranding({ ...branding, favicon_url: e.target.value })}
                className="input-field"
                placeholder="https://example.com/favicon.ico"
              />
            </div>

            <button onClick={handleSaveBranding} disabled={saving} className="btn-primary w-full">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              Save Branding
            </button>
          </div>
        </div>

        {/* Preview Card */}
        <div className="card p-6">
          <div className="flex items-center gap-2 mb-4">
            <Eye className="h-5 w-5 text-accent" />
            <h2 className="text-lg font-semibold text-ink">Preview</h2>
          </div>

          <div
            className="rounded-xl border border-hairline overflow-hidden"
            style={{
              '--preview-primary': branding.primary_color,
              '--preview-secondary': branding.secondary_color,
            }}
          >
            {/* Themed header */}
            <div className="p-4 text-white" style={{ background: branding.primary_color }}>
              <div className="flex items-center gap-3">
                {branding.logo_url ? (
                  <img src={branding.logo_url} alt="logo" className="h-8 w-8 rounded object-contain bg-white/20" />
                ) : (
                  <div className="h-8 w-8 rounded bg-white/20 flex items-center justify-center text-sm font-bold">
                    {branding.company_name?.charAt(0) || 'A'}
                  </div>
                )}
                <div>
                  <p className="font-semibold text-sm">{branding.company_name || 'Your Company'}</p>
                  <p className="text-xs opacity-80">Call Center Dashboard</p>
                </div>
              </div>
            </div>

            {/* Themed button */}
            <div className="p-4 space-y-3">
              <div className="flex gap-2">
                <button className="px-4 py-2 rounded-lg text-sm font-medium text-white" style={{ background: branding.primary_color }}>
                  Primary Button
                </button>
                <button className="px-4 py-2 rounded-lg text-sm font-medium text-white" style={{ background: branding.secondary_color }}>
                  Secondary Button
                </button>
              </div>

              {/* Sample card */}
              <div className="rounded-lg border border-hairline p-3">
                <p className="text-sm font-medium text-ink">Sample Card</p>
                <p className="text-xs text-ink-muted mt-1">This is how themed UI components will appear.</p>
                <div className="mt-2 h-2 rounded-full" style={{ background: branding.primary_color, width: '60%' }} />
              </div>

              {/* Status badges */}
              <div className="flex gap-2">
                <span className="text-xs px-2 py-0.5 rounded-full text-white" style={{ background: branding.primary_color }}>Online</span>
                <span className="text-xs px-2 py-0.5 rounded-full text-white" style={{ background: branding.secondary_color }}>Away</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Domain Section */}
      <div className="card p-6 mt-6">
        <div className="flex items-center gap-2 mb-4">
          <Globe className="h-5 w-5 text-accent" />
          <h2 className="text-lg font-semibold text-ink">Custom Domain</h2>
        </div>

        <div className="space-y-4">
          <div className="flex gap-3">
            <input
              type="text"
              value={domainInput}
              onChange={e => setDomainInput(e.target.value)}
              className="input-field flex-1"
              placeholder="callcenter.yourcompany.com"
            />
            <button onClick={handleSetDomain} disabled={loading} className="btn-primary">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Globe className="h-4 w-4" />}
              Save Domain
            </button>
          </div>

          {domain.domain && (
            <div className="flex items-center gap-3 p-3 rounded-lg bg-surface-subtle">
              <div className="flex-1">
                <p className="text-sm font-medium text-ink">{domain.domain}</p>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${
                    domain.verified
                      ? 'bg-call-green-soft text-call-green'
                      : 'bg-call-amber-soft text-telecom-amber'
                  }`}>
                    {domain.verified ? (
                      <CheckCircle2 className="h-3 w-3" />
                    ) : (
                      <AlertTriangle className="h-3 w-3" />
                    )}
                    SSL: {domain.ssl_status || 'pending'}
                  </span>
                  <span className="text-xs text-ink-muted">
                    {domain.verified ? 'Verified' : 'Not verified'}
                  </span>
                </div>
              </div>
              {!domain.verified && (
                <button onClick={handleVerifyDomain} disabled={verifying} className="btn-secondary text-sm">
                  {verifying ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                  Verify DNS
                </button>
              )}
            </div>
          )}

          {/* DNS Setup Instructions */}
          <div className="rounded-lg border border-hairline p-4">
            <h3 className="text-sm font-medium text-ink mb-2">DNS Setup Instructions</h3>
            <div className="space-y-2 text-sm text-ink-muted">
              <p>1. Add a CNAME record pointing your domain to <code className="text-accent font-mono text-xs">app.aetherdesk.com</code></p>
              <p>2. Wait for DNS propagation (may take up to 48 hours)</p>
              <p>3. Click "Verify DNS" to confirm the setup</p>
              <p>4. SSL certificate will be provisioned automatically</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
