import { describe, it, expect } from 'vitest'
import React from 'react'
import { render } from '@testing-library/react'
import FlyerPreview from '../pages/admin/flyers/FlyerPreview'
import { FLYER_TEMPLATES } from '../pages/admin/flyers/templates'

describe('Flyer templates', () => {
  it('registers 10+ templates across 3 categories', () => {
    expect(FLYER_TEMPLATES.length).toBeGreaterThanOrEqual(10)
    const cats = new Set(FLYER_TEMPLATES.map((t) => t.category))
    expect(cats).toEqual(new Set(['event', 'donation', 'business']))
  })

  it('every template has a theme default of 4', () => {
    const defaultThemes = new Set(FLYER_TEMPLATES.map((t) => t.theme))
    expect(defaultThemes.size).toBe(4)
  })

  it('renders the title, subtitle, and CTA for every template', () => {
    for (const tpl of FLYER_TEMPLATES) {
      const { container } = render(
        <FlyerPreview templateId={tpl.id} theme={tpl.theme} title="Health Fair" subtitle="Free screenings" ctaText="Register" />
      )
      expect(container.textContent).toContain('Health Fair')
      expect(container.textContent).toContain('Free screenings')
      expect(container.textContent).toContain('Register')
    }
  })

  it('renders date, venue, and location when provided', () => {
    const { container } = render(
      <FlyerPreview templateId="event-banner" theme="teal" title="T" subtitle="S" ctaText="Go" date="Sat, Jun 20" venue="City Hall" location="Downtown" />
    )
    expect(container.textContent).toContain('Sat, Jun 20')
    expect(container.textContent).toContain('City Hall')
    expect(container.textContent).toContain('Downtown')
  })
})
