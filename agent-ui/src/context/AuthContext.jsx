/**
 * AuthContext — Supabase-powered authentication provider
 *
 * Integrates Supabase Auth with React state, providing:
 *   - Email/password signup and login
 *   - Email verification flow
 *   - Password reset (forgot/reset)
 *   - Session persistence via Supabase's built-in storage
 *   - Automatic token refresh
 *   - Tenant mapping via custom auth metadata
 */

import React, { createContext, useContext, useEffect, useReducer, useCallback, useRef } from 'react'
import { supabase, db } from '../lib/supabase'
import { toast } from 'sonner'
import { z } from 'zod'

// ─── Response schemas ───────────────────────────────────────────────────────
const UserMetaSchema = z.object({
  userId:   z.string(),
  name:     z.string(),
  role:     z.string(),
  email:    z.string().email(),
  tenantId: z.string().optional(),
})

// ─── Auth reducer ────────────────────────────────────────────────────────────
const initialState = {
  user:      null,
  tenant:    null,
  loading:   true,
  isLoading: false,
  error:     null,
}

function authReducer(state, action) {
  switch (action.type) {
    case 'SESSION_INIT':
      return { ...state, loading: true }
    case 'SESSION_LOADED':
      return {
        ...state,
        user:    action.user,
        tenant:  action.tenant,
        loading: false,
        error:   null,
      }
    case 'SESSION_CLEARED':
      return { ...initialState, loading: false }
    case 'OP_START':
      return { ...state, isLoading: true, error: null }
    case 'OP_SUCCESS':
      return {
        ...state,
        user:      action.user,
        tenant:    action.tenant,
        isLoading: false,
        error:     null,
      }
    case 'OP_ERROR':
      return { ...state, isLoading: false, error: action.error }
    case 'LOGOUT':
      return { ...initialState, loading: false }
    default:
      return state
  }
}

// ─── Context ────────────────────────────────────────────────────────────────
const AuthContext = createContext(null)

