import React, { useEffect, useState, useCallback } from 'react'
import { toast } from 'sonner'
import { Search, Plus } from 'lucide-react'
import { adminApi } from '../../services/api'

export default function CRMPage() {
  const [contacts, setContacts] = useState([])
  const [search, setSearch] = useState('')
  const [source, setSource] = useState('all')
  const [selected, setSelected] = useState(null)
  const [notes, setNotes] = useState([])
  const [noteText, setNoteText] = useState('')
  const [showDonor, setShowDonor] = useState(false)
  const [donor, setDonor] = useState({ name: '', email: '', phone: '', amount: '', tier: '' })
  const [savingNote, setSavingNote] = useState(false)

  const load = useCallback(async () => {
    try {
      const { data } = await adminApi.listContacts()
      setContacts(data || [])
    } catch { setContacts([]) }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = contacts.filter((c) => {
    const q = search.toLowerCase()
    const matchesQ = !q || `${c.name || ''} ${c.email || ''} ${c.phone || ''}`.toLowerCase().includes(q)
    const matchesSource = source === 'all' || c.source === source
    return matchesQ && matchesSource
  })

  async function openContact(c) {
    setSelected(c)
    try {
      const { data } = await adminApi.listNotes(c.source, c.id)
      setNotes(data || [])
    } catch { setNotes([]) }
  }

  async function addNote() {
    if (!noteText.trim()) return
    setSavingNote(true)
    try {
      await adminApi.addNote(selected.source, selected.id, noteText.trim())
      setNoteText('')
      const { data } = await adminApi.listNotes(selected.source, selected.id)
      setNotes(data || [])
    } catch { toast.error('Failed to add note') }
    finally { setSavingNote(false) }
  }

  async function createDonor() {
    try {
      await adminApi.createDonor({ ...donor, amount: Number(donor.amount || 0) })
      toast.success('Donor added')
      setShowDonor(false)
      setDonor({ name: '', email: '', phone: '', amount: '', tier: '' })
      load()
    } catch { toast.error('Failed to create donor') }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black text-slate-900">CRM</h1>
          <p className="text-sm text-slate-500 mt-1">Unified contacts — leads, donors, and signups. Select a row to view details and notes.</p>
        </div>
        <button type="button" onClick={() => setShowDonor(true)} className="flex items-center gap-2 px-4 py-2 text-sm font-bold bg-slate-900 text-white rounded-xl"><Plus className="h-4 w-4" /> Add Donor</button>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center flex-1 min-w-52 bg-white border border-slate-200 rounded-2xl px-3 py-2">
          <Search className="h-4 w-4 text-slate-400" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search name, email, phone" className="bg-transparent border-none text-sm ml-2 w-full focus:outline-none" />
        </div>
        <select value={source} onChange={(e) => setSource(e.target.value)} className="px-3 py-2 rounded-xl border border-slate-200 text-sm bg-white">
          <option value="all">All sources</option>
          <option value="lead">Leads</option>
          <option value="donor">Donors</option>
          <option value="signup">Signups</option>
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3 bg-white rounded-2xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-[10px] uppercase tracking-widest text-slate-400">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Phone</th>
                <th className="px-4 py-3">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {filtered.map((c) => (
                <tr key={`${c.source}-${c.id}`} onClick={() => openContact(c)} className="cursor-pointer hover:bg-slate-50">
                  <td className="px-4 py-3 font-semibold text-slate-900">{c.name || '—'}</td>
                  <td className="px-4 py-3 text-slate-500">{c.email || '—'}</td>
                  <td className="px-4 py-3 text-slate-500">{c.phone || '—'}</td>
                  <td className="px-4 py-3"><span className="px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-slate-100 text-slate-600">{c.source}</span></td>
                </tr>
              ))}
              {filtered.length === 0 && <tr><td colSpan="4" className="px-4 py-8 text-center text-slate-400 text-sm">No contacts found.</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200 p-5">
          {selected ? (
            <>
              <p className="text-sm font-black text-slate-900">{selected.name || 'Contact'}</p>
              <p className="text-xs text-slate-500 mb-2">{selected.email || 'no email'} · {selected.phone || 'no phone'}</p>
              <span className="inline-block px-2 py-0.5 rounded-full text-[10px] font-bold uppercase bg-slate-100 text-slate-600 mb-2">{selected.source}</span>
              {selected.amount != null && <p className="text-sm font-bold text-green-600 mb-3">Donated: ${selected.amount}</p>}
              <div className="border-t border-slate-100 pt-3">
                <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-2">Notes</p>
                <div className="space-y-2 mb-3 max-h-40 overflow-y-auto">
                  {notes.map((n) => <p key={n.id} className="text-xs text-slate-600 bg-slate-50 rounded-lg px-3 py-2">{n.note}</p>)}
                  {notes.length === 0 && <p className="text-xs text-slate-400">No notes yet.</p>}
                </div>
                <div className="flex gap-2">
                  <input value={noteText} onChange={(e) => setNoteText(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && addNote()} placeholder="Add a note..." className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-sm" />
                  <button type="button" onClick={addNote} disabled={savingNote} className="px-3 py-2 text-xs font-bold bg-slate-900 text-white rounded-xl disabled:opacity-50">Add</button>
                </div>
              </div>
            </>
          ) : (
            <p className="text-sm text-slate-400 text-center py-10">Select a contact to view details and notes.</p>
          )}
        </div>
      </div>

      {showDonor && (
        <div className="fixed inset-0 bg-slate-900/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md space-y-3">
            <p className="text-sm font-black text-slate-900">Add Donor</p>
            {['name', 'email', 'phone', 'amount', 'tier'].map((k) => (
              <input key={k} value={donor[k]} onChange={(e) => setDonor({ ...donor, [k]: e.target.value })} placeholder={k} className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            ))}
            <div className="flex gap-2">
              <button type="button" onClick={createDonor} className="flex-1 px-4 py-2 text-sm font-bold bg-slate-900 text-white rounded-xl">Save</button>
              <button type="button" onClick={() => setShowDonor(false)} className="px-4 py-2 text-sm font-bold bg-slate-100 text-slate-700 rounded-xl">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
