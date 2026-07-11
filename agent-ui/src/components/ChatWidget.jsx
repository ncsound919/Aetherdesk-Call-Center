/**
 * ChatWidget — production-hardened floating chat widget
 *
 * Addresses all 24 audit findings:
 *   #1  tenantId used in API headers via apiClient built from apiBaseUrl
 *   #2  Polling merges/deduplicates by id — no overwrite of local messages
 *   #3  handleSend shows error toast + rolls back optimistic message
 *   #4  Typing indicator driven by poll — checks for agent 'typing' event type
 *   #5  handleStart disables button + shows loading state
 *   #6  sessionId persisted in localStorage; reconnects on mount
 *   #7  Initial message NOT added optimistically; server response drives it
 *   #8  Polling interval 5s; pauses when document is hidden (#visibilitychange)
 *   #9  Auto-scroll only when user is near bottom or sends a message
 *   #10 Close button has aria-label; inputs have id + htmlFor associations
 *   #12 API client built from apiBaseUrl prop with tenantId header
 *   #13 tenantId sent as X-Tenant-ID header on every request
 *   #15 Send button disabled while request in flight
 *   #19 onClose callback prop
 *   #22 Inputs disabled during submission
 *   #23 Temp message IDs use crypto.randomUUID()
 *   #24 Network error banner shown when polling fails consecutively
 */

import React, { useState, useRef, useEffect, useCallback } from 'react';
import axios from 'axios';

// ─── Styles (object kept for embeddable widget portability) ──────────────────
const S = {
  container: {
    position: 'fixed', bottom: 20, right: 20, zIndex: 9999,
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },
  fab: {
    width: 56, height: 56, borderRadius: '50%', backgroundColor: '#6366f1',
    color: '#fff', border: 'none', cursor: 'pointer', display: 'flex',
    alignItems: 'center', justifyContent: 'center',
    boxShadow: '0 4px 12px rgba(99,102,241,0.4)', transition: 'transform 0.2s',
  },
  panel: {
    position: 'absolute', bottom: 72, right: 0, width: 360, height: 520,
    backgroundColor: '#fff', borderRadius: 16,
    boxShadow: '0 8px 32px rgba(0,0,0,0.15)', display: 'flex',
    flexDirection: 'column', overflow: 'hidden',
  },
  header: {
    padding: '16px 20px', backgroundColor: '#6366f1', color: '#fff',
    fontWeight: 600, fontSize: 15, display: 'flex',
    justifyContent: 'space-between', alignItems: 'center',
  },
  formContainer: {
    padding: 24, display: 'flex', flexDirection: 'column',
    gap: 12, flex: 1, justifyContent: 'center', overflowY: 'auto',
  },
  label: { fontSize: 13, fontWeight: 500, color: '#475569', display: 'block', marginBottom: 4 },
  input: {
    width: '100%', padding: '10px 14px', border: '1px solid #e2e8f0',
    borderRadius: 8, fontSize: 14, outline: 'none', boxSizing: 'border-box',
  },
  textarea: {
    width: '100%', padding: '10px 14px', border: '1px solid #e2e8f0',
    borderRadius: 8, fontSize: 14, outline: 'none', resize: 'none',
    minHeight: 60, boxSizing: 'border-box',
  },
  button: {
    padding: '10px 20px', backgroundColor: '#6366f1', color: '#fff',
    border: 'none', borderRadius: 8, cursor: 'pointer', fontWeight: 500, fontSize: 14,
  },
  buttonDisabled: { opacity: 0.6, cursor: 'not-allowed' },
  messages: {
    flex: 1, overflowY: 'auto', padding: 16,
    display: 'flex', flexDirection: 'column', gap: 8,
  },
  bubbleVisitor: {
    alignSelf: 'flex-end', backgroundColor: '#6366f1', color: '#fff',
    padding: '8px 14px', borderRadius: '12px 12px 4px 12px',
    maxWidth: '80%', fontSize: 14, lineHeight: 1.4,
  },
  bubbleAgent: {
    alignSelf: 'flex-start', backgroundColor: '#f1f5f9', color: '#1e293b',
    padding: '8px 14px', borderRadius: '12px 12px 12px 4px',
    maxWidth: '80%', fontSize: 14, lineHeight: 1.4,
  },
  inputRow: {
    display: 'flex', gap: 8, padding: '12px 16px',
    borderTop: '1px solid #e2e8f0',
  },
  msgInput: {
    flex: 1, padding: '8px 12px', border: '1px solid #e2e8f0',
    borderRadius: 20, fontSize: 14, outline: 'none',
  },
  sendBtn: {
    width: 36, height: 36, borderRadius: '50%', backgroundColor: '#6366f1',
    color: '#fff', border: 'none', cursor: 'pointer',
    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
  },
  closeBtn: {
    background: 'none', border: 'none', color: '#fff',
    cursor: 'pointer', fontSize: 20, lineHeight: 1, padding: 0,
  },
  errorBanner: {
    backgroundColor: '#fef2f2', color: '#991b1b',
    fontSize: 12, padding: '6px 16px', textAlign: 'center',
    borderBottom: '1px solid #fecaca',
  },
  typingBubble: {
    alignSelf: 'flex-start', backgroundColor: '#f1f5f9', color: '#64748b',
    padding: '8px 14px', borderRadius: '12px 12px 12px 4px',
    fontSize: 13, fontStyle: 'italic', opacity: 0.8,
  },
};

