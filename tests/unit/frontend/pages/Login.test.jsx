import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import Login from '../../../../agent-ui/src/pages/Login'
import { AuthProvider } from '../../../../agent-ui/src/context/AuthContext'
import api from '../../../../agent-ui/src/services/api'

jest.mock('../../../../agent-ui/src/services/api')

function renderLogin() {
  return render(
    <BrowserRouter>
      <AuthProvider>
        <Login />
      </AuthProvider>
    </BrowserRouter>
  )
}

describe('Login Page', () => {
  beforeEach(() => {
    localStorage.clear()
    jest.clearAllMocks()
  })

  test('renders email and password inputs', () => {
    renderLogin()
    expect(screen.getByPlaceholderText(/email/i)).toBeTruthy()
    expect(screen.getByPlaceholderText(/password/i)).toBeTruthy()
  })

  test('renders login button', () => {
    renderLogin()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeTruthy()
  })

  test('shows error on failed login', async () => {
    api.post.mockRejectedValue({ response: { data: { detail: 'Invalid credentials' } } })

    renderLogin()
    fireEvent.change(screen.getByPlaceholderText(/email/i), { target: { value: 'test@test.com' } })
    fireEvent.change(screen.getByPlaceholderText(/password/i), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByText(/invalid email or password/i)).toBeTruthy()
    })
  })

  test('calls API with correct credentials', async () => {
    api.post.mockResolvedValue({
      data: { token: 'tok', tenantId: 'T-1', name: 'User', role: 'admin', userId: 'u-1' }
    })

    renderLogin()
    fireEvent.change(screen.getByPlaceholderText(/email/i), { target: { value: 'a@b.com' } })
    fireEvent.change(screen.getByPlaceholderText(/password/i), { target: { value: 'pass' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/auth/login', { email: 'a@b.com', password: 'pass' })
    })
  })
})
