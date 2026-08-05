import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import Dashboard from '../pages/Dashboard'

const TEST_USER = { name: 'Admin', role: 'admin' }
const TEST_TENANT = { id: 'TENANT-001' }

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ user: TEST_USER, tenant: TEST_TENANT }),
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
    mockGet.mockReset().mockResolvedValue({ data: {} })
    mockPost.mockReset().mockResolvedValue({ data: {} })
    mockList.mockReset().mockResolvedValue({ data: [] })
  })

  it('renders page heading', async () => {
    renderDashboard()
    expect(await screen.findByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Overview of your call center operations')).toBeInTheDocument()
  })

  it('renders stat cards', async () => {
    renderDashboard()
    expect(await screen.findByText('Active Calls')).toBeInTheDocument()
    expect(await screen.findByText('Total Calls Today')).toBeInTheDocument()
    expect(await screen.findByText('Avg Call Duration')).toBeInTheDocument()
    expect(await screen.findByText('Available Agents')).toBeInTheDocument()
  })

  it('renders Make a Call button', async () => {
    renderDashboard()
    expect(await screen.findByText('Make a Call')).toBeInTheDocument()
  })

  it('renders welcome section when no calls', async () => {
    renderDashboard()
    expect(await screen.findByText('Welcome to AetherDesk')).toBeInTheDocument()
  })

  it('renders RecentCalls component', async () => {
    renderDashboard()
    expect(await screen.findByTestId('recent-calls')).toBeInTheDocument()
  })
})