// ─── Storage keys ───────────────────────────────────────────────────────────
const STORAGE_KEY_SESSION = 'cw_session_id';
const STORAGE_KEY_VISITOR  = 'cw_visitor';    // { name, email }

// ─── Unique temp ID for optimistic messages (#23) ──────────────────────────
function tempId() {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? `temp_${crypto.randomUUID()}`
    : `temp_${Date.now()}_${Math.random()}`;
}

// ─── Merge messages by id — no duplicates (#2) ───────────────────────────
function mergeMessages(existing, incoming) {
  const map = new Map(existing.map(m => [m.id, m]));
  incoming.forEach(m => {
    if (!String(m.id).startsWith('temp_')) map.set(m.id, m);
  });
  // Remove temp messages whose content now exists in server messages
  const serverContents = new Set(incoming.map(m => m.content));
  existing
    .filter(m => String(m.id).startsWith('temp_') && serverContents.has(m.content))
    .forEach(m => map.delete(m.id));
  return Array.from(map.values())
    .sort((a, b) => new Date(a.created_at ?? 0) - new Date(b.created_at ?? 0));
}

// ─── Component ────────────────────────────────────────────────────────────────

/**
 * @param {{
 *   tenantId: string,
 *   apiBaseUrl: string,
 *   onClose?: () => void
 * }} props
 */
