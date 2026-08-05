import React from 'react'

// 12 fixed templates across 3 categories, each rendered with 4 theme
// variants (48 looks). Templates are 100% client-side HTML/CSS so export
// works offline via html2canvas. Follows Canva/Figma principles: bold type,
// gradient depth, clear CTA hierarchy.

const THEMES = {
  midnight: { bg: 'linear-gradient(135deg,#05060a 0%,#10182e 100%)', accent: '#22d3ee', text: '#ffffff', sub: '#a5b4fc' },
  teal:    { bg: 'linear-gradient(135deg,#0f766e 0%,#134e4a 100%)', accent: '#2dd4bf', text: '#ffffff', sub: '#99f6e4' },
  gold:    { bg: 'linear-gradient(135deg,#78350f 0%,#451a03 100%)', accent: '#fbbf24', text: '#ffffff', sub: '#fde68a' },
  cyan:    { bg: 'linear-gradient(135deg,#164e63 0%,#083344 100%)', accent: '#38bdf8', text: '#ffffff', sub: '#bae6fd' },
}

export const FLYER_THEME_KEYS = Object.keys(THEMES)

function MetaRow({ theme, date, venue, location, metaOnly = false }) {
  const t = THEMES[theme] || THEMES.midnight
  const hasMeta = date || venue || location
  if (!hasMeta && metaOnly) return null
  const parts = [date, venue, location].filter(Boolean)
  return (
    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: metaOnly ? 24 : 20 }}>
      {parts.map((p, i) => (
        <span
          key={i}
          style={{
            background: 'rgba(0,0,0,0.22)',
            border: `1px solid ${t.accent}55`,
            color: t.sub,
            fontSize: 15,
            fontWeight: 700,
            letterSpacing: 0.5,
            padding: '8px 14px',
            borderRadius: 999,
          }}
        >
          {p}
        </span>
      ))}
    </div>
  )
}

function Logo({ src }) {
  if (!src) return null
  return (
    <img
      src={src}
      alt="logo"
      style={{ height: 44, objectFit: 'contain', marginBottom: 14, display: 'block' }}
      onError={(e) => { e.currentTarget.style.display = 'none' }}
    />
  )
}

// ── Layouts ──────────────────────────────────────────────────────────

function Banner({ theme, title, subtitle, ctaText, date, venue, location, logo }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 800, height: 400, background: t.bg, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 64px', fontFamily: 'Arial, sans-serif', position: 'relative', overflow: 'hidden' }}>
      <div style={{ position: 'absolute', top: -80, right: -80, width: 260, height: 260, borderRadius: '50%', background: `${t.accent}22`, }} />
      <Logo src={logo} />
      <div style={{ fontSize: 16, color: t.accent, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 16 }}>Overlay365</div>
      <div style={{ fontSize: 52, color: t.text, fontWeight: 900, lineHeight: 1.1, marginBottom: 12, maxWidth: 640 }}>{title}</div>
      <div style={{ fontSize: 22, color: t.sub, marginBottom: 8, maxWidth: 560 }}>{subtitle}</div>
      <MetaRow theme={theme} date={date} venue={venue} location={location} />
      <div style={{ alignSelf: 'flex-start', background: t.accent, color: '#05060a', fontWeight: 800, padding: '14px 32px', borderRadius: 999, fontSize: 18, marginTop: 22 }}>{ctaText}</div>
    </div>
  )
}

function SquareCard({ theme, title, subtitle, ctaText, date, venue, location, logo }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 600, height: 600, background: t.bg, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center', padding: 48, fontFamily: 'Arial, sans-serif', position: 'relative', overflow: 'hidden' }}>
      <div style={{ position: 'absolute', bottom: -120, right: -120, width: 300, height: 300, borderRadius: '50%', background: `${t.accent}1a` }} />
      <Logo src={logo} />
      <div style={{ width: 80, height: 80, borderRadius: '50%', background: t.accent, marginBottom: 32 }} />
      <div style={{ fontSize: 44, color: t.text, fontWeight: 900, marginBottom: 12 }}>{title}</div>
      <div style={{ fontSize: 20, color: t.sub, marginBottom: 28, maxWidth: 420 }}>{subtitle}</div>
      <MetaRow theme={theme} date={date} venue={venue} location={location} />
      <div style={{ background: t.accent, color: '#05060a', fontWeight: 800, padding: '14px 40px', borderRadius: 999, fontSize: 18, marginTop: 28 }}>{ctaText}</div>
    </div>
  )
}

