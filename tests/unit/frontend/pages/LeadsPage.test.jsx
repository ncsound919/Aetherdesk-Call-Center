import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import LeadsPage from '../../../../agent-ui/src/pages/LeadsPage'

jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => jest.fn(),
}))

jest.mock('../../../../agent-ui/src/services/api', () => ({
  __esModule: true,
  default: { get: jest.fn() },
}))

jest.mock('../../../../agent-ui/src/context/AuthContext', () => ({
  useAuth: () => ({ tenant: { id: 'T-123' }, user: { name: 'Test' } }),
  AuthProvider: ({ children }) => children,
}))

jest.mock('sonner', () => ({
  toast: { error: jest.fn(), success: jest.fn() },
}))

const api = require('../../../../agent-ui/src/services/api').default

describe('LeadsPage', () => {
  beforeEach(() => jest.clearAllMocks())

  test('renders leads heading', async () => {
    api.get.mockResolvedValue({ data: [] })
    render(<BrowserRouter><LeadsPage /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText('Leads')).toBeTruthy()
    })
  })

  test('displays leads in table', async () => {
    api.get.mockResolvedValue({
      data: [{ id: 'L-1', name: 'John Doe', phone: '+1234567890', email: 'john@test.com' }]
    })
    render(<BrowserRouter><LeadsPage /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText('John Doe')).toBeTruthy()
      expect(screen.getByText('+1234567890')).toBeTruthy()
    })
  })

  test('shows empty state', async () => {
    api.get.mockResolvedValue({ data: [] })
    render(<BrowserRouter><LeadsPage /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText(/no leads yet/i)).toBeTruthy()
    })
  })

  test('shows import button', async () => {
    api.get.mockResolvedValue({ data: [] })
    render(<BrowserRouter><LeadsPage /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText(/import csv/i)).toBeTruthy()
    })
  })
})
