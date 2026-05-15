import React, { createContext, useContext, useEffect, useRef, useCallback } from 'react'
import { useAuth } from './AuthContext'

const SocketContext = createContext(null)

export function SocketProvider({ children }) {
  const { user } = useAuth()
  const socketRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)

  const connectWebSocket = useCallback(() => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:3000'
    const wsUrl = apiUrl.replace(/^http/, 'ws') + '/ws/agent/' + (user?.agentId || '')

    // Clean up existing connection
    if (socketRef.current) {
      socketRef.current.close()
      socketRef.current = null
    }

    // Don't connect without auth
    if (!user?.token) {
      return
    }

    // Add tenant WebSocket for call updates
    const tenantWsUrl = apiUrl.replace(/^http/, 'ws') + '/ws/calls/' + (user?.tenantId || '')

    const tenantSocket = new WebSocket(tenantWsUrl)

    tenantSocket.onopen = () => {
      console.log('Tenant WebSocket connected')
    }

    tenantSocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        // Dispatch custom event for call status updates
        window.dispatchEvent(new CustomEvent('call:status', { detail: data }))
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
      }
    }

    tenantSocket.onerror = (error) => {
      console.error('Tenant WebSocket error:', error)
    }

    tenantSocket.onclose = () => {
      console.log('Tenant WebSocket disconnected')
      // Reconnect after delay
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = setTimeout(connectWebSocket, 5000)
    }

    socketRef.current = {
      tenantSocket,
      // Agent socket (for call assignments)
      agentSocket: null,
    }

    // Connect agent WebSocket if user is an agent
    if (user?.agentId) {
      const agentSocket = new WebSocket(wsUrl)

      agentSocket.onopen = () => {
        console.log('Agent WebSocket connected, authenticating...')
        // Send auth token
        agentSocket.send(JSON.stringify({ type: 'auth', token: user.token }))
      }

      agentSocket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'auth_success') {
            console.log('Agent WebSocket authenticated')
          } else if (data.type === 'call_assignment') {
            window.dispatchEvent(new CustomEvent('call:assigned', { detail: data }))
          }
        } catch (e) {
          console.error('Failed to parse agent WebSocket message:', e)
        }
      }

      agentSocket.onerror = (error) => {
        console.error('Agent WebSocket error:', error)
      }

      agentSocket.onclose = () => {
        console.log('Agent WebSocket disconnected')
      }

      socketRef.current.agentSocket = agentSocket
    }
  }, [user])

  useEffect(() => {
    connectWebSocket()

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      if (socketRef.current) {
        socketRef.current.tenantSocket?.close()
        socketRef.current.agentSocket?.close()
        socketRef.current = null
      }
    }
  }, [connectWebSocket])

  return (
    <SocketContext.Provider value={socketRef.current}>
      {children}
    </SocketContext.Provider>
  )
}

export function useSocket() {
  return useContext(SocketContext)
}