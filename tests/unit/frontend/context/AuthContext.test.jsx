import React from 'react'
import { render, screen, act, waitFor } from '@testing-library/react'
import { AuthProvider, useAuth } from '../../../../agent-ui/src/context/AuthContext'
import api from '../../../../agent-ui/src/services/api'

jest.mock('../../../../agent-ui/src/services/api')

function TestComponent() {
  const { user, tenant, loading, isAuthenticated, login, logout } = useAuth()
  const handleLogin = async () => {
    try {
      await login('test@example.com', 'password123')
    } catch (e) {
      // expected to throw on error
    }
  }
  return (
    <div>
      <span data-testid="loading">{loading.toString()}</span>
      <span data-testid="authenticated">{isAuthenticated.toString()}</span>
      <span data-testid="user">{user ? user.name : 'null'}</span>
      <span data-testid="tenant">{tenant ? tenant.id : 'null'}</span>
      <button onClick={handleLogin}>Login</button>
      <button onClick={logout}>Logout</button>
    </div>
  )
}

describe('AuthContext', () => {
  beforeEach(() => {
    localStorage.clear()
    jest.clearAllMocks()
  })

  test('initializes with loading true then false', async () => {
    render(<AuthProvider><TestComponent /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
  })

  test('restores user from localStorage', async () => {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('tenantId', 'TENANT-123')
    localStorage.setItem('userName', 'Test User')
    localStorage.setItem('userRole', 'admin')
    localStorage.setItem('userEmail', 'test@example.com')
    localStorage.setItem('userId', 'user-1')

    render(<AuthProvider><TestComponent /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('authenticated').textContent).toBe('true')
    expect(screen.getByTestId('user').textContent).toBe('Test User')
    expect(screen.getByTestId('tenant').textContent).toBe('TENANT-123')
  })

  test('login stores user data and sets authenticated', async () => {
    api.post.mockResolvedValue({
      data: { token: 'new-token', tenantId: 'T-456', name: 'Jane', role: 'agent', userId: 'u-2' }
    })

    render(<AuthProvider><TestComponent /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))

    await act(async () => {
      screen.getByText('Login').click()
    })

    expect(api.post).toHaveBeenCalledWith('/auth/login', { email: 'test@example.com', password: 'password123' })
    expect(screen.getByTestId('authenticated').textContent).toBe('true')
    expect(screen.getByTestId('user').textContent).toBe('Jane')
    expect(localStorage.getItem('token')).toBe('new-token')
    expect(localStorage.getItem('tenantId')).toBe('T-456')
  })

  test('logout clears user data', async () => {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('tenantId', 'T-123')
    localStorage.setItem('userName', 'Test')
    localStorage.setItem('userRole', 'admin')
    localStorage.setItem('userEmail', 'test@test.com')
    localStorage.setItem('userId', 'u-1')

    render(<AuthProvider><TestComponent /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('authenticated').textContent).toBe('true')

    await act(async () => {
      screen.getByText('Logout').click()
    })

    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    expect(localStorage.getItem('token')).toBeNull()
  })

  test('login does not set authenticated on API error', async () => {
    api.post.mockRejectedValue(new Error('Invalid credentials'))

    render(<AuthProvider><TestComponent /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))

    await act(async () => {
      screen.getByText('Login').click()
    })

    expect(api.post).toHaveBeenCalledWith('/auth/login', { email: 'test@example.com', password: 'password123' })
    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    expect(screen.getByTestId('user').textContent).toBe('null')
  })
})
