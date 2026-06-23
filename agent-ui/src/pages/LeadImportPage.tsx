import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../lib/api';

const LEAD_FIELDS = ['phone', 'company_name', 'contact_name', 'first_name', 'last_name', 'email', 'industry', 'notes'];

export default function LeadImportPage() {
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const [step, setStep] = useState<'upload' | 'mapping' | 'done'>('upload');
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState('');
  const [headers, setHeaders] = useState<string[]>([]);
  const [rows, setRows] = useState<any[]>([]);
  const [preview, setPreview] = useState<any[]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<{ imported: number; errors: any[] } | null>(null);

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true);
    setError('');
    try {
      const data: any = await api.uploadLeadsCsv(f);
      setHeaders(data.headers || []);
      setPreview(data.preview || []);
      setRowCount(data.row_count || 0);
      // Try to auto-map common column names
      const autoMap: Record<string, string> = {};
      for (const col of data.headers || []) {
        const lower = col.toLowerCase();
        if (lower.includes('phone') || lower.includes('mobile') || lower.includes('tel')) autoMap[col] = 'phone';
        else if (lower.includes('company') || lower.includes('organization')) autoMap[col] = 'company_name';
        else if (lower.includes('first') && lower.includes('name')) autoMap[col] = 'first_name';
        else if (lower.includes('last') && lower.includes('name')) autoMap[col] = 'last_name';
        else if (lower.includes('email')) autoMap[col] = 'email';
        else if (lower.includes('industry') || lower.includes('sector')) autoMap[col] = 'industry';
        else if (lower.includes('contact') || lower.includes('name')) autoMap[col] = 'contact_name';
      }
      setMapping(autoMap);
      setStep('mapping');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setUploading(false);
    }
  };

  const handleImport = async () => {
    setImporting(true);
    setError('');
    try {
      // Need actual full row data, but upload endpoint returns preview only
      // So we'll re-parse the file client-side
      const file = fileRef.current?.files?.[0];
      if (!file) {
        throw new Error('File lost. Please re-upload.');
      }
      const text = await file.text();
      const lines = text.split(/\r?\n/).filter((l) => l.trim());
      const csvHeaders = lines[0].split(',').map((h) => h.trim().replace(/^"|"$/g, ''));
      const dataRows = lines.slice(1).map((line) => {
        const values = line.split(',').map((v) => v.trim().replace(/^"|"$/g, ''));
        const obj: any = {};
        csvHeaders.forEach((h, i) => {
          obj[h] = values[i] || '';
        });
        return obj;
      });

      const res: any = await api.importLeadsFromRows(mapping, dataRows);
      setResult(res);
      setStep('done');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 p-6">
      <div className="max-w-4xl mx-auto">
        <header className="mb-6">
          <button onClick={() => navigate('/leads')} className="text-gray-400 hover:text-white text-sm mb-2">← Back to leads</button>
          <h1 className="text-3xl font-bold text-white">Import Leads</h1>
          <p className="text-gray-400 mt-1">Upload a CSV file with your contacts</p>
        </header>

        {error && (
          <div className="mb-4 p-3 bg-red-500/20 border border-red-500/50 rounded-lg text-red-300 text-sm">{error}</div>
        )}

        {step === 'upload' && (
          <div className="bg-white/5 backdrop-blur-lg rounded-2xl border border-white/10 p-8">
            <div className="border-2 border-dashed border-white/20 rounded-lg p-12 text-center">
              <input
                ref={fileRef}
                type="file"
                accept=".csv"
                onChange={handleFile}
                className="hidden"
              />
              <button
                onClick={() => fileRef.current?.click()}
                disabled={uploading}
                className="px-6 py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-600/50 text-white rounded-lg"
              >
                {uploading ? 'Uploading...' : 'Choose CSV file'}
              </button>
              <p className="text-gray-400 text-sm mt-4">CSV files up to 10MB and 10,000 rows</p>
            </div>
          </div>
        )}

        {step === 'mapping' && (
          <div className="bg-white/5 backdrop-blur-lg rounded-2xl border border-white/10 p-8">
            <h2 className="text-xl font-semibold text-white mb-2">Map columns ({rowCount} rows found)</h2>
            <p className="text-gray-400 text-sm mb-6">Match CSV columns to lead fields</p>

            <div className="mb-6 overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-400">
                    {headers.slice(0, 4).map((h) => (
                      <th key={h} className="px-2 py-1 text-left">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.slice(0, 3).map((row, i) => (
                    <tr key={i}>
                      {headers.slice(0, 4).map((h) => (
                        <td key={h} className="px-2 py-1 text-gray-300">{row[h] || '-'}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="space-y-3 mb-6">
              {headers.map((col) => (
                <div key={col} className="flex items-center gap-3">
                  <span className="w-40 text-sm text-gray-300">{col}</span>
                  <select
                    value={mapping[col] || ''}
                    onChange={(e) => setMapping({ ...mapping, [col]: e.target.value })}
                    className="flex-1 px-3 py-2 bg-white/5 border border-white/10 rounded text-white text-sm"
                  >
                    <option value="">-- Skip --</option>
                    {LEAD_FIELDS.map((f) => (
                      <option key={f} value={f}>{f}</option>
                    ))}
                  </select>
                </div>
              ))}
            </div>

            <div className="flex gap-3">
              <button onClick={() => setStep('upload')} className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-lg">
                Back
              </button>
              <button
                onClick={handleImport}
                disabled={importing || !Object.values(mapping).includes('phone')}
                className="flex-1 py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-600/50 text-white font-semibold rounded-lg"
              >
                {importing ? 'Importing...' : 'Import Leads'}
              </button>
            </div>
            {!Object.values(mapping).includes('phone') && (
              <p className="text-yellow-400 text-sm mt-2">You must map at least one column to "phone"</p>
            )}
          </div>
        )}

        {step === 'done' && result && (
          <div className="bg-white/5 backdrop-blur-lg rounded-2xl border border-white/10 p-8 text-center">
            <h2 className="text-2xl font-bold text-white mb-4">Import complete!</h2>
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div className="bg-green-600/20 rounded-lg p-4">
                <div className="text-3xl font-bold text-green-300">{result.imported}</div>
                <div className="text-gray-300 text-sm">Imported</div>
              </div>
              <div className="bg-red-600/20 rounded-lg p-4">
                <div className="text-3xl font-bold text-red-300">{result.errors?.length || 0}</div>
                <div className="text-gray-300 text-sm">Errors</div>
              </div>
            </div>
            {result.errors && result.errors.length > 0 && (
              <div className="text-left mb-4">
                <details className="text-sm text-gray-300">
                  <summary className="cursor-pointer text-gray-400">View errors</summary>
                  <pre className="mt-2 p-3 bg-black/30 rounded text-xs overflow-auto max-h-40">
                    {JSON.stringify(result.errors.slice(0, 20), null, 2)}
                  </pre>
                </details>
              </div>
            )}
            <div className="flex gap-3 justify-center">
              <button onClick={() => navigate('/leads')} className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg">
                View leads
              </button>
              <button onClick={() => { setStep('upload'); setResult(null); }} className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-lg">
                Import another
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}