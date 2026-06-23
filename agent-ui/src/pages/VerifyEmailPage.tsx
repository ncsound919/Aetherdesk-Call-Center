import { useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { api } from '../lib/api';

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');

  useEffect(() => {
    const token = searchParams.get('token') || localStorage.getItem('verification_token');
    if (token) {
      api.verifyEmail(token)
        .then(() => setStatus('success'))
        .catch(() => setStatus('error'));
    } else {
      setStatus('error');
    }
  }, []);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      <div className="w-full max-w-md p-8 bg-white/5 backdrop-blur-lg rounded-2xl border border-white/10 text-center">
        {status === 'loading' && <p className="text-white">Verifying email...</p>}
        {status === 'success' && (
          <>
            <h1 className="text-2xl font-bold text-white mb-4">Email Verified!</h1>
            <p className="text-gray-400 mb-6">Your email has been verified. You can now sign in.</p>
            <Link to="/login" className="inline-block px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg">Sign In</Link>
          </>
        )}
        {status === 'error' && (
          <>
            <h1 className="text-2xl font-bold text-white mb-4">Verification Failed</h1>
            <p className="text-gray-400 mb-6">The verification link is invalid or has expired.</p>
            <Link to="/signup" className="inline-block px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg">Sign Up Again</Link>
          </>
        )}
      </div>
    </div>
  );
}