import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [tenant, setTenant] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    const tenantId = localStorage.getItem('tenantId')
    const userName = localStorage.getItem('userName')
    const userRole = localStorage.getItem('userRole')
    const userEmail = localStorage.getItem('userEmail')
    const userId = localStorage.getItem('userId')
    if (token && tenantId) {
      setUser({ token, name: userName, role: userRole, email: userEmail, userId })
      setTenant({ id: tenantId })
    }
    setLoading(false)
  }, [])

  const login = useCallback(async (email, password) => {
    const response = await api.post('/auth/login', { email, password })
    const { token, tenantId, name, role, userId } = response.data
    const userData = { name, role, userId, email }
    localStorage.setItem('token', token)
    localStorage.setItem('tenantId', tenantId)
    localStorage.setItem('userName', name)
    localStorage.setItem('userRole', role)
    localStorage.setItem('userEmail', email)
    localStorage.setItem('userId', userId)
    setUser(userData)
    setTenant({ id: tenantId })
    return userData
  }, [])

  const signup = useCallback(async (email, password, companyName) => {
    const response = await api.post('/auth/signup', { email, password, company_name: companyName })
    return response.data
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('token')
    localStorage.removeItem('tenantId')
    localStorage.removeItem('userName')
    localStorage.removeItem('userRole')
    localStorage.removeItem('userEmail')
    localStorage.removeItem('userId')
    setUser(null)
    setTenant(null)
  }, [])

  const isAuthenticated = !!user

  return (
    <AuthContext.Provider value={{ user, tenant, loading, isAuthenticated, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
