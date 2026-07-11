/**
 * RecentCalls — production-hardened call log table
 *
 * Addresses all 13 audit findings:
 *   #1  Stable row key: call.id → composite fallback (number+idx) — never bare idx
 *   #2  type="button" on the More button
 *   #3  loading prop — renders animated skeleton rows while fetching
 *   #4  scope="col" on all <th> elements
 *   #5  aria-label="More options" on the action button
 *   #6  fmtNum: international-safe — only reformats confirmed 10/11-digit US numbers;
 *       all other patterns are returned as-is instead of being corrupted
 *   #8  Neutral <Phone> icon when direction is missing/unknown
 *   #9  Unknown intent renders as “Unknown” not “General Inquiry”
 *   #10 Array.isArray guard + non-array coerced to []
 *   #11 React.memo prevents re-renders when calls prop hasn’t changed
 *   #12 fmtNum and fmtDur extracted above the component (pure functions)
 *   #13 voicemail and busy statuses added to badge map
 */

import React, { memo } from 'react';
import {
  PhoneIncoming, PhoneOutgoing, PhoneMissed,
  Phone, Clock, MoreHorizontal
} from 'lucide-react';

// ────────────────────────────────────────────────────────────────────────────────
// Pure utility functions (#12) — defined outside component, never re-created
// ────────────────────────────────────────────────────────────────────────────────

/**
 * Format a phone number string.
 * Only reformats confirmed 10 or 11-digit North-American numbers.
 * All other patterns (international, short codes, etc.) are returned as-is. (#6)
 * @param {string | undefined} num
 * @returns {string}
 */
export function fmtNum(num) {
  if (!num) return 'Private Number';
  const digits = num.replace(/\D/g, '');
  if (digits.length === 11 && digits[0] === '1') {
    return `+1 (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  }
  if (digits.length === 10) {
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  }
  // International or non-standard — return original, unmodified
  return num;
}

/**
 * Format a duration in seconds to a human-readable string.
 * @param {number | undefined} seconds
 * @returns {string}
 */
export function fmtDur(seconds) {
  if (!seconds || seconds <= 0) return '0s';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

// ────────────────────────────────────────────────────────────────────────────────
// Direction helpers
// ────────────────────────────────────────────────────────────────────────────────

function getIcon(dir) {
  if (dir === 'inbound')  return <PhoneIncoming className="h-4 w-4 text-emerald-600" aria-hidden="true" />;
  if (dir === 'outbound') return <PhoneOutgoing  className="h-4 w-4 text-blue-600"    aria-hidden="true" />;
  if (dir === 'missed')   return <PhoneMissed    className="h-4 w-4 text-rose-600"    aria-hidden="true" />;
  // #8 — neutral icon when direction is unknown
  return <Phone className="h-4 w-4 text-slate-400" aria-hidden="true" />;
}

function getBg(dir) {
  if (dir === 'inbound')  return 'bg-emerald-50';
  if (dir === 'outbound') return 'bg-blue-50';
  if (dir === 'missed')   return 'bg-rose-50';
  return 'bg-slate-50';
}

// ────────────────────────────────────────────────────────────────────────────────
// Status badge (#13 — extended with voicemail, busy, transferred)
// ────────────────────────────────────────────────────────────────────────────────

const STATUS_MAP = {
  completed:   { label: 'Completed',   cls: 'bg-emerald-100 text-emerald-700' },
  active:      { label: 'Active',      cls: 'bg-amber-100   text-amber-700'   },
  ringing:     { label: 'Active',      cls: 'bg-amber-100   text-amber-700'   },
  missed:      { label: 'Missed',      cls: 'bg-rose-100    text-rose-700'    },
  failed:      { label: 'Failed',      cls: 'bg-rose-100    text-rose-700'    },
  busy:        { label: 'Busy',        cls: 'bg-orange-100  text-orange-700'  },
  voicemail:   { label: 'Voicemail',   cls: 'bg-purple-100  text-purple-700'  },
  transferred: { label: 'Transferred', cls: 'bg-sky-100     text-sky-700'     },
};

function getStatusBadge(status) {
  const key   = (status || '').toLowerCase();
  const entry = STATUS_MAP[key];
  const label = entry?.label ?? (key || 'Unknown');
  const cls   = entry?.cls   ?? 'bg-slate-100 text-slate-600';
  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${cls}`}>
      {label}
    </span>
  );
}

