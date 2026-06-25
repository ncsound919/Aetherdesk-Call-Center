import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from '../pages/Dashboard'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { name: 'Admin', role: 'admin' },
    tenant: { id: 'TENANT-001' },
  }),
}))

vi.mock('../context/SocketContext', () => ({
  useSocket: () => ({ tenantSocket: null }),
}))

const mockGet = vi.fn().mockResolvedValue({ data: {} })
const mockPost = vi.fn().mockResolvedValue({ data: {} })
const mockList = vi.fn().mockResolvedValue({ data: [] })

vi.mock('../services/api', () => ({
  default: { get: (...a) => mockGet(...a), post: (...a) => mockPost(...a) },
  agentApi: { list: (...a) => mockList(...a) },
}))

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}))

vi.mock('../components/RecentCalls', () => ({
  default: ({ calls }) => <div data-testid="recent-calls">RecentCalls ({calls?.length || 0})</div>,
}))

function renderDashboard() {
  return render(
    <MemoryRouter>
      <Dashboard />
    </MemoryRouter>
  )
}

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders page heading', () => {
    renderDashboard()
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Overview of your call center operations')).toBeInTheDocument()
  })

  it('renders stat cards', async () => {
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByText('Active Calls')).toBeInTheDocument()
    })
    expect(screen.getByText('Total Calls Today')).toBeInTheDocument()
    expect(screen.getByText('Avg Call Duration')).toBeInTheDocument()
    expect(screen.getByText('Available Agents')).toBeInTheDocument()
  })

  it('renders Make a Call button', () => {
    renderDashboard()
    expect(screen.getByText('Make a Call')).toBeInTheDocument()
  })

  it('renders welcome section when no calls', () => {
    renderDashboard()
    expect(screen.getByText('Welcome to AetherDesk')).toBeInTheDocument()
  })

  it('renders RecentCalls component', () => {
    renderDashboard()
    expect(screen.getByTestId('recent-calls')).toBeInTheDocument()
  })
})