// ─── Provider ───────────────────────────────────────────────────────────────
export function AuthProvider({ children }) {
  const [state, dispatch] = useReducer(authReducer, initialState)
  const listenerRef = useRef(null)

  // Parse Supabase session into our user shape
  const parseSession = useCallback(async (session) => {
    if (!session?.user) return null

    const sbUser = session.user
    const meta   = sbUser.user_metadata || {}

    // Fetch tenant from the tenants table if we have a tenant_id
    let tenantData = null
    if (meta.tenant_id) {
      const { data } = await db.tenants()
        .select('id, name')
        .eq('id', meta.tenant_id)
        .single()
      tenantData = data
    }

    const user = UserMetaSchema.parse({
      userId:   sbUser.id,
      email:    sbUser.email,
      name:     meta.full_name || sbUser.email?.split('@')[0] || 'User',
      role:     meta.role || 'agent',
      tenantId: meta.tenant_id,
    })

    const tenant = tenantData ? { id: tenantData.id, name: tenantData.name } : null

    return { user, tenant }
  }, [])

  // Initialize: check for existing session
  useEffect(() => {
    dispatch({ type: 'SESSION_INIT' })

    supabase.auth.getSession().then(async ({ data: { session }, error }) => {
      if (error) {
        console.error('[AuthContext] getSession error:', error)
        dispatch({ type: 'SESSION_CLEARED' })
        return
      }

      if (!session) {
        dispatch({ type: 'SESSION_CLEARED' })
        return
      }

      const parsed = await parseSession(session)
      if (parsed) {
        dispatch({ type: 'SESSION_LOADED', user: parsed.user, tenant: parsed.tenant })
      } else {
        dispatch({ type: 'SESSION_CLEARED' })
      }
    })

    // Listen for auth changes (login/logout/token refresh)
    const { data: authListener } = supabase.auth.onAuthStateChange(async (event, session) => {
      if (event === 'SIGNED_IN' && session) {
        const parsed = await parseSession(session)
        if (parsed) {
          dispatch({ type: 'SESSION_LOADED', user: parsed.user, tenant: parsed.tenant })
        }
      } else if (event === 'SIGNED_OUT') {
        dispatch({ type: 'LOGOUT' })
      } else if (event === 'TOKEN_REFRESHED' && session) {
        const parsed = await parseSession(session)
        if (parsed) {
          dispatch({ type: 'SESSION_LOADED', user: parsed.user, tenant: parsed.tenant })
        }
      }
    })

    listenerRef.current = authListener.subscription

    return () => {
      listenerRef.current?.unsubscribe()
    }
  }, [parseSession])

  // ─── Login ────────────────────────────────────────────────────────────────
  const login = useCallback(async (email, password) => {
    dispatch({ type: 'OP_START' })
    try {
      const { data, error } = await supabase.auth.signInWithPassword({ email, password })
      if (error) throw error

      const parsed = await parseSession(data.session)
      if (!parsed) throw new Error('Failed to parse session')

      dispatch({ type: 'OP_SUCCESS', user: parsed.user, tenant: parsed.tenant })
      toast.success('Signed in successfully')
      return parsed.user
    } catch (err) {
      const msg = err?.message || 'Login failed'
      dispatch({ type: 'OP_ERROR', error: msg })
      throw new Error(msg)
    }
  }, [parseSession])

  // ─── Signup ───────────────────────────────────────────────────────────────
  const signup = useCallback(async (email, password, fullName = '', tenantName = '') => {
    dispatch({ type: 'OP_START' })
    try {
      // 1. Create tenant (if tenantName provided)
      let tenantId = null
      if (tenantName) {
        const { data: tenant, error: tenantError } = await db.tenants()
          .insert({ name: tenantName })
          .select('id')
          .single()
        if (tenantError) throw tenantError
        tenantId = tenant.id
      }

      // 2. Sign up with Supabase Auth
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            full_name:  fullName,
            role:       'admin', // first user = admin
            tenant_id:  tenantId,
          },
        },
      })
      if (error) throw error

      // Note: Supabase may require email verification before session is created.
      // If data.session is null, the user must verify their email first.
      if (!data.session) {
        toast.info('Please check your email to verify your account.')
        dispatch({ type: 'OP_ERROR', error: null })
        return { success: true, requiresEmailVerification: true }
      }

      const parsed = await parseSession(data.session)
      if (!parsed) throw new Error('Failed to parse session')

      dispatch({ type: 'OP_SUCCESS', user: parsed.user, tenant: parsed.tenant })
      toast.success('Account created successfully!')
      return { success: true, user: parsed.user }
    } catch (err) {
      const msg = err?.message || 'Signup failed'
      dispatch({ type: 'OP_ERROR', error: msg })
      throw new Error(msg)
    }
  }, [parseSession])

  // ─── Logout ──────────────────────────────────────────────────────────────
  const logout = useCallback(async () => {
    await supabase.auth.signOut()
    dispatch({ type: 'LOGOUT' })
    toast.info('Logged out')
  }, [])

  // ─── Password reset ────────────────────────────────────────────────────────
  const forgotPassword = useCallback(async (email) => {
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email, {
        redirectTo: `${window.location.origin}/reset-password`,
      })
      if (error) throw error
      toast.success('Password reset email sent. Check your inbox.')
    } catch (err) {
      const msg = err?.message || 'Failed to send reset email'
      toast.error(msg)
      throw new Error(msg)
    }
  }, [])

  const resetPassword = useCallback(async (newPassword) => {
    try {
      const { error } = await supabase.auth.updateUser({ password: newPassword })
      if (error) throw error
      toast.success('Password updated successfully')
    } catch (err) {
      const msg = err?.message || 'Password reset failed'
      toast.error(msg)
      throw new Error(msg)
    }
  }, [])

  // ─── Email verification ────────────────────────────────────────────────────
  const verifyEmail = useCallback(async (token) => {
    try {
      const { error } = await supabase.auth.verifyOtp({
        token_hash: token,
        type: 'email',
      })
      if (error) throw error
      toast.success('Email verified successfully!')
    } catch (err) {
      const msg = err?.message || 'Email verification failed'
      toast.error(msg)
      throw new Error(msg)
    }
  }, [])

  // ─── Context value ─────────────────────────────────────────────────────────
  const value = {
    user:             state.user,
    tenant:           state.tenant,
    loading:          state.loading,
    isLoading:        state.isLoading,
    error:            state.error,
    isAuthenticated:  !!state.user,
    login,
    signup,
    logout,
    forgotPassword,
    resetPassword,
    verifyEmail,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}

export { AuthContext }
