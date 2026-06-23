import React from 'react'
import { render, screen } from '@testing-library/react'
import StatCard from '../../../../agent-ui/src/components/StatCard'

describe('StatCard', () => {
  test('renders title and value', () => {
    render(<StatCard title="Total Calls" value={150} icon={<span>icon</span>} color="text-blue-600" bgColor="bg-blue-50" />)
    expect(screen.getByText('Total Calls')).toBeTruthy()
    expect(screen.getByText('150')).toBeTruthy()
  })

  test('renders with string value', () => {
    render(<StatCard title="Status" value="Active" icon={<span>icon</span>} color="text-green-600" bgColor="bg-green-50" />)
    expect(screen.getByText('Active')).toBeTruthy()
  })

  test('renders icon', () => {
    render(<StatCard title="Test" value={0} icon={<span data-testid="test-icon">X</span>} color="text-red-600" bgColor="bg-red-50" />)
    expect(screen.getByTestId('test-icon')).toBeTruthy()
  })

  test('applies background color class', () => {
    const { container } = render(<StatCard title="T" value={0} icon={null} color="text-purple-600" bgColor="bg-purple-50" />)
    expect(container.firstChild.className).toContain('bg-purple-200')
  })
})
