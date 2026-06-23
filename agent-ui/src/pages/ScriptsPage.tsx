import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';

interface Script {
  id: string;
  name: string;
  content: any;
  variables: any[];
  is_active: boolean;
  version: number;
  created_at: string;
}

interface Template {
  id: string;
  name: string;
  description?: string;
  industry?: string;
}

export default function ScriptsPage() {
  const navigate = useNavigate();
  const [scripts, setScripts] = useState<Script[]>([]);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [industryFilter, setIndustryFilter] = useState('');

  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [scriptsRes, templatesRes]: any[] = await Promise.all([
        api.listScripts({ limit: 100 }),
        api.listTemplates({ industry: industryFilter || undefined, limit: 50 }),
      ]);
      setScripts(scriptsRes.items || []);
      setTemplates(templatesRes.items || []);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, [industryFilter]);

  const handleClone = async (templateId: string) => {
    try {
      await api.cloneTemplate(templateId);
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this script?')) return;
    try {
      await api.deleteScript(id);
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
            <h1 className="text-3xl font-bold text-white">Scripts</h1>
            <p className="text-gray-400 mt-1">Manage your call scripts and templates</p>
          </div>
          <button
            onClick={async () => {
              const name = prompt('Script name:');
              if (!name) return;
              try {
                const result: any = await api.createScript({
                  name,
                  content: { blocks: [] },
                  variables: [],
                });
                navigate(`/scripts/editor/${result.id}`);
              } catch (err: any) {
                setError(err.message);
              }
            }}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm"
          >
            + New Script
          </button>
        </header>

        {error && (
          <div className="mb-4 p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300 text-sm">{error}</div>
        )}

        <section className="mb-8">
          <div className="flex justify-between items-center mb-3">
            <h2 className="text-xl font-semibold text-white">Template Gallery</h2>
            <input
              type="text"
              placeholder="Filter by industry..."
              value={industryFilter}
              onChange={(e) => setIndustryFilter(e.target.value)}
              className="px-3 py-1 bg-white/5 border border-white/10 rounded text-white text-sm"
            />
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {templates.map((tpl) => (
              <div key={tpl.id} className="bg-white/5 backdrop-blur-lg rounded-xl border border-white/10 p-4">
                <h3 className="font-semibold text-white">{tpl.name}</h3>
                {tpl.description && <p className="text-gray-400 text-sm mt-1">{tpl.description}</p>}
                {tpl.industry && (
                  <span className="inline-block mt-2 px-2 py-1 bg-purple-600/20 text-purple-300 rounded text-xs">{tpl.industry}</span>
                )}
                <button
                  onClick={() => handleClone(tpl.id)}
                  className="mt-3 w-full py-2 bg-white/10 hover:bg-white/20 text-white rounded text-sm"
                >
                  Clone Template
                </button>
              </div>
            ))}
          </div>
        </section>

        <section>
          <h2 className="text-xl font-semibold text-white mb-3">Your Scripts</h2>
          <div className="bg-white/5 backdrop-blur-lg rounded-2xl border border-white/10 overflow-hidden">
            <table className="w-full">
              <thead className="bg-white/5">
                <tr className="text-left text-xs text-gray-400 uppercase">
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Version</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Variables</th>
                  <th className="px-4 py-3 w-32">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/10">
                {loading && (
                  <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-400">Loading...</td></tr>
                )}
                {!loading && scripts.length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-400">No scripts yet. Clone a template or create one from scratch.</td></tr>
                )}
                {!loading && scripts.map((script) => (
                  <tr key={script.id} className="hover:bg-white/5 text-sm">
                    <td className="px-4 py-3 text-white">{script.name}</td>
                    <td className="px-4 py-3 text-gray-300">v{script.version}</td>
                    <td className="px-4 py-3">
                      {script.is_active ? (
                        <span className="px-2 py-1 bg-green-600/30 text-green-300 rounded text-xs">Active</span>
                      ) : (
                        <span className="px-2 py-1 bg-white/10 text-gray-400 rounded text-xs">Draft</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{script.variables?.length || 0}</td>
                    <td className="px-4 py-3 flex gap-2">
                      <button onClick={() => navigate(`/scripts/editor/${script.id}`)} className="text-purple-400 hover:text-purple-300 text-xs">Edit</button>
                      <button onClick={() => handleDelete(script.id)} className="text-red-400 hover:text-red-300 text-xs">Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}