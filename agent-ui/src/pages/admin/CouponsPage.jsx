import React, { useEffect, useState, useCallback } from 'react'
import { toast } from 'sonner'
import { Plus } from 'lucide-react'
import { adminApi } from '../../services/api'

const EMPTY = { code: '', type: 'percent', value: '', min_amount: '', max_uses: '', starts_at: '', ends_at: '' }

export default function CouponsPage() {
  const [coupons, setCoupons] = useState([])
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [creating, setCreating] = useState(false)
  const [disabling, setDisabling] = useState(null)

  const load = useCallback(async () => {
    try {
      const { data } = await adminApi.listCoupons()
      setCoupons(data || [])
    } catch { setCoupons([]) }
  }, [])

  useEffect(() => { load() }, [load])

  async function createCoupon() {
    if (!form.code) return toast.error('Code is required')
    if (!form.value || Number(form.value) <= 0) return toast.error('Value must be greater than zero')
    setCreating(true)
    try {
      await adminApi.createCoupon({
        code: form.code, type: form.type, value: Number(form.value),
        min_amount: form.min_amount ? Number(form.min_amount) : null,
        max_uses: form.max_uses ? Number(form.max_uses) : null,
        starts_at: form.starts_at || null, ends_at: form.ends_at || null,
      })
      toast.success('Coupon created')
      setShowForm(false)
      setForm(EMPTY)
      load()
    } catch { toast.error('Failed to create coupon') }
    finally { setCreating(false) }
  }

  async function disable(couponId) {
    setDisabling(couponId)
    try {
      await adminApi.disableCoupon(couponId)
      toast.success('Coupon disabled')
      load()
    } catch { toast.error('Failed to disable') }
    finally { setDisabling(null) }
  }

  const statusClasses = {
    active: 'bg-green-100 text-green-700',
    disabled: 'bg-slate-100 text-slate-500',
    local_only: 'bg-amber-100 text-amber-700',
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-black text-slate-900">Coupons</h1>
          <p className="text-sm text-slate-500 mt-1">Discount codes for subscriptions. Created as Stripe coupons when configured.</p>
        </div>
        <button type="button" onClick={() => setShowForm(true)} className="flex items-center gap-2 px-4 py-2 text-sm font-bold bg-slate-900 text-white rounded-xl"><Plus className="h-4 w-4" /> New Coupon</button>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-100 text-left text-[10px] uppercase tracking-widest text-slate-400">
              <th className="px-4 py-3">Code</th>
              <th className="px-4 py-3">Type</th>
              <th className="px-4 py-3">Value</th>
              <th className="px-4 py-3">Max Uses</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-50">
            {coupons.map((c) => (
              <tr key={c.id}>
                <td className="px-4 py-3 font-mono font-bold text-slate-900">{c.code}</td>
                <td className="px-4 py-3 text-slate-500">{c.type}</td>
                <td className="px-4 py-3 text-slate-500">{c.type === 'percent' ? `${c.value}%` : `$${c.value}`}</td>
                <td className="px-4 py-3 text-slate-500">{c.max_uses ?? '∞'}</td>
                <td className="px-4 py-3"><span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase ${statusClasses[c.status] || 'bg-amber-100 text-amber-700'}`}>{c.status}</span></td>
                <td className="px-4 py-3 text-right">
                  {c.status !== 'disabled' && (
                    <button type="button" onClick={() => disable(c.id)} disabled={disabling === c.id} className="text-xs font-bold text-rose-600 hover:underline disabled:opacity-50">Disable</button>
                  )}
                </td>
              </tr>
            ))}
            {coupons.length === 0 && <tr><td colSpan="6" className="px-4 py-8 text-center text-slate-400">No coupons yet.</td></tr>}
          </tbody>
        </table>
      </div>

      {showForm && (
        <div className="fixed inset-0 bg-slate-900/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md space-y-3">
            <p className="text-sm font-black text-slate-900">New Coupon</p>
            <input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="Code (e.g. WELCOME20)" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            <div className="flex gap-3">
              <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className="px-3 py-2 rounded-xl border border-slate-200 text-sm bg-white">
                <option value="percent">Percent</option>
                <option value="amount">Amount</option>
              </select>
              <input value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} placeholder="Value" type="number" min="0" step="any" className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <input value={form.min_amount} onChange={(e) => setForm({ ...form, min_amount: e.target.value })} placeholder="Min amount" type="number" min="0" step="any" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
              <input value={form.max_uses} onChange={(e) => setForm({ ...form, max_uses: e.target.value })} placeholder="Max uses" type="number" min="0" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            </div>
            <input value={form.ends_at} onChange={(e) => setForm({ ...form, ends_at: e.target.value })} placeholder="Ends at (optional)" type="datetime-local" className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm" />
            <div className="flex gap-2">
              <button type="button" onClick={createCoupon} disabled={creating} className="flex-1 px-4 py-2 text-sm font-bold bg-slate-900 text-white rounded-xl disabled:opacity-50">Create</button>
              <button type="button" onClick={() => setShowForm(false)} className="px-4 py-2 text-sm font-bold bg-slate-100 text-slate-700 rounded-xl">Cancel</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
