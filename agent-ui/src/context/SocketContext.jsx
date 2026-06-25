import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react'
import { useAuth } from './AuthContext'

const SocketContext = createContext(null)

export function SocketProvider({ children }) {
  const { user, tenant } = useAuth()
  const tenantSocketRef = useRef(null)
  const agentSocketRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const heartbeatTimerRef = useRef(null)
  const [connectionStatus, setConnectionStatus] = useState('disconnected')
  const retryCountRef = useRef(0)

  const getWsUrl = (path) => {
    const base = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    const wsBase = base.replace(/^http/, 'ws')
    return `${wsBase}${path}`
  }

  const connectTenantSocket = useCallback(() => {
    const tid = tenant?.id
    if (!tid) return

    if (tenantSocketRef.current?.readyState === WebSocket.OPEN) return

    const url = getWsUrl(`/ws/calls/${tid}`)
    const ws = new WebSocket(url)
    tenantSocketRef.current = ws
    setConnectionStatus('connecting')

    ws.onopen = () => {
      setConnectionStatus('connected')
      retryCountRef.current = 0
      // Heartbeat
      heartbeatTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }))
      }, 30000)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'call:status' || data.type === 'call:assigned') {
          window.dispatchEvent(new CustomEvent(data.type, { detail: data }))
        }
      } catch { /* ignore */ }
    }

    ws.onclose = () => {
      setConnectionStatus('disconnected')
      clearInterval(heartbeatTimerRef.current)
      // Exponential backoff reconnect
      const delay = Math.min(1000 * Math.pow(2, retryCountRef.current), 30000)
      retryCountRef.current++
      reconnectTimerRef.current = setTimeout(connectTenantSocket, delay)
    }

    ws.onerror = () => { ws.close() }
  }, [tenant?.id])

  const disconnect = useCallback(() => {
    clearTimeout(reconnectTimerRef.current)
    clearInterval(heartbeatTimerRef.current)
    tenantSocketRef.current?.close()
    agentSocketRef.current?.close()
    tenantSocketRef.current = null
    agentSocketRef.current = null
    setConnectionStatus('disconnected')
  }, [])

  useEffect(() => {
    const handleCallStatus = (e) => window.dispatchEvent(new CustomEvent('call:status', { detail: e.detail }))
    const handleCallAssigned = (e) => window.dispatchEvent(new CustomEvent('call:assigned', { detail: e.detail }))
    window.addEventListener('call:status', handleCallStatus)
    window.addEventListener('call:assigned', handleCallAssigned)

    connectTenantSocket()
    return () => {
      window.removeEventListener('call:status', handleCallStatus)
      window.removeEventListener('call:assigned', handleCallAssigned)
      disconnect()
    }
  }, [connectTenantSocket, disconnect])

  return (
    <SocketContext.Provider value={{
      tenantSocket: tenantSocketRef.current,
      agentSocket: agentSocketRef.current,
      connectionStatus,
      disconnect,
    }}>
      {children}
    </SocketContext.Provider>
  )
}

export function useSocket() {
  const ctx = useContext(SocketContext)
  return ctx
}
