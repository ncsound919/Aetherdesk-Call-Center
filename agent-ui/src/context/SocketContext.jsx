/**
 * SocketContext — Supabase Realtime integration
 *
 * Replaces raw WebSocket with Supabase Realtime channels for:
 *   - Call status updates (INSERT/UPDATE on calls table)
 *   - Agent status changes (UPDATE on agents table)
 *   - Chat messages (INSERT on chat_messages table)
 *
 * Automatically scoped to the authenticated user's tenantId.
 * Channels are created/cleaned up based on auth state.
 */

import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { supabase, tenantChannel } from '../lib/supabase'
import { useAuth } from './AuthContext'

const SocketContext = createContext(null)

export function SocketProvider({ children }) {
  const { tenant, isAuthenticated } = useAuth()
  const channelsRef = useRef(new Map())
  const subscribersRef = useRef(new Map())
  const [connectionStatus, setConnectionStatus] = useState('disconnected')

  // ─── Subscribe to realtime events ────────────────────────────────────────────
  const subscribe = useCallback((eventType, handler) => {
    if (!subscribersRef.current.has(eventType)) {
      subscribersRef.current.set(eventType, new Set())
    }
    subscribersRef.current.get(eventType).add(handler)

    // Return unsubscribe function
    return () => {
      const handlers = subscribersRef.current.get(eventType)
      if (handlers) {
        handlers.delete(handler)
        if (handlers.size === 0) subscribersRef.current.delete(eventType)
      }
    }
  }, [])

  // Emit event to all subscribers
  const emit = useCallback((eventType, payload) => {
    const handlers = subscribersRef.current.get(eventType)
    if (handlers) {
      handlers.forEach(h => h(payload))
    }
  }, [])

  // ─── Setup Realtime channels when authenticated ─────────────────────────────────
  useEffect(() => {
    if (!isAuthenticated || !tenant?.id) {
      // Cleanup any existing channels
      channelsRef.current.forEach(ch => supabase.removeChannel(ch))
      channelsRef.current.clear()
      setConnectionStatus('disconnected')
      return
    }

    setConnectionStatus('connecting')

    const tenantId = tenant.id

    // ─── Calls channel ──────────────────────────────────────────────────────────
    const callsChannel = tenantChannel('calls', tenantId)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'calls',
          filter: `tenant_id=eq.${tenantId}`,
        },
        (payload) => {
          emit('call:new', payload.new)
        }
      )
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'calls',
          filter: `tenant_id=eq.${tenantId}`,
        },
        (payload) => {
          emit('call:status', payload.new)
        }
      )
      .subscribe((status) => {
        if (status === 'SUBSCRIBED') {
          setConnectionStatus('connected')
        } else if (status === 'CLOSED') {
          setConnectionStatus('disconnected')
        } else if (status === 'CHANNEL_ERROR') {
          setConnectionStatus('failed')
        }
      })

    // ─── Agents channel ────────────────────────────────────────────────────────
    const agentsChannel = tenantChannel('agents', tenantId)
      .on(
        'postgres_changes',
        {
          event: 'UPDATE',
          schema: 'public',
          table: 'agents',
          filter: `tenant_id=eq.${tenantId}`,
        },
        (payload) => {
          emit('agent:status', payload.new)
        }
      )
      .subscribe()

    // ─── Chat channel ───────────────────────────────────────────────────────────
    const chatChannel = tenantChannel('chat', tenantId)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'chat_messages',
        },
        (payload) => {
          emit('chat:message', payload.new)
        }
      )
      .subscribe()

    channelsRef.current.set('calls', callsChannel)
    channelsRef.current.set('agents', agentsChannel)
    channelsRef.current.set('chat', chatChannel)

    // Cleanup on unmount or tenant change
    return () => {
      channelsRef.current.forEach(ch => supabase.removeChannel(ch))
      channelsRef.current.clear()
      setConnectionStatus('disconnected')
    }
  }, [isAuthenticated, tenant?.id, emit])

  const value = {
    connectionStatus,
    subscribe,
    disconnect: () => {
      channelsRef.current.forEach(ch => supabase.removeChannel(ch))
      channelsRef.current.clear()
      setConnectionStatus('disconnected')
    },
  }

  return <SocketContext.Provider value={value}>{children}</SocketContext.Provider>
}

export function useSocket() {
  const context = useContext(SocketContext)
  return context
}

export { SocketContext }
