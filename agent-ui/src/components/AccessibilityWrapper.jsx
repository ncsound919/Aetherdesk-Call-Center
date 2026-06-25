import React, { useEffect, useCallback } from 'react'
import SkipToContent from './SkipToContent'

export default function AccessibilityWrapper({ children }) {
  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Escape') {
      const modals = document.querySelectorAll('.fixed.inset-0.z-50')
      if (modals.length > 0) {
        const closeBtn = modals[modals.length - 1].querySelector('button')
        closeBtn?.click()
      }
    }
  }, [])

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  return (
    <div role="application" aria-label="AetherDesk Call Center Application">
      <SkipToContent />
      {children}
    </div>
  )
}
