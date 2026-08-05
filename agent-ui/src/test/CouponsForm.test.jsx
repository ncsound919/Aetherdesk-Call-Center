import { describe, it, expect, vi, beforeEach } from 'vitest'
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import CouponsPage from '../pages/admin/CouponsPage'

const mockList = vi.fn()
const mockCreate = vi.fn()
const mockDisable = vi.fn()

vi.mock('../services/api', () => ({
  adminApi: {
    listCoupons: (...a) => mockList(...a),
    createCoupon: (...a) => mockCreate(...a),
    disableCoupon: (...a) => mockDisable(...a),
  },
}))

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}))

describe('CouponsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockList.mockResolvedValue({ data: [{ id: '1', code: 'WELCOME20', type: 'percent', value: 20, max_uses: null, status: 'local_only' }] })
  })

  it('renders existing coupons', async () => {
    render(<CouponsPage />)
    expect(await screen.findByText('WELCOME20')).toBeInTheDocument()
  })

  it('opens the form and creates a coupon', async () => {
    mockCreate.mockResolvedValue({ data: { id: '2' } })
    render(<CouponsPage />)
    fireEvent.click(await screen.findByText('New Coupon'))
    fireEvent.change(screen.getByPlaceholderText('Code (e.g. WELCOME20)'), { target: { value: 'TEST10' } })
    fireEvent.change(screen.getByPlaceholderText('Value'), { target: { value: '10' } })
    fireEvent.click(screen.getByText('Create'))
    await waitFor(() => expect(mockCreate).toHaveBeenCalled())
    expect(mockCreate.mock.calls[0][0].code).toBe('TEST10')
  })

  it('blocks creation when value is missing', async () => {
    render(<CouponsPage />)
    fireEvent.click(await screen.findByText('New Coupon'))
    fireEvent.change(screen.getByPlaceholderText('Code (e.g. WELCOME20)'), { target: { value: 'TEST10' } })
    fireEvent.click(screen.getByText('Create'))
    await waitFor(() => expect(mockCreate).not.toHaveBeenCalled())
  })

  it('disables a coupon', async () => {
    mockDisable.mockResolvedValue({ data: { ok: true } })
    render(<CouponsPage />)
    fireEvent.click(await screen.findByText('WELCOME20'))
    fireEvent.click(await screen.findByText('Disable'))
    await waitFor(() => expect(mockDisable).toHaveBeenCalledWith('1'))
  })
})