function SplitLayout({ theme, title, subtitle, ctaText, date, venue, location, logo }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 800, height: 500, display: 'flex', fontFamily: 'Arial, sans-serif' }}>
      <div style={{ width: '45%', background: t.accent, color: '#05060a', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
        {logo ? <img src={logo} alt="logo" style={{ maxHeight: 80, objectFit: 'contain', marginBottom: 20 }} onError={(e) => { e.currentTarget.style.display = 'none' }} /> : <div style={{ fontSize: 96, fontWeight: 900 }}>✦</div>}
        <div style={{ fontSize: 18, fontWeight: 800, textAlign: 'center', letterSpacing: 1, textTransform: 'uppercase' }}>Overlay365</div>
      </div>
      <div style={{ width: '55%', background: t.bg, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: 40 }}>
        <div style={{ fontSize: 14, color: t.accent, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 12 }}>Overlay365</div>
        <div style={{ fontSize: 38, color: t.text, fontWeight: 900, marginBottom: 10 }}>{title}</div>
        <div style={{ fontSize: 18, color: t.sub, marginBottom: 20 }}>{subtitle}</div>
        <MetaRow theme={theme} date={date} venue={venue} location={location} />
        <div style={{ display: 'inline-block', alignSelf: 'flex-start', border: `2px solid ${t.accent}`, color: t.accent, fontWeight: 800, padding: '12px 28px', borderRadius: 999, fontSize: 16, marginTop: 22 }}>{ctaText}</div>
      </div>
    </div>
  )
}

function RibbonTop({ theme, title, subtitle, ctaText, date, venue, location, logo }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 800, height: 500, background: t.bg, fontFamily: 'Arial, sans-serif', display: 'flex', flexDirection: 'column' }}>
      <div style={{ background: t.accent, color: '#05060a', fontWeight: 800, textAlign: 'center', padding: 12, fontSize: 14, letterSpacing: 2, textTransform: 'uppercase' }}>Overlay365 · One Platform</div>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center', padding: 40 }}>
        <Logo src={logo} />
        <div style={{ fontSize: 46, color: t.text, fontWeight: 900, marginBottom: 12 }}>{title}</div>
        <div style={{ fontSize: 20, color: t.sub, marginBottom: 24, maxWidth: 520 }}>{subtitle}</div>
        <MetaRow theme={theme} date={date} venue={venue} location={location} />
        <div style={{ background: t.accent, color: '#05060a', fontWeight: 800, padding: '14px 36px', borderRadius: 999, fontSize: 18, marginTop: 24 }}>{ctaText}</div>
      </div>
    </div>
  )
}

// 8 additional layouts for variety across the three categories.

function VaultPanel({ theme, title, subtitle, ctaText, date, venue, location, logo }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 800, height: 520, background: t.bg, fontFamily: 'Arial, sans-serif', display: 'flex', flexDirection: 'column', padding: 56, justifyContent: 'space-between', position: 'relative', overflow: 'hidden' }}>
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 10, background: t.accent }} />
      <div>
        <Logo src={logo} />
        <div style={{ fontSize: 14, color: t.accent, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 14 }}>Overlay365</div>
        <div style={{ fontSize: 48, color: t.text, fontWeight: 900, lineHeight: 1.08, maxWidth: 640 }}>{title}</div>
      </div>
      <div style={{ fontSize: 22, color: t.sub, maxWidth: 560 }}>{subtitle}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 28, flexWrap: 'wrap' }}>
        <MetaRow theme={theme} date={date} venue={venue} location={location} metaOnly />
        <div style={{ background: t.accent, color: '#05060a', fontWeight: 800, padding: '14px 34px', borderRadius: 999, fontSize: 17 }}>{ctaText}</div>
      </div>
    </div>
  )
}

