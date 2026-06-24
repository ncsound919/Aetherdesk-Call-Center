import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useNavigate, Link } from 'react-router-dom'
import { PhoneCall, Eye, EyeOff, Loader2, Shield, Headphones, BarChart3 } from 'lucide-react'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPw, setShowPw] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      await login(email, password)
      navigate('/')
    } catch (err) {
      setError(err?.response?.data?.detail || 'Invalid email or password')
    } finally { setLoading(false) }
  }

  return (
    <div className="min-h-screen flex">
      {/* Left - Brand Panel */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden bg-gradient-to-br from-[#0c1628] via-[#0f1d30] to-[#1e3a5f]">
        {/* Animated gradient orbs */}
        <div className="absolute -top-40 -right-40 w-96 h-96 rounded-full bg-accent/10 blur-3xl animate-pulse" style={{ animationDuration: '4s' }} />
        <div className="absolute -bottom-40 -left-40 w-80 h-80 rounded-full bg-blue-500/10 blur-3xl animate-pulse" style={{ animationDuration: '6s' }} />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full bg-gradient-to-br from-accent/5 to-blue-500/5 blur-3xl" />

        <div className="relative z-10 w-full flex flex-col px-16 py-12">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-accent to-blue-400 flex items-center justify-center shadow-lg shadow-accent/30">
              <PhoneCall className="h-5 w-5 text-white" />
            </div>
            <span className="text-xl font-semibold text-white">AetherDesk</span>
          </div>

          {/* Hero */}
          <div className="flex-1 flex flex-col justify-center">
            <h1 className="text-4xl font-bold text-white leading-tight tracking-tight">
              Enterprise call center
              <br />
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-blue-300">
                reimagined.
              </span>
            </h1>
            <p className="mt-4 text-lg text-white/50 max-w-md leading-relaxed">
              AI-powered digital call center with real-time analytics,
              intelligent routing, and seamless telecom integration.
            </p>

            {/* Feature highlights */}
            <div className="mt-12 grid grid-cols-3 gap-6">
              {[
                { icon: Shield, label: '99.9% Uptime', sub: 'Enterprise SLA' },
                { icon: Headphones, label: '&lt;1.5s Response', sub: 'AI-powered' },
                { icon: BarChart3, label: '10k+ Concurrent', sub: 'Scalable' },
              ].map((f, i) => (
                <div key={i} className="text-center p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.06] transition-colors">
                  <f.icon className="h-5 w-5 mx-auto mb-2 text-accent" />
                  <p className="text-sm font-semibold text-white">{f.label}</p>
                  <p className="text-xs text-white/30 mt-0.5">{f.sub}</p>
                </div>
              ))}
            </div>
          </div>

          <p className="text-white/20 text-xs">&copy; 2026 AetherDesk. All rights reserved.</p>
        </div>
      </div>

      {/* Right - Login Form */}
      <div className="flex-1 flex items-center justify-center px-6 py-12 bg-gradient-to-br from-canvas to-white relative overflow-hidden">
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-accent/20 to-transparent" />
        
        <div className="w-full max-w-sm animate-slide-up">
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-3 mb-10 justify-center">
            <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-accent to-blue-400 flex items-center justify-center shadow-lg">
              <PhoneCall className="h-5 w-5 text-white" />
            </div>
            <span className="text-xl font-semibold text-ink">AetherDesk</span>
          </div>

          <div className="text-center mb-8">
            <h2 className="text-2xl font-bold text-ink tracking-tight">Welcome back</h2>
            <p className="mt-1.5 text-sm text-ink-muted">Sign in to your call center dashboard</p>
          </div>

          {error && (
            <div className="mb-6 bg-call-red-soft border border-call-red/20 text-call-red px-4 py-3 rounded-lg text-sm flex items-center gap-2 animate-slide-up">
              <div className="h-1.5 w-1.5 rounded-full bg-call-red live-dot-red shrink-0" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-ink">Email</label>
              <div className="relative group">
                <div className="absolute -inset-0.5 rounded-lg bg-gradient-to-r from-accent/0 via-accent/0 to-accent/0 group-focus-within:from-accent/10 group-focus-within:via-accent/5 group-focus-within:to-blue-500/10 transition-all duration-300 blur-sm" />
                <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                  className="input-field relative" placeholder="admin@aetherdesk.com" autoFocus />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-ink">Password</label>
              <div className="relative">
                <input type={showPw ? 'text' : 'password'} required value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input-field pr-10" placeholder="Enter your password" />
                <button type="button" onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-subtle hover:text-ink-muted transition-colors">
                  {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-end">
              <Link to="/forgot-password" className="text-sm text-accent hover:text-accent-strong font-medium transition-colors">
                Forgot password?
              </Link>
            </div>

            <button type="submit" disabled={loading}
              className="btn-primary w-full py-2.5 glow-ring relative overflow-hidden group">
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent shimmer-dark group-hover:opacity-100 opacity-0 transition-opacity" />
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>

          <p className="mt-8 text-center text-sm text-ink-muted">
            Don&apos;t have an account?{' '}
            <Link to="/signup" className="text-accent hover:text-accent-strong font-medium transition-colors">
              Sign up
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
