/**
 * AetherDesk – Supabase client singleton
 *
 * Project URL : https://mpcbgtntllzixuadhkay.supabase.co
 * Env vars required:
 *   VITE_SUPABASE_URL     – your project URL
 *   VITE_SUPABASE_ANON_KEY – public anon/service key
 *
 * Usage:
 *   import { supabase } from '@/lib/supabase'
 */

import { createClient } from '@supabase/supabase-js'

const SUPABASE_URL =
  import.meta.env.VITE_SUPABASE_URL ?? 'https://mpcbgtntllzixuadhkay.supabase.co'

const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!SUPABASE_ANON_KEY) {
  console.warn(
    '[AetherDesk] VITE_SUPABASE_ANON_KEY is not set. ' +
      'Add it to agent-ui/.env — see .env.example'
  )
}

/**
 * Main singleton client.
 * - Auth tokens are persisted in localStorage under 'sb-session'
 * - Realtime is enabled for calls, agents, and chat_sessions tables
 */
export const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY ?? '', {
  auth: {
    persistSession: true,
    storageKey: 'sb-session',
    autoRefreshToken: true,
    detectSessionInUrl: true,
    flowType: 'pkce',
  },
  realtime: {
    params: {
      eventsPerSecond: 10,
    },
  },
  global: {
    headers: {
      'x-application': 'aetherdesk-agent-ui',
    },
  },
})

// ─── Typed table helpers ────────────────────────────────────────────────────
// Wrap raw supabase.from() calls so TypeScript (and JSDoc) consumers
// get table-scoped query builders without a generated types file.

/** @returns {import('@supabase/supabase-js').SupabaseQueryBuilder} */
export const db = {
  tenants:           () => supabase.from('tenants'),
  agents:            () => supabase.from('agents'),
  calls:             () => supabase.from('calls'),
  leads:             () => supabase.from('leads'),
  scripts:           () => supabase.from('scripts'),
  qa_scores:         () => supabase.from('qa_scores'),
  qa_rubrics:        () => supabase.from('qa_rubrics'),
  wfm_shifts:        () => supabase.from('wfm_shifts'),
  chat_sessions:     () => supabase.from('chat_sessions'),
  chat_messages:     () => supabase.from('chat_messages'),
  sms_log:           () => supabase.from('sms_log'),
  billing:           () => supabase.from('billing'),
  integrations:      () => supabase.from('integrations'),
  api_keys:          () => supabase.from('api_keys'),
  webhooks:          () => supabase.from('webhooks'),
  voice_profiles:    () => supabase.from('voice_profiles'),
  ai_experiments:    () => supabase.from('ai_experiments'),
  training_courses:  () => supabase.from('training_courses'),
  cdp_customers:     () => supabase.from('cdp_customers'),
  audit_log:         () => supabase.from('audit_log'),
}

// ─── Storage bucket helpers ──────────────────────────────────────────────────
export const storage = {
  recordings: () => supabase.storage.from('call-recordings'),
  avatars:    () => supabase.storage.from('avatars'),
  leads:      () => supabase.storage.from('lead-imports'),
}

// ─── Realtime channel factory ─────────────────────────────────────────────────
/**
 * Creates a named Realtime channel scoped to a tenant.
 * @param {string} name   - logical channel name  (e.g. 'calls')
 * @param {string} tenantId
 * @returns {import('@supabase/supabase-js').RealtimeChannel}
 */
export function tenantChannel(name, tenantId) {
  return supabase.channel(`${name}:${tenantId}`)
}

export default supabase
