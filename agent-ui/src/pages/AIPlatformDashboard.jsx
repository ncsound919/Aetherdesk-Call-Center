import React, { useEffect, useState, useCallback, useMemo } from 'react'
import { useAuth } from '../context/AuthContext'
import { platformApi } from '../services/api'
import {
  BrainCircuit, Cpu, Layers, GitBranch, TrendingUp,
  Mic2, Activity, Heart, BarChart3, Plus, Loader2, X,
  Play, Download, CheckCircle2, AlertTriangle,
  Database, Tags, ExternalLink, Eye, EyeOff,
  Archive, RefreshCw, Award, FileText, Search,
  ChevronRight, ChevronDown, Home, Settings,
  Sliders, HelpCircle, Copy, Clock, Shield,
  UserCheck, Users, Flag, Trash2, Undo2,
  List, Grid3X3, Maximize2, Minimize2,
  Lightbulb, BookOpen, Radio, Webhook,
  Zap, Server, Cloud
} from 'lucide-react'
import { toast } from 'sonner'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, BarChart, Bar, Cell, PieChart, Pie, Legend
} from 'recharts'

const EMOTION_COLORS = { happy: '#22c55e', neutral: '#6366f1', angry: '#ef4444', sad: '#f59e0b', anxious: '#ec4899' }

const MODEL_STATE_COLORS = {
  draft: 'bg-gray-100 text-gray-600 border-gray-200',
  training: 'bg-blue-50 text-blue-600 border-blue-200',
  trained: 'bg-green-50 text-green-600 border-green-200',
  evaluated: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  approved: 'bg-purple-50 text-purple-600 border-purple-200',
  production: 'bg-amber-50 text-amber-600 border-amber-300',
  retired: 'bg-red-50 text-red-500 border-red-200',
}

// ── Role-based config ──
const ROLE_VIEWS = {
  admin: { tabs: ['training', 'models', 'voice', 'datasets', 'labeling', 'system'], canDelete: true, canPromote: true },
  reviewer: { tabs: ['models', 'datasets', 'labeling'], canDelete: false, canPromote: false },
  operator: { tabs: ['training', 'models', 'voice'], canDelete: false, canPromote: false },
  engineer: { tabs: ['training', 'models', 'voice', 'datasets', 'system'], canDelete: true, canPromote: true },
}

const TABS = [
  { id: 'training', label: 'Pipelines', icon: Cpu },
  { id: 'models', label: 'Model Registry', icon: Layers },
  { id: 'voice', label: 'Voice Biometrics', icon: Mic2 },
  { id: 'datasets', label: 'Datasets', icon: Database },
  { id: 'labeling', label: 'QA Labeling', icon: Tags },
  { id: 'system', label: 'System', icon: Settings },
]

function StatusBadge({ state }) {
  const cls = MODEL_STATE_COLORS[state] || 'bg-gray-50 text-gray-500 border-gray-200'
  return <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${cls}`}>{state}</span>
}

function CopyButton({ text }) {
  return (
    <button onClick={() => { navigator.clipboard.writeText(text); toast.success('Copied') }}
      className="p-1 hover:bg-white/10 rounded transition-colors" title="Copy">
      <Copy className="h-3.5 w-3.5 text-white/50" />
    </button>
  )
}

function ConfirmDialog({ open, title, message, onConfirm, onCancel, destructive }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-[#1a2332] border border-white/10 rounded-xl p-6 max-w-md w-full mx-4 shadow-2xl">
        <h3 className="text-lg font-semibold text-white mb-2">{title}</h3>
        <p className="text-sm text-white/60 mb-6">{message}</p>
        <div className="flex gap-3 justify-end">
          <button onClick={onCancel} className="px-4 py-2 rounded-lg text-sm text-white/60 hover:text-white hover:bg-white/5 transition-colors">Cancel</button>
          <button onClick={onConfirm} className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${destructive ? 'bg-red-500 hover:bg-red-600 text-white' : 'bg-accent hover:bg-accent/80 text-white'}`}>
            Confirm
          </button>
        </div>
      </div>
    </div>
  )
}

function SearchBar({ value, onChange, placeholder }) {
  return (
    <div className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-white/30" />
      <input type="text" value={value} onChange={e => onChange(e.target.value)}
        placeholder={placeholder || 'Search...'}
        className="w-full pl-9 pr-4 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-white/30 focus:outline-none focus:ring-2 focus:ring-accent/50" />
    </div>
  )
}

function Pagination({ page, totalPages, onPageChange }) {
  if (totalPages <= 1) return null
  return (
    <div className="flex items-center justify-center gap-2 mt-4">
      <button disabled={page <= 0} onClick={() => onPageChange(page - 1)} className="px-3 py-1 rounded text-sm text-white/50 hover:text-white disabled:opacity-30">Prev</button>
      <span className="text-sm text-white/40">{page + 1} / {totalPages}</span>
      <button disabled={page >= totalPages - 1} onClick={() => onPageChange(page + 1)} className="px-3 py-1 rounded text-sm text-white/50 hover:text-white disabled:opacity-30">Next</button>
    </div>
  )
}

function SkeletonRow() {
  return <div className="h-12 bg-white/5 rounded animate-pulse" />
}

function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <Icon className="h-12 w-12 text-white/20 mb-4" />
      <h3 className="text-lg font-medium text-white/60 mb-1">{title}</h3>
      <p className="text-sm text-white/30 max-w-md">{description}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

function MetricCard({ icon: Icon, label, value, color, trend }) {
  return (
    <div className="bg-white/5 border border-white/10 rounded-xl p-4 hover:bg-white/[0.07] transition-colors">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-white/40 uppercase tracking-wider">{label}</span>
        <Icon className={`h-4 w-4 ${color || 'text-white/40'}`} />
      </div>
      <div className="text-2xl font-bold text-white">{value}</div>
      {trend !== undefined && (
        <div className={`text-xs mt-1 ${trend >= 0 ? 'text-green-400' : 'text-red-400'}`}>
          {trend >= 0 ? '↑' : '↓'} {Math.abs(trend)}%
        </div>
      )}
    </div>
  )
}

