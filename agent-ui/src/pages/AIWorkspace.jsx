import React, { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../context/AuthContext'
import { aiAssistApi } from '../services/api'
import {
  BrainCircuit, CheckCircle2, XCircle, Lightbulb,
  BookOpen, Search, Plus, Trash2, Sparkles, Loader2
} from 'lucide-react'
import { toast } from 'sonner'

const TABS = [
  { key: 'validation', label: 'Validation', icon: CheckCircle2 },
  { key: 'agent-assist', label: 'Agent Assist', icon: Lightbulb },
  { key: 'knowledge', label: 'Knowledge Base', icon: BookOpen },
]

export default function AIWorkspace() {
  const { tenant } = useAuth()
  const [activeTab, setActiveTab] = useState('validation')
  const [schemas, setSchemas] = useState([])
  const [jsonInput, setJsonInput] = useState('')
  const [selectedSchema, setSelectedSchema] = useState('intent_classification')
  const [validationResult, setValidationResult] = useState(null)

  const [callId, setCallId] = useState('')
  const [transcriptSegment, setTranscriptSegment] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [suggestionsLoading, setSuggestionsLoading] = useState(false)

  const [kbQuery, setKbQuery] = useState('')
  const [kbResults, setKbResults] = useState([])
  const [showKbForm, setShowKbForm] = useState(false)
  const [kbForm, setKbForm] = useState({ title: '', content: '', tags: '', category: 'general' })
  const [kbLoading, setKbLoading] = useState(false)

  useEffect(() => {
    if (!tenant) return
    aiAssistApi.getSchemas().then(res => {
      if (res.data?.schemas) setSchemas(res.data.schemas)
    }).catch(() => {})
  }, [tenant])

  async function handleValidate() {
    if (!jsonInput) return
    setValidationResult(null)
    try {
      const res = await aiAssistApi.validate({ output: jsonInput, schema_name: selectedSchema })
      setValidationResult(res.data)
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Validation failed')
    }
  }

  async function handleAutoFix() {
    if (!jsonInput) return
    try {
      const res = await aiAssistApi.fixOutput({ output: jsonInput, error: '' })
      setJsonInput(res.data.fixed)
      toast.success('Output fixed')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Fix failed')
    }
  }

  async function handleGetSuggestions() {
    if (!transcriptSegment) return
    setSuggestionsLoading(true)
    setSuggestions([])
    try {
      const res = await aiAssistApi.getSuggestions({
        call_id: callId || undefined,
        transcript_segment: transcriptSegment,
        context: {},
      })
      setSuggestions(res.data.suggestions || [])
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to get suggestions')
    } finally {
      setSuggestionsLoading(false)
    }
  }

  async function handleKbSearch() {
    if (!kbQuery) return
    setKbLoading(true)
    try {
      const res = await aiAssistApi.searchKnowledge({ query: kbQuery, limit: 20 })
      setKbResults(res.data.results || [])
    } catch {
      setKbResults([])
    } finally {
      setKbLoading(false)
    }
  }

  async function handleCreateKb(e) {
    e.preventDefault()
    try {
      await aiAssistApi.createKnowledge({
        title: kbForm.title,
        content: kbForm.content,
        tags: kbForm.tags ? kbForm.tags.split(',').map(t => t.trim()) : [],
        category: kbForm.category,
      })
      toast.success('Knowledge snippet created')
      setShowKbForm(false)
      setKbForm({ title: '', content: '', tags: '', category: 'general' })
      if (kbQuery) handleKbSearch()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to create snippet')
    }
  }

  async function handleDeleteKb(id) {
    try {
      await aiAssistApi.deleteKnowledge(id)
      toast.success('Snippet deleted')
      setKbResults(prev => prev.filter(s => s.id !== id))
    } catch {
      toast.error('Failed to delete snippet')
    }
  }

  const intentActions = ['action', 'knowledge_article', 'script', 'detected_intent']
  const grouped = {}
  intentActions.forEach(type => { grouped[type] = suggestions.filter(s => s.type === type) })

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center gap-3 mb-6">
        <BrainCircuit className="h-6 w-6 text-accent" />
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">AI Workspace</h1>
          <p className="text-sm text-ink-muted mt-0.5">Structured output validation and agent assistance</p>
        </div>
      </div>

      <div className="flex gap-1 mb-6 border-b border-hairline">
        {TABS.map(tab => {
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

      {activeTab === 'validation' && (
        <div className="space-y-6">
          <div className="card p-6">
            <label className="block text-sm font-medium text-ink mb-2">JSON Schema</label>
            <select
              value={selectedSchema}
              onChange={e => setSelectedSchema(e.target.value)}
              className="input-field mb-4"
            >
              {schemas.map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <label className="block text-sm font-medium text-ink mb-2">LLM Output (JSON)</label>
            <textarea
              value={jsonInput}
              onChange={e => setJsonInput(e.target.value)}
              rows={8}
              className="input-field font-mono text-sm mb-4"
              placeholder='{"intent": "billing_invoice", "confidence": 0.95}'
            />
            <div className="flex gap-3">
              <button onClick={handleValidate} className="btn-primary">
                <CheckCircle2 className="h-4 w-4" /> Validate
              </button>
              <button onClick={handleAutoFix} className="btn-secondary">
                <Sparkles className="h-4 w-4" /> Auto-Fix
              </button>
            </div>
          </div>

          {validationResult && (
            <div className={`card p-6 ${validationResult.valid ? 'border-call-green' : 'border-red-200'}`}>
              <div className="flex items-center gap-2 mb-3">
                {validationResult.valid ? (
                  <CheckCircle2 className="h-5 w-5 text-call-green" />
                ) : (
                  <XCircle className="h-5 w-5 text-red-500" />
                )}
                <span className={`font-semibold ${validationResult.valid ? 'text-call-green' : 'text-red-500'}`}>
                  {validationResult.valid ? 'Valid' : 'Invalid'}
                </span>
              </div>
              {validationResult.errors?.length > 0 && (
                <ul className="space-y-1">
                  {validationResult.errors.map((err, i) => (
                    <li key={i} className="text-sm text-red-600 flex items-start gap-2">
                      <XCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                      {err}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      {activeTab === 'agent-assist' && (
        <div className="space-y-6">
          <div className="card p-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Call ID (optional)</label>
                <input
                  type="text"
                  value={callId}
                  onChange={e => setCallId(e.target.value)}
                  className="input-field"
                  placeholder="CALL-001"
                />
              </div>
            </div>
            <div className="mb-4">
              <label className="block text-sm font-medium text-ink mb-1.5">Transcript Segment</label>
              <textarea
                value={transcriptSegment}
                onChange={e => setTranscriptSegment(e.target.value)}
                rows={4}
                className="input-field"
                placeholder="I need help with my bill, I was charged twice..."
              />
            </div>
            <button onClick={handleGetSuggestions} disabled={suggestionsLoading} className="btn-primary">
              {suggestionsLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Lightbulb className="h-4 w-4" />}
              Get Suggestions
            </button>
          </div>

          {grouped.detected_intent?.length > 0 && (
            <div className="card p-4">
              <div className="flex items-center gap-2 text-sm text-ink-muted mb-1">
                <BrainCircuit className="h-4 w-4" /> Detected Intent
              </div>
              <p className="text-lg font-semibold text-ink capitalize">
                {grouped.detected_intent[0].intent?.replace(/_/g, ' ')}
              </p>
            </div>
          )}

          {grouped.action?.length > 0 && (
            <div className="card p-6">
              <h3 className="text-sm font-medium text-ink mb-3 flex items-center gap-2">
                <Lightbulb className="h-4 w-4 text-accent" /> Suggested Actions
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {grouped.action.map((s, i) => (
                  <div key={i} className="flex items-center justify-between p-3 rounded-lg border border-hairline">
                    <div>
                      <p className="text-sm font-medium text-ink">{s.label}</p>
                      <p className="text-xs text-ink-muted">{s.action}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                        s.confidence >= 0.8 ? 'bg-call-green-soft text-call-green' :
                        s.confidence >= 0.5 ? 'bg-call-amber-soft text-telecom-amber' :
                        'bg-surface-subtle text-ink-muted'
                      }`}>
                        {(s.confidence * 100).toFixed(0)}%
                      </span>
                      <button className="p-1 rounded hover:bg-surface-hover text-ink-muted hover:text-accent">
                        <CheckCircle2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {grouped.knowledge_article?.length > 0 && (
            <div className="card p-6">
              <h3 className="text-sm font-medium text-ink mb-3 flex items-center gap-2">
                <BookOpen className="h-4 w-4 text-accent" /> Knowledge Articles
              </h3>
              <div className="space-y-3">
                {grouped.knowledge_article.map((s, i) => (
                  <div key={i} className="p-3 rounded-lg border border-hairline">
                    <div className="flex items-start justify-between">
                      <p className="text-sm font-medium text-ink">{s.title}</p>
                      <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-accent-soft text-accent">
                        {(s.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <p className="text-xs text-ink-muted mt-1 line-clamp-2">{s.content}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {grouped.script?.length > 0 && (
            <div className="card p-6">
              <h3 className="text-sm font-medium text-ink mb-3 flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-accent" /> Script Snippet
              </h3>
              {grouped.script.map((s, i) => (
                <div key={i} className="p-3 rounded-lg bg-surface-subtle border border-hairline">
                  <p className="text-sm text-ink italic">"{s.text}"</p>
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-xs text-ink-muted capitalize">{s.key}</span>
                    <button className="p-1 rounded hover:bg-surface-hover text-ink-muted hover:text-accent">
                      <CheckCircle2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {!suggestionsLoading && suggestions.length === 0 && (
            <div className="card p-12 text-center text-ink-muted">
              Enter a transcript segment and click Get Suggestions.
            </div>
          )}
        </div>
      )}

      {activeTab === 'knowledge' && (
        <div className="space-y-6">
          <div className="card p-6">
            <div className="flex gap-3">
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-ink-muted" />
                <input
                  type="text"
                  value={kbQuery}
                  onChange={e => setKbQuery(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleKbSearch()}
                  className="input-field pl-9"
                  placeholder="Search knowledge base..."
                />
              </div>
              <button onClick={handleKbSearch} disabled={kbLoading} className="btn-primary">
                {kbLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                Search
              </button>
              <button onClick={() => setShowKbForm(true)} className="btn-secondary">
                <Plus className="h-4 w-4" /> New
              </button>
            </div>
          </div>

          {kbResults.length > 0 && (
            <div className="card overflow-hidden">
              <div className="divide-y divide-hairline">
                {kbResults.map(snippet => (
                  <div key={snippet.id} className="p-4 hover:bg-surface-hover transition-colors">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <h4 className="text-sm font-medium text-ink">{snippet.title}</h4>
                          <span className="text-xs px-2 py-0.5 rounded-full bg-surface-subtle text-ink-muted">
                            {snippet.category}
                          </span>
                        </div>
                        <p className="text-sm text-ink-muted line-clamp-2">{snippet.content}</p>
                        {snippet.tags && (
                          <div className="flex gap-1 mt-2">
                            {(typeof snippet.tags === 'string' ? JSON.parse(snippet.tags) : snippet.tags).map((tag, i) => (
                              <span key={i} className="text-xs px-1.5 py-0.5 rounded bg-accent-soft text-accent">{tag}</span>
                            ))}
                          </div>
                        )}
                      </div>
                      <button
                        onClick={() => handleDeleteKb(snippet.id)}
                        className="p-1.5 rounded-lg text-ink-muted hover:text-red-500 hover:bg-red-50 transition-colors ml-3"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {kbResults.length === 0 && !kbLoading && (
            <div className="card p-12 text-center text-ink-muted">
              Search the knowledge base or create a new snippet.
            </div>
          )}

          {showKbForm && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
              <div className="bg-white rounded-xl shadow-modal w-full max-w-lg mx-4 p-6">
                <div className="flex items-center justify-between mb-5">
                  <h2 className="text-lg font-semibold text-ink">Create Knowledge Snippet</h2>
                  <button onClick={() => setShowKbForm(false)} className="p-1.5 rounded-lg hover:bg-surface-hover">
                    <XCircle className="h-5 w-5 text-ink-muted" />
                  </button>
                </div>
                <form onSubmit={handleCreateKb} className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5">Title</label>
                    <input
                      type="text"
                      value={kbForm.title}
                      onChange={e => setKbForm({ ...kbForm, title: e.target.value })}
                      className="input-field"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5">Content</label>
                    <textarea
                      value={kbForm.content}
                      onChange={e => setKbForm({ ...kbForm, content: e.target.value })}
                      rows={4}
                      className="input-field"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5">Tags (comma-separated)</label>
                    <input
                      type="text"
                      value={kbForm.tags}
                      onChange={e => setKbForm({ ...kbForm, tags: e.target.value })}
                      className="input-field"
                      placeholder="billing, refund, policy"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-ink mb-1.5">Category</label>
                    <select
                      value={kbForm.category}
                      onChange={e => setKbForm({ ...kbForm, category: e.target.value })}
                      className="input-field"
                    >
                      <option value="general">General</option>
                      <option value="billing">Billing</option>
                      <option value="technical">Technical</option>
                      <option value="policy">Policy</option>
                      <option value="product">Product</option>
                    </select>
                  </div>
                  <div className="flex gap-3 pt-2">
                    <button type="button" onClick={() => setShowKbForm(false)} className="btn-secondary flex-1">Cancel</button>
                    <button type="submit" className="btn-primary flex-1">
                      <Plus className="h-4 w-4" /> Create
                    </button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
