import { useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { api } from '../lib/api';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const [password, setPassword] = useState('');
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const token = searchParams.get('token');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) { setError('Invalid reset link'); return; }
    setLoading(true);
    try {
      await api.resetPassword(token, password);
      setSuccess(true);
    } catch (err: any) {
      setError(err.message || 'Reset failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      <div className="w-full max-w-md p-8 bg-white/5 backdrop-blur-lg rounded-2xl border border-white/10">
        <h1 className="text-2xl font-bold text-white text-center mb-4">Set New Password</h1>
        {success ? (
          <div className="text-center">
            <p className="text-gray-400 mb-4">Password reset successfully.</p>
            <Link to="/login" className="inline-block px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg">Sign In</Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {error && <p className="text-red-400 text-sm">{error}</p>}
            <input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)}
              placeholder="New password (min 8 characters)"
              className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:border-purple-500" />
            <button type="submit" disabled={loading}
              className="w-full py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-600/50 text-white font-semibold rounded-lg">
              {loading ? 'Resetting...' : 'Reset Password'}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}