import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { useNavigate, Link } from 'react-router-dom'
import api from '../services/api'
import { PhoneCall, Eye, EyeOff, Loader2, Shield, Headphones, BarChart3 } from 'lucide-react'

export default function Login() {
  const { t } = useTranslation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPw, setShowPw] = useState(false)
  const [mfaPending, setMfaPending] = useState(false)
  const [mfaToken, setMfaToken] = useState('')
  const [mfaCode, setMfaCode] = useState('')
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await api.post('/auth/login', { email, password })
      if (res.data.mfa_required) {
        setMfaPending(true)
        setMfaToken(res.data.temp_token)
        setLoading(false)
        return
      }
      // Normal login success - call login to sync AuthContext state
      await login(email, password)
      navigate('/')
    } catch (err) {
      setError(err?.response?.data?.detail || t('auth.invalidCredentials'))
    } finally { setLoading(false) }
  }

  const handleMFASubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await api.post('/auth/mfa/login', { session_token: mfaToken, code: mfaCode })
      const { token, tenantId, userId, role } = res.data
      const name = res.data.name || email
      localStorage.setItem('token', token)
      localStorage.setItem('tenantId', tenantId)
      localStorage.setItem('userName', name)
      localStorage.setItem('userRole', role)
      localStorage.setItem('userEmail', email)
      localStorage.setItem('userId', userId)
      navigate('/')
    } catch (err) {
      setError(err?.response?.data?.detail || t('settings.invalidCode'))
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
            <span className="text-xl font-semibold text-white">{t('app.name')}</span>
          </div>

          {/* Hero */}
          <div className="flex-1 flex flex-col justify-center">
            <h1 className="text-4xl font-bold text-white leading-tight tracking-tight">
              {t('auth.enterpriseTitle')}
            </h1>
            <p className="mt-4 text-lg text-white/50 max-w-md leading-relaxed">
              {t('auth.enterpriseDesc')}
            </p>

            {/* Feature highlights */}
            <div className="mt-12 grid grid-cols-3 gap-6">
              {[
                { icon: Shield, label: t('auth.uptime'), sub: t('auth.uptimeSub') },
                { icon: Headphones, label: t('auth.responseTime'), sub: t('auth.responseTimeSub') },
                { icon: BarChart3, label: t('auth.concurrent'), sub: t('auth.concurrentSub') },
              ].map((f, i) => (
                <div key={i} className="text-center p-4 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:bg-white/[0.06] transition-colors">
                  <f.icon className="h-5 w-5 mx-auto mb-2 text-accent" />
                  <p className="text-sm font-semibold text-white">{f.label}</p>
                  <p className="text-xs text-white/30 mt-0.5">{f.sub}</p>
                </div>
              ))}
            </div>
          </div>

          <p className="text-white/20 text-xs">{t('auth.copyright')}</p>
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
            <span className="text-xl font-semibold text-ink">{t('app.name')}</span>
          </div>

          <div className="text-center mb-8">
            <h2 className="text-2xl font-bold text-ink tracking-tight">{t('auth.welcomeBack')}</h2>
            <p className="mt-1.5 text-sm text-ink-muted">{t('auth.signInSubtitle')}</p>
          </div>

          {error && (
            <div className="mb-6 bg-call-red-soft border border-call-red/20 text-call-red px-4 py-3 rounded-lg text-sm flex items-center gap-2 animate-slide-up">
              <div className="h-1.5 w-1.5 rounded-full bg-call-red live-dot-red shrink-0" />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5" role="form" aria-label={t('accessibility.loginForm')}>
            <div className="space-y-1.5">
              <label className="text-sm font-medium text-ink" htmlFor="login-email">{t('auth.email')}</label>
              <div className="relative group">
                <div className="absolute -inset-0.5 rounded-lg bg-gradient-to-r from-accent/0 via-accent/0 to-accent/0 group-focus-within:from-accent/10 group-focus-within:via-accent/5 group-focus-within:to-blue-500/10 transition-all duration-300 blur-sm" />
                <input id="login-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                  className="input-field relative" placeholder="admin@aetherdesk.com" autoFocus autoComplete="email" aria-label={t('auth.email')} />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-sm font-medium text-ink" htmlFor="login-password">{t('auth.password')}</label>
              <div className="relative">
                <input id="login-password" type={showPw ? 'text' : 'password'} required value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="input-field pr-10" placeholder={t('auth.enterPassword')} autoComplete="current-password" aria-label={t('auth.password')} />
                <button type="button" onClick={() => setShowPw(!showPw)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-subtle hover:text-ink-muted transition-colors" aria-label={showPw ? 'Hide password' : 'Show password'}>
                  {showPw ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-end">
              <Link to="/forgot-password" className="text-sm text-accent hover:text-accent-strong font-medium transition-colors">
                {t('auth.forgotPassword')}
              </Link>
            </div>

            <button type="submit" disabled={loading}
              className="btn-primary w-full py-2.5 glow-ring relative overflow-hidden group" aria-label={loading ? t('auth.signingIn') : t('auth.signIn')}>
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent shimmer-dark group-hover:opacity-100 opacity-0 transition-opacity" />
              {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {loading ? t('auth.signingIn') : t('auth.signIn')}
            </button>
          </form>

          {/* MFA Form */}
          {mfaPending && (
            <form onSubmit={handleMFASubmit} className="space-y-5 mt-6 animate-slide-up">
              <div className="text-center">
                <Shield className="h-10 w-10 text-accent mx-auto mb-2" />
                <h3 className="text-lg font-semibold text-ink">{t('auth.mfaVerification')}</h3>
                <p className="text-sm text-ink-muted">{t('auth.mfaCode')}</p>
              </div>
              <div>
                <input type="text" value={mfaCode} onChange={(e) => setMfaCode(e.target.value)}
                  placeholder="000000" maxLength={6}
                  className="input-field text-center text-lg tracking-widest" autoFocus />
              </div>
              <button type="submit" disabled={loading || mfaCode.length !== 6}
                className="btn-primary w-full py-2.5 glow-ring relative overflow-hidden group">
                <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/10 to-transparent shimmer-dark group-hover:opacity-100 opacity-0 transition-opacity" />
                {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Shield className="h-4 w-4" />}
                {loading ? t('auth.verifying') : t('auth.verifyCode')}
              </button>
              <button type="button" onClick={() => { setMfaPending(false); setMfaCode(''); setError('') }}
                className="w-full text-sm text-ink-muted hover:text-ink transition-colors">
                {t('auth.backToLogin')}
              </button>
            </form>
          )}

          <p className="mt-8 text-center text-sm text-ink-muted">
            {t('auth.noAccount')}{' '}
            <Link to="/signup" className="text-accent hover:text-accent-strong font-medium transition-colors">
              {t('auth.signUpLink')}
            </Link>
          </p>
        </div>
      </div>
    </div>
  )
}
