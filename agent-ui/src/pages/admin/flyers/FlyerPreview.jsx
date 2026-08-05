import React, { forwardRef } from 'react'
import { FLYER_TEMPLATES } from './templates'

const FlyerPreview = forwardRef(function FlyerPreview(
  { templateId, theme, title, subtitle, ctaText, ctaUrl, date, venue, location, logo },
  ref,
) {
  const tpl = FLYER_TEMPLATES.find((t) => t.id === templateId) || FLYER_TEMPLATES[0]
  const C = tpl.component
  return (
    <div ref={ref} style={{ borderRadius: 12, overflow: 'hidden', boxShadow: '0 20px 60px rgba(0,0,0,.4)' }}>
      <C
        theme={theme || tpl.theme}
        title={title || 'Your Headline Here'}
        subtitle={subtitle || 'Your supporting message goes here.'}
        ctaText={ctaText || 'Get Started'}
        date={date || ''}
        venue={venue || ''}
        location={location || ''}
        logo={logo || ''}
        ctaUrl={ctaUrl || ''}
      />
    </div>
  )
})

export default FlyerPreview
