import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import ScriptsPage from '../../../../agent-ui/src/pages/ScriptsPage'

jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => jest.fn(),
}))

jest.mock('../../../../agent-ui/src/services/api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), delete: jest.fn() },
}))

jest.mock('../../../../agent-ui/src/context/AuthContext', () => ({
  useAuth: () => ({ tenant: { id: 'T-123' }, user: { name: 'Test' } }),
  AuthProvider: ({ children }) => children,
}))

jest.mock('sonner', () => ({
  toast: { error: jest.fn(), success: jest.fn() },
}))

const api = require('../../../../agent-ui/src/services/api').default

describe('ScriptsPage', () => {
  beforeEach(() => jest.clearAllMocks())

  test('renders scripts heading', async () => {
    api.get.mockResolvedValue({ data: [] })
    render(<BrowserRouter><ScriptsPage /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText('Scripts')).toBeTruthy()
    })
  })

  test('displays scripts list', async () => {
    api.get.mockResolvedValue({
      data: [{ id: 'S-1', name: 'Sales Script', content: 'Hello there!' }]
    })
    render(<BrowserRouter><ScriptsPage /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText('Sales Script')).toBeTruthy()
      expect(screen.getByText('Hello there!')).toBeTruthy()
    })
  })

  test('shows empty state', async () => {
    api.get.mockResolvedValue({ data: [] })
    render(<BrowserRouter><ScriptsPage /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText(/no scripts yet/i)).toBeTruthy()
    })
  })

  test('has new script input', async () => {
    api.get.mockResolvedValue({ data: [] })
    render(<BrowserRouter><ScriptsPage /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/new script name/i)).toBeTruthy()
      expect(screen.getByText(/new script/i)).toBeTruthy()
    })
  })
})