function AgendaStrip({ theme, title, subtitle, ctaText, date, venue, location, logo }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 800, height: 480, background: t.bg, fontFamily: 'Arial, sans-serif', padding: '48px 56px', display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
      <Logo src={logo} />
      <div style={{ fontSize: 16, color: t.accent, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 14 }}>Overlay365</div>
      <div style={{ fontSize: 46, color: t.text, fontWeight: 900, marginBottom: 10 }}>{title}</div>
      <div style={{ fontSize: 20, color: t.sub, marginBottom: 30, maxWidth: 560 }}>{subtitle}</div>
      <div style={{ display: 'flex', gap: 14, marginBottom: 30 }}>
        {[['DATE', date], ['VENUE', venue], ['LOCATION', location]].map(([label, val]) => (
          <div key={label} style={{ flex: 1, border: `1px solid ${t.accent}44`, borderRadius: 16, padding: '14px 18px', background: 'rgba(0,0,0,0.18)' }}>
            <div style={{ fontSize: 11, color: t.accent, fontWeight: 800, letterSpacing: 2, marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: 15, color: t.text, fontWeight: 700 }}>{val || 'TBA'}</div>
          </div>
        ))}
      </div>
      <div style={{ alignSelf: 'flex-start', background: t.accent, color: '#05060a', fontWeight: 800, padding: '14px 32px', borderRadius: 999, fontSize: 17 }}>{ctaText}</div>
    </div>
  )
}

function BadgeCircle({ theme, title, subtitle, ctaText, date, venue, location, logo }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 600, height: 600, background: t.bg, fontFamily: 'Arial, sans-serif', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: 48, position: 'relative', overflow: 'hidden' }}>
      <Logo src={logo} />
      <div style={{ width: 200, height: 200, borderRadius: '50%', background: t.accent, color: '#05060a', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 900, fontSize: 26, textTransform: 'uppercase', marginBottom: 26, boxShadow: `0 24px 60px ${t.accent}44` }}>{ctaText}</div>
      <div style={{ fontSize: 40, color: t.text, fontWeight: 900, marginBottom: 12 }}>{title}</div>
      <div style={{ fontSize: 19, color: t.sub, marginBottom: 20, maxWidth: 420 }}>{subtitle}</div>
      <MetaRow theme={theme} date={date} venue={venue} location={location} />
    </div>
  )
}

function OfferStrip({ theme, title, subtitle, ctaText, date, venue, location, logo }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 800, height: 400, background: t.bg, fontFamily: 'Arial, sans-serif', padding: 40, display: 'flex', flexDirection: 'column', justifyContent: 'center', border: `3px dashed ${t.accent}66`, margin: 0, boxSizing: 'border-box' }}>
      <Logo src={logo} />
      <div style={{ fontSize: 14, color: t.accent, fontWeight: 800, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 14 }}>Limited Offer</div>
      <div style={{ fontSize: 50, color: t.text, fontWeight: 900, marginBottom: 12 }}>{title}</div>
      <div style={{ fontSize: 21, color: t.sub, marginBottom: 8, maxWidth: 560 }}>{subtitle}</div>
      <MetaRow theme={theme} date={date} venue={venue} location={location} />
      <div style={{ alignSelf: 'flex-start', background: t.accent, color: '#05060a', fontWeight: 800, padding: '14px 32px', borderRadius: 999, fontSize: 18, marginTop: 22 }}>{ctaText}</div>
    </div>
  )
}

