import React from 'react'
import { TrendingUp } from 'lucide-react'

export default function StatCard({ title, value, icon, color = "text-accent", bgColor = "bg-accent-soft", trend }) {
  return (
    <div className="stat-card group cursor-default">
      <div className="flex items-start justify-between relative z-10">
        <div className="space-y-1.5">
          <p className="text-xs font-medium text-ink-muted tracking-wide uppercase">{title}</p>
          <p className="text-3xl font-bold text-ink tracking-tight tabular-nums">{value}</p>
          {trend && (
            <div className="flex items-center gap-1 text-xs font-medium" style={{ color: trend > 0 ? '#059669' : '#dc2626' }}>
              <TrendingUp className={`h-3 w-3 ${trend > 0 ? '' : 'rotate-180'}`} />
              <span>{Math.abs(trend)}% vs last week</span>
            </div>
          )}
        </div>
        <div className={`p-2.5 rounded-xl ${bgColor} ${color} group-hover:scale-110 group-hover:rotate-3 transition-all duration-300 ease-out shadow-sm`}>
          {icon}
        </div>
      </div>
    </div>
  )
}