export default function ChatWidget({ tenantId, apiBaseUrl, onClose }) {
  // ── Build a scoped API client from props (#1, #12, #13) ──────────────────
  const apiRef = useRef(null);
  useEffect(() => {
    apiRef.current = axios.create({
      baseURL: apiBaseUrl,
      headers: { 'X-Tenant-ID': tenantId },
    });
  }, [apiBaseUrl, tenantId]);

  // ── UI state ──────────────────────────────────────────────────────────
  const [open,         setOpen]         = useState(false);
  const [registered,   setRegistered]   = useState(false);
  const [name,         setName]         = useState('');
  const [email,        setEmail]        = useState('');
  const [message,      setMessage]      = useState('');
  const [sessionId,    setSessionId]    = useState(null);
  const [messages,     setMessages]     = useState([]);
  const [typing,       setTyping]       = useState(false);
  const [starting,     setStarting]     = useState(false);  // #5
  const [sending,      setSending]      = useState(false);  // #15
  const [netError,     setNetError]     = useState(false);  // #24
  const [errorMsg,     setErrorMsg]     = useState(null);   // inline error

  const messagesEndRef  = useRef(null);
  const messagesBoxRef  = useRef(null);
  const pollRef         = useRef(null);
  const pollFailsRef    = useRef(0);
  const shouldScrollRef = useRef(true); // tracks whether user is near bottom

  // ── Restore session on mount (#6) ────────────────────────────────────
  useEffect(() => {
    const sid = localStorage.getItem(STORAGE_KEY_SESSION);
    const vis = JSON.parse(localStorage.getItem(STORAGE_KEY_VISITOR) ?? 'null');
    if (sid && vis?.name) {
      setSessionId(sid);
      setName(vis.name);
      setEmail(vis.email ?? '');
      setRegistered(true);
    }
  }, []);

  // ── Smart scroll: only auto-scroll when near bottom (#9) ─────────────────
  const handleScroll = useCallback(() => {
    const el = messagesBoxRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    shouldScrollRef.current = nearBottom;
  }, []);

  useEffect(() => {
    if (shouldScrollRef.current && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // ── Polling: visibility-aware, deduplicating (#2, #8, #24) ──────────────
  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  const startPolling = useCallback((sid) => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      if (document.visibilityState === 'hidden') return; // pause when tab hidden (#8)
      try {
        const res = await apiRef.current.get(`/api/v1/chat/sessions/${sid}/messages`);
        const incoming = Array.isArray(res.data?.data) ? res.data.data
          : Array.isArray(res.data) ? res.data : [];

        setMessages(prev => mergeMessages(prev, incoming)); // merge, not overwrite (#2)

        // Typing indicator: check for agent typing events (#4)
        const isTyping = incoming.some(m => m.type === 'agent_typing');
        setTyping(isTyping);

        pollFailsRef.current = 0;
        setNetError(false);
      } catch {
        pollFailsRef.current++;
        if (pollFailsRef.current >= 3) setNetError(true); // show banner after 3 failures (#24)
      }
    }, 5000); // 5s interval (#8)
  }, [stopPolling]);

  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible' && open && sessionId) {
        // Resume by kicking off an immediate poll
        apiRef.current?.get(`/api/v1/chat/sessions/${sessionId}/messages`)
          .then(res => {
            const incoming = Array.isArray(res.data?.data) ? res.data.data
              : Array.isArray(res.data) ? res.data : [];
            setMessages(prev => mergeMessages(prev, incoming));
          })
          .catch(() => {});
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => document.removeEventListener('visibilitychange', handleVisibility);
  }, [open, sessionId]);

  useEffect(() => {
    if (open && sessionId) {
      startPolling(sessionId);
    } else {
      stopPolling();
    }
    return stopPolling;
  }, [open, sessionId, startPolling, stopPolling]);

  // ── handleStart (#5, #6, #7) ──────────────────────────────────────────
  const handleStart = useCallback(async (e) => {
    e.preventDefault();
    if (!name.trim() || starting) return;
    setStarting(true);
    setErrorMsg(null);
    try {
      const res = await apiRef.current.post('/api/v1/chat/sessions', {
        visitor_id:      `visitor_${Date.now()}`,
        visitor_name:    name,
        visitor_email:   email || undefined,
        initial_message: message || undefined,
        tenant_id:       tenantId,
      });
      const sid = res.data?.data?.id ?? res.data?.id;
      setSessionId(sid);
      setRegistered(true);
      // Persist for reconnection (#6)
      localStorage.setItem(STORAGE_KEY_SESSION, sid);
      localStorage.setItem(STORAGE_KEY_VISITOR, JSON.stringify({ name, email }));
      // Do NOT add optimistic initial message — next poll will fetch it (#7)
      setMessage('');
    } catch (err) {
      setErrorMsg(err.response?.data?.error ?? 'Failed to start chat. Please try again.');
    } finally {
      setStarting(false);
    }
  }, [name, email, message, tenantId, starting]);

  // ── handleSend (#3, #15, #22, #23) ────────────────────────────────────
  const handleSend = useCallback(async (e) => {
    e.preventDefault();
    const content = message.trim();
    if (!content || !sessionId || sending) return;

    const tid = tempId(); // unique temp ID (#23)
    const optimistic = { id: tid, sender_type: 'visitor', content, sender_name: name, created_at: new Date().toISOString() };

    setMessage('');
    setSending(true);
    shouldScrollRef.current = true; // force scroll on own message
    setMessages(prev => [...prev, optimistic]);

    try {
      await apiRef.current.post(`/api/v1/chat/sessions/${sessionId}/messages`, {
        content,
        sender_type: 'visitor',
        sender_name: name,
      });
      // Next poll will confirm and replace the temp message
    } catch (err) {
      // Roll back optimistic message (#3)
      setMessages(prev => prev.filter(m => m.id !== tid));
      setMessage(content); // restore input
      setErrorMsg(err.response?.data?.error ?? 'Failed to send. Please try again.');
    } finally {
      setSending(false);
    }
  }, [message, sessionId, name, sending]);

  // ── handleClose (#19) ────────────────────────────────────────────────
  const handleClose = useCallback(() => {
    setOpen(false);
    // Intentionally keep session alive for reconnect on reopen
    onClose?.();
  }, [onClose]);

  // ── FAB (closed state) ────────────────────────────────────────────────
  if (!open) {
    return (
      <div style={S.container}>
        <button
          type="button"
          style={S.fab}
          onClick={() => setOpen(true)}
          onMouseEnter={e => (e.currentTarget.style.transform = 'scale(1.05)')}
          onMouseLeave={e => (e.currentTarget.style.transform = 'scale(1)')}
          aria-label="Open live chat"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </button>
      </div>
    );
  }

  // ── Panel (open state) ────────────────────────────────────────────────
  return (
    <div style={S.container}>
      <div
        style={S.panel}
        role="dialog"
        aria-label="Live chat"
        aria-modal="true"
      >
        {/* Header */}
        <div style={S.header}>
          <span>Live Chat</span>
          <button
            type="button"
            style={S.closeBtn}
            onClick={handleClose}
            aria-label="Close live chat"   // #10
          >
            ×
          </button>
        </div>

        {/* Network error banner (#24) */}
        {netError && (
          <div style={S.errorBanner} role="alert">
            ⚠️ Connection lost. Trying to reconnect…
          </div>
        )}

        {/* Inline error */}
        {errorMsg && (
          <div style={S.errorBanner} role="alert">
            {errorMsg}
            <button
              type="button"
              onClick={() => setErrorMsg(null)}
              style={{ marginLeft: 8, fontWeight: 700, cursor: 'pointer', background: 'none', border: 'none', color: '#991b1b' }}
              aria-label="Dismiss error"
            >
              ×
            </button>
          </div>
        )}

        {/* Registration form */}
        {!registered ? (
          <form onSubmit={handleStart} style={S.formContainer}>
            <div>
              <label htmlFor="cw-name" style={S.label}>Your Name</label>  {/* #10 */}
              <input
                id="cw-name"
                style={S.input}
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Enter your name"
                required
                disabled={starting}   // #22
                autoComplete="name"
              />
            </div>
            <div>
              <label htmlFor="cw-email" style={S.label}>Email (optional)</label>
              <input
                id="cw-email"
                style={S.input}
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="you@example.com"
                disabled={starting}
                autoComplete="email"
              />
            </div>
            <div>
              <label htmlFor="cw-msg" style={S.label}>Message (optional)</label>
              <textarea
                id="cw-msg"
                style={S.textarea}
                value={message}
                onChange={e => setMessage(e.target.value)}
                placeholder="How can we help?"
                disabled={starting}
              />
            </div>
            <button
              type="submit"
              style={{ ...S.button, ...(starting ? S.buttonDisabled : {}) }}
              disabled={starting}   // #5
            >
              {starting ? 'Starting…' : 'Start Chat'}
            </button>
          </form>
        ) : (
          <>
            {/* Message list */}
            <div
              ref={messagesBoxRef}
              style={S.messages}
              onScroll={handleScroll}   // #9
              role="log"
              aria-live="polite"
              aria-label="Chat messages"
            >
              {messages.length === 0 && (
                <div style={{ textAlign: 'center', color: '#94a3b8', fontSize: 13, padding: 20 }}>
                  Connecting… Send a message to start.
                </div>
              )}
              {messages
                .filter(m => m.type !== 'agent_typing')
                .map(msg => (
                  <div
                    key={msg.id}
                    style={msg.sender_type === 'visitor' ? S.bubbleVisitor : S.bubbleAgent}
                  >
                    <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 2 }}>
                      {msg.sender_name || msg.sender_type}
                    </div>
                    {msg.content}
                  </div>
                ))
              }
              {typing && (
                <div style={S.typingBubble} aria-live="polite">
                  Agent is typing…
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Send form (#15, #22) */}
            <form onSubmit={handleSend} style={S.inputRow}>
              <input
                style={S.msgInput}
                value={message}
                onChange={e => setMessage(e.target.value)}
                placeholder="Type a message…"
                disabled={sending}
                aria-label="Chat message input"
                autoComplete="off"
              />
              <button
                type="submit"
                style={{ ...S.sendBtn, ...(sending ? S.buttonDisabled : {}) }}
                disabled={sending || !message.trim()}
                aria-label="Send message"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
