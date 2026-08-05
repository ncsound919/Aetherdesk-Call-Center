import React, { useState, useRef, useCallback, useEffect } from 'react'
import { toast } from 'sonner'
import { Wand2, Download, Save, Search, ImagePlus } from 'lucide-react'
import { adminApi } from '../../services/api'
import FlyerPreview from './flyers/FlyerPreview'
import { FLYER_TEMPLATES, FLYER_THEMES, FLYER_CATEGORIES } from './flyers/templates'
import { exportFlyerToPng } from './flyers/exportFlyer'

const EMPTY_FIELDS = {
  title: '', subtitle: '', ctaText: '', ctaUrl: '',
  date: '', venue: '', location: '', logo: '',
}

export default function FlyersPage() {
  const [category, setCategory] = useState('event')
  const [templateId, setTemplateId] = useState(FLYER_TEMPLATES[0].id)
  const [theme, setTheme] = useState(FLYER_TEMPLATES[0].theme)
  const [fields, setFields] = useState(EMPTY_FIELDS)
  const [topic, setTopic] = useState('')
  const [audience, setAudience] = useState('the Black community')
  const [saved, setSaved] = useState([])
  const [exporting, setExporting] = useState(false)
  const [saving, setSaving] = useState(false)
  const previewRef = useRef(null)

  const templates = FLYER_TEMPLATES.filter((t) => t.category === category)

  const loadSaved = useCallback(async () => {
    try {
      const { data } = await adminApi.listFlyers()
      setSaved(data || [])
    } catch { setSaved([]) }
  }, [])

  useEffect(() => { loadSaved() }, [loadSaved])

  const pickTemplate = useCallback((tpl) => {
    setTemplateId(tpl.id)
    setTheme(tpl.theme)
  }, [])

  const switchCategory = useCallback((id) => {
    setCategory(id)
    const first = FLYER_TEMPLATES.find((t) => t.category === id)
    if (first) {
      setTemplateId(first.id)
      setTheme(first.theme)
    }
  }, [])

  const setField = useCallback((key) => (e) => {
    setFields((f) => ({ ...f, [key]: e.target.value }))
  }, [])

  const handleGenerate = useCallback(async () => {
    try {
      const { data } = await adminApi.generateFlyerCopy({
        topic: topic || 'Overlay365 community event',
        audience,
        cta: fields.ctaText || 'Join us',
      })
      setFields((f) => ({
        ...f,
        title: data.title || f.title,
        subtitle: data.subtitle || f.subtitle,
        ctaText: data.cta_text || f.ctaText,
      }))
      toast.success('AI copy generated — review and edit before exporting')
    } catch {
      toast.error('AI copy generation failed')
    }
  }, [topic, audience, fields.ctaText])

  const handleLogoUpload = useCallback((e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => setFields((f) => ({ ...f, logo: reader.result }))
    reader.readAsDataURL(file)
  }, [])

  const handleExport = useCallback(async () => {
    setExporting(true)
    try {
      await exportFlyerToPng(previewRef.current, 'overlay365-flyer.png')
      toast.success('Flyer exported as PNG')
    } catch (err) {
      toast.error(err.message || 'Export failed')
    } finally {
      setExporting(false)
    }
  }, [])

  const handleSave = useCallback(async () => {
    setSaving(true)
    try {
      await adminApi.saveFlyer({
        template_id: templateId,
        title: fields.title,
        subtitle: fields.subtitle,
        cta_text: fields.ctaText,
        cta_url: fields.ctaUrl,
        theme,
        logo_url: fields.logo,
        config: { date: fields.date, venue: fields.venue, location: fields.location },
      })
      toast.success('Flyer saved')
      loadSaved()
    } catch {
      toast.error('Save failed')
    } finally {
      setSaving(false)
    }
  }, [templateId, theme, fields, loadSaved])

  const restoreSaved = useCallback((f) => {
    setTemplateId(f.template_id)
    setTheme(f.theme || 'midnight')
    setFields({
      title: f.title || '',
      subtitle: f.subtitle || '',
      ctaText: f.cta_text || '',
      ctaUrl: f.cta_url || '',
      date: f.config_json?.date || '',
      venue: f.config_json?.venue || '',
      location: f.config_json?.location || '',
      logo: f.logo_url || '',
    })
    const cat = FLYER_TEMPLATES.find((t) => t.id === f.template_id)?.category
    if (cat) setCategory(cat)
    toast.success('Flyer loaded')
  }, [])

  const themeColor = (th) => (th === 'midnight' ? '#05060a' : th === 'teal' ? '#0f766e' : th === 'gold' ? '#b45309' : '#0e7490')

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-slate-900">Flyer Studio</h1>
        <p className="text-sm text-slate-500 mt-1">Pick a template, customize, and export a print-ready PNG — no image API, works offline.</p>
      </div>

      {/* AI assist */}
      <div className="bg-gradient-to-r from-violet-50 to-fuchsia-50 rounded-2xl border border-violet-100 p-4">
        <div className="flex items-center gap-3 flex-wrap">
          <Wand2 className="h-4 w-4 text-violet-500" />
          <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Topic, e.g. community health fair" className="flex-1 min-w-40 px-3 py-2 rounded-xl border border-violet-200 text-sm" />
          <input value={audience} onChange={(e) => setAudience(e.target.value)} placeholder="Audience" className="w-44 px-3 py-2 rounded-xl border border-violet-200 text-sm" />
          <button type="button" onClick={handleGenerate} className="px-4 py-2 text-sm font-bold bg-violet-600 text-white rounded-xl hover:bg-violet-700">Generate Copy</button>
        </div>
      </div>

      {/* Category filter */}
      <div className="flex gap-2 flex-wrap">
        {FLYER_CATEGORIES.map((c) => (
          <button key={c.id} type="button" onClick={() => switchCategory(c.id)} className={`px-3 py-1.5 rounded-xl text-xs font-bold ${category === c.id ? 'bg-slate-900 text-white' : 'bg-white text-slate-600 border border-slate-200'}`}>{c.label}</button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Left: templates + fields */}
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-white rounded-2xl border border-slate-200 p-4 space-y-2">
            <p className="text-xs font-black uppercase tracking-widest text-slate-400">Templates</p>
            <div className="grid grid-cols-2 gap-2">
              {templates.map((t) => (
                <button key={t.id} type="button" onClick={() => pickTemplate(t)} className={`text-left px-3 py-3 rounded-xl border text-xs font-bold ${templateId === t.id ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 text-slate-700 hover:border-slate-400'}`}>{t.name}</button>
              ))}
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 p-4 space-y-3">
            <p className="text-xs font-black uppercase tracking-widest text-slate-400">Customize</p>
            <input value={fields.title} onChange={setField('title')} placeholder="Headline" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            <textarea value={fields.subtitle} onChange={setField('subtitle')} placeholder="Subtitle / message" rows={2} className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            <div className="grid grid-cols-2 gap-2">
              <input value={fields.date} onChange={setField('date')} placeholder="Date (e.g. Sat, Jun 20)" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
              <input value={fields.venue} onChange={setField('venue')} placeholder="Venue" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            </div>
            <input value={fields.location} onChange={setField('location')} placeholder="Location / address" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            <input value={fields.ctaText} onChange={setField('ctaText')} placeholder="CTA button text" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            <input value={fields.ctaUrl} onChange={setField('ctaUrl')} placeholder="CTA link (optional)" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-500">Theme:</span>
              {FLYER_THEMES.map((th) => (
                <button key={th} type="button" onClick={() => setTheme(th)} className={`h-7 w-7 rounded-full border-2 ${theme === th ? 'border-slate-900' : 'border-transparent'}`} style={{ background: themeColor(th) }} title={th} aria-label={`Theme ${th}`} />
              ))}
            </div>
            <label className="flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-sm text-slate-600 cursor-pointer hover:border-slate-400">
              <ImagePlus className="h-4 w-4" />
              {fields.logo ? 'Replace logo' : 'Upload logo'}
              <input type="file" accept="image/*" onChange={handleLogoUpload} className="hidden" />
            </label>
          </div>

          <div className="flex gap-2">
            <button type="button" onClick={handleExport} disabled={exporting} className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-bold bg-slate-900 text-white rounded-xl disabled:opacity-50">
              <Download className="h-4 w-4" /> {exporting ? 'Exporting…' : 'Export PNG'}
            </button>
            <button type="button" onClick={handleSave} disabled={saving} className="flex items-center gap-2 px-4 py-2.5 text-sm font-bold bg-white border border-slate-200 rounded-xl text-slate-700 disabled:opacity-50">
              <Save className="h-4 w-4" /> Save
            </button>
          </div>
        </div>

        {/* Right: live preview */}
        <div className="lg:col-span-3 bg-white rounded-2xl border border-slate-200 p-6 flex items-center justify-center overflow-auto">
          <FlyerPreview ref={previewRef} templateId={templateId} theme={theme} {...fields} />
        </div>
      </div>

      {/* Saved flyers */}
      {saved.length > 0 && (
        <div className="bg-white rounded-2xl border border-slate-200 p-4">
          <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">Saved Flyers</p>
          <div className="flex gap-2 flex-wrap">
            {saved.map((f) => (
              <button key={f.id} type="button" onClick={() => restoreSaved(f)} className="flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-xs font-bold text-slate-700 hover:border-slate-400">
                <Search className="h-3 w-3 text-slate-400" />
                {f.title || f.template_id}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