function ImpactSplit({ theme, title, subtitle, ctaText, date, venue, location, logo }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 800, height: 500, display: 'flex', fontFamily: 'Arial, sans-serif' }}>
      <div style={{ width: '50%', background: t.bg, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: 44 }}>
        <Logo src={logo} />
        <div style={{ fontSize: 14, color: t.accent, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 12 }}>Overlay365</div>
        <div style={{ fontSize: 42, color: t.text, fontWeight: 900, marginBottom: 12 }}>{title}</div>
        <div style={{ fontSize: 19, color: t.sub, marginBottom: 10 }}>{subtitle}</div>
        <MetaRow theme={theme} date={date} venue={venue} location={location} />
        <div style={{ display: 'inline-block', alignSelf: 'flex-start', background: t.accent, color: '#05060a', fontWeight: 800, padding: '13px 30px', borderRadius: 999, fontSize: 16, marginTop: 22 }}>{ctaText}</div>
      </div>
      <div style={{ width: '50%', background: t.accent, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', gap: 24, color: '#05060a', padding: 40 }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 56, fontWeight: 900 }}>100%</div>
          <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase' }}>Community</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 56, fontWeight: 900 }}>1</div>
          <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: 1, textTransform: 'uppercase' }}>Overlay365</div>
        </div>
      </div>
    </div>
  )
}

function HeroRight({ theme, title, subtitle, ctaText, date, venue, location, logo }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 800, height: 500, display: 'flex', fontFamily: 'Arial, sans-serif' }}>
      <div style={{ width: '58%', background: t.bg, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: 48 }}>
        <Logo src={logo} />
        <div style={{ fontSize: 14, color: t.accent, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 12 }}>Overlay365</div>
        <div style={{ fontSize: 46, color: t.text, fontWeight: 900, lineHeight: 1.05, marginBottom: 14 }}>{title}</div>
        <div style={{ fontSize: 19, color: t.sub, marginBottom: 20, maxWidth: 420 }}>{subtitle}</div>
        <MetaRow theme={theme} date={date} venue={venue} location={location} />
        <div style={{ display: 'inline-block', alignSelf: 'flex-start', border: `2px solid ${t.accent}`, color: t.accent, fontWeight: 800, padding: '13px 30px', borderRadius: 999, fontSize: 16, marginTop: 22 }}>{ctaText}</div>
      </div>
      <div style={{ width: '42%', background: `radial-gradient(circle at 50% 40%, ${t.accent}cc 0%, ${t.accent}33 55%, transparent 70%)`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ width: 180, height: 180, borderRadius: 40, background: t.accent, opacity: 0.9 }} />
      </div>
    </div>
  )
}

function StatBanner({ theme, title, subtitle, ctaText, date, venue, location, logo }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 800, height: 420, background: t.bg, fontFamily: 'Arial, sans-serif', padding: '48px 56px', display: 'flex', flexDirection: 'column', justifyContent: 'center', position: 'relative', overflow: 'hidden' }}>
      <div style={{ position: 'absolute', left: -60, top: -60, width: 240, height: 240, borderRadius: '50%', background: `${t.accent}1f` }} />
      <Logo src={logo} />
      <div style={{ fontSize: 15, color: t.accent, fontWeight: 700, letterSpacing: 3, textTransform: 'uppercase', marginBottom: 14 }}>Overlay365</div>
      <div style={{ fontSize: 48, color: t.text, fontWeight: 900, marginBottom: 12 }}>{title}</div>
      <div style={{ fontSize: 21, color: t.sub, marginBottom: 26, maxWidth: 560 }}>{subtitle}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 30, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {[date, venue, location].filter(Boolean).map((p, i) => (
            <span key={i} style={{ color: t.text, fontSize: 16, fontWeight: 700 }}>{p}</span>
          ))}
        </div>
        <div style={{ background: t.accent, color: '#05060a', fontWeight: 800, padding: '14px 32px', borderRadius: 999, fontSize: 18 }}>{ctaText}</div>
      </div>
    </div>
  )
}

