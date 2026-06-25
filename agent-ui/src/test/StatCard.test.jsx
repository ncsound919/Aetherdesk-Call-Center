import React from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect, vi } from 'vitest'
import StatCard from '../components/StatCard'

describe('StatCard', () => {
  it('renders title and value', () => {
    render(<StatCard title="Active Calls" value={5} icon={<span>icon</span>} />)
    expect(screen.getByText('Active Calls')).toBeInTheDocument()
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('renders trend when provided', () => {
    render(<StatCard title="Calls" value={10} trend={12} icon={<span>icon</span>} />)
    expect(screen.getByText(/12%/)).toBeInTheDocument()
    expect(screen.getByText(/vs last week/)).toBeInTheDocument()
  })

  it('renders negative trend in red', () => {
    render(<StatCard title="Calls" value={10} trend={-5} icon={<span>icon</span>} />)
    const trendEl = screen.getByText(/5%/)
    expect(trendEl).toBeInTheDocument()
  })

  it('does not render trend when not provided', () => {
    render(<StatCard title="Calls" value={10} icon={<span>icon</span>} />)
    expect(screen.queryByText(/vs last week/)).not.toBeInTheDocument()
  })

  it('applies custom color and bg classes', () => {
    const { container } = render(
      <StatCard title="Test" value={1} color="text-red-500" bgColor="bg-red-100" icon={<span>icon</span>} />
    )
    expect(container.querySelector('.text-red-500')).toBeInTheDocument()
    expect(container.querySelector('.bg-red-100')).toBeInTheDocument()
  })
})