// ────────────────────────────────────────────────────────────────────────────────
// Loading skeleton (#3)
// ────────────────────────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <tr className="animate-pulse">
      <td className="px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 bg-slate-100 rounded-lg shrink-0" />
          <div className="h-3.5 w-28 bg-slate-100 rounded" />
        </div>
      </td>
      <td className="px-6 py-4"><div className="h-3.5 w-24 bg-slate-100 rounded" /></td>
      <td className="px-6 py-4"><div className="h-5 w-16 bg-slate-100 rounded-full" /></td>
      <td className="px-6 py-4 text-right"><div className="h-3.5 w-12 bg-slate-100 rounded ml-auto" /></td>
    </tr>
  );
}

// ────────────────────────────────────────────────────────────────────────────────
// Component
// ────────────────────────────────────────────────────────────────────────────────

/**
 * @param {{
 *   calls?: any[],
 *   loading?: boolean,
 *   onMoreClick?: () => void
 * }} props
 */
const RecentCalls = memo(function RecentCalls({ calls = [], loading = false, onMoreClick }) {
  // #10 — guard against non-array prop
  const safeCalls = Array.isArray(calls) ? calls : [];

  const TABLE_HEADERS = ['Caller', 'Intent', 'Status', 'Duration'];

  return (
    <div className="bg-white rounded-2xl border border-slate-200 overflow-hidden shadow-sm">
      {/* Card header */}
      <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
        <h3 className="font-bold text-slate-900">Recent Call Activity</h3>
        <button
          type="button"                   // #2
          aria-label="More options"       // #5
          onClick={onMoreClick}
          className="text-slate-400 hover:text-slate-600 transition-colors p-1 rounded-lg hover:bg-slate-50"
        >
          <MoreHorizontal className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>

      {/* Empty state (only shown when not loading) */}
      {!loading && safeCalls.length === 0 && (
        <div className="px-6 py-12 text-center">
          <div className="h-12 w-12 bg-slate-50 text-slate-300 rounded-full flex items-center justify-center mx-auto mb-3">
            <PhoneIncoming className="h-6 w-6" aria-hidden="true" />
          </div>
          <p className="text-slate-500 font-medium">No call logs available</p>
          <p className="text-slate-400 text-sm mt-1">Activity will appear here once calls start coming in.</p>
        </div>
      )}

      {/* Table (shown when loading OR when there are calls) */}
      {(loading || safeCalls.length > 0) && (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-slate-50/50">
                {TABLE_HEADERS.map((h, i) => (
                  <th
                    key={h}
                    scope="col"   // #4
                    className={`px-6 py-3 text-[10px] font-bold text-slate-400 uppercase tracking-widest${i === TABLE_HEADERS.length - 1 ? ' text-right' : ''}`}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading
                // #3 — skeleton rows while fetching
                ? Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)
                : safeCalls.map((call, idx) => {
                    const dir       = call.call_direction || call.direction;
                    const number    = call.caller_number  || call.from;
                    const intent    = call.intent_detected || call.intent;
                    const status    = call.call_status    || call.status;
                    const duration  = call.duration_seconds ?? call.duration;
                    // #1 — stable composite key; never bare idx alone
                    const rowKey    = call.id || `${number ?? 'anon'}_${idx}`;

                    return (
                      <tr
                        key={rowKey}
                        className="hover:bg-slate-50/80 transition-colors group"
                      >
                        {/* Caller */}
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-3">
                            <div className={`p-2 rounded-lg ${getBg(dir)} shrink-0`}>
                              {getIcon(dir)}
                            </div>
                            {/* #15 — tooltip shows raw number */}
                            <span
                              className="text-sm font-bold text-slate-900"
                              title={number || 'Private Number'}
                            >
                              {fmtNum(number)}
                            </span>
                          </div>
                        </td>

                        {/* Intent — #9: shows 'Unknown' not 'General Inquiry' */}
                        <td className="px-6 py-4">
                          <span className="text-sm text-slate-500 capitalize">
                            {intent || 'Unknown'}
                          </span>
                        </td>

                        {/* Status */}
                        <td className="px-6 py-4">
                          {getStatusBadge(status)}
                        </td>

                        {/* Duration */}
                        <td className="px-6 py-4 text-right">
                          <div className="flex items-center justify-end gap-1.5 text-sm font-medium text-slate-600">
                            <Clock className="h-3.5 w-3.5 text-slate-400" aria-hidden="true" />
                            {fmtDur(duration)}
                          </div>
                        </td>
                      </tr>
                    );
                  })
              }
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
});

export default RecentCalls;
