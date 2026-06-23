import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';

interface Lead {
  id: string;
  phone: string;
  company_name?: string;
  contact_name?: string;
  first_name?: string;
  last_name?: string;
  email?: string;
  industry?: string;
  status: string;
  priority: number;
  score: number;
  created_at: string;
}

const LEAD_STATUSES = ['new', 'queued', 'calling', 'answered', 'voicemail', 'no_answer', 'interested', 'follow_up', 'converted', 'declined', 'do_not_call'];

export default function LeadsPage() {
  const navigate = useNavigate();
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [industryFilter, setIndustryFilter] = useState('');
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const result: any = await api.listLeads({
        status: statusFilter || undefined,
        industry: industryFilter || undefined,
        limit: 100,
      });
      setLeads(result.items || []);
      setSelected(new Set());
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [statusFilter, industryFilter]);

  const toggleSelect = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const toggleSelectAll = () => {
    if (selected.size === leads.length) setSelected(new Set());
    else setSelected(new Set(leads.map((l) => l.id)));
  };

  const handleBulkDelete = async () => {
    if (selected.size === 0) return;
    if (!confirm(`Delete ${selected.size} leads?`)) return;
    try {
      await api.bulkDeleteLeads(Array.from(selected));
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleBulkStatus = async (status: string) => {
    if (selected.size === 0) return;
    try {
      await api.bulkUpdateLeads(Array.from(selected), { status });
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this lead?')) return;
    try {
      await api.deleteLead(id);
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 p-6">
      <div className="max-w-7xl mx-auto">
        <header className="mb-6 flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-bold text-white">Leads</h1>
            <p className="text-gray-400 mt-1">Manage your call list</p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={() => navigate('/leads/import')}
              className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg text-sm"
            >
              Import CSV
            </button>
            <button
              onClick={async () => {
                const phone = prompt('Phone number:');
                if (!phone) return;
                try {
                  await api.createLead({ phone });
                  await load();
                } catch (err: any) {
                  setError(err.message);
                }
              }}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm"
            >
              + New Lead
            </button>
          </div>
        </header>

        {error && (
          <div className="mb-4 p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300 text-sm">{error}</div>
        )}

        <div className="bg-white/5 backdrop-blur-lg rounded-2xl border border-white/10 p-4 mb-4 flex gap-3">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 bg-white/5 border border-white/10 rounded text-white text-sm"
          >
            <option value="">All statuses</option>
            {LEAD_STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <input
            type="text"
            placeholder="Filter by industry..."
            value={industryFilter}
            onChange={(e) => setIndustryFilter(e.target.value)}
            className="px-3 py-2 bg-white/5 border border-white/10 rounded text-white text-sm flex-1"
          />
        </div>

        {selected.size > 0 && (
          <div className="bg-white/5 rounded-lg p-3 mb-4 flex items-center gap-3">
            <span className="text-white text-sm">{selected.size} selected</span>
            <select
              onChange={(e) => e.target.value && handleBulkStatus(e.target.value)}
              className="px-3 py-1 bg-white/10 text-white rounded text-sm"
              defaultValue=""
            >
              <option value="">Change status...</option>
              {LEAD_STATUSES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <button
              onClick={handleBulkDelete}
              className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white rounded text-sm"
            >
              Delete
            </button>
          </div>
        )}

        <div className="bg-white/5 backdrop-blur-lg rounded-2xl border border-white/10 overflow-hidden">
          <table className="w-full">
            <thead className="bg-white/5">
              <tr className="text-left text-xs text-gray-400 uppercase">
                <th className="px-4 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={leads.length > 0 && selected.size === leads.length}
                    onChange={toggleSelectAll}
                    className="rounded"
                  />
                </th>
                <th className="px-4 py-3">Phone</th>
                <th className="px-4 py-3">Company</th>
                <th className="px-4 py-3">Contact</th>
                <th className="px-4 py-3">Industry</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Score</th>
                <th className="px-4 py-3 w-20">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {loading && (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-400">Loading...</td></tr>
              )}
              {!loading && leads.length === 0 && (
                <tr><td colSpan={8} className="px-4 py-8 text-center text-gray-400">No leads yet. Import a CSV or add one manually.</td></tr>
              )}
              {!loading && leads.map((lead) => (
                <tr key={lead.id} className="hover:bg-white/5 text-sm">
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selected.has(lead.id)}
                      onChange={() => toggleSelect(lead.id)}
                      className="rounded"
                    />
                  </td>
                  <td className="px-4 py-3 text-white">{lead.phone}</td>
                  <td className="px-4 py-3 text-gray-300">{lead.company_name || '-'}</td>
                  <td className="px-4 py-3 text-gray-300">
                    {lead.first_name || lead.contact_name || '-'}
                    {lead.last_name ? ` ${lead.last_name}` : ''}
                  </td>
                  <td className="px-4 py-3 text-gray-400">{lead.industry || '-'}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded text-xs ${lead.status === 'interested' || lead.status === 'converted' ? 'bg-green-600/30 text-green-300' : lead.status === 'do_not_call' || lead.status === 'declined' ? 'bg-red-600/30 text-red-300' : 'bg-white/10 text-gray-300'}`}>
                      {lead.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-300">{lead.score?.toFixed(1) || '0.0'}</td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => handleDelete(lead.id)}
                      className="text-red-400 hover:text-red-300 text-xs"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}