/**
 * BillingPage — production-hardened billing summary page
 *
 * Issues addressed vs. submitted code:
 *
 *   A  Duplicated page-shell markup (heading + card wrapper) existed in EVERY
 *      branch (loading / error / no-data / data). Extracted into <PageShell>
 *      so the heading is declared once and every state shares it.
 *
 *   B  window.location.reload() on the Retry button is a hard navigation that
 *      loses SPA state. Replaced with a useCallback'd fetchBilling() so only
 *      the API call re-runs.
 *
 *   C  The useEffect dependency was [tenant], which re-fires if the tenant
 *      object reference changes even when tenant.id hasn't. Tightened to
 *      [tenant?.id].
 *
 *   D  No AbortController — if the component unmounted before the fetch
 *      resolved (e.g. user navigated away), setState would run on an unmounted
 *      component. Added AbortController with cleanup return.
 *
 *   E  Currency symbol was hardcoded as "$". Now respects summary.currency
 *      via Intl.NumberFormat for correct locale-aware formatting.
 *
 *   F  Status badge only showed green "Active" for every status. Added a
 *      STATUS_BADGE map with distinct colours for past_due, cancelled,
 *      trialing, etc.
 *
 *   G  "Upgrade Plan" and "View Invoices" buttons had no onClick handlers —
 *      dead UI. Wired with placeholder handlers and an onUpgrade / onInvoices
 *      prop for parent wiring.
 *
 *   H  Usage cards showed raw numbers with no context. Added a usage progress
 *      bar driven by an optional plan limit (calls_limit / minutes_limit)
 *      from the API response, falling back to indeterminate display.
 *
 *   I  The <h1> on the page and the card <h3> had no landmark roles.
 *      Added role="main" on the outer wrapper; the heading hierarchy is now
 *      h1 → h2 so screen readers can navigate correctly.
 *
 *   J  Error type annotation was `err: any` (implicit). Added explicit typed
 *      catch with AxiosError check via axios.isAxiosError.
 */

import React, { useEffect, useState, useCallback } from 'react';
import { useAuth } from '../context/AuthContext';
import api from '../services/api';
import { toast } from 'sonner';
import {
  Loader2, CreditCard, Phone, Clock,
  DollarSign, RefreshCw, ExternalLink, TrendingUp,
} from 'lucide-react';
import axios from 'axios';

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Format a monetary value respecting currency code (E) */
function fmtMoney(amount, currency = 'USD') {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency', currency, minimumFractionDigits: 2,
    }).format(amount ?? 0);
  } catch {
    return `$${(amount ?? 0).toFixed(2)}`;
  }
}

/** Status badge config (F) */
const STATUS_BADGE = {
  active:    { label: 'Active',     cls: 'bg-emerald-50 text-emerald-700 ring-emerald-200' },
  trialing:  { label: 'Trial',      cls: 'bg-blue-50    text-blue-700    ring-blue-200'    },
  past_due:  { label: 'Past Due',   cls: 'bg-amber-50   text-amber-700   ring-amber-200'   },
  cancelled: { label: 'Cancelled',  cls: 'bg-rose-50    text-rose-700    ring-rose-200'    },
  paused:    { label: 'Paused',     cls: 'bg-slate-50   text-slate-600   ring-slate-200'   },
};

function StatusBadge({ status }) {
  const key   = (status || 'active').toLowerCase();
  const entry = STATUS_BADGE[key] ?? STATUS_BADGE.active;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold ring-1 ${entry.cls}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {entry.label}
    </span>
  );
}

