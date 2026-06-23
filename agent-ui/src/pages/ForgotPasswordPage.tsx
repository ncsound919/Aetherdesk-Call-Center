import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    await api.forgotPassword(email);
    setSent(true);
    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      <div className="w-full max-w-md p-8 bg-white/5 backdrop-blur-lg rounded-2xl border border-white/10">
        <h1 className="text-2xl font-bold text-white text-center mb-4">Reset Password</h1>
        {sent ? (
          <p className="text-gray-400 text-center">If the email exists, a reset link has been sent.</p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              placeholder="Enter your email"
              className="w-full px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white focus:outline-none focus:border-purple-500" />
            <button type="submit" disabled={loading}
              className="w-full py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-600/50 text-white font-semibold rounded-lg">
              {loading ? 'Sending...' : 'Send Reset Link'}
            </button>
          </form>
        )}
        <p className="mt-4 text-center text-sm text-gray-400">
          <Link to="/login" className="text-purple-400 hover:text-purple-300">Back to Sign In</Link>
        </p>
      </div>
    </div>
  );
}