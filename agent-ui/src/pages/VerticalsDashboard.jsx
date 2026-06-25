import React, { useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { verticalsApi } from '../services/api'
import {
  Stethoscope, DollarSign, Building2, ShoppingCart,
  Shield, FileText, CheckCircle2, Loader2, ChevronRight, X
} from 'lucide-react'
import { toast } from 'sonner'

const ICON_MAP = {
  Stethoscope: Stethoscope,
  DollarSign: DollarSign,
  Building2: Building2,
  ShoppingCart: ShoppingCart,
}

export default function VerticalsDashboard() {
  const { tenant } = useAuth()
  const [verticals, setVerticals] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [config, setConfig] = useState(null)
  const [compliance, setCompliance] = useState(null)
  const [scripts, setScripts] = useState(null)
  const [loading, setLoading] = useState(false)
  const [applying, setApplying] = useState(null)

  useEffect(() => {
    fetchVerticals()
  }, [])

  async function fetchVerticals() {
    try {
      const res = await verticalsApi.list()
      setVerticals(Array.isArray(res.data) ? res.data : [])
    } catch { setVerticals([]) }
  }

  async function handleSelect(id) {
    if (selectedId === id) {
      setSelectedId(null)
      setConfig(null)
      setCompliance(null)
      setScripts(null)
      return
    }
    setSelectedId(id)
    setLoading(true)
    try {
      const [cfg, cmp, scr] = await Promise.all([
        verticalsApi.getConfig(id),
        verticalsApi.getCompliance(id),
        verticalsApi.getScripts(id),
      ])
      setConfig(cfg.data)
      setCompliance(cmp.data)
      setScripts(scr.data)
    } catch { toast.error('Failed to load vertical details') }
    finally { setLoading(false) }
  }

  async function handleApply(id) {
    if (!tenant) return
    setApplying(id)
    try {
      await verticalsApi.apply(id, { tenant_id: tenant.id })
      toast.success('Vertical template applied successfully')
    } catch { toast.error('Failed to apply template') }
    finally { setApplying(null) }
  }

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-ink tracking-tight">Vertical Solutions</h1>
        <p className="text-sm text-ink-muted mt-0.5">Industry-specific templates with compliance, scripts, and routing</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {verticals.map(v => {
          const Icon = ICON_MAP[v.icon] || Stethoscope
          const isSelected = selectedId === v.id

          return (
            <div key={v.id} className={`card overflow-hidden transition-all ${isSelected ? 'ring-2 ring-accent' : ''}`}>
              <div className="p-6">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-lg bg-accent-soft flex items-center justify-center">
                      <Icon className="h-5 w-5 text-accent" />
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-ink">{v.name}</h3>
                      <p className="text-xs text-ink-muted">{v.intent_count} intents · {v.script_count} scripts</p>
                    </div>
                  </div>
                  <button
                    onClick={() => handleSelect(v.id)}
                    className="p-1.5 rounded-lg hover:bg-surface-hover transition-colors"
                  >
                    <ChevronRight className={`h-4 w-4 text-ink-muted transition-transform ${isSelected ? 'rotate-90' : ''}`} />
                  </button>
                </div>

                <p className="text-sm text-ink-muted mb-4">{v.description}</p>

                <div className="flex flex-wrap gap-2 mb-4">
                  {(v.compliance || []).map(c => (
                    <span key={c} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700">
                      <Shield className="h-3 w-3" /> {c}
                    </span>
                  ))}
                </div>

                <button
                  onClick={() => handleApply(v.id)}
                  disabled={applying === v.id}
                  className="btn-primary text-sm w-full"
                >
                  {applying === v.id ? (
                    <><Loader2 className="h-4 w-4 animate-spin" /> Applying...</>
                  ) : (
                    <><CheckCircle2 className="h-4 w-4" /> Apply Template</>
                  )}
                </button>
              </div>

              {isSelected && config && (
                <div className="border-t border-hairline bg-surface-subtle">
                  <div className="p-6 space-y-6">
                    <div>
                      <h4 className="text-sm font-medium text-ink mb-2 flex items-center gap-2"><FileText className="h-4 w-4" /> Intents</h4>
                      <div className="flex flex-wrap gap-2">
                        {(config.intents || []).map((intent, i) => (
                          <span key={i} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-surface-hover text-ink">{intent}</span>
                        ))}
                      </div>
                    </div>

                    {compliance && (
                      <div>
                        <h4 className="text-sm font-medium text-ink mb-2 flex items-center gap-2"><Shield className="h-4 w-4" /> Compliance Rules</h4>
                        <div className="space-y-1.5">
                          {Object.entries(compliance.compliance_rules || {}).map(([key, val]) => (
                            <div key={key} className="flex items-center justify-between text-xs">
                              <span className="text-ink-muted">{key.replace(/_/g, ' ')}</span>
                              <span className={`font-medium ${val ? 'text-call-green' : 'text-ink-muted'}`}>
                                {val === true ? 'Required' : val === false ? 'Not Required' : String(val)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {scripts && (
                      <div>
                        <h4 className="text-sm font-medium text-ink mb-2 flex items-center gap-2"><FileText className="h-4 w-4" /> Script Templates</h4>
                        <div className="flex flex-wrap gap-2">
                          {(scripts.script_templates || []).map((s, i) => (
                            <span key={i} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-accent-soft text-accent">{s}</span>
                          ))}
                        </div>
                      </div>
                    )}

                    <div>
                      <h4 className="text-sm font-medium text-ink mb-2">Required Integrations</h4>
                      <div className="flex flex-wrap gap-2">
                        {(config.required_integrations || []).map((ri, i) => (
                          <span key={i} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-purple-50 text-purple-600">{ri}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )
        })}

        {verticals.length === 0 && (
          <div className="col-span-2 card p-12 text-center text-ink-muted">
            <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
            Loading vertical templates...
          </div>
        )}
      </div>
    </div>
  )
}
