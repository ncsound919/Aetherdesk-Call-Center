import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import Dashboard from '../../../../agent-ui/src/pages/Dashboard'

jest.mock('../../../../agent-ui/src/services/api', () => ({
  __esModule: true,
  default: { get: jest.fn(), post: jest.fn() },
}))

jest.mock('../../../../agent-ui/src/context/AuthContext', () => ({
  useAuth: () => ({ tenant: { id: 'T-123' }, user: { name: 'Test' } }),
  AuthProvider: ({ children }) => children,
}))

jest.mock('../../../../agent-ui/src/context/SocketContext', () => ({
  useSocket: () => ({ tenantSocket: null }),
  SocketProvider: ({ children }) => children,
}))

jest.mock('../../../../agent-ui/src/components/StatCard', () => (props) => (
  <div data-testid={`stat-${props.title}`}>{props.title}: {String(props.value)}</div>
))
jest.mock('../../../../agent-ui/src/components/AgentStatusChart', () => () => <div data-testid="agent-chart" />)
jest.mock('../../../../agent-ui/src/components/CallVolumeChart', () => () => <div data-testid="call-chart" />)
jest.mock('../../../../agent-ui/src/components/RecentCalls', () => (props) => (
  <div data-testid="recent-calls">{props.calls.length} calls</div>
))

const api = require('../../../../agent-ui/src/services/api').default

describe('Dashboard Page', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  test('renders dashboard heading', async () => {
    api.get.mockResolvedValue({ data: { total_calls: 0, active_agents: 0 } })
    render(<BrowserRouter><Dashboard /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeTruthy()
    })
  })

  test('displays stat cards', async () => {
    api.get
      .mockResolvedValueOnce({ data: { active_calls: 5, total_calls: 20, avg_call_duration: 120, active_agents: 3, total_agents: 8 } })
      .mockResolvedValueOnce({ data: [] })
    render(<BrowserRouter><Dashboard /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByTestId('stat-Active Calls')).toBeTruthy()
      expect(screen.getByTestId('stat-Total Calls Today')).toBeTruthy()
    })
  })

  test('handles API error gracefully', async () => {
    api.get.mockRejectedValue(new Error('Network error'))
    render(<BrowserRouter><Dashboard /></BrowserRouter>)
    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeTruthy()
    })
  })
})