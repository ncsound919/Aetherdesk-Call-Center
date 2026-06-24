import React, { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import api from '../services/api'
import {
  Save, Loader2, ArrowLeft, FileText, BookOpen, Lightbulb,
  Plus, Trash2, GripVertical, Eye, Code, Sparkles
} from 'lucide-react'
import { toast } from 'sonner'

const TEMPLATES = [
  {
    id: 'sales-cold',
    name: 'Sales — Cold Call',
    businessType: 'sales',
    content: `## Opening (0-10s)
"Hi [Name], this is [Agent] from AetherDesk. I'm calling because we help companies like yours improve [specific pain point]."

## Qualification (10-45s)
- "Can I ask — how are you currently handling [problem]?"
- "What's your biggest challenge with [topic]?"
- "How much time does your team spend on [task]?"

## Value Proposition (45-90s)
"Here's what we've done for similar companies — [specific result]."
"Our platform reduces [metric] by [X]% while improving [other metric]."

## Objection Handling
- Price: "I understand budget is tight. Would it help if I showed you the ROI breakdown?"
- Timing: "When would be a better time to revisit this?"
- Not interested: "What would need to change for this to be a priority?"

## Close (90-120s)
"Based on what you've shared, I think [next step]. Does [day/time] work for a quick demo?"
  `,
  },
  {
    id: 'support-inbound',
    name: 'Support — Inbound',
    businessType: 'support',
    content: `## Greeting (0-5s)
"Thank you for calling AetherDesk support. My name is [Agent]. How can I help you today?"

## Empathy & Understanding (5-20s)
"I understand that's frustrating. Let me look into this for you right away."
"Thank you for bringing this to our attention. I'll make sure we get this resolved."

## Troubleshooting (20-120s)
"Let's start with a few quick checks..."
"Have you tried [step 1]? Let's do that together."
"Here's what I've found — [diagnosis]. Here's what we need to do."

## Resolution (120-180s)
"I've [action taken] on my end. Here's what you need to do on yours:"
- Step 1: [clear instruction]
- Step 2: [clear instruction]
- Step 3: [clear instruction]

## Closing
"Just to confirm — does everything look good now?"
"Is there anything else I can help you with today?"
"Thanks for your patience. Have a great day!"
  `,
  },
  {
    id: 'billing-dispute',
    name: 'Billing — Dispute Resolution',
    businessType: 'billing',
    content: `## Verification (0-15s)
"Thank you for calling AetherDesk billing. For security, can I verify your account?"
- Full name
- Account number or email
- Last 4 digits of card on file

## Understanding the Issue (15-45s)
"I see the charge you're referring to. Let me explain what happened:"
"Here's a breakdown of how this charge was calculated:"
"I understand why this looks confusing. Let me clarify..."

## Resolution Options (45-120s)
Here are the options available:
- **Credit**: "I can issue a credit of [amount] for this charge."
- **Payment Plan**: "Would a payment plan make this easier to manage?"
- **Correction**: "Let me correct this charge right now."

## Confirmation (120-150s)
"To confirm, I've [action taken]. You'll see [result] within [timeframe]."
"I'll send you a confirmation email with the details."

## Closing
"Is there anything else I can help you with?"
"Thank you for your patience. We appreciate your business."
  `,
  },
  {
    id: 'tech-troubleshoot',
    name: 'Technical — Troubleshooting',
    businessType: 'technical',
    content: `## Greeting & Verification (0-10s)
"Thank you for contacting AetherDesk technical support. This is [Agent]. Can I start with your account details?"

## Problem Assessment (10-30s)
"Can you describe what's happening? When did this start?"
"What error message are you seeing?"
"Has anything changed recently — software update, new device, configuration change?"

## Diagnostic Flow (30-120s)
### Step 1: Basic Checks
- "Is the device powered on and connected?"
- "Have you tried restarting?"
- "Are other services working?"

### Step 2: Specific Tests
- "Let's run a quick diagnostic..."
- "Can you try [specific test] and tell me what happens?"
- "Here's what I'm seeing on my end..."

## Resolution (120-240s)
"I've identified the issue. Here's the fix:"
"[Clear step-by-step instructions]"
"I'm going to make a change on my end. One moment please..."

## Verification
"Can you confirm that's working now?"
"The issue should be resolved. Let me know if it comes back."

## Closing
"Is there anything else I can help you with?"
"I'll send you a summary of what we did today."
  `,
  },
]

export default function ScriptEditorPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const isNew = !id || id === 'new'
  const [name, setName] = useState('')
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(!isNew)
  const [saving, setSaving] = useState(false)
  const [showTemplates, setShowTemplates] = useState(false)
  const [showPreview, setShowPreview] = useState(false)

  useEffect(() => {
    if (!isNew) {
      api.get(`/scripts/${id}`)
        .then((res) => { setName(res.data.name || ''); setContent(res.data.content || '') })
        .catch(() => { toast.error('Failed to load script'); navigate('/scripts') })
        .finally(() => setLoading(false))
    }
  }, [id])

  const handleSave = async () => {
    if (!name.trim()) { toast.error('Script name is required'); return }
    setSaving(true)
    try {
      if (isNew) {
        const res = await api.post('/scripts', { name, content })
        toast.success('Script created')
        navigate(`/scripts/${res.data.id}`)
      } else {
        await api.put(`/scripts/${id}`, { name, content })
        toast.success('Script saved')
      }
    } catch { toast.error('Failed to save script') }
    finally { setSaving(false) }
  }

  const applyTemplate = (tpl) => {
    setName(tpl.name)
    setContent(tpl.content)
    setShowTemplates(false)
    toast.success(`Template "${tpl.name}" applied`)
  }

  const insertSection = (type) => {
    const sections = {
      greeting: '\n## Greeting\n"Hello, this is [Agent] from AetherDesk. How can I help you today?"\n',
      question: '\n## Question\n"- Can you tell me more about that?"\n"- What specific issue are you experiencing?"\n',
      objection: '\n## Objection Handling\n"- I understand your concern. Here\'s how we address that..."\n"- Many customers feel that way initially, but what they find is..."\n',
      closing: '\n## Closing\n"Thank you for your time. Is there anything else I can help with?"\n',
    }
    setContent(prev => prev + '\n' + (sections[type] || ''))
  }

  if (loading) return <div className="p-6 max-w-5xl mx-auto"><div className="card p-12 text-center"><Loader2 className="h-6 w-6 animate-spin mx-auto text-ink-subtle" /></div></div>

  return (
    <div className="p-6 max-w-5xl mx-auto animate-slide-up">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/scripts')} className="btn-ghost p-2">
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-xl font-semibold text-ink tracking-tight">{isNew ? 'New Script' : 'Edit Script'}</h1>
            <p className="text-sm text-ink-muted">Build and format your call scripts</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setShowPreview(!showPreview)} className="btn-secondary">
            <Eye className="h-4 w-4" />
            {showPreview ? 'Edit' : 'Preview'}
          </button>
          <button onClick={handleSave} disabled={saving} className="btn-primary">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            {saving ? 'Saving...' : 'Save Script'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Sidebar */}
        <div className="lg:col-span-1 space-y-4">
          {/* Templates */}
          <div className="card p-4">
            <div className="flex items-center gap-2 mb-3">
              <BookOpen className="h-4 w-4 text-accent" />
              <h3 className="text-sm font-semibold text-ink">Templates</h3>
            </div>
            <div className="space-y-1.5">
              {TEMPLATES.map(tpl => (
                <button key={tpl.id} onClick={() => applyTemplate(tpl)}
                  className="w-full text-left p-2.5 rounded-lg text-sm hover:bg-surface-hover border border-transparent hover:border-hairline transition-all">
                  <p className="font-medium text-ink">{tpl.name}</p>
                  <p className="text-xs text-ink-muted mt-0.5 capitalize">{tpl.businessType}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Building Blocks */}
          <div className="card p-4">
            <div className="flex items-center gap-2 mb-3">
              <Plus className="h-4 w-4 text-call-green" />
              <h3 className="text-sm font-semibold text-ink">Building Blocks</h3>
            </div>
            <div className="space-y-1.5">
              {[
                { type: 'greeting', label: 'Greeting', desc: 'Opening statement' },
                { type: 'question', label: 'Question', desc: 'Discovery question' },
                { type: 'objection', label: 'Objection Handler', desc: 'Common rebuttal' },
                { type: 'closing', label: 'Closing', desc: 'Ending statement' },
              ].map(block => (
                <button key={block.type} onClick={() => insertSection(block.type)}
                  className="w-full text-left p-2.5 rounded-lg text-sm hover:bg-surface-hover border border-transparent hover:border-hairline transition-all">
                  <p className="font-medium text-ink">{block.label}</p>
                  <p className="text-xs text-ink-muted">{block.desc}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Tips */}
          <div className="card p-4 bg-gradient-to-br from-accent/5 to-purple-500/5">
            <div className="flex items-center gap-2 mb-2">
              <Lightbulb className="h-4 w-4 text-call-amber" />
              <h3 className="text-sm font-semibold text-ink">Script Tips</h3>
            </div>
            <ul className="space-y-2 text-xs text-ink-muted">
              <li>• Keep opening under 10 seconds</li>
              <li>• Use customer&apos;s name 2-3 times</li>
              <li>• Add pause points for responses</li>
              <li>• Include objection handlers</li>
              <li>• End with a clear CTA</li>
            </ul>
          </div>
        </div>

        {/* Editor */}
        <div className="lg:col-span-3">
          <div className="card overflow-hidden">
            <div className="p-4 border-b border-hairline">
              <input type="text" value={name} onChange={(e) => setName(e.target.value)}
                className="w-full text-lg font-semibold text-ink bg-transparent border-none outline-none placeholder:text-ink-subtle"
                placeholder="Script name..." />
            </div>
            {showPreview ? (
              <div className="p-6 min-h-[400px] prose prose-sm max-w-none">
                {content.split('\n').map((line, i) => {
                  if (line.startsWith('# ')) return <h1 key={i} className="text-lg font-bold text-ink mt-4 mb-2">{line.slice(2)}</h1>
                  if (line.startsWith('## ')) return <h2 key={i} className="text-base font-semibold text-ink mt-3 mb-1.5">{line.slice(3)}</h2>
                  if (line.startsWith('### ')) return <h3 key={i} className="text-sm font-semibold text-ink mt-2 mb-1">{line.slice(4)}</h3>
                  if (line.startsWith('- ')) return <li key={i} className="text-sm text-ink-muted ml-4">{line.slice(2)}</li>
                  if (line.startsWith('"')) return <p key={i} className="text-sm text-ink italic pl-3 border-l-2 border-accent/30 my-1">{line}</p>
                  if (line.trim() === '') return <br key={i} />
                  return <p key={i} className="text-sm text-ink-muted">{line}</p>
                })}
              </div>
            ) : (
              <textarea value={content} onChange={(e) => setContent(e.target.value)}
                className="w-full min-h-[400px] p-6 text-sm font-mono text-ink bg-white border-none outline-none resize-y placeholder:text-ink-subtle leading-relaxed"
                placeholder={`# Script Title\n\n## Section\n"Your script content here..."\n\n- Bullet point\n- Key action item\n\n## Closing\n"Thank you."`}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
