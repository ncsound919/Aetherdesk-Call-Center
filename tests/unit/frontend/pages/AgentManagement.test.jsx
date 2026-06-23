import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import AgentManagement from '../../../../agent-ui/src/pages/AgentManagement'

jest.mock('../../../../agent-ui/src/services/api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn(), put: jest.fn(), delete: jest.fn(), patch: jest.fn() },
}))

jest.mock('../../../../agent-ui/src/context/AuthContext', () => ({
  useAuth: () => ({ tenant: { id: 'T-123' }, user: { name: 'Test' } }),
  AuthProvider: ({ children }) => children,
}))

const api = require('../../../../agent-ui/src/services/api').default

describe('AgentManagement Page', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  test('renders agent list', async () => {
    api.get.mockResolvedValue({
      data: [
        { id: 'A-1', name: 'Agent 1', status: 'available', agent_type: 'ai', skills: ['sales'], email: 'a1@test.com', display_name: 'Agent 1', sip_extension: '1001', total_calls: 50, config: {} },
        { id: 'A-2', name: 'Agent 2', status: 'busy', agent_type: 'human', skills: ['support'], email: 'a2@test.com', display_name: 'Agent 2', sip_extension: '1002', total_calls: 30, config: {} }
      ]
    })
    render(<BrowserRouter><AgentManagement /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText('Agent 1')).toBeTruthy()
      expect(screen.getByText('Agent 2')).toBeTruthy()
    })
  })

  test('shows add agent button', async () => {
    api.get.mockResolvedValue({ data: [] })
    render(<BrowserRouter><AgentManagement /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText(/add agent/i)).toBeTruthy()
    })
  })

  test('shows empty state when no agents', async () => {
    api.get.mockResolvedValue({ data: [] })
    render(<BrowserRouter><AgentManagement /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByRole('table')).toBeTruthy()
    })
  })

  test('displays agent status badges', async () => {
    api.get.mockResolvedValue({
      data: [{ id: 'A-1', name: 'Agent 1', status: 'available', agent_type: 'ai', skills: [], email: 'a@test.com', display_name: 'Agent 1', total_calls: 0, config: {} }]
    })
    render(<BrowserRouter><AgentManagement /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText('available')).toBeTruthy()
    })
  })
})