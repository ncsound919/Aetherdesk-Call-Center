import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import BillingPage from '../../../../agent-ui/src/pages/BillingPage'

jest.mock('../../../../agent-ui/src/services/api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}))

jest.mock('../../../../agent-ui/src/context/AuthContext', () => ({
  useAuth: () => ({ tenant: { id: 'T-123' }, user: { name: 'Test' } }),
  AuthProvider: ({ children }) => children,
}))

jest.mock('sonner', () => ({
  toast: { error: jest.fn(), success: jest.fn() },
}))

const api = require('../../../../agent-ui/src/services/api').default

describe('BillingPage', () => {
  beforeEach(() => jest.clearAllMocks())

  test('shows loading state initially', () => {
    api.get.mockReturnValue(new Promise(() => {}))
    render(<BrowserRouter><BillingPage /></BrowserRouter>)
    expect(screen.getByText(/loading billing/i)).toBeTruthy()
  })

  test('renders billing summary', async () => {
    api.get.mockResolvedValue({
      data: { plan: 'Pro', calls_this_month: 500, minutes_used: 1200, estimated_cost: 299.99 }
    })
    render(<BrowserRouter><BillingPage /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText('Billing')).toBeTruthy()
      expect(screen.getByText('Pro')).toBeTruthy()
      expect(screen.getByText('500')).toBeTruthy()
      expect(screen.getByText('$299.99')).toBeTruthy()
    })
  })

  test('shows no billing info when summary is null', async () => {
    api.get.mockResolvedValue({ data: null })
    render(<BrowserRouter><BillingPage /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText(/no billing information/i)).toBeTruthy()
    })
  })
})
