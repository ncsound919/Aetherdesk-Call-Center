import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import Sidebar from '../../../../agent-ui/src/components/Sidebar'

function renderSidebar(open = true, onClose = jest.fn()) {
  return render(
    <BrowserRouter>
      <Sidebar open={open} onClose={onClose} />
    </BrowserRouter>
  )
}

describe('Sidebar', () => {
  test('renders navigation links', () => {
    renderSidebar()
    expect(screen.getByText('Dashboard')).toBeTruthy()
    expect(screen.getByText('Agents')).toBeTruthy()
    expect(screen.getByText('Call Logs')).toBeTruthy()
    expect(screen.getByText('Settings')).toBeTruthy()
    expect(screen.getByText('Billing')).toBeTruthy()
    expect(screen.getByText('Leads')).toBeTruthy()
    expect(screen.getByText('Scripts')).toBeTruthy()
    expect(screen.getByText('Voice Cloning')).toBeTruthy()
  })

  test('renders AetherDesk branding', () => {
    renderSidebar()
    expect(screen.getByText('AetherDesk')).toBeTruthy()
  })

  test('renders admin info', () => {
    renderSidebar()
    expect(screen.getByText('Admin')).toBeTruthy()
    expect(screen.getByText('admin@aetherdesk.com')).toBeTruthy()
  })

  test('applies translate transform when closed', () => {
    const { container } = renderSidebar(false)
    const aside = container.querySelector('aside')
    expect(aside.className).toContain('-translate-x-full')
  })

  test('does not apply negative translate when open', () => {
    const { container } = renderSidebar(true)
    const aside = container.querySelector('aside')
    expect(aside.className).toContain('translate-x-0')
  })
})
