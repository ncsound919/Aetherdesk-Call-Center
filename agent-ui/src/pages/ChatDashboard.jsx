import React, { useEffect, useState, useCallback, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import { omnichannelApi, agentApi } from '../services/api'
import {
  MessageCircle, Users, SendHorizonal, Clock, CheckCircle2,
  Loader2
} from 'lucide-react'
import { toast } from 'sonner'

export default function ChatDashboard() {
  const { tenant } = useAuth()
  const [activeTab, setActiveTab] = useState('waiting')
  const [loading, setLoading] = useState(false)
  const [waitingSessions, setWaitingSessions] = useState([])
  const [agents, setAgents] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [newMessage, setNewMessage] = useState('')
  const [chatHistory, setChatHistory] = useState([])
  const messagesEndRef = useRef(null)

  const fetchWaiting = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await omnichannelApi.getWaitingChats()
      setWaitingSessions(Array.isArray(res.data) ? res.data : [])
    } catch { setWaitingSessions([]) }
  }, [tenant])

  const fetchAgents = useCallback(async () => {
    if (!tenant) return
    try {
      const res = await agentApi.list(tenant.id)
      setAgents(Array.isArray(res.data) ? res.data : [])
    } catch { setAgents([]) }
  }, [tenant])

  useEffect(() => {
    fetchWaiting()
    fetchAgents()
  }, [fetchWaiting, fetchAgents])

  useEffect(() => {
    const interval = setInterval(() => {
      if (activeTab === 'waiting') fetchWaiting()
    }, 10000)
    return () => clearInterval(interval)
  }, [activeTab, fetchWaiting])

  async function openSession(sessionId) {
    setActiveSessionId(sessionId)
    try {
      const res = await omnichannelApi.getChatMessages(sessionId)
      setMessages(Array.isArray(res.data) ? res.data : [])
    } catch { setMessages([]) }
  }

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages])

  async function handleSendMessage(e) {
    e.preventDefault()
    if (!newMessage.trim() || !activeSessionId) return
    try {
      const res = await omnichannelApi.sendChatMessage(activeSessionId, {
        content: newMessage,
        sender_type: 'agent',
        sender_name: 'Agent',
      })
      setMessages(prev => [...prev, res.data])
      setNewMessage('')
    } catch (err) {
      toast.error('Failed to send message')
    }
  }

  async function handleAssign(sessionId, agentId) {
    try {
      await omnichannelApi.assignChat(sessionId, { agent_id: agentId })
      toast.success('Chat assigned')
      fetchWaiting()
    } catch (err) {
      toast.error('Failed to assign')
    }
  }

  async function handleClose(sessionId) {
    try {
      await omnichannelApi.closeChat(sessionId)
      toast.success('Chat closed')
      if (activeSessionId === sessionId) {
        setActiveSessionId(null)
        setMessages([])
      }
      fetchWaiting()
    } catch (err) {
      toast.error('Failed to close chat')
    }
  }

  function formatWaitTime(seconds) {
    if (!seconds && seconds !== 0) return '—'
    if (seconds < 60) return `${seconds}s`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
  }

  const tabs = [
    { key: 'waiting', label: 'Waiting Queue', icon: Users },
    { key: 'active', label: 'Active Chat', icon: MessageCircle },
  ]

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Live Chat</h1>
          <p className="text-sm text-ink-muted mt-0.5">Manage visitor chat sessions in real time</p>
        </div>
      </div>

      <div className="flex gap-1 mb-6 border-b border-hairline">
        {tabs.map(tab => {
          const Icon = tab.icon
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-accent text-accent'
                  : 'border-transparent text-ink-muted hover:text-ink'
              }`}
            >
              <Icon className="h-4 w-4" />
              {tab.label}
            </button>
          )
        })}
      </div>

      {activeTab === 'waiting' && (
        <div className="space-y-4">
          {waitingSessions.length === 0 && (
            <div className="card p-12 text-center text-ink-muted">No waiting sessions.</div>
          )}
          {waitingSessions.map(session => (
            <div key={session.id} className="card p-4 flex items-center justify-between">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-3 mb-1">
                  <span className="font-medium text-ink">{session.visitor_name || 'Anonymous'}</span>
                  <span className="flex items-center gap-1 text-xs text-ink-muted">
                    <Clock className="h-3 w-3" />
                    {formatWaitTime(session.wait_time_seconds)}
                  </span>
                  {session.message_count > 0 && (
                    <span className="text-xs bg-accent-soft text-accent px-2 py-0.5 rounded-full">
                      {session.message_count} msgs
                    </span>
                  )}
                </div>
                <p className="text-sm text-ink-muted truncate">{session.visitor_email || 'No email'}</p>
              </div>
              <div className="flex items-center gap-2 ml-4">
                <select
                  onChange={e => handleAssign(session.id, e.target.value)}
                  className="input-field text-sm py-1.5"
                  defaultValue=""
                >
                  <option value="" disabled>Assign to...</option>
                  {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
                <button
                  onClick={() => openSession(session.id)}
                  className="btn-primary text-sm py-1.5"
                >
                  <MessageCircle className="h-4 w-4" /> Open
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === 'active' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {activeSessionId ? (
            <>
              <div className="lg:col-span-2 card p-0 flex flex-col min-h-[500px]">
                <div className="flex items-center justify-between px-4 py-3 border-b border-hairline">
                  <h3 className="text-sm font-medium text-ink">Chat Session</h3>
                  <div className="flex items-center gap-2">
                    <button onClick={() => handleClose(activeSessionId)} className="text-sm text-red-500 hover:text-red-600">
                      <CheckCircle2 className="h-4 w-4" /> Close
                    </button>
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-[400px]">
                  {messages.length === 0 && (
                    <div className="text-center text-ink-muted py-8">No messages yet.</div>
                  )}
                  {messages.map(msg => (
                    <div key={msg.id} className={`flex ${msg.sender_type === 'agent' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[70%] rounded-lg px-3 py-2 text-sm ${
                        msg.sender_type === 'agent'
                          ? 'bg-accent text-white'
                          : 'bg-surface-subtle text-ink'
                      }`}>
                        <p className="text-xs opacity-70 mb-0.5">{msg.sender_name || msg.sender_type}</p>
                        <p>{msg.content}</p>
                      </div>
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>
                <form onSubmit={handleSendMessage} className="flex items-center gap-2 p-3 border-t border-hairline">
                  <input
                    type="text" value={newMessage}
                    onChange={e => setNewMessage(e.target.value)}
                    className="input-field flex-1" placeholder="Type a message..." required
                  />
                  <button type="submit" className="btn-primary p-2.5">
                    <SendHorizonal className="h-4 w-4" />
                  </button>
                </form>
              </div>
              <div className="card p-4">
                <h3 className="text-sm font-medium text-ink mb-3">Session Details</h3>
                <p className="text-sm text-ink-muted mb-2">Assign agent to handle this chat.</p>
                <select
                  onChange={e => handleAssign(activeSessionId, e.target.value)}
                  className="input-field text-sm w-full"
                  defaultValue=""
                >
                  <option value="" disabled>Select agent...</option>
                  {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </div>
            </>
          ) : (
            <div className="lg:col-span-3 card p-12 text-center text-ink-muted">
              <MessageCircle className="h-12 w-12 mx-auto mb-3 opacity-40" />
              <p>Select a waiting session to start chatting.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