function WizardStepper({ steps, currentStep, onStepClick }) {
  return (
    <div className="flex items-center gap-2 mb-6">
      {steps.map((s, i) => (
        <React.Fragment key={i}>
          <button onClick={() => onStepClick(i)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              i === currentStep ? 'bg-accent/20 text-accent' : i < currentStep ? 'text-green-400' : 'text-white/30'
            }`}>
            {i < currentStep ? <CheckCircle2 className="h-3.5 w-3.5" /> : <span className="h-3.5 w-3.5 rounded-full border border-current flex items-center justify-center text-[10px]">{i + 1}</span>}
            {s}
          </button>
          {i < steps.length - 1 && <ChevronRight className="h-3 w-3 text-white/20" />}
        </React.Fragment>
      ))}
    </div>
  )
}

function TooltipLabel({ text }) {
  return (
    <span className="inline-flex ml-1 group relative cursor-help">
      <HelpCircle className="h-3.5 w-3.5 text-white/30 group-hover:text-white/60 transition-colors" />
      <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 px-2 py-1 bg-gray-800 text-white text-xs rounded shadow-lg whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">{text}</span>
    </span>
  )
}

function JobLogViewer({ jobId, logs }) {
  return (
    <div className="bg-black/30 rounded-lg p-3 font-mono text-xs max-h-48 overflow-y-auto mt-2">
      {(!logs || logs.length === 0) ? (
        <div className="text-white/20 italic">No logs available</div>
      ) : (
        logs.map((log, i) => (
          <div key={i} className={`py-0.5 ${log.level === 'error' ? 'text-red-400' : log.level === 'warn' ? 'text-yellow-400' : 'text-white/50'}`}>
            <span className="text-white/30">[{log.timestamp || ''}]</span> {log.message}
          </div>
        ))
      )}
    </div>
  )
}

function SystemHealthBar() {
  const [health, setHealth] = useState(null)
  useEffect(() => {
    async function fetch() {
      try {
        const res = await platformApi.getHealth?.()
        setHealth(res.data || {})
      } catch { setHealth({}) }
    }
    fetch()
    const interval = setInterval(fetch, 30000)
    return () => clearInterval(interval)
  }, [])
  return (
    <div className="flex items-center gap-4 px-4 py-2 bg-white/[0.03] border-b border-white/5">
      <span className="text-xs font-medium text-white/40 uppercase tracking-wider">System Health</span>
      {['Data Pipeline', 'Model Registry', 'Voice Biometrics', 'GPU Queue'].map(s => (
        <div key={s} className="flex items-center gap-1.5">
          <div className={`h-2 w-2 rounded-full ${health?.[s] === 'healthy' ? 'bg-green-400' : 'bg-green-400'}`} />
          <span className="text-xs text-white/50">{s}</span>
        </div>
      ))}
    </div>
  )
}

// ── WIZARD: Create Dataset ──
function CreateDatasetWizard({ open, onClose, onCreated, tenant }) {
  const [step, setStep] = useState(0)
  const [form, setForm] = useState({ name: '', recipe_type: 'dialogue', source_start_date: '', source_end_date: '', description: '' })
  const [building, setBuilding] = useState(false)
  const steps = ['Configure', 'Source Data', 'Build']

  async function handleFinish() {
    setBuilding(true)
    try {
      const data = { name: form.name, recipe_type: form.recipe_type, description: form.description, tenant_id: tenant?.id }
      if (form.source_start_date) data.source_start_date = form.source_start_date
      if (form.source_end_date) data.source_end_date = form.source_end_date
      await platformApi.createDataset(data)
      toast.success('Dataset building...')
      onCreated?.()
      onClose()
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
    finally { setBuilding(false) }
  }

  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-[#1a2332] border border-white/10 rounded-xl p-6 max-w-2xl w-full mx-4 shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Create Dataset</h2>
          <button onClick={onClose} className="p-1 hover:bg-white/5 rounded"><X className="h-5 w-5 text-white/40" /></button>
        </div>
        <WizardStepper steps={steps} currentStep={step} onStepClick={setStep} />
        {step === 0 && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-white/70 mb-1">Name <TooltipLabel text="A unique identifier for this dataset" /></label>
              <input value={form.name} onChange={e => setForm({...form, name: e.target.value})} className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white" placeholder="my-training-dataset" />
            </div>
            <div>
              <label className="block text-sm text-white/70 mb-1">Recipe Type</label>
              <select value={form.recipe_type} onChange={e => setForm({...form, recipe_type: e.target.value})} className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white">
                <option value="dialogue">Dialogue (conversation pairs)</option>
                <option value="classification">Classification (intent labels)</option>
                <option value="summarization">Summarization (call summaries)</option>
              </select>
            </div>
            <div>
              <label className="block text-sm text-white/70 mb-1">Description</label>
              <textarea value={form.description} onChange={e => setForm({...form, description: e.target.value})} className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white h-20" placeholder="Optional description" />
            </div>
          </div>
        )}
        {step === 1 && (
          <div className="space-y-4">
            <p className="text-sm text-white/50">Select the date range of calls to include in this dataset.</p>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-white/70 mb-1">Start Date</label>
                <input type="date" value={form.source_start_date} onChange={e => setForm({...form, source_start_date: e.target.value})} className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white" />
              </div>
              <div>
                <label className="block text-sm text-white/70 mb-1">End Date</label>
                <input type="date" value={form.source_end_date} onChange={e => setForm({...form, source_end_date: e.target.value})} className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white" />
              </div>
            </div>
          </div>
        )}
        {step === 2 && (
          <div className="space-y-4">
            <div className="bg-white/5 rounded-lg p-4 space-y-2">
              <div className="flex justify-between text-sm"><span className="text-white/50">Name</span><span className="text-white">{form.name || '—'}</span></div>
              <div className="flex justify-between text-sm"><span className="text-white/50">Recipe</span><span className="text-white">{form.recipe_type}</span></div>
              <div className="flex justify-between text-sm"><span className="text-white/50">Source</span><span className="text-white">{form.source_start_date || '—'} to {form.source_end_date || '—'}</span></div>
            </div>
            {building && (
              <div className="flex items-center gap-3 text-sm text-white/60">
                <Loader2 className="h-4 w-4 animate-spin text-accent" /> Building dataset...
              </div>
            )}
          </div>
        )}
        <div className="flex justify-between mt-6">
          <button disabled={step === 0} onClick={() => setStep(s => s - 1)} className="px-4 py-2 text-sm text-white/50 hover:text-white">Back</button>
          <div className="flex gap-3">
            {step < 2 ? (
              <button onClick={() => setStep(s => s + 1)} className="px-4 py-2 bg-accent/20 text-accent rounded-lg text-sm font-medium hover:bg-accent/30 transition-colors">Next</button>
            ) : (
              <button onClick={handleFinish} disabled={building} className="px-4 py-2 bg-accent text-white rounded-lg text-sm font-medium hover:bg-accent/80 transition-colors disabled:opacity-50">
                {building ? <><Loader2 className="h-4 w-4 animate-spin inline mr-2" />Building...</> : 'Create Dataset'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── WIZARD: Register Model ──
function RegisterModelWizard({ open, onClose, onCreated }) {
  const [step, setStep] = useState(0)
  const [form, setForm] = useState({ name: '', version: '1.0.0', model_type: 'intent', family: 'llm', config: '{}', description: '' })
  const steps = ['Details', 'Configuration', 'Review']

  async function handleFinish() {
    try {
      const config = JSON.parse(form.config || '{}')
      await platformApi.registerModel({ name: form.name, version: form.version, model_type: form.model_type, config })
      toast.success('Model registered')
      onCreated?.()
      onClose()
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed') }
  }

  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-[#1a2332] border border-white/10 rounded-xl p-6 max-w-2xl w-full mx-4 shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Register Model</h2>
          <button onClick={onClose} className="p-1 hover:bg-white/5 rounded"><X className="h-5 w-5 text-white/40" /></button>
        </div>
        <WizardStepper steps={steps} currentStep={step} onStepClick={setStep} />
        {step === 0 && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-white/70 mb-1">Model Name <TooltipLabel text="Used across all API calls" /></label>
              <input value={form.name} onChange={e => setForm({...form, name: e.target.value})} className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white" placeholder="my-intent-model" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-white/70 mb-1">Model Family</label>
                <select value={form.family} onChange={e => setForm({...form, family: e.target.value})} className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white">
                  <option value="llm">LLM</option>
                  <option value="classifier">Classifier</option>
                  <option value="summarizer">Summarizer</option>
                  <option value="sentiment">Sentiment</option>
                  <option value="intent">Intent</option>
                  <option value="voice_biometric">Voice Biometric</option>
                </select>
              </div>
              <div>
                <label className="block text-sm text-white/70 mb-1">Version (semver)</label>
                <input value={form.version} onChange={e => setForm({...form, version: e.target.value})} className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white" placeholder="1.0.0" />
              </div>
            </div>
          </div>
        )}
        {step === 1 && (
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-white/70 mb-1">Configuration (JSON) <TooltipLabel text="Model hyperparameters and settings" /></label>
              <textarea value={form.config} onChange={e => setForm({...form, config: e.target.value})} className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white font-mono h-32" />
            </div>
          </div>
        )}
        {step === 2 && (
          <div className="bg-white/5 rounded-lg p-4 space-y-2">
            <div className="flex justify-between text-sm"><span className="text-white/50">Name</span><span className="text-white">{form.name}</span></div>
            <div className="flex justify-between text-sm"><span className="text-white/50">Family</span><span className="text-white">{form.family}</span></div>
            <div className="flex justify-between text-sm"><span className="text-white/50">Version</span><span className="text-white">{form.version}</span></div>
            <CopyButton text={`curl -X POST https://api.aetherdesk.com/api/v1/ai-platform/models -H "Authorization: Bearer $API_KEY" -d '{"name":"${form.name}","version":"${form.version}","model_type":"${form.family}"}'`} />
          </div>
        )}
        <div className="flex justify-between mt-6">
          <button disabled={step === 0} onClick={() => setStep(s => s - 1)} className="px-4 py-2 text-sm text-white/50 hover:text-white">Back</button>
          <div className="flex gap-3">
            {step < 2 ? (
              <button onClick={() => setStep(s => s + 1)} className="px-4 py-2 bg-accent/20 text-accent rounded-lg text-sm font-medium hover:bg-accent/30">Next</button>
            ) : (
              <button onClick={handleFinish} className="px-4 py-2 bg-accent text-white rounded-lg text-sm font-medium hover:bg-accent/80 transition-colors">Register Model</button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── ONBOARDING TOUR ──
function OnboardingTour({ open, onClose }) {
  const [step, setStep] = useState(0)
  const steps = [
    { title: 'Welcome to AI Platform', desc: 'Build, train, and manage AI models for your call center.', icon: BrainCircuit },
    { title: 'Collect Training Data', desc: 'Import call transcripts and generate training examples.', icon: Database },
    { title: 'Train & Evaluate', desc: 'Create training jobs, monitor progress, and evaluate results.', icon: Cpu },
    { title: 'Model Registry', desc: 'Version, approve, and promote models to production.', icon: Layers },
    { title: 'Voice Biometrics', desc: 'Identify speakers, detect emotions, and analyze sentiment.', icon: Mic2 },
  ]
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-md">
      <div className="bg-[#1a2332] border border-white/10 rounded-2xl p-8 max-w-lg w-full mx-4 shadow-2xl text-center">
        {React.createElement(steps[step].icon, { className: 'h-16 w-16 text-accent mx-auto mb-4' })}
        <h2 className="text-xl font-bold text-white mb-2">{steps[step].title}</h2>
        <p className="text-sm text-white/50 mb-8">{steps[step].desc}</p>
        <div className="flex items-center justify-center gap-2 mb-6">
          {steps.map((_, i) => <div key={i} className={`h-1.5 w-6 rounded-full transition-colors ${i === step ? 'bg-accent' : 'bg-white/10'}`} />)}
        </div>
        <div className="flex justify-between">
          <button onClick={onClose} className="text-sm text-white/30 hover:text-white/60">Skip</button>
          <div className="flex gap-3">
            {step > 0 && <button onClick={() => setStep(s => s - 1)} className="px-4 py-2 text-sm text-white/50 hover:text-white">Back</button>}
            {step < steps.length - 1 ? (
              <button onClick={() => setStep(s => s + 1)} className="px-6 py-2 bg-accent text-white rounded-lg text-sm font-medium hover:bg-accent/80">Next</button>
            ) : (
              <button onClick={onClose} className="px-6 py-2 bg-accent text-white rounded-lg text-sm font-medium hover:bg-accent/80">Get Started</button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── MAIN EXPORT ──
export default function AIPlatformDashboard() {
  const { tenant, user } = useAuth()
  const userRole = user?.role || 'admin'
  const roleCfg = ROLE_VIEWS[userRole] || ROLE_VIEWS.admin
  const [activeTab, setActiveTab] = useState('training')
  const [loading, setLoading] = useState(false)
  const [globalSearch, setGlobalSearch] = useState('')
  const [viewMode, setViewMode] = useState('list')
  const [showOnboarding, setShowOnboarding] = useState(() => !localStorage.getItem('ai-platform-tour-done'))

  // Training state
  const [trainingJobs, setTrainingJobs] = useState([])
  const [trainingCount, setTrainingCount] = useState(null)
  const [showCreateJob, setShowCreateJob] = useState(false)
  const [jobForm, setJobForm] = useState({ name: '', model_base: 'llama-3.1-8b', hyperparams: '{"epochs":3,"learning_rate":0.0002,"batch_size":8}' })
  const [expandedJobLogs, setExpandedJobLogs] = useState(null)
  const [trainingPage, setTrainingPage] = useState(0)
  const [confirmAction, setConfirmAction] = useState(null)

  // Models state
  const [models, setModels] = useState([])
  const [activeModels, setActiveModels] = useState({})
  const [showRegisterModel, setShowRegisterModel] = useState(false)
  const [compareResult, setCompareResult] = useState(null)
  const [compareForm, setCompareForm] = useState({ model_id: '', version_a: '', version_b: '' })
  const [modelFamilyFilter, setModelFamilyFilter] = useState('')
  const [auditLog, setAuditLog] = useState(null)
  const [auditModelId, setAuditModelId] = useState(null)
  const [expandedModelMetrics, setExpandedModelMetrics] = useState(null)
  const [modelsPage, setModelsPage] = useState(0)

  // Voice state
  const [voiceProfiles, setVoiceProfiles] = useState([])
  const [emotionTrends, setEmotionTrends] = useState([])
  const [showCreateProfile, setShowCreateProfile] = useState(false)
  const [profileForm, setProfileForm] = useState({ speaker_name: '' })
  const [identifyResult, setIdentifyResult] = useState(null)
  const [emotionResult, setEmotionResult] = useState(null)

  // Datasets state
  const [datasets, setDatasets] = useState([])
  const [showCreateDataset, setShowCreateDataset] = useState(false)
  const [expandedDataset, setExpandedDataset] = useState(null)
  const [datasetTurns, setDatasetTurns] = useState([])
  const [datasetsPage, setDatasetsPage] = useState(0)

  // Labeling state
  const [labelDatasets, setLabelDatasets] = useState([])
  const [selectedLabelDataset, setSelectedLabelDataset] = useState(null)
  const [browseTurns, setBrowseTurns] = useState([])
  const [labelForm, setLabelForm] = useState({ turn_id: '', label_type: 'intent', label_value: '', confidence: 1.0, notes: '' })
  const [labelStats, setLabelStats] = useState({})
  const [labelingPage, setLabelingPage] = useState(0)

  const fetchTrainingJobs = useCallback(async () => {
    if (!tenant) return
    try { const res = await platformApi.listTrainingJobs({ tenant_id: tenant.id }); setTrainingJobs(Array.isArray(res.data) ? res.data : []) }
    catch { setTrainingJobs([]) }
  }, [tenant])
  const fetchModels = useCallback(async () => {
    if (!tenant) return
    try { const res = await platformApi.listModels({ tenant_id: tenant.id }); setModels(Array.isArray(res.data) ? res.data : []) }
    catch { setModels([]) }
  }, [tenant])
  const fetchActiveModels = useCallback(async () => {
    if (!tenant) return
    try { const res = await platformApi.getActiveModels({ tenant_id: tenant.id }); setActiveModels(res.data || {}) }
    catch { setActiveModels({}) }
  }, [tenant])
  const fetchVoiceProfiles = useCallback(async () => {
    if (!tenant) return
    try { const res = await platformApi.listVoiceProfiles({ tenant_id: tenant.id }); setVoiceProfiles(Array.isArray(res.data) ? res.data : []) }
    catch { setVoiceProfiles([]) }
  }, [tenant])
  const fetchDatasets = useCallback(async () => {
    if (!tenant) return
    try { const res = await platformApi.listDatasets({ tenant_id: tenant.id }); setDatasets(Array.isArray(res.data) ? res.data : []) }
    catch { setDatasets([]) }
  }, [tenant])

  useEffect(() => {
    if (activeTab === 'training') fetchTrainingJobs()
    if (activeTab === 'models') { fetchModels(); fetchActiveModels() }
    if (activeTab === 'voice') fetchVoiceProfiles()
    if (activeTab === 'datasets') fetchDatasets()
    if (activeTab === 'labeling') fetchDatasets()
  }, [activeTab, fetchTrainingJobs, fetchModels, fetchActiveModels, fetchVoiceProfiles, fetchDatasets])

  // Polling for active jobs
  useEffect(() => {
    if (activeTab !== 'training') return
    const hasActive = trainingJobs.some(j => j.status === 'training' || j.status === 'pending')
    if (!hasActive) return
    const interval = setInterval(fetchTrainingJobs, 5000)
    return () => clearInterval(interval)
  }, [activeTab, trainingJobs, fetchTrainingJobs])

  const visibleTabs = useMemo(() => TABS.filter(t => roleCfg.tabs.includes(t.id)), [roleCfg])

  async function handleCollectData(e) {
    e.preventDefault()
    if (!tenant) return
    setLoading(true)
    try {
      const end = new Date().toISOString()
      const start = new Date(Date.now() - 7 * 86400000).toISOString()
      const res = await platformApi.collectTrainingData({ tenant_id: tenant.id, start_date: start, end_date: end })
      setTrainingCount(res.data?.total || 0)
      toast.success(`Collected ${res.data?.total || 0} training examples`)
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to collect data') }
    finally { setLoading(false) }
  }

  async function handleCreateJob(e) {
    e.preventDefault()
    try {
      let hyperparams
      try { hyperparams = JSON.parse(jobForm.hyperparams) } catch { hyperparams = { epochs: 3, learning_rate: 2e-4, batch_size: 8 } }
      await platformApi.createTrainingJob({ name: jobForm.name, model_base: jobForm.model_base, hyperparams })
      toast.success('Training job created')
      setShowCreateJob(false)
      setJobForm({ name: '', model_base: 'llama-3.1-8b', hyperparams: '{"epochs":3,"learning_rate":0.0002,"batch_size":8}' })
      fetchTrainingJobs()
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to create job') }
  }

  async function handleRetryJob(jobId) {
    try {
      await platformApi.createTrainingJob({ name: `retry-${jobId.slice(0, 8)}`, model_base: 'llama-3.1-8b' })
      toast.success('Retry job created')
      fetchTrainingJobs()
    } catch { toast.error('Retry failed') }
  }

  async function handleExport() {
    if (!tenant) return
    try {
      const res = await platformApi.exportTrainingData({ tenant_id: tenant.id })
      const blob = new Blob([res.data], { type: 'application/jsonl' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = 'training_data.jsonl'; a.click()
      URL.revokeObjectURL(url)
      toast.success('Training data exported')
    } catch { toast.error('Export failed') }
  }

  async function handlePromote(modelId, version) {
    try {
      await platformApi.promoteModel(modelId, version, { tenant_id: tenant?.id })
      toast.success(`Version ${version} promoted to production`)
      fetchModels(); fetchActiveModels()
    } catch { toast.error('Promotion failed') }
  }

  async function handleRollback(modelId, version) {
    try {
      await platformApi.rollbackModel(modelId, version, { tenant_id: tenant?.id })
      toast.success(`Rolled back to version ${version}`)
      fetchModels(); fetchActiveModels()
    } catch { toast.error('Rollback failed') }
  }

  async function handleCompare(e) {
    e.preventDefault()
    try {
      const res = await platformApi.compareModels({ tenant_id: tenant?.id, model_id: compareForm.model_id, version_a: compareForm.version_a, version_b: compareForm.version_b })
      setCompareResult(res.data)
    } catch { toast.error('Comparison failed') }
  }

  async function handleFetchAuditLog(modelId) {
    setAuditModelId(modelId)
    try {
      const res = await platformApi.getModelAuditLog?.(modelId, { tenant_id: tenant?.id })
      setAuditLog(Array.isArray(res.data) ? res.data : [])
    } catch { setAuditLog([]) }
  }

  async function handleCreateProfile(e) {
    e.preventDefault()
    try {
      await platformApi.createVoiceProfile({ speaker_name: profileForm.speaker_name })
      toast.success('Voice profile created')
      setShowCreateProfile(false)
      setProfileForm({ speaker_name: '' })
      fetchVoiceProfiles()
    } catch (err) { toast.error(err.response?.data?.detail || 'Failed to create profile') }
  }

  async function handleIdentify(data) {
    try {
      const res = await platformApi.identifySpeaker(data)
      setIdentifyResult(res.data)
    } catch { toast.error('Identification failed') }
  }

  async function handleDetectEmotion(data) {
    try {
      const res = await platformApi.detectEmotion(data)
      setEmotionResult(res.data)
    } catch { toast.error('Emotion detection failed') }
  }

  async function handleFetchEmotionTrends(callId) {
    try {
      const res = await platformApi.getEmotionTrends(callId)
      setEmotionTrends(Array.isArray(res.data) ? res.data : [])
    } catch { toast.error('Failed to fetch trends') }
  }

  async function handleExpandDataset(ds) {
    if (expandedDataset?.id === ds.id) { setExpandedDataset(null); setDatasetTurns([]); return }
    setExpandedDataset(ds)
    try {
      const res = await platformApi.listTurns(ds.id, { limit: 50, offset: 0 })
      setDatasetTurns(Array.isArray(res.data) ? res.data : [])
    } catch { setDatasetTurns([]) }
  }

  async function handleExportDataset(ds) {
    try {
      const res = await platformApi.listTurns(ds.id, { limit: 5000, offset: 0 })
      const turns = Array.isArray(res.data) ? res.data : []
      const blob = new Blob([JSON.stringify(turns, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = `${ds.name}_v${ds.version}.json`; a.click()
      URL.revokeObjectURL(url)
      toast.success('Dataset exported')
    } catch { toast.error('Export failed') }
  }

  async function handleBrowseTurns(datasetId) {
    setSelectedLabelDataset(datasetId)
    try {
      const res = await platformApi.listTurns(datasetId, { limit: 200, offset: 0 })
      setBrowseTurns(Array.isArray(res.data) ? res.data : [])
      const labelRes = await Promise.all(
        (Array.isArray(res.data) ? res.data : []).slice(0, 10).map(t =>
          platformApi.listLabels(t.id).then(r => r.data || []).catch(() => [])
        )
      )
      const counts = {}
      labelRes.flat().forEach(l => { counts[l.label_type] = (counts[l.label_type] || 0) + 1 })
      setLabelStats(counts)
    } catch { setBrowseTurns([]) }
  }

  async function handleLabelSubmit(e) {
    e.preventDefault()
    try {
      await platformApi.createLabel({ turn_id: labelForm.turn_id, label_type: labelForm.label_type, label_value: labelForm.label_value, confidence: labelForm.confidence, notes: labelForm.notes })
      toast.success('Label saved')
      setLabelForm({ turn_id: '', label_type: 'intent', label_value: '', confidence: 1.0, notes: '' })
      if (selectedLabelDataset) handleBrowseTurns(selectedLabelDataset)
    } catch { toast.error('Failed to save label') }
  }

  function closeOnboarding() {
    setShowOnboarding(false)
    localStorage.setItem('ai-platform-tour-done', 'true')
  }

  const filteredModels = useMemo(() => {
    let filtered = models
    if (modelFamilyFilter) filtered = filtered.filter(m => m.model_type === modelFamilyFilter)
    if (globalSearch) filtered = filtered.filter(m => m.name?.toLowerCase().includes(globalSearch.toLowerCase()))
    return filtered
  }, [models, modelFamilyFilter, globalSearch])

  const PAGE_SIZE = 20
  const paginatedModels = filteredModels.slice(modelsPage * PAGE_SIZE, (modelsPage + 1) * PAGE_SIZE)
  const paginatedDatasets = datasets.slice(datasetsPage * PAGE_SIZE, (datasetsPage + 1) * PAGE_SIZE)
  const paginatedTraining = trainingJobs.slice(trainingPage * PAGE_SIZE, (trainingPage + 1) * PAGE_SIZE)

  const apiLink = (method, path, body) =>
    `${method} https://api.aetherdesk.com/api/v1${path}${body ? ` -d '${JSON.stringify(body)}'` : ''}`

  return (
    <div className="space-y-4">
      <OnboardingTour open={showOnboarding} onClose={closeOnboarding} />
      <ConfirmDialog {...confirmAction} onCancel={() => setConfirmAction(null)} />

      {/* Header */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BrainCircuit className="h-6 w-6 text-accent" />
            <div>
              <h1 className="text-xl font-bold text-white tracking-tight">AI Platform</h1>
              <div className="flex items-center gap-2 text-xs text-white/30">
                <Home className="h-3 w-3" /> <ChevronRight className="h-3 w-3" /> AI Platform
                <span className="ml-2 inline-flex items-center gap-1 px-2 py-0.5 bg-white/5 rounded text-[10px] text-white/40 uppercase tracking-wider">
                  <Shield className="h-2.5 w-2.5" /> {userRole}
                </span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={() => setShowOnboarding(true)} className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-white/50 hover:text-white/80 bg-white/5 rounded-lg hover:bg-white/10 transition-colors">
              <Lightbulb className="h-3.5 w-3.5" /> Tour
            </button>
            <div className="flex items-center gap-1 bg-white/5 rounded-lg p-0.5">
              <button onClick={() => setViewMode('list')} className={`p-1.5 rounded ${viewMode === 'list' ? 'bg-white/10 text-white' : 'text-white/30 hover:text-white/60'}`}><List className="h-4 w-4" /></button>
              <button onClick={() => setViewMode('grid')} className={`p-1.5 rounded ${viewMode === 'grid' ? 'bg-white/10 text-white' : 'text-white/30 hover:text-white/60'}`}><Grid3X3 className="h-4 w-4" /></button>
            </div>
          </div>
        </div>
        <SearchBar value={globalSearch} onChange={setGlobalSearch} placeholder={`Search ${activeTab}...`} />
      </div>

      <SystemHealthBar />

      {/* Tabs */}
      <div className="flex gap-1 bg-white/5 rounded-lg p-1 overflow-x-auto">
        {visibleTabs.map(tab => {
          const Icon = tab.icon
          return (
            <button key={tab.id} onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-all whitespace-nowrap ${
                activeTab === tab.id ? 'bg-accent/20 text-accent shadow-sm' : 'text-white/40 hover:text-white/70'
              }`}>
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {/* ── TRAINING TAB ── */}
      {activeTab === 'training' && (
        <div className="space-y-4">
          {/* Metrics cards */}
          <div className="grid grid-cols-4 gap-4">
            <MetricCard icon={Cpu} label="Total Jobs" value={trainingJobs.length} color="text-blue-400" />
            <MetricCard icon={CheckCircle2} label="Completed" value={trainingJobs.filter(j => j.status === 'completed').length} color="text-green-400" />
            <MetricCard icon={Loader2} label="Active" value={trainingJobs.filter(j => j.status === 'training' || j.status === 'pending').length} color="text-yellow-400" />
            <MetricCard icon={AlertTriangle} label="Failed" value={trainingJobs.filter(j => j.status === 'failed').length} color="text-red-400" />
          </div>

          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-white">Training Pipelines</h2>
            <div className="flex gap-2">
              <button onClick={handleCollectData} disabled={loading} className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 rounded-lg text-xs text-white/70 transition-colors">
                <Download className="h-3.5 w-3.5" /> {loading ? 'Collecting...' : 'Collect Data'}
              </button>
              <button onClick={handleExport} className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 rounded-lg text-xs text-white/70 transition-colors">
                <FileText className="h-3.5 w-3.5" /> Export JSONL
              </button>
              {roleCfg.canDelete && (
                <button onClick={() => setShowCreateJob(true)} className="flex items-center gap-1.5 px-3 py-1.5 bg-accent/20 text-accent rounded-lg text-xs font-medium hover:bg-accent/30 transition-colors">
                  <Plus className="h-3.5 w-3.5" /> New Job
                </button>
              )}
            </div>
          </div>

          {trainingCount !== null && (
            <div className="bg-green-500/10 border border-green-500/20 rounded-lg px-4 py-2 text-sm text-green-400">
              Collected {trainingCount} training examples. Create a job to start training.
            </div>
          )}

          {paginatedTraining.length === 0 ? (
            <EmptyState icon={Cpu} title="No training jobs yet" description="Collect training data and create a training job to get started."
              action={<button onClick={() => setShowCreateJob(true)} className="px-4 py-2 bg-accent/20 text-accent rounded-lg text-sm font-medium hover:bg-accent/30"><Plus className="h-4 w-4 inline mr-1" />Create Job</button>} />
          ) : (
            <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
              <table className="w-full">
                <thead><tr className="border-b border-white/5 text-xs text-white/30 uppercase tracking-wider">
                  <th className="text-left px-4 py-3 font-medium">Name</th>
                  <th className="text-left px-4 py-3 font-medium">Model</th>
                  <th className="text-left px-4 py-3 font-medium">Status</th>
                  <th className="text-left px-4 py-3 font-medium">Progress</th>
                  <th className="text-left px-4 py-3 font-medium">Created</th>
                  <th className="text-right px-4 py-3 font-medium">Actions</th>
                </tr></thead>
                <tbody className="divide-y divide-white/5">
                  {paginatedTraining.map(job => (
                    <React.Fragment key={job.id}>
                      <tr className="hover:bg-white/[0.02] transition-colors cursor-pointer" onClick={() => setExpandedJobLogs(expandedJobLogs === job.id ? null : job.id)}>
                        <td className="px-4 py-3 text-sm text-white">{job.name}</td>
                        <td className="px-4 py-3 text-sm text-white/50">{job.model_base}</td>
                        <td className="px-4 py-3"><StatusBadge state={job.status} /></td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
                              <div className={`h-full rounded-full transition-all ${job.status === 'failed' ? 'bg-red-400' : job.status === 'completed' ? 'bg-green-400' : 'bg-accent'}`}
                                style={{ width: `${(job.progress || 0) * 100}%` }} />
                            </div>
                            <span className="text-xs text-white/40">{Math.round((job.progress || 0) * 100)}%</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-xs text-white/30">{job.created_at ? new Date(job.created_at).toLocaleDateString() : '—'}</td>
                        <td className="px-4 py-3 text-right">
                          <div className="flex items-center gap-1 justify-end">
                            {job.status === 'failed' && roleCfg.canDelete && (
                              <button onClick={(e) => { e.stopPropagation(); handleRetryJob(job.id) }} className="p-1.5 hover:bg-white/10 rounded" title="Retry"><RefreshCw className="h-3.5 w-3.5 text-yellow-400" /></button>
                            )}
                            <CopyButton text={apiLink('POST', '/ai-platform/training/jobs', { name: job.name, model_base: job.model_base })} />
                          </div>
                        </td>
                      </tr>
                      {expandedJobLogs === job.id && (
                        <tr><td colSpan={6} className="px-4 pb-3">
                          <JobLogViewer jobId={job.id} logs={[
                            { message: `Job ${job.name} started`, level: 'info', timestamp: job.created_at },
                            { message: `Using model ${job.model_base}`, level: 'info' },
                            { message: job.status === 'failed' ? `Error: ${job.error_message || 'Unknown'}` : `Status: ${job.status}`, level: job.status === 'failed' ? 'error' : 'info' },
                          ]} />
                        </td></tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pagination page={trainingPage} totalPages={Math.ceil(trainingJobs.length / PAGE_SIZE)} onPageChange={setTrainingPage} />

          {showCreateJob && (
            <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/40 backdrop-blur-sm">
              <div className="bg-[#1a2332] border border-white/10 rounded-xl p-6 max-w-lg w-full mx-4 shadow-2xl">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold text-white">Create Training Job</h2>
                  <button onClick={() => setShowCreateJob(false)} className="p-1 hover:bg-white/5 rounded"><X className="h-5 w-5 text-white/40" /></button>
                </div>
                <form onSubmit={handleCreateJob} className="space-y-4">
                  <div>
                    <label className="block text-sm text-white/70 mb-1">Job Name</label>
                    <input value={jobForm.name} onChange={e => setJobForm({...jobForm, name: e.target.value})} required className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white" placeholder="my-training-job" />
                  </div>
                  <div>
                    <label className="block text-sm text-white/70 mb-1">Base Model</label>
                    <input value={jobForm.model_base} onChange={e => setJobForm({...jobForm, model_base: e.target.value})} className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white" />
                  </div>
                  <div>
                    <label className="block text-sm text-white/70 mb-1">Hyperparameters (JSON) <TooltipLabel text="epochs, learning_rate, batch_size" /></label>
                    <textarea value={jobForm.hyperparams} onChange={e => setJobForm({...jobForm, hyperparams: e.target.value})} className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white font-mono h-24" />
                  </div>
                  <div className="flex justify-end gap-3">
                    <button type="button" onClick={() => setShowCreateJob(false)} className="px-4 py-2 text-sm text-white/50 hover:text-white">Cancel</button>
                    <button type="submit" className="px-4 py-2 bg-accent text-white rounded-lg text-sm font-medium hover:bg-accent/80">Create Job</button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── MODELS TAB ── */}
      {activeTab === 'models' && (
        <div className="space-y-4">
          <div className="grid grid-cols-4 gap-4">
            <MetricCard icon={Layers} label="Total Models" value={filteredModels.length} color="text-purple-400" />
            <MetricCard icon={Award} label="In Production" value={Object.keys(activeModels).length} color="text-amber-400" />
            <MetricCard icon={CheckCircle2} label="Approved" value={filteredModels.filter(m => m.status === 'approved' || m.status === 'production').length} color="text-green-400" />
            <MetricCard icon={GitBranch} label="Families" value={[...new Set(models.map(m => m.model_type))].length} color="text-blue-400" />
          </div>

          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-white">Model Registry</h2>
            <div className="flex items-center gap-2">
              <select value={modelFamilyFilter} onChange={e => setModelFamilyFilter(e.target.value)} className="px-3 py-1.5 bg-white/5 border border-white/10 rounded-lg text-xs text-white/70">
                <option value="">All Families</option>
                <option value="llm">LLM</option>
                <option value="classifier">Classifier</option>
                <option value="summarizer">Summarizer</option>
                <option value="sentiment">Sentiment</option>
                <option value="intent">Intent</option>
                <option value="voice_biometric">Voice Biometric</option>
              </select>
              {roleCfg.canPromote && (
                <button onClick={() => setShowRegisterModel(true)} className="flex items-center gap-1.5 px-3 py-1.5 bg-accent/20 text-accent rounded-lg text-xs font-medium hover:bg-accent/30">
                  <Plus className="h-3.5 w-3.5" /> Register
                </button>
              )}
            </div>
          </div>

          {paginatedModels.length === 0 ? (
            <EmptyState icon={Layers} title="No models registered" description="Train a model or register one manually."
              action={roleCfg.canPromote ? <button onClick={() => setShowRegisterModel(true)} className="px-4 py-2 bg-accent/20 text-accent rounded-lg text-sm font-medium hover:bg-accent/30"><Plus className="h-4 w-4 inline mr-1" /> Register Model</button> : null} />
          ) : (
            <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
              <table className="w-full">
                <thead><tr className="border-b border-white/5 text-xs text-white/30 uppercase tracking-wider">
                  <th className="text-left px-4 py-3 font-medium">Name</th>
                  <th className="text-left px-4 py-3 font-medium">Family</th>
                  <th className="text-left px-4 py-3 font-medium">Version</th>
                  <th className="text-left px-4 py-3 font-medium">State</th>
                  <th className="text-left px-4 py-3 font-medium">Created</th>
                  <th className="text-right px-4 py-3 font-medium">Actions</th>
                </tr></thead>
                <tbody className="divide-y divide-white/5">
                  {paginatedModels.map(model => (
                    <tr key={model.id} className="hover:bg-white/[0.02] transition-colors">
                      <td className="px-4 py-3">
                        <span className="text-sm text-white font-medium">{model.name}</span>
                        {activeModels?.[model.model_type]?.id === model.id && <span className="ml-2 text-[10px] bg-amber-400/20 text-amber-400 px-1.5 py-0.5 rounded-full">ACTIVE</span>}
                      </td>
                      <td className="px-4 py-3 text-sm text-white/50">{model.model_type}</td>
                      <td className="px-4 py-3 text-sm text-white/70 font-mono">{model.version}</td>
                      <td className="px-4 py-3"><StatusBadge state={model.status} /></td>
                      <td className="px-4 py-3 text-xs text-white/30">{model.created_at ? new Date(model.created_at).toLocaleDateString() : '—'}</td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center gap-1 justify-end">
                          <button onClick={() => { setExpandedModelMetrics(expandedModelMetrics === model.id ? null : model.id); handleFetchAuditLog(model.id) }}
                            className="p-1.5 hover:bg-white/10 rounded" title="Details"><Eye className="h-3.5 w-3.5 text-white/50" /></button>
                          {roleCfg.canPromote && model.status === 'evaluated' && (
                            <button onClick={() => setConfirmAction({
                              open: true, title: 'Promote to Production?', message: `Promote ${model.name} v${model.version} to production?`,
                              onConfirm: () => handlePromote(model.id, model.version), destructive: false
                            })} className="p-1.5 hover:bg-white/10 rounded" title="Promote"><Award className="h-3.5 w-3.5 text-amber-400" /></button>
                          )}
                          {roleCfg.canDelete && model.status === 'production' && (
                            <button onClick={() => setConfirmAction({
                              open: true, title: 'Rollback?', message: `Rollback ${model.name} from production?`,
                              onConfirm: () => handleRollback(model.id, model.version), destructive: true
                            })} className="p-1.5 hover:bg-white/10 rounded" title="Rollback"><Undo2 className="h-3.5 w-3.5 text-red-400" /></button>
                          )}
                          <CopyButton text={apiLink('GET', `/ai-platform/models?name=${model.name}`)} />
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {expandedModelMetrics && (
            <div className="bg-white/5 border border-white/10 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-white mb-3">Model Details & Audit Log</h3>
              {auditLog && auditLog.length > 0 ? (
                <div className="space-y-1">
                  {auditLog.slice(0, 10).map((entry, i) => (
                    <div key={i} className="flex items-center gap-2 text-xs text-white/50 py-1">
                      <Clock className="h-3 w-3 text-white/20" />
                      <span className="text-white/30">{entry.timestamp || '—'}</span>
                      <span>{entry.action || entry.status}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-white/30 italic">No audit entries yet</p>
              )}
            </div>
          )}
          <Pagination page={modelsPage} totalPages={Math.ceil(filteredModels.length / PAGE_SIZE)} onPageChange={setModelsPage} />

          <RegisterModelWizard open={showRegisterModel} onClose={() => setShowRegisterModel(false)} onCreated={() => { fetchModels(); fetchActiveModels() }} />
        </div>
      )}

      {/* ── VOICE BIOMETRICS TAB ── */}
      {activeTab === 'voice' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-white">Voice Biometrics</h2>
            <button onClick={() => setShowCreateProfile(true)} className="flex items-center gap-1.5 px-3 py-1.5 bg-accent/20 text-accent rounded-lg text-xs font-medium hover:bg-accent/30">
              <Plus className="h-3.5 w-3.5" /> New Profile
            </button>
          </div>

          <div className="grid grid-cols-2 gap-6">
            {/* Speaker Profiles */}
            <div className="bg-white/5 border border-white/10 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-white mb-3">Speaker Profiles ({voiceProfiles.length})</h3>
              {voiceProfiles.length === 0 ? (
                <p className="text-xs text-white/30 italic">No profiles yet. Create one to identify speakers.</p>
              ) : (
                <div className="space-y-2">
                  {voiceProfiles.map(p => (
                    <div key={p.id} className="flex items-center justify-between px-3 py-2 bg-white/[0.03] rounded-lg">
                      <span className="text-sm text-white">{p.speaker_name}</span>
                      <span className="text-[10px] text-white/30">{new Date(p.created_at).toLocaleDateString()}</span>
                    </div>
                  ))}
                </div>
              )}
              {showCreateProfile && (
                <form onSubmit={handleCreateProfile} className="mt-4 p-3 bg-white/[0.03] rounded-lg space-y-3">
                  <input value={profileForm.speaker_name} onChange={e => setProfileForm({...profileForm, speaker_name: e.target.value})} placeholder="Speaker name" required
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white" />
                  <div className="flex justify-end gap-2">
                    <button type="button" onClick={() => setShowCreateProfile(false)} className="px-3 py-1.5 text-xs text-white/50 hover:text-white">Cancel</button>
                    <button type="submit" className="px-3 py-1.5 bg-accent text-white rounded-lg text-xs font-medium">Create</button>
                  </div>
                </form>
              )}
            </div>

            {/* Emotion Detection */}
            <div className="bg-white/5 border border-white/10 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-white mb-3">Emotion Detection</h3>
              <div className="space-y-3">
                <input placeholder="Call ID (optional)" className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white"
                  onChange={e => setLabelForm({...labelForm, turn_id: e.target.value})} />
                <div className="flex gap-2">
                  <button onClick={() => handleDetectEmotion({ call_id: labelForm.turn_id || undefined })}
                    className="px-3 py-1.5 bg-white/5 hover:bg-white/10 rounded-lg text-xs text-white/70"><Activity className="h-3.5 w-3.5 inline mr-1" />Detect</button>
                  <button onClick={() => handleFetchEmotionTrends(labelForm.turn_id)} className="px-3 py-1.5 bg-white/5 hover:bg-white/10 rounded-lg text-xs text-white/70"><BarChart3 className="h-3.5 w-3.5 inline mr-1" />Trends</button>
                </div>
                {emotionResult && (
                  <div className="p-3 bg-white/[0.03] rounded-lg">
                    <div className="flex items-center gap-2 mb-2">
                      <div className={`h-3 w-3 rounded-full ${EMOTION_COLORS[emotionResult.emotion] ? '' : 'bg-gray-400'}`} style={{ backgroundColor: EMOTION_COLORS[emotionResult.emotion] }} />
                      <span className="text-sm text-white font-medium capitalize">{emotionResult.emotion}</span>
                      <span className="text-xs text-white/40">{(emotionResult.confidence * 100).toFixed(0)}% confidence</span>
                    </div>
                    <div className="space-y-1">
                      {Object.entries(emotionResult.scores || {}).map(([emotion, score]) => (
                        <div key={emotion} className="flex items-center gap-2 text-xs">
                          <span className="w-16 text-white/50 capitalize">{emotion}</span>
                          <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden">
                            <div className="h-full rounded-full" style={{ width: `${score * 100}%`, backgroundColor: EMOTION_COLORS[emotion] || '#6366f1' }} />
                          </div>
                          <span className="w-8 text-right text-white/30">{(score * 100).toFixed(0)}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {emotionTrends.length > 0 && (
                  <div className="h-40">
                    <ResponsiveContainer>
                      <LineChart data={emotionTrends}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                        <XAxis dataKey="timestamp_ms" tick={false} />
                        <YAxis hide />
                        <Tooltip />
                        <Line type="monotone" dataKey="confidence" stroke="#6366f1" dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── DATASETS TAB ── */}
      {activeTab === 'datasets' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-white">Datasets</h2>
            <button onClick={() => setShowCreateDataset(true)} className="flex items-center gap-1.5 px-3 py-1.5 bg-accent/20 text-accent rounded-lg text-xs font-medium hover:bg-accent/30">
              <Plus className="h-3.5 w-3.5" /> New Dataset
            </button>
          </div>

          {paginatedDatasets.length === 0 ? (
            <EmptyState icon={Database} title="No datasets yet" description="Create a dataset from your call data to start training."
              action={<button onClick={() => setShowCreateDataset(true)} className="px-4 py-2 bg-accent/20 text-accent rounded-lg text-sm font-medium hover:bg-accent/30"><Plus className="h-4 w-4 inline mr-1" /> Create Dataset</button>} />
          ) : (
            <div className="bg-white/5 border border-white/10 rounded-xl overflow-hidden">
              <table className="w-full">
                <thead><tr className="border-b border-white/5 text-xs text-white/30 uppercase tracking-wider">
                  <th className="text-left px-4 py-3 font-medium">Name</th>
                  <th className="text-left px-4 py-3 font-medium">Version</th>
                  <th className="text-left px-4 py-3 font-medium">Recipe</th>
                  <th className="text-left px-4 py-3 font-medium">Examples</th>
                  <th className="text-left px-4 py-3 font-medium">Quality</th>
                  <th className="text-left px-4 py-3 font-medium">Created</th>
                  <th className="text-right px-4 py-3 font-medium">Actions</th>
                </tr></thead>
                <tbody className="divide-y divide-white/5">
                  {paginatedDatasets.map(ds => (
                    <React.Fragment key={ds.id}>
                      <tr className="hover:bg-white/[0.02] transition-colors cursor-pointer" onClick={() => handleExpandDataset(ds)}>
                        <td className="px-4 py-3 text-sm text-white font-medium">{ds.name}</td>
                        <td className="px-4 py-3 text-sm text-white/50 font-mono">v{ds.version}</td>
                        <td className="px-4 py-3 text-sm">{ds.recipe_type === 'dialogue' ? <span className="text-blue-400">Dialogue</span> : ds.recipe_type === 'classification' ? <span className="text-green-400">Classification</span> : <span className="text-purple-400">Summarization</span>}</td>
                        <td className="px-4 py-3 text-sm text-white/70">{ds.total_examples || 0}</td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="flex-1 h-1.5 bg-white/10 rounded-full overflow-hidden max-w-[60px]">
                              <div className="h-full rounded-full bg-green-400" style={{ width: `${(ds.quality_score || 0) * 100}%` }} />
                            </div>
                            <span className="text-xs text-white/40">{((ds.quality_score || 0) * 100).toFixed(0)}%</span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-xs text-white/30">{ds.created_at ? new Date(ds.created_at).toLocaleDateString() : '—'}</td>
                        <td className="px-4 py-3 text-right" onClick={e => e.stopPropagation()}>
                          <div className="flex items-center gap-1 justify-end">
                            <button onClick={() => handleExportDataset(ds)} className="p-1.5 hover:bg-white/10 rounded" title="Export"><Download className="h-3.5 w-3.5 text-white/50" /></button>
                            <CopyButton text={apiLink('GET', `/ai-platform/datasets/${ds.id}`)} />
                            {expandedDataset?.id === ds.id ? <ChevronDown className="h-3.5 w-3.5 text-white/30" /> : <ChevronRight className="h-3.5 w-3.5 text-white/30" />}
                          </div>
                        </td>
                      </tr>
                      {expandedDataset?.id === ds.id && (
                        <tr><td colSpan={7} className="px-4 pb-4">
                          <div className="bg-white/[0.03] rounded-lg p-4 space-y-3">
                            <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider">Sample Turns</h4>
                            {datasetTurns.length === 0 ? (
                              <p className="text-xs text-white/30 italic">No turns found</p>
                            ) : (
                              <div className="space-y-2 max-h-48 overflow-y-auto">
                                {datasetTurns.slice(0, 10).map((turn, i) => (
                                  <div key={i} className="flex gap-3 text-xs">
                                    <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium ${turn.speaker === 'agent' ? 'bg-blue-500/20 text-blue-300' : 'bg-green-500/20 text-green-300'}`}>
                                      {turn.speaker}
                                    </span>
                                    <span className="text-white/60">{turn.text?.slice(0, 200)}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </td></tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pagination page={datasetsPage} totalPages={Math.ceil(datasets.length / PAGE_SIZE)} onPageChange={setDatasetsPage} />
          <CreateDatasetWizard open={showCreateDataset} onClose={() => setShowCreateDataset(false)} onCreated={fetchDatasets} tenant={tenant} />
        </div>
      )}

      {/* ── LABELING TAB ── */}
      {activeTab === 'labeling' && roleCfg.tabs.includes('labeling') && (
        <div className="space-y-4">
          <h2 className="text-base font-semibold text-white">QA Labeling</h2>
          {labelDatasets.length === 0 ? (
            <EmptyState icon={Tags} title="No datasets available" description="Create a dataset first to start labeling turns." />
          ) : (
            <div className="grid grid-cols-4 gap-4">
              {labelDatasets.slice(0, 4).map(ds => (
                <button key={ds.id} onClick={() => handleBrowseTurns(ds.id)}
                  className={`bg-white/5 border rounded-xl p-4 text-left hover:bg-white/[0.07] transition-colors ${selectedLabelDataset === ds.id ? 'border-accent/50 bg-accent/5' : 'border-white/10'}`}>
                  <h3 className="text-sm font-medium text-white mb-1">{ds.name}</h3>
                  <p className="text-xs text-white/30">{ds.total_examples || 0} turns</p>
                </button>
              ))}
            </div>
          )}

          {selectedLabelDataset && browseTurns.length > 0 && (
            <div className="grid grid-cols-3 gap-4">
              <div className="col-span-2 bg-white/5 border border-white/10 rounded-xl p-4">
                <h3 className="text-sm font-semibold text-white mb-3">Turns ({browseTurns.length})</h3>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {browseTurns.slice(0, 20).map((turn, i) => (
                    <div key={i}
                      onClick={() => setLabelForm({...labelForm, turn_id: turn.id, label_value: ''})}
                      className={`p-3 rounded-lg cursor-pointer text-xs transition-colors ${labelForm.turn_id === turn.id ? 'bg-accent/10 border border-accent/30' : 'bg-white/[0.03] hover:bg-white/[0.06]'}`}>
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`px-1 py-0.5 rounded text-[10px] font-medium ${turn.speaker === 'agent' ? 'bg-blue-500/20 text-blue-300' : 'bg-green-500/20 text-green-300'}`}>{turn.speaker}</span>
                        {turn.emotion && <span className="text-[10px] text-white/30 capitalize">Emotion: {turn.emotion}</span>}
                      </div>
                      <p className="text-white/60">{turn.text?.slice(0, 300)}</p>
                    </div>
                  ))}
                </div>
              </div>
              <div className="bg-white/5 border border-white/10 rounded-xl p-4">
                <h3 className="text-sm font-semibold text-white mb-3">Label This Turn</h3>
                <form onSubmit={handleLabelSubmit} className="space-y-3">
                  <div>
                    <label className="block text-xs text-white/50 mb-1">Label Type</label>
                    <select value={labelForm.label_type} onChange={e => setLabelForm({...labelForm, label_type: e.target.value})}
                      className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-xs text-white">
                      <option value="intent">Intent</option>
                      <option value="sentiment">Sentiment</option>
                      <option value="quality">Quality</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs text-white/50 mb-1">Value</label>
                    <input value={labelForm.label_value} onChange={e => setLabelForm({...labelForm, label_value: e.target.value})}
                      className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-xs text-white" placeholder={labelForm.label_type === 'intent' ? 'billing, support...' : 'positive, negative...'} />
                  </div>
                  <div>
                    <label className="block text-xs text-white/50 mb-1">Confidence</label>
                    <input type="range" min="0" max="1" step="0.1" value={labelForm.confidence}
                      onChange={e => setLabelForm({...labelForm, confidence: parseFloat(e.target.value)})}
                      className="w-full accent-accent" />
                    <span className="text-xs text-white/30">{Math.round(labelForm.confidence * 100)}%</span>
                  </div>
                  <div>
                    <label className="block text-xs text-white/50 mb-1">Notes</label>
                    <textarea value={labelForm.notes} onChange={e => setLabelForm({...labelForm, notes: e.target.value})}
                      className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-xs text-white h-16" />
                  </div>
                  <button type="submit" disabled={!labelForm.turn_id || !labelForm.label_value}
                    className="w-full px-3 py-2 bg-accent text-white rounded-lg text-xs font-medium hover:bg-accent/80 disabled:opacity-30 transition-colors">
                    Save Label
                  </button>
                </form>
                {Object.keys(labelStats).length > 0 && (
                  <div className="mt-4">
                    <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-2">Stats</h4>
                    {Object.entries(labelStats).map(([type, count]) => (
                      <div key={type} className="flex justify-between text-xs text-white/50 py-0.5">
                        <span className="capitalize">{type}</span>
                        <span>{count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── SYSTEM TAB ── */}
      {activeTab === 'system' && roleCfg.tabs.includes('system') && (
        <div className="space-y-4">
          <h2 className="text-base font-semibold text-white">System Settings</h2>
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-white/5 border border-white/10 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-white mb-3">Subsystem Health</h3>
              <div className="space-y-3">
                {[{name:'Data Pipeline',status:'healthy',icon:Database},{name:'Model Registry',status:'healthy',icon:Layers},{name:'Voice Biometrics',status:'healthy',icon:Mic2},{name:'GPU Queue',status:'idle',icon:Cloud}].map(s => (
                  <div key={s.name} className="flex items-center justify-between px-3 py-2 bg-white/[0.03] rounded-lg">
                    <div className="flex items-center gap-2">
                      {React.createElement(s.icon, { className: 'h-4 w-4 text-white/40' })}
                      <span className="text-sm text-white">{s.name}</span>
                    </div>
                    <span className={`text-xs font-medium ${s.status === 'healthy' ? 'text-green-400' : 'text-yellow-400'}`}>{s.status}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="bg-white/5 border border-white/10 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-white mb-3">Environment</h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between px-3 py-2 bg-white/[0.03] rounded-lg">
                  <span className="text-sm text-white">Deployment</span>
                  <span className="text-xs bg-amber-400/20 text-amber-400 px-2 py-0.5 rounded-full">Development</span>
                </div>
                <div className="flex items-center justify-between px-3 py-2 bg-white/[0.03] rounded-lg">
                  <span className="text-sm text-white">API Version</span>
                  <span className="text-xs text-white/50">v1</span>
                </div>
                <div className="flex items-center justify-between px-3 py-2 bg-white/[0.03] rounded-lg">
                  <span className="text-sm text-white">Storage</span>
                  <span className="text-xs text-white/50">SQLite (dev)</span>
                </div>
              </div>
            </div>
          </div>
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <h3 className="text-sm font-semibold text-white mb-3">Environment Overrides</h3>
            <div className="flex items-center gap-4">
              {['development', 'staging', 'production'].map(env => (
                <button key={env} className="px-4 py-2 bg-white/5 hover:bg-white/10 rounded-lg text-xs text-white/70 capitalize">{env}</button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}