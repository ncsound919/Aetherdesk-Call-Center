import React, { useState, useRef, useEffect, useCallback } from 'react'
import { omnichannelApi } from '../services/api'

const styles = {
  container: {
    position: 'fixed',
    bottom: 20,
    right: 20,
    zIndex: 9999,
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },
  fab: {
    width: 56,
    height: 56,
    borderRadius: '50%',
    backgroundColor: '#6366f1',
    color: '#fff',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0 4px 12px rgba(99,102,241,0.4)',
    transition: 'transform 0.2s',
  },
  panel: {
    position: 'absolute',
    bottom: 72,
    right: 0,
    width: 360,
    height: 520,
    backgroundColor: '#fff',
    borderRadius: 16,
    boxShadow: '0 8px 32px rgba(0,0,0,0.15)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    animation: 'slideUp 0.3s ease',
  },
  header: {
    padding: '16px 20px',
    backgroundColor: '#6366f1',
    color: '#fff',
    fontWeight: 600,
    fontSize: 15,
  },
  formContainer: {
    padding: 24,
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
    flex: 1,
    justifyContent: 'center',
  },
  input: {
    width: '100%',
    padding: '10px 14px',
    border: '1px solid #e2e8f0',
    borderRadius: 8,
    fontSize: 14,
    outline: 'none',
    boxSizing: 'border-box',
  },
  textarea: {
    width: '100%',
    padding: '10px 14px',
    border: '1px solid #e2e8f0',
    borderRadius: 8,
    fontSize: 14,
    outline: 'none',
    resize: 'none',
    minHeight: 60,
    boxSizing: 'border-box',
  },
  button: {
    padding: '10px 20px',
    backgroundColor: '#6366f1',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    cursor: 'pointer',
    fontWeight: 500,
    fontSize: 14,
  },
  messages: {
    flex: 1,
    overflowY: 'auto',
    padding: 16,
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
  },
  bubbleUser: {
    alignSelf: 'flex-start',
    backgroundColor: '#f1f5f9',
    color: '#1e293b',
    padding: '8px 14px',
    borderRadius: '12px 12px 12px 4px',
    maxWidth: '80%',
    fontSize: 14,
    lineHeight: 1.4,
  },
  bubbleAgent: {
    alignSelf: 'flex-end',
    backgroundColor: '#6366f1',
    color: '#fff',
    padding: '8px 14px',
    borderRadius: '12px 12px 4px 12px',
    maxWidth: '80%',
    fontSize: 14,
    lineHeight: 1.4,
  },
  inputRow: {
    display: 'flex',
    gap: 8,
    padding: '12px 16px',
    borderTop: '1px solid #e2e8f0',
  },
  msgInput: {
    flex: 1,
    padding: '8px 12px',
    border: '1px solid #e2e8f0',
    borderRadius: 20,
    fontSize: 14,
    outline: 'none',
  },
  sendBtn: {
    width: 36,
    height: 36,
    borderRadius: '50%',
    backgroundColor: '#6366f1',
    color: '#fff',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: {
    fontSize: 13,
    fontWeight: 500,
    color: '#475569',
  },
  closeBtn: {
    background: 'none',
    border: 'none',
    color: '#fff',
    cursor: 'pointer',
    fontSize: 20,
    lineHeight: 1,
    padding: 0,
  },
}

export default function ChatWidget({ tenantId, apiBaseUrl }) {
  const [open, setOpen] = useState(false)
  const [registered, setRegistered] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [typing, setTyping] = useState(false)
  const messagesEndRef = useRef(null)
  const pollRef = useRef(null)

  useEffect(() => {
    if (open && sessionId && !pollRef.current) {
      pollRef.current = setInterval(async () => {
        try {
          const res = await omnichannelApi.getChatMessages(sessionId)
          const msgs = Array.isArray(res.data) ? res.data : []
          setMessages(msgs)
        } catch {}
      }, 3000)
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [open, sessionId])

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  async function handleStart(e) {
    e.preventDefault()
    if (!name.trim()) return
    try {
      const res = await omnichannelApi.createChatSession({
        visitor_id: `visitor_${Date.now()}`,
        visitor_name: name,
        visitor_email: email,
        initial_message: message || undefined,
      })
      setSessionId(res.data?.id)
      setRegistered(true)
      if (message) {
        setMessages([{ id: 'temp', sender_type: 'visitor', content: message, sender_name: name }])
      }
    } catch {
      alert('Failed to start chat')
    }
  }

  async function handleSend(e) {
    e.preventDefault()
    if (!message.trim() || !sessionId) return
    const content = message
    setMessage('')
    setMessages(prev => [...prev, { id: 'temp', sender_type: 'visitor', content, sender_name: name }])
    try {
      await omnichannelApi.sendChatMessage(sessionId, {
        content,
        sender_type: 'visitor',
        sender_name: name,
      })
    } catch {}
  }

  if (!open) {
    return (
      <div style={styles.container}>
        <button
          style={styles.fab}
          onClick={() => setOpen(true)}
          onMouseEnter={e => e.currentTarget.style.transform = 'scale(1.05)'}
          onMouseLeave={e => e.currentTarget.style.transform = 'scale(1)'}
          aria-label="Open chat"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
        </button>
      </div>
    )
  }

  return (
    <div style={styles.container}>
      <div style={styles.panel}>
        <div style={{ ...styles.header, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Live Chat</span>
          <button style={styles.closeBtn} onClick={() => { setOpen(false); setRegistered(false); setSessionId(null); setMessages([]) }}>×</button>
        </div>

        {!registered ? (
          <form onSubmit={handleStart} style={styles.formContainer}>
            <div>
              <label style={styles.label}>Your Name</label>
              <input style={styles.input} value={name} onChange={e => setName(e.target.value)} placeholder="Enter your name" required />
            </div>
            <div>
              <label style={styles.label}>Email (optional)</label>
              <input style={styles.input} type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
            </div>
            <div>
              <label style={styles.label}>Message (optional)</label>
              <textarea style={styles.textarea} value={message} onChange={e => setMessage(e.target.value)} placeholder="How can we help?" />
            </div>
            <button type="submit" style={styles.button}>Start Chat</button>
          </form>
        ) : (
          <>
            <div style={styles.messages}>
              {messages.length === 0 && (
                <div style={{ textAlign: 'center', color: '#94a3b8', fontSize: 13, padding: 20 }}>
                  No messages yet. Send a message to start.
                </div>
              )}
              {messages.map(msg => (
                <div key={msg.id} style={msg.sender_type === 'agent' ? styles.bubbleAgent : styles.bubbleUser}>
                  <div style={{ fontSize: 11, opacity: 0.7, marginBottom: 2 }}>
                    {msg.sender_name || msg.sender_type}
                  </div>
                  {msg.content}
                </div>
              ))}
              {typing && (
                <div style={{ ...styles.bubbleUser, opacity: 0.6, fontStyle: 'italic' }}>
                  Agent is typing...
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
            <form onSubmit={handleSend} style={styles.inputRow}>
              <input
                style={styles.msgInput}
                value={message}
                onChange={e => setMessage(e.target.value)}
                placeholder="Type a message..."
              />
              <button type="submit" style={styles.sendBtn} aria-label="Send">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
