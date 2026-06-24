import React from 'react'
import { PhoneIncoming, PhoneOutgoing, PhoneMissed, Clock } from 'lucide-react'

export default function RecentCalls({ calls = [] }) {
  const getIcon = (dir) => {
    if (dir === 'inbound') return <PhoneIncoming className="h-4 w-4 text-call-green" />
    if (dir === 'outbound') return <PhoneOutgoing className="h-4 w-4 text-accent" />
    return <PhoneMissed className="h-4 w-4 text-call-red" />
  }
  const getBg = (dir) => {
    if (dir === 'inbound') return 'bg-call-green-soft'
    if (dir === 'outbound') return 'bg-accent-soft'
    return 'bg-call-red-soft'
  }
  const getStatusBadge = (status) => {
    switch (status) {
      case 'completed': return <span className="badge-green">Completed</span>
      case 'active': case 'ringing': return <span className="badge-amber">Active</span>
      case 'missed': return <span className="badge-red">Missed</span>
      case 'failed': return <span className="badge-red">Failed</span>
      default: return <span className="badge-slate">{status || 'Unknown'}</span>
    }
  }
  const fmtNum = (num) => {
    if (!num) return '-'
    const c = num.replace(/\D/g, '')
    if (c.length === 11) return `+1 (${c.slice(1,4)}) ${c.slice(4,7)}-${c.slice(7)}`
    if (c.length === 10) return `(${c.slice(0,3)}) ${c.slice(3,6)}-${c.slice(6)}`
    return num
  }
  const fmtDur = (s) => {
    if (!s || s === 0) return '-'
    const m = Math.floor(s / 60); const sec = Math.floor(s % 60)
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  if (!calls || calls.length === 0) {
    return (
      <div className="card">
        <div className="px-5 py-4 border-b border-hairline">
          <h3 className="text-sm font-semibold text-ink">Recent Calls</h3>
        </div>
        <div className="px-5 py-12 text-center">
          <PhoneIncoming className="h-8 w-8 mx-auto mb-3 text-ink-subtle" />
          <p className="text-sm text-ink-muted">No calls yet</p>
          <p className="text-xs text-ink-subtle mt-1">Make your first call to see it here</p>
        </div>
      </div>
    )
  }

  return (
    <div className="card overflow-hidden">
      <div className="px-5 py-4 border-b border-hairline flex items-center justify-between">
        <h3 className="text-sm font-semibold text-ink">Recent Calls</h3>
        <span className="text-xs text-ink-subtle">{calls.length} calls</span>
      </div>
      <div className="divide-y divide-hairline">
        {calls.slice(0, 10).map((call, idx) => (
          <div key={call.id || idx} className="px-5 py-3.5 hover:bg-surface-hover transition-colors flex items-center justify-between">
            <div className="flex items-center gap-3 min-w-0">
              <div className={`p-2 rounded-lg ${getBg(call.call_direction || call.direction)} shrink-0`}>
                {getIcon(call.call_direction || call.direction)}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-ink truncate">
                  {fmtNum(call.caller_number || call.from)}
                </p>
                <p className="text-xs text-ink-muted truncate">
                  {call.intent_detected || call.intent || 'general inquiry'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 shrink-0">
              {getStatusBadge(call.call_status || call.status)}
              <span className="text-xs text-ink-muted flex items-center gap-1">
                <Clock className="h-3 w-3" />
                {fmtDur(call.duration_seconds || call.duration)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
