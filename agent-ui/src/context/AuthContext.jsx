import React, { createContext, useContext, useState, useEffect } from 'react'
import api from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [tenant, setTenant] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    const tenantId = localStorage.getItem('tenantId')
    if (token && tenantId) {
      setUser({ token })
      setTenant({ id: tenantId })
    }
    setLoading(false)
  }, [])

  const login = async (email, password) => {
    const response = await api.post('/auth/login', { email, password })
    const { token, tenantId, name, role, userId } = response.data
    const userData = { name, role, userId, email }
    localStorage.setItem('token', token)
    localStorage.setItem('tenantId', tenantId)
    setUser(userData)
    setTenant({ id: tenantId })
    return userData
  }

  const logout = () => {
    localStorage.removeItem('token')
    localStorage.removeItem('tenantId')
    setUser(null)
    setTenant(null)
  }

  const isAuthenticated = !!user

  return (
    <AuthContext.Provider value={{ user, tenant, loading, isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}