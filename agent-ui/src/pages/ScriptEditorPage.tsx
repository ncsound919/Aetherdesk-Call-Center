import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { api } from '../lib/api';

interface Block {
  type: string;
  text?: string;
  condition?: string;
  trigger?: string;
  response?: string;
}

interface Variable {
  name: string;
  type: string;
  source?: string;
  default?: string;
}

const BLOCK_TYPES = [
  { value: 'greeting', label: 'Greeting' },
  { value: 'pitch', label: 'Pitch' },
  { value: 'branch', label: 'Branch (conditional)' },
  { value: 'objection', label: 'Objection handler' },
  { value: 'close', label: 'Close / CTA' },
  { value: 'qualify', label: 'Qualify' },
];

export default function ScriptEditorPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [variables, setVariables] = useState<Variable[]>([]);
  const [isActive, setIsActive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [version, setVersion] = useState(1);

  useEffect(() => {
    if (!id) return;
    const load = async () => {
      try {
        const data: any = await api.getScript(id);
        setName(data.name || '');
        setBlocks(data.content?.blocks || []);
        setVariables(data.variables || []);
        setIsActive(data.is_active || false);
        setVersion(data.version || 1);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  const addBlock = (type: string) => {
    const newBlock: Block = { type, text: '' };
    if (type === 'branch') newBlock.condition = '';
    if (type === 'objection') newBlock.trigger = '';
    setBlocks([...blocks, newBlock]);
  };

  const updateBlock = (index: number, updates: Partial<Block>) => {
    setBlocks(blocks.map((b, i) => (i === index ? { ...b, ...updates } : b)));
  };

  const deleteBlock = (index: number) => {
    setBlocks(blocks.filter((_, i) => i !== index));
  };

  const moveBlock = (index: number, direction: -1 | 1) => {
    const newIdx = index + direction;
    if (newIdx < 0 || newIdx >= blocks.length) return;
    const next = [...blocks];
    [next[index], next[newIdx]] = [next[newIdx], next[index]];
    setBlocks(next);
  };

  const addVariable = () => {
    setVariables([...variables, { name: '', type: 'string', source: 'lead' }]);
  };

  const updateVariable = (index: number, updates: Partial<Variable>) => {
    setVariables(variables.map((v, i) => (i === index ? { ...v, ...updates } : v)));
  };

  const deleteVariable = (index: number) => {
    setVariables(variables.filter((_, i) => i !== index));
  };

  const handleSave = async () => {
    setSaving(true);
    setError('');
    try {
      await api.updateScript(id!, {
        name,
        content: { blocks },
        variables,
        is_active: isActive,
      });
      navigate('/scripts');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="min-h-screen flex items-center justify-center text-white">Loading...</div>;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 p-6">
      <div className="max-w-5xl mx-auto">
        <header className="mb-6 flex justify-between items-center">
          <div>
            <button onClick={() => navigate('/scripts')} className="text-gray-400 hover:text-white text-sm mb-2">← Back</button>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="text-3xl font-bold text-white bg-transparent border-b border-transparent hover:border-white/20 focus:border-purple-500 outline-none w-full"
              placeholder="Script name..."
            />
            <div className="text-gray-400 text-sm mt-1">v{version}</div>
          </div>
          <div className="flex gap-3">
            <label className="flex items-center gap-2 text-sm text-white cursor-pointer">
              <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} className="rounded" />
              Active
            </label>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-600/50 text-white rounded-lg text-sm"
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </header>

        {error && (
          <div className="mb-4 p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300 text-sm">{error}</div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <h2 className="text-lg font-semibold text-white">Blocks</h2>
            {blocks.length === 0 && (
              <div className="text-center py-8 bg-white/5 rounded-xl border border-dashed border-white/20 text-gray-400">
                No blocks yet. Add one below.
              </div>
            )}
            {blocks.map((block, i) => (
              <div key={i} className="bg-white/5 backdrop-blur-lg rounded-xl border border-white/10 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs uppercase tracking-wide text-purple-300 font-semibold">{block.type}</span>
                  <div className="flex gap-1">
                    <button onClick={() => moveBlock(i, -1)} disabled={i === 0} className="text-gray-400 hover:text-white disabled:opacity-30 px-1">↑</button>
                    <button onClick={() => moveBlock(i, 1)} disabled={i === blocks.length - 1} className="text-gray-400 hover:text-white disabled:opacity-30 px-1">↓</button>
                    <button onClick={() => deleteBlock(i)} className="text-red-400 hover:text-red-300 px-2">✕</button>
                  </div>
                </div>
                {(block.type === 'greeting' || block.type === 'pitch' || block.type === 'close' || block.type === 'qualify' || block.type === 'verify' || block.type === 'reschedule' || block.type === 'purpose' || block.type === 'intro' || block.type === 'diagnose' || block.type === 'options' || block.type === 'recap') && (
                  <textarea
                    rows={2}
                    value={block.text || ''}
                    onChange={(e) => updateBlock(i, { text: e.target.value })}
                    placeholder="What the agent says..."
                    className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white text-sm"
                  />
                )}
                {block.type === 'branch' && (
                  <>
                    <input
                      type="text"
                      value={block.condition || ''}
                      onChange={(e) => updateBlock(i, { condition: e.target.value })}
                      placeholder='Condition (e.g., industry == "tech")'
                      className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white text-sm font-mono mb-2"
                    />
                    <input
                      type="text"
                      value={block.text || ''}
                      onChange={(e) => updateBlock(i, { text: e.target.value })}
                      placeholder="Branch text..."
                      className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white text-sm"
                    />
                  </>
                )}
                {block.type === 'objection' && (
                  <>
                    <input
                      type="text"
                      value={block.trigger || ''}
                      onChange={(e) => updateBlock(i, { trigger: e.target.value })}
                      placeholder="Trigger phrase (e.g., 'not interested')"
                      className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white text-sm mb-2"
                    />
                    <textarea
                      rows={2}
                      value={block.response || ''}
                      onChange={(e) => updateBlock(i, { response: e.target.value })}
                      placeholder="Response to objection..."
                      className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded text-white text-sm"
                    />
                  </>
                )}
              </div>
            ))}
            <div className="flex flex-wrap gap-2">
              {BLOCK_TYPES.map((bt) => (
                <button
                  key={bt.value}
                  onClick={() => addBlock(bt.value)}
                  className="px-3 py-2 bg-white/10 hover:bg-white/20 text-white rounded text-sm"
                >
                  + {bt.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-white mb-4">Variables</h2>
            <div className="bg-white/5 backdrop-blur-lg rounded-xl border border-white/10 p-4 space-y-3">
              {variables.map((v, i) => (
                <div key={i} className="space-y-2 p-2 bg-white/5 rounded">
                  <input
                    type="text"
                    value={v.name}
                    onChange={(e) => updateVariable(i, { name: e.target.value })}
                    placeholder="name"
                    className="w-full px-2 py-1 bg-white/5 border border-white/10 rounded text-white text-xs font-mono"
                  />
                  <div className="flex gap-1">
                    <select
                      value={v.source}
                      onChange={(e) => updateVariable(i, { source: e.target.value })}
                      className="flex-1 px-2 py-1 bg-white/5 border border-white/10 rounded text-white text-xs"
                    >
                      <option value="lead">lead</option>
                      <option value="custom">custom</option>
                      <option value="call">call</option>
                    </select>
                    <button onClick={() => deleteVariable(i)} className="px-2 text-red-400 hover:text-red-300 text-xs">✕</button>
                  </div>
                </div>
              ))}
              <button onClick={addVariable} className="w-full py-2 bg-white/10 hover:bg-white/20 text-white rounded text-sm">
                + Add Variable
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}