function PledgeStrip({ theme, title, subtitle, ctaText, date, venue, location, logo }) {
  const t = THEMES[theme] || THEMES.midnight
  return (
    <div style={{ width: 800, height: 460, background: t.bg, fontFamily: 'Arial, sans-serif', display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', textAlign: 'center', padding: 48, position: 'relative', overflow: 'hidden' }}>
      <div style={{ position: 'absolute', top: 0, left: 20, right: 20, height: 8, background: `linear-gradient(90deg, ${t.accent}, transparent)` }} />
      <Logo src={logo} />
      <div style={{ width: 180, height: 10, borderRadius: 999, background: `${t.accent}33`, marginBottom: 36, overflow: 'hidden', position: 'relative' }}>
        <div style={{ width: '72%', height: '100%', background: t.accent, borderRadius: 999 }} />
      </div>
      <div style={{ fontSize: 44, color: t.text, fontWeight: 900, marginBottom: 12 }}>{title}</div>
      <div style={{ fontSize: 20, color: t.sub, marginBottom: 22, maxWidth: 500 }}>{subtitle}</div>
      <MetaRow theme={theme} date={date} venue={venue} location={location} />
      <div style={{ background: t.accent, color: '#05060a', fontWeight: 800, padding: '14px 36px', borderRadius: 999, fontSize: 18, marginTop: 26 }}>{ctaText}</div>
    </div>
  )
}

// ── Registry ─────────────────────────────────────────────────────────
// Each entry: id, category (event | donation | business), name, component, default theme
export const FLYER_TEMPLATES = [
  // Event / Community
  { id: 'event-banner',   category: 'event',    name: 'Event Banner',    component: Banner,      theme: 'midnight' },
  { id: 'event-card',     category: 'event',    name: 'Community Card',  component: SquareCard,  theme: 'teal' },
  { id: 'event-split',    category: 'event',    name: 'Split Promo',     component: SplitLayout, theme: 'gold' },
  { id: 'event-ribbon',   category: 'event',    name: 'Ribbon Top',      component: RibbonTop,   theme: 'cyan' },
  { id: 'event-agenda',   category: 'event',    name: 'Agenda Strip',    component: AgendaStrip, theme: 'midnight' },
  { id: 'event-vault',    category: 'event',    name: 'Vault Panel',     component: VaultPanel,  theme: 'teal' },
  // Donation Drive
  { id: 'donate-banner',  category: 'donation', name: 'Donation Banner', component: Banner,        theme: 'gold' },
  { id: 'donate-card',    category: 'donation', name: 'Giving Card',     component: SquareCard,    theme: 'midnight' },
  { id: 'donate-split',   category: 'donation', name: 'Impact Split',    component: ImpactSplit,   theme: 'teal' },
  { id: 'donate-pledge',  category: 'donation', name: 'Pledge Strip',    component: PledgeStrip,   theme: 'cyan' },
  { id: 'donate-badge',   category: 'donation', name: 'Giving Badge',    component: BadgeCircle,   theme: 'gold' },
  // Business Promo
  { id: 'biz-banner',     category: 'business', name: 'Business Banner', component: Banner,       theme: 'teal' },
  { id: 'biz-card',       category: 'business', name: 'Business Card',   component: SquareCard,   theme: 'midnight' },
  { id: 'biz-offer',      category: 'business', name: 'Offer Strip',     component: OfferStrip,   theme: 'cyan' },
  { id: 'biz-hero',       category: 'business', name: 'Hero Right',      component: HeroRight,    theme: 'gold' },
  { id: 'biz-stats',      category: 'business', name: 'Stat Banner',     component: StatBanner,   theme: 'teal' },
  { id: 'biz-ribbon',     category: 'business', name: 'Offer Ribbon',    component: RibbonTop,    theme: 'gold' },
]

export const FLYER_THEMES = FLYER_THEME_KEYS

export const FLYER_CATEGORIES = [
  { id: 'event', label: 'Event / Community' },
  { id: 'donation', label: 'Donation Drive' },
  { id: 'business', label: 'Business Promo' },
]
