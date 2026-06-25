import React from 'react'
import { useTranslation } from 'react-i18next'

export default function SkipToContent() {
  const { t } = useTranslation()

  return (
    <a
      href="#main-content"
      className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:bg-accent focus:text-white focus:rounded-lg focus:text-sm focus:font-medium focus:shadow-lg focus:outline-none"
    >
      {t('accessibility.skipToContent')}
    </a>
  )
}