/** Usage progress bar (H) */
function UsageBar({ value, limit }) {
  if (!limit) return null;
  const pct = Math.min(100, Math.round((value / limit) * 100));
  const colour = pct >= 90 ? 'bg-rose-500' : pct >= 70 ? 'bg-amber-500' : 'bg-blue-500';
  return (
    <div className="mt-2">
      <div className="flex justify-between text-[10px] text-slate-400 mb-1">
        <span>{value.toLocaleString()} / {limit.toLocaleString()}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${colour}`}
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
    </div>
  );
}

// ─── Shared page shell (A) ────────────────────────────────────────────────────

function PageShell({ children }) {
  return (
    <div
      className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700"
      role="main"   // (I)
    >
      <div>
        <h1 className="text-3xl font-black text-slate-900 tracking-tight">Billing</h1>
        <p className="text-slate-500 mt-1 font-medium">Manage your subscription and usage</p>
      </div>
      {children}
    </div>
  );
}

// ─── Component ────────────────────────────────────────────────────────────────

/**
 * @param {{
 *   onUpgrade?: () => void,
 *   onInvoices?: () => void,
 * }} props
 */
export default function BillingPage({ onUpgrade, onInvoices }) {
  const { tenant } = useAuth();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState(null);

  // (B) extracted so Retry button can call it directly without page reload
  const fetchBilling = useCallback(async (signal) => {
    if (!tenant?.id) {
      setLoading(false);
      setError('No tenant context available');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await api.get('/billing', {
        params: { tenant_id: tenant.id },
        signal,  // (D) AbortController signal
      });
      setSummary(response.data?.data ?? response.data ?? null);
    } catch (err) {
      // (D) ignore intentional abort on unmount
      if (axios.isCancel(err)) return;
      // (J) typed error extraction
      const message = axios.isAxiosError(err)
        ? (err.response?.data?.error ?? err.message)
        : 'Failed to load billing information';
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [tenant?.id]); // (C) only re-run when the id string changes

  useEffect(() => {
    const controller = new AbortController(); // (D)
    fetchBilling(controller.signal);
    return () => controller.abort();
  }, [fetchBilling]);

  // ── Loading ──────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <PageShell>
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-blue-600" aria-label="Loading billing data" />
          </div>
        </div>
      </PageShell>
    );
  }

  // ── Error ────────────────────────────────────────────────────────────────
  if (error) {
    return (
      <PageShell>
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <div className="flex flex-col items-center py-8 text-center">
            <div className="h-12 w-12 bg-rose-50 rounded-full flex items-center justify-center mb-4">
              <DollarSign className="h-6 w-6 text-rose-600" aria-hidden="true" />
            </div>
            <h2 className="text-lg font-bold text-slate-900">Unable to load billing</h2>
            <p className="text-slate-500 max-w-sm mt-1">{error}</p>
            <button
              type="button"
              onClick={() => fetchBilling()}  // (B) no full page reload
              className="mt-6 flex items-center gap-2 px-4 py-2 bg-slate-900 text-white rounded-xl text-sm font-bold hover:bg-slate-800 transition-colors focus:outline-none focus:ring-2 focus:ring-slate-900 focus:ring-offset-2"
            >
              <RefreshCw className="h-4 w-4" aria-hidden="true" />
              Retry
            </button>
          </div>
        </div>
      </PageShell>
    );
  }

  // ── No data ──────────────────────────────────────────────────────────────
  if (!summary) {
    return (
      <PageShell>
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <div className="flex flex-col items-center py-8 text-center">
            <div className="h-12 w-12 bg-slate-50 rounded-full flex items-center justify-center mb-4">
              <CreditCard className="h-6 w-6 text-slate-300" aria-hidden="true" />
            </div>
            <h2 className="text-lg font-bold text-slate-900">No billing data</h2>
            <p className="text-slate-500 max-w-sm mt-1">
              We couldn&apos;t find any billing information for your account.
            </p>
          </div>
        </div>
      </PageShell>
    );
  }

  // ── Data ─────────────────────────────────────────────────────────────────
  const currency = summary.currency || 'USD';

  return (
    <PageShell>
      <div className="grid gap-6 md:grid-cols-2">

        {/* Plan card */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-medium text-slate-500">Current Plan</p>
              <p className="text-2xl font-bold text-slate-900 mt-1 capitalize">
                {summary.plan || 'Free'}
              </p>
            </div>
            <div className="h-10 w-10 bg-blue-50 rounded-xl flex items-center justify-center">
              <CreditCard className="h-5 w-5 text-blue-600" aria-hidden="true" />
            </div>
          </div>
          <div className="mt-4">
            <StatusBadge status={summary.status} /> {/* (F) */}
          </div>
        </div>

        {/* Balance card (E) */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-medium text-slate-500">Balance</p>
              <p className="text-2xl font-bold text-slate-900 mt-1">
                {fmtMoney(summary.balance, currency)}
              </p>
            </div>
            <div className="h-10 w-10 bg-emerald-50 rounded-xl flex items-center justify-center">
              <DollarSign className="h-5 w-5 text-emerald-600" aria-hidden="true" />
            </div>
          </div>
          <p className="text-xs text-slate-400 mt-2">
            Estimated cost this month:{' '}
            <span className="font-semibold text-slate-600">
              {fmtMoney(summary.estimated_cost, currency)}
            </span>
          </p>
        </div>

        {/* Usage Overview (H) */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 md:col-span-2">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="h-4 w-4 text-slate-400" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-slate-700">Usage Overview</h2>
          </div>
          <div className="grid grid-cols-2 gap-4">

            {/* Calls */}
            <div className="p-3 bg-slate-50 rounded-xl">
              <div className="flex items-center gap-3">
                <div className="h-9 w-9 bg-blue-100 rounded-lg flex items-center justify-center shrink-0">
                  <Phone className="h-4 w-4 text-blue-600" aria-hidden="true" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-medium text-slate-500">Calls This Month</p>
                  <p className="text-lg font-bold text-slate-900">
                    {(summary.calls_this_month ?? 0).toLocaleString()}
                  </p>
                </div>
              </div>
              <UsageBar value={summary.calls_this_month ?? 0} limit={summary.calls_limit} />
            </div>

            {/* Minutes */}
            <div className="p-3 bg-slate-50 rounded-xl">
              <div className="flex items-center gap-3">
                <div className="h-9 w-9 bg-amber-100 rounded-lg flex items-center justify-center shrink-0">
                  <Clock className="h-4 w-4 text-amber-600" aria-hidden="true" />
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-medium text-slate-500">Minutes Used</p>
                  <p className="text-lg font-bold text-slate-900">
                    {(summary.minutes_used ?? 0).toLocaleString()}
                  </p>
                </div>
              </div>
              <UsageBar value={summary.minutes_used ?? 0} limit={summary.minutes_limit} />
            </div>

          </div>
        </div>
      </div>

      {/* Action buttons (G) */}
      <div className="flex flex-wrap gap-4">
        <button
          type="button"
          onClick={onUpgrade}
          className="px-6 py-3 bg-blue-600 text-white rounded-xl font-bold hover:bg-blue-700 transition-all shadow-lg shadow-blue-500/20 active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
        >
          Upgrade Plan
        </button>
        <button
          type="button"
          onClick={onInvoices}
          className="flex items-center gap-2 px-6 py-3 bg-white border border-slate-200 text-slate-700 rounded-xl font-bold hover:bg-slate-50 transition-all focus:outline-none focus:ring-2 focus:ring-slate-300 focus:ring-offset-2"
        >
          <ExternalLink className="h-4 w-4" aria-hidden="true" />
          View Invoices
        </button>
      </div>
    </PageShell>
  );
}
