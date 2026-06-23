import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import CallLogs from '../../../../agent-ui/src/pages/CallLogs'

jest.mock('../../../../agent-ui/src/services/api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}))

jest.mock('../../../../agent-ui/src/context/AuthContext', () => ({
  useAuth: () => ({ tenant: { id: 'T-123' }, user: { name: 'Test' } }),
  AuthProvider: ({ children }) => children,
}))

const api = require('../../../../agent-ui/src/services/api').default

describe('CallLogs Page', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  test('renders call logs heading', async () => {
    api.get.mockResolvedValue({ data: [] })
    render(<BrowserRouter><CallLogs /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText('Call Logs')).toBeTruthy()
    })
  })

  test('displays call data in table', async () => {
    api.get.mockResolvedValue({
      data: [
        { id: 'C-1', caller_number: '+1234567890', called_number: '+0987654321', call_direction: 'inbound', call_status: 'completed', duration_seconds: 120, total_cost: 0.50, intent_detected: 'sales' },
        { id: 'C-2', caller_number: '+0987654321', called_number: '+1234567890', call_direction: 'outbound', call_status: 'missed', duration_seconds: 0, total_cost: 0, intent_detected: null }
      ]
    })
    render(<BrowserRouter><CallLogs /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getAllByText('+1234567890').length).toBeGreaterThan(0)
      expect(screen.getAllByText('+0987654321').length).toBeGreaterThan(0)
    })
  })

  test('shows empty state when no calls', async () => {
    api.get.mockResolvedValue({ data: [] })
    render(<BrowserRouter><CallLogs /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText(/no calls found/i)).toBeTruthy()
    })
  })

  test('displays loading state', async () => {
    api.get.mockReturnValue(new Promise(() => {})) // never resolves
    render(<BrowserRouter><CallLogs /></BrowserRouter>)
    expect(screen.getByText(/loading calls/i)).toBeTruthy()
  })

  test('renders filter controls', async () => {
    api.get.mockResolvedValue({ data: [] })
    render(<BrowserRouter><CallLogs /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText('Status')).toBeTruthy()
      expect(screen.getByText('Date From')).toBeTruthy()
      expect(screen.getByText('Date To')).toBeTruthy()
    })
  })
})