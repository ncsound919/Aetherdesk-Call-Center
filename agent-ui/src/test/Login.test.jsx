import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import Login from '../pages/Login'

const mockLogin = vi.fn()

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ login: mockLogin }),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return { ...actual, useNavigate: () => vi.fn() }
})

function renderLogin() {
  return render(
    <MemoryRouter>
      <Login />
    </MemoryRouter>
  )
}

describe('Login', () => {
  beforeEach(() => {
    mockLogin.mockReset()
  })

  it('renders welcome heading', () => {
    renderLogin()
    expect(screen.getByText('Welcome back')).toBeInTheDocument()
    expect(screen.getByText('Sign in to your call center dashboard')).toBeInTheDocument()
  })

  it('renders email and password inputs', () => {
    renderLogin()
    expect(screen.getByPlaceholderText('admin@aetherdesk.com')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Enter your password')).toBeInTheDocument()
  })

  it('renders sign in button', () => {
    renderLogin()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('renders forgot password link', () => {
    renderLogin()
    expect(screen.getByText('Forgot password?')).toBeInTheDocument()
  })

  it('renders sign up link', () => {
    renderLogin()
    expect(screen.getByText('Sign up')).toBeInTheDocument()
  })

  it('calls login with email and password on submit', async () => {
    mockLogin.mockResolvedValueOnce({})
    renderLogin()
    await userEvent.type(screen.getByPlaceholderText('admin@aetherdesk.com'), 'test@example.com')
    await userEvent.type(screen.getByPlaceholderText('Enter your password'), 'password123')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('test@example.com', 'password123')
    })
  })

  it('shows error message on login failure', async () => {
    mockLogin.mockRejectedValueOnce({ response: { data: { detail: 'Invalid credentials' } } })
    renderLogin()
    await userEvent.type(screen.getByPlaceholderText('admin@aetherdesk.com'), 'bad@example.com')
    await userEvent.type(screen.getByPlaceholderText('Enter your password'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await waitFor(() => {
      expect(screen.getByText('Invalid credentials')).toBeInTheDocument()
    })
  })

  it('toggles password visibility', async () => {
    renderLogin()
    const pwInput = screen.getByPlaceholderText('Enter your password')
    expect(pwInput.type).toBe('password')
    const toggleBtn = screen.getByRole('button', { name: '' })
    await userEvent.click(toggleBtn)
    expect(pwInput.type).toBe('text')
  })
})
