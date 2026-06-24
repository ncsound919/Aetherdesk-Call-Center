# AetherDesk Design System

## Brand Identity
AetherDesk is a telecom-grade digital call center platform. The design communicates trust, clarity, and calm authority — essential for high-stress call center environments.

**Design principles:**
- Calm clarity — information is organized, not overwhelming
- Enterprise trust — solid colors, clear hierarchy, deliberate spacing
- Telecom heritage — deep blues, signal indicators, data-rich dashboards

## Colors

```json
{
  "ink": "#0f172a",
  "ink-muted": "#475569",
  "ink-subtle": "#94a3b8",
  "ink-tertiary": "#cbd5e1",
  "canvas": "#f1f5f9",
  "surface": "#ffffff",
  "surface-hover": "#f8fafc",
  "surface-raised": "#ffffff",
  "surface-sunken": "#e2e8f0",
  "hairline": "#e2e8f0",
  "hairline-soft": "#f1f5f9",
  "accent": "#2563eb",
  "accent-soft": "#eff6ff",
  "accent-strong": "#1d4ed8",
  "primary": "#1e3a5f",
  "primary-light": "#2d5a8e",
  "telecom-blue": "#0066cc",
  "call-green": "#059669",
  "call-green-soft": "#ecfdf5",
  "missed-red": "#dc2626",
  "missed-red-soft": "#fef2f2",
  "warning-amber": "#d97706",
  "warning-amber-soft": "#fffbeb"
}
```

## Typography

- **Font**: Inter (system-ui fallback)
- **Headings**: Weight 600, tight tracking
- **Body**: Weight 400, comfortable leading
- **Monospace**: JetBrains Mono for call IDs, durations, SIP data

## Spacing

- 4px base unit
- Card padding: 24px
- Section gaps: 20px
- Content max-width: 1440px

## Components

### Cards
White background, rounded-xl (12px), subtle shadow, hairline border. Hover states shift shadow subtly.

### Buttons
- **Primary**: Solid accent blue, white text, rounded-lg
- **Secondary**: White surface, hairline border, ink text
- **Ghost**: No border, subtle hover background
- **Danger**: Red accent for destructive actions

### Status Badges
Small pills with semantic colors:
- Active/Online: green
- Offline/Busy: amber  
- Error/Missed: red
- Completed: green
- Pending: slate

### Tables
Clean rows with hairline dividers, hover highlight, minimal visual noise.

### Navigation Sidebar
Dark navy background, white text, active state with accent blue indicator. Collapsible.
