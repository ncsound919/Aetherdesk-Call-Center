import React, { useEffect, useState, useCallback } from 'react'
import { toast } from 'sonner'
import { Wand2, Plus, Save } from 'lucide-react'
import { adminApi } from '../../services/api'

const EMPTY_FORM = {
  slug: '', meta_title: '', meta_description: '', og_title: '', og_description: '',
  keywords: '', body: '', status: 'draft',
}

export default function SEOContentPage() {
  const [records, setRecords] = useState([])
  const [selected, setSelected] = useState(null)
  const [topic, setTopic] = useState('')
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    try {
      const { data } = await adminApi.listSEO()
      setRecords(data || [])
    } catch { setRecords([]) }
  }, [])

  useEffect(() => { load() }, [load])

  function openRecord(rec) {
    setSelected(rec)
    setForm({
      slug: rec.slug, meta_title: rec.meta_title || '', meta_description: rec.meta_description || '',
      og_title: rec.og_title || '', og_description: rec.og_description || '',
      keywords: rec.keywords || '', body: rec.body || '', status: rec.status || 'draft',
    })
  }

  function resetNew() {
    setSelected(null)
    setForm(EMPTY_FORM)
  }

  async function handleGenerate() {
    if (!topic) return toast.error('Enter a topic first')
    try {
      const { data } = await adminApi.generateSEO({ topic, audience: 'the Black community' })
      setForm((f) => ({
        ...f,
        meta_title: data.meta_title || f.meta_title,
        meta_description: data.meta_description || f.meta_description,
        og_title: data.og_title || f.og_title,
        og_description: data.og_description || f.og_description,
        keywords: data.keywords || f.keywords,
      }))
      toast.success('AI drafted SEO fields — review before saving')
    } catch { toast.error('Generation failed') }
  }

  async function handleSave() {
    if (!form.slug) return toast.error('Slug is required')
    setSaving(true)
    try {
      await adminApi.upsertSEO(form.slug, form)
      toast.success('Saved')
      load()
      setSelected({ ...selected, ...form })
    } catch { toast.error('Save failed') }
    finally { setSaving(false) }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black text-slate-900">SEO Content</h1>
        <p className="text-sm text-slate-500 mt-1">Manage metadata for overlay365.com pages. Published records are served to the site at build time.</p>
      </div>

      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-2xl border border-blue-100 p-4 flex items-center gap-3 flex-wrap">
        <Wand2 className="h-4 w-4 text-blue-500" />
        <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Topic for AI metadata, e.g. financial wellness" className="flex-1 min-w-40 px-3 py-2 rounded-xl border border-blue-200 text-sm" />
        <button type="button" onClick={handleGenerate} className="px-4 py-2 text-sm font-bold bg-blue-600 text-white rounded-xl hover:bg-blue-700">Generate</button>
        <button type="button" onClick={resetNew} className="flex items-center gap-2 px-4 py-2 text-sm font-bold bg-slate-900 text-white rounded-xl"><Plus className="h-4 w-4" /> New</button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-4">
          <p className="text-xs font-black uppercase tracking-widest text-slate-400 mb-3">Pages</p>
          <div className="space-y-1">
            {records.map((r) => (
              <button key={r.slug} type="button" onClick={() => openRecord(r)} className={`w-full text-left px-3 py-2.5 rounded-xl text-sm font-semibold ${selected?.slug === r.slug ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-50'}`}>
                <span>{r.slug}</span>
                <span className={`ml-2 text-[10px] font-bold uppercase ${r.status === 'published' ? 'text-green-500' : 'text-amber-500'}`}>{r.status}</span>
              </button>
            ))}
            {records.length === 0 && <p className="text-sm text-slate-400 px-3 py-4">No content records yet. Create one with "New".</p>}
          </div>
        </div>

        <div className="lg:col-span-3 bg-white rounded-2xl border border-slate-200 p-5 space-y-3">
          <p className="text-xs font-black uppercase tracking-widest text-slate-400">Edit</p>
          <input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} placeholder="slug (e.g. home, health)" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
          <input value={form.meta_title} onChange={(e) => setForm({ ...form, meta_title: e.target.value })} placeholder="Meta title (under 60 chars)" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
          <textarea value={form.meta_description} onChange={(e) => setForm({ ...form, meta_description: e.target.value })} placeholder="Meta description (under 160 chars)" rows={2} className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
          <div className="grid grid-cols-2 gap-3">
            <input value={form.og_title} onChange={(e) => setForm({ ...form, og_title: e.target.value })} placeholder="OG title" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            <input value={form.og_description} onChange={(e) => setForm({ ...form, og_description: e.target.value })} placeholder="OG description" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
          </div>
          <input value={form.keywords} onChange={(e) => setForm({ ...form, keywords: e.target.value })} placeholder="Keywords (comma separated)" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
          <textarea value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} placeholder="Page body content" rows={6} className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
          <div className="flex items-center gap-3">
            <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} className="px-3 py-2 rounded-xl border border-slate-200 text-sm bg-white">
              <option value="draft">Draft</option>
              <option value="published">Published</option>
            </select>
            <button type="button" onClick={handleSave} disabled={saving} className="flex items-center gap-2 px-4 py-2 text-sm font-bold bg-slate-900 text-white rounded-xl disabled:opacity-50"><Save className="h-4 w-4" /> Save</button>
          </div>
        </div>
      </div>
    </div>
  )
}
