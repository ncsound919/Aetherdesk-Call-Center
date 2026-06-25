import React from 'react'
import { useTranslation } from 'react-i18next'
import { Globe } from 'lucide-react'

export default function LanguageSwitcher() {
  const { i18n } = useTranslation()

  const toggleLanguage = () => {
    const next = i18n.language?.startsWith('es') ? 'en' : 'es'
    i18n.changeLanguage(next)
    localStorage.setItem('i18nextLng', next)
  }

  return (
    <button
      onClick={toggleLanguage}
      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium text-ink-muted hover:text-ink hover:bg-surface-hover transition-colors"
      aria-label={`Switch language to ${i18n.language?.startsWith('es') ? 'English' : 'Spanish'}`}
    >
      <Globe className="h-3.5 w-3.5" />
      {i18n.language?.startsWith('es') ? 'EN' : 'ES'}
    </button>
  )
}
