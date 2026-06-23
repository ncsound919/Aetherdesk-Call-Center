import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import SignupPage from '../../../../agent-ui/src/pages/SignupPage'

jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => jest.fn(),
}))

jest.mock('../../../../agent-ui/src/services/api', () => ({
  __esModule: true,
  default: { post: jest.fn() },
}))

const mockSignup = jest.fn().mockResolvedValue({})

jest.mock('../../../../agent-ui/src/context/AuthContext', () => ({
  useAuth: () => ({ signup: mockSignup }),
  AuthProvider: ({ children }) => children,
}))

jest.mock('sonner', () => ({
  toast: { error: jest.fn(), success: jest.fn() },
}))

describe('SignupPage', () => {
  beforeEach(() => jest.clearAllMocks())

  test('renders signup form fields', () => {
    render(<BrowserRouter><SignupPage /></BrowserRouter>)
    expect(screen.getByPlaceholderText(/company name/i)).toBeTruthy()
    expect(screen.getByPlaceholderText(/email/i)).toBeTruthy()
    expect(screen.getByPlaceholderText(/password/i)).toBeTruthy()
  })

  test('renders signup button', () => {
    render(<BrowserRouter><SignupPage /></BrowserRouter>)
    expect(screen.getByRole('button', { name: /sign up/i })).toBeTruthy()
  })

  test('calls signup on form submit', async () => {
    render(<BrowserRouter><SignupPage /></BrowserRouter>)
    fireEvent.change(screen.getByPlaceholderText(/company name/i), { target: { value: 'Acme' } })
    fireEvent.change(screen.getByPlaceholderText(/email/i), { target: { value: 'a@b.com' } })
    fireEvent.change(screen.getByPlaceholderText(/password/i), { target: { value: 'pass123' } })
    fireEvent.click(screen.getByRole('button', { name: /sign up/i }))
    await waitFor(() => {
      expect(mockSignup).toHaveBeenCalledWith('a@b.com', 'pass123', 'Acme')
    })
  })
})
