import React, { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { platformOpsApi } from '../services/api'
import {
  Rocket, Phone, CheckCircle2, Settings, BarChart3, ArrowRight, ArrowLeft, Loader2, Globe
} from 'lucide-react'
import { toast } from 'sonner'

const STEPS = [
  { key: 'welcome', label: 'Company Info', icon: Rocket },
  { key: 'phone_number', label: 'Phone Number', icon: Phone },
  { key: 'quickstart', label: 'Quickstart', icon: Settings },
  { key: 'health_check', label: 'Health Check', icon: BarChart3 },
]

export default function SelfServeSetup() {
  const { tenant } = useAuth()
  const [currentStepIdx, setCurrentStepIdx] = useState(0)
  const [completedSteps, setCompletedSteps] = useState([])
  const [allDone, setAllDone] = useState(false)
  const [progress, setProgress] = useState({ percent_complete: 0 })
  const [loading, setLoading] = useState(false)

  // Step 1: Company info
  const [companyName, setCompanyName] = useState('')
  const [industry, setIndustry] = useState('')

  // Step 2: Phone number
  const [areaCode, setAreaCode] = useState('')
  const [provisionedNumber, setProvisionedNumber] = useState(null)

  // Step 4: Health check
  const [healthResult, setHealthResult] = useState(null)
  const [healthRunning, setHealthRunning] = useState(false)

  const fetchProgress = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await platformOpsApi.getSetupProgress(tenant.id)
      setProgress(res.data)
      if (res.data?.onboarding_complete) {
        setAllDone(true)
      }
      if (res.data?.completed_steps) {
        setCompletedSteps(res.data.completed_steps)
        const idx = STEPS.findIndex(s => s.key === res.data.current_step)
        if (idx >= 0) setCurrentStepIdx(idx)
      }
    } catch { /* ignore */ }
  }, [tenant])

  const fetchStatus = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await platformOpsApi.getOnboardingStatus(tenant.id)
      if (res.data?.steps_completed) {
        setCompletedSteps(res.data.steps_completed)
        const idx = STEPS.findIndex(s => s.key === res.data.current_step)
        if (idx >= 0) setCurrentStepIdx(idx)
        if (res.data.completed) setAllDone(true)
      }
    } catch { /* ignore */ }
  }, [tenant])

  useEffect(() => {
    fetchProgress()
    fetchStatus()
  }, [fetchProgress, fetchStatus])

  async function completeCurrentStep(step) {
    if (!tenant) return null
    try {
      const res = await platformOpsApi.completeOnboardingStep(tenant.id, step)
      setCompletedSteps(res.data?.steps_completed || [])
      if (res.data?.completed) setAllDone(true)
      return res.data
    } catch {
      toast.error('Failed to complete step')
      return null
    }
  }

  async function handleCompanySubmit(e) {
    e.preventDefault()
    if (!companyName.trim()) return
    setLoading(true)
    await completeCurrentStep('welcome')
    setLoading(false)
    setCurrentStepIdx(1)
    toast.success('Company info saved')
  }

  async function handleProvisionNumber() {
    if (!tenant || areaCode.length < 3) return
    setLoading(true)
    try {
      const res = await platformOpsApi.provisionNumber(tenant.id, areaCode)
      setProvisionedNumber(res.data?.phone_number)
      await completeCurrentStep('phone_number')
      toast.success(`Number reserved: ${res.data?.phone_number}`)
      setCurrentStepIdx(2)
    } catch {
      toast.error('Failed to provision number')
    } finally {
      setLoading(false)
    }
  }

  async function handleQuickstartDone() {
    if (!tenant) return
    setLoading(true)
    await completeCurrentStep('quickstart')
    setLoading(false)
    setCurrentStepIdx(3)
    toast.success('Quickstart guide completed')
  }

  async function handleRunHealthCheck() {
    if (!tenant) return
    setHealthRunning(true)
    try {
      const res = await platformOpsApi.runHealthCheck(tenant.id)
      setHealthResult(res.data)
      await completeCurrentStep('health_check')
      toast.success(res.data?.overall_status === 'passed' ? 'All checks passed!' : 'Some checks failed')
      setCurrentStepIdx(4)
      fetchProgress()
    } catch {
      toast.error('Health check failed')
    } finally {
      setHealthRunning(false)
    }
  }

  if (allDone) {
    return (
      <div className="p-6 max-w-3xl mx-auto">
        <div className="card p-12 text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-call-green-soft mb-4">
            <CheckCircle2 className="h-8 w-8 text-call-green" />
          </div>
          <h2 className="text-xl font-semibold text-ink mb-2">Setup Complete!</h2>
          <p className="text-ink-muted mb-6">Your call center is ready to go. Start configuring agents and scripts.</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-lg mx-auto">
            <a href="/agents" className="btn-primary">
              <Rocket className="h-4 w-4" /> Add Agents
            </a>
            <a href="/scripts" className="btn-secondary">
              <Settings className="h-4 w-4" /> Create Scripts
            </a>
            <a href="/settings" className="btn-secondary">
              <Globe className="h-4 w-4" /> Settings
            </a>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-ink tracking-tight">Setup Your Call Center</h1>
        <p className="text-sm text-ink-muted mt-0.5">Complete these steps to get started</p>
      </div>

      {/* Progress Bar */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-medium text-ink-muted">Progress</span>
          <span className="text-xs font-medium text-accent">{progress.percent_complete || 0}%</span>
        </div>
        <div className="w-full h-2 bg-surface-subtle rounded-full overflow-hidden">
          <div
            className="h-full bg-accent rounded-full transition-all duration-500"
            style={{ width: `${progress.percent_complete || 0}%` }}
          />
        </div>
      </div>

      {/* Step Indicators */}
      <div className="flex items-center justify-between mb-8">
        {STEPS.map((step, idx) => {
          const Icon = step.icon
          const isActive = idx === currentStepIdx
          const isComplete = completedSteps.includes(step.key)
          return (
            <div key={step.key} className="flex items-center">
              <div className="flex flex-col items-center">
                <div className={`w-10 h-10 rounded-full flex items-center justify-center border-2 transition-all ${
                  isComplete
                    ? 'bg-call-green-soft border-call-green text-call-green'
                    : isActive
                    ? 'bg-accent-soft border-accent text-accent'
                    : 'bg-surface-subtle border-hairline text-ink-muted'
                }`}>
                  {isComplete ? <CheckCircle2 className="h-5 w-5" /> : <Icon className="h-5 w-5" />}
                </div>
                <span className={`text-xs mt-1.5 font-medium ${
                  isActive ? 'text-accent' : isComplete ? 'text-call-green' : 'text-ink-muted'
                }`}>{step.label}</span>
              </div>
              {idx < STEPS.length - 1 && (
                <div className={`w-12 md:w-20 h-0.5 mx-2 ${
                  completedSteps.includes(step.key) ? 'bg-call-green' : 'bg-hairline'
                }`} />
              )}
            </div>
          )
        })}
      </div>

      <div className="card p-6">
        {/* Step 1: Welcome & Company Info */}
        {currentStepIdx === 0 && (
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Rocket className="h-5 w-5 text-accent" />
              <h2 className="text-lg font-semibold text-ink">Welcome! Tell us about your company</h2>
            </div>
            <form onSubmit={handleCompanySubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Company Name</label>
                <input
                  type="text"
                  value={companyName}
                  onChange={e => setCompanyName(e.target.value)}
                  className="input-field"
                  placeholder="Acme Corp"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Industry</label>
                <select value={industry} onChange={e => setIndustry(e.target.value)} className="input-field">
                  <option value="">Select industry...</option>
                  <option value="sales">Sales</option>
                  <option value="support">Customer Support</option>
                  <option value="healthcare">Healthcare</option>
                  <option value="finance">Finance</option>
                  <option value="real_estate">Real Estate</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <button type="submit" disabled={loading} className="btn-primary w-full">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowRight className="h-4 w-4" />}
                Get Started
              </button>
            </form>
          </div>
        )}

        {/* Step 2: Phone Number */}
        {currentStepIdx === 1 && (
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Phone className="h-5 w-5 text-accent" />
              <h2 className="text-lg font-semibold text-ink">Provision a Phone Number</h2>
            </div>
            <p className="text-sm text-ink-muted mb-4">Choose an area code to reserve a local phone number for your call center.</p>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Area Code</label>
                <input
                  type="text"
                  value={areaCode}
                  onChange={e => setAreaCode(e.target.value.replace(/\D/g, '').slice(0, 3))}
                  className="input-field max-w-[120px]"
                  placeholder="555"
                  maxLength={3}
                />
              </div>
              {provisionedNumber && (
                <div className="p-3 rounded-lg bg-call-green-soft border border-call-green/20">
                  <p className="text-sm font-medium text-call-green">Number Reserved</p>
                  <p className="text-lg font-mono font-semibold text-ink mt-1">{provisionedNumber}</p>
                </div>
              )}
              <button onClick={handleProvisionNumber} disabled={loading || areaCode.length < 3} className="btn-primary w-full">
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Phone className="h-4 w-4" />}
                {provisionedNumber ? 'Re-provision' : 'Reserve Number'}
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Quickstart Guide */}
        {currentStepIdx === 2 && (
          <div>
            <div className="flex items-center gap-2 mb-4">
              <Settings className="h-5 w-5 text-accent" />
              <h2 className="text-lg font-semibold text-ink">Quickstart Guide</h2>
            </div>
            <p className="text-sm text-ink-muted mb-4">Complete these tasks to set up your call center:</p>
            <div className="space-y-3">
              {[
                { id: 'configure_greetings', label: 'Configure Greetings' },
                { id: 'add_agents', label: 'Add AI Agents' },
                { id: 'set_hours', label: 'Set Business Hours' },
                { id: 'configure_routing', label: 'Configure Call Routing' },
                { id: 'create_scripts', label: 'Create Call Scripts' },
                { id: 'invite_team', label: 'Invite Team Members' },
              ].map(item => (
                <div key={item.id} className="flex items-center gap-3 p-3 rounded-lg border border-hairline">
                  <div className="w-5 h-5 rounded border-2 border-hairline flex items-center justify-center">
                    <CheckCircle2 className="h-4 w-4 text-call-green opacity-0" />
                  </div>
                  <span className="text-sm text-ink">{item.label}</span>
                </div>
              ))}
            </div>
            <button onClick={handleQuickstartDone} disabled={loading} className="btn-primary w-full mt-4">
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              Mark as Complete
            </button>
          </div>
        )}

        {/* Step 4: Health Check */}
        {currentStepIdx === 3 && (
          <div>
            <div className="flex items-center gap-2 mb-4">
              <BarChart3 className="h-5 w-5 text-accent" />
              <h2 className="text-lg font-semibold text-ink">Health Check</h2>
            </div>
            <p className="text-sm text-ink-muted mb-4">Verify that everything is working properly.</p>

            {healthResult && (
              <div className="space-y-2 mb-4">
                {Object.entries(healthResult.checks || {}).map(([key, check]) => (
                  <div key={key} className="flex items-center justify-between p-3 rounded-lg border border-hairline">
                    <div className="flex items-center gap-2">
                      {check.status === 'passed' ? (
                        <CheckCircle2 className="h-4 w-4 text-call-green" />
                      ) : (
                        <div className="h-4 w-4 rounded-full bg-red-400" />
                      )}
                      <span className="text-sm text-ink capitalize">{key.replace(/_/g, ' ')}</span>
                    </div>
                    <span className="text-xs text-ink-muted">{check.message}</span>
                  </div>
                ))}
                <div className={`p-3 rounded-lg text-sm font-medium ${
                  healthResult.overall_status === 'passed'
                    ? 'bg-call-green-soft text-call-green'
                    : 'bg-red-50 text-red-600'
                }`}>
                  Overall: {healthResult.overall_status === 'passed' ? 'All Systems Go' : 'Issues Found'}
                </div>
              </div>
            )}

            <button onClick={handleRunHealthCheck} disabled={healthRunning} className="btn-primary w-full">
              {healthRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <BarChart3 className="h-4 w-4" />}
              {healthRunning ? 'Running Checks...' : healthResult ? 'Re-run Health Check' : 'Run Health Check'}
            </button>
          </div>
        )}

        {/* Step 5: Complete (hidden but fallback) */}
        {currentStepIdx >= 4 && !allDone && (
          <div className="text-center py-8">
            <CheckCircle2 className="h-12 w-12 text-call-green mx-auto mb-3" />
            <p className="text-lg font-semibold text-ink">All steps completed!</p>
            <p className="text-sm text-ink-muted mt-1">Redirecting to dashboard...</p>
          </div>
        )}

        {/* Navigation */}
        <div className="flex justify-between mt-6 pt-4 border-t border-hairline">
          <button
            onClick={() => setCurrentStepIdx(Math.max(0, currentStepIdx - 1))}
            disabled={currentStepIdx === 0}
            className="btn-secondary"
          >
            <ArrowLeft className="h-4 w-4" /> Back
          </button>
          {currentStepIdx < 3 && (
            <button
              onClick={() => setCurrentStepIdx(Math.min(3, currentStepIdx + 1))}
              className="btn-secondary"
            >
              Skip <ArrowRight className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
