import React from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  LayoutDashboard, Users, PhoneCall, Mic2, CreditCard,
  Users2, FileText, Settings, LogOut, BarChart3,
  CalendarClock, ClipboardCheck,
  Activity, BrainCircuit, Heart, Plug,
  MessageSquare, MessageCircle, Sparkles, GitBranch,
  Tv, GraduationCap, Clock, Shield, Lock, Activity as ReliabilityIcon,
  Radio, Star, Code, Globe,
  Cpu, Key, Building2, Palette, Rocket
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'

export default function Sidebar({ open, onClose }) {
  const { t } = useTranslation()
  const location = useLocation()
  const navigate = useNavigate()
  const { logout } = useAuth()

  const menuItems = [
    { icon: LayoutDashboard, label: t('nav.dashboard'), path: '/' },
    { icon: BarChart3, label: t('nav.analytics'), path: '/analytics' },
    { icon: Users, label: t('nav.agents'), path: '/agents' },
    { icon: PhoneCall, label: t('nav.callLogs'), path: '/calls' },
    { icon: Mic2, label: t('nav.voice'), path: '/voice-cloning' },
    { icon: CreditCard, label: t('nav.billing'), path: '/billing' },
    { icon: Users2, label: t('nav.leads'), path: '/leads' },
    { icon: FileText, label: t('nav.scripts'), path: '/scripts' },
    { icon: CalendarClock, label: t('nav.wfm'), path: '/wfm' },
    { icon: ClipboardCheck, label: t('nav.qa'), path: '/qa' },
    { icon: Activity, label: t('nav.voiceQuality'), path: '/voice-quality' },
    { icon: BrainCircuit, label: t('nav.aiOps'), path: '/ai-ops' },
    { icon: Heart, label: t('nav.cx'), path: '/cx' },
    { icon: Plug, label: t('nav.integrations'), path: '/integrations' },
    { icon: MessageSquare, label: t('nav.sms'), path: '/sms' },
    { icon: MessageCircle, label: t('nav.chat'), path: '/chat' },
    { icon: Sparkles, label: t('nav.aiWorkspace'), path: '/ai-workspace' },
    { icon: GitBranch, label: t('nav.dataGovernance'), path: '/data-governance' },
    { icon: Tv, label: t('nav.supervisor'), path: '/supervisor' },
    { icon: Clock, label: t('nav.wfmMetrics'), path: '/wfm-metrics' },
    { icon: GraduationCap, label: t('nav.training'), path: '/training' },
    { icon: Shield, label: t('nav.businessContinuity'), path: '/business-continuity' },
    { icon: Lock, label: t('nav.security'), path: '/security-hardening' },
    { icon: ReliabilityIcon, label: t('nav.reliability'), path: '/reliability' },
    { icon: Radio, label: t('nav.failover'), path: '/failover' },
    { icon: Star, label: t('nav.conversationQuality'), path: '/conversation-quality' },
    { icon: Code, label: t('nav.apiVersions'), path: '/api-versions' },
    { icon: Globe, label: t('nav.customerPortal'), path: '/customer-portal' },
    { icon: Cpu, label: t('nav.aiPlatform'), path: '/ai-platform' },
    { icon: Key, label: t('nav.developer'), path: '/developer' },
    { icon: Users, label: t('nav.cdp'), path: '/cdp' },
    { icon: Building2, label: t('nav.verticals'), path: '/verticals' },
    { icon: Palette, label: t('nav.branding'), path: '/branding' },
    { icon: Rocket, label: t('nav.onboarding'), path: '/onboarding' },
    { icon: Settings, label: t('nav.settings'), path: '/settings' },
  ]

  const isActive = (p) => p === '/' ? location.pathname === '/' : location.pathname.startsWith(p)

  return (
    <>
      {open && <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-40 lg:hidden" onClick={onClose} />}
      <aside role="navigation" aria-label={t('accessibility.navigationMenu')} className={`fixed lg:static inset-y-0 left-0 w-64 bg-gradient-to-b from-[#0c1628] via-[#0f1d30] to-[#0f1d30] transform ${open ? 'translate-x-0' : '-translate-x-full'} lg:translate-x-0 transition-transform duration-200 ease-in-out z-50 flex flex-col border-r border-white/5`}>
        
        {/* Logo */}
        <div className="h-16 flex items-center gap-3 px-5 border-b border-white/[0.06] shrink-0">
          <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-accent to-blue-400 flex items-center justify-center shadow-lg shadow-accent/25">
            <PhoneCall className="h-4 w-4 text-white" />
          </div>
          <div>
            <span className="text-base font-semibold text-white tracking-tight">{t('app.name')}</span>
            <p className="text-[10px] text-white/30 font-medium tracking-wider uppercase">{t('app.tagline')}</p>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-4 px-3 space-y-0.5 overflow-y-auto">
          <p className="px-3 pb-2 text-[10px] font-semibold text-white/20 uppercase tracking-widest">{t('nav.menu')}</p>
          {menuItems.map((item) => {
            const Icon = item.icon
            const active = isActive(item.path)
            return (
              <button
                key={item.path}
                onClick={() => { navigate(item.path); onClose?.() }}
                role="link"
                aria-label={item.label}
                className={`nav-glow w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 overflow-hidden ${
                  active
                    ? 'text-white shadow-sm'
                    : 'text-white/40 hover:text-white/70'
                }`}
              >
                {active && (
                  <div className="absolute inset-0 bg-gradient-to-r from-accent/20 via-accent/10 to-transparent" />
                )}
                {active && (
                  <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-full bg-accent shadow-sm shadow-accent/50" />
                )}
                <Icon className={`h-4 w-4 shrink-0 relative z-10 ${active ? 'text-accent' : ''}`} />
                <span className="relative z-10">{item.label}</span>
                {active && (
                  <div className="ml-auto relative z-10 h-1.5 w-1.5 rounded-full bg-accent glow-ring" />
                )}
              </button>
            )
          })}
        </nav>

        {/* User */}
        <div className="p-4 border-t border-white/[0.06] shrink-0" role="complementary" aria-label={t('accessibility.userInfo')}>
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-full bg-gradient-to-br from-accent to-blue-500 flex items-center justify-center shadow-inner">
              <span className="text-white text-xs font-bold">AD</span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-white/80 truncate">{t('nav.admin', 'Admin')}</p>
              <p className="text-xs text-white/30 truncate">admin@aetherdesk.com</p>
            </div>
            <button onClick={logout} className="p-1.5 rounded-lg text-white/20 hover:text-white/60 hover:bg-white/5 transition-colors">
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>
    </>
  )
}
