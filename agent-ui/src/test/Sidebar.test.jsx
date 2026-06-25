import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import Sidebar from '../components/Sidebar'

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { name: 'Admin', email: 'admin@aetherdesk.com' },
    logout: vi.fn(),
  }),
}))

function renderSidebar(initialPath = '/', props = {}) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Sidebar open={true} onClose={vi.fn()} {...props} />
    </MemoryRouter>
  )
}

describe('Sidebar', () => {
  it('renders AetherDesk branding', () => {
    renderSidebar()
    expect(screen.getByText('AetherDesk')).toBeInTheDocument()
    expect(screen.getByText('Call Center')).toBeInTheDocument()
  })

  it('renders all navigation items', () => {
    renderSidebar()
    const labels = ['Dashboard', 'Analytics', 'Agents', 'Call Logs', 'Voice', 'Billing', 'Leads', 'Scripts', 'Settings']
    labels.forEach(label => {
      expect(screen.getByText(label)).toBeInTheDocument()
    })
  })

  it('highlights active route', () => {
    renderSidebar('/agents')
    const agentsBtn = screen.getByText('Agents').closest('button')
    expect(agentsBtn.className).toContain('text-white')
  })

  it('shows user info', () => {
    renderSidebar()
    expect(screen.getByText('Admin')).toBeInTheDocument()
    expect(screen.getByText('admin@aetherdesk.com')).toBeInTheDocument()
  })

  it('calls onClose when nav item clicked', async () => {
    const onClose = vi.fn()
    renderSidebar('/', { onClose })
    await userEvent.click(screen.getByText('Analytics'))
    expect(onClose).toHaveBeenCalled()
  })
})
