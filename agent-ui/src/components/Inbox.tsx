
import React, { useEffect, useState, useCallback } from "react";

type QueueItem = { 
  session_id: string; 
  protocol_id: string; 
  preview: string; 
  queue: string; 
  created_ts: number; 
};

export function Inbox({ onClaim }: { onClaim: (id: string) => void }) {
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [agentId] = useState<string>(() => {
    const saved = localStorage.getItem('aether_agent_id');
    if (saved) return saved;
    const newId = "agent-" + Math.floor(Math.random() * 10000);
    localStorage.setItem('aether_agent_id', newId);
    return newId;
  });

  const API = useCallback((p: string) => `/api/v1/agent${p}`, []);

  const refresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const r = await fetch(API(`/peek?queue=general&n=50`));
      const j = await r.json();
      setQueue(j.items || []);
    } catch (err) {
      console.error("Failed to fetch queue", err);
    } finally {
      setTimeout(() => setIsRefreshing(false), 500);
    }
  }, [API]);

  async function claim() {
    try {
      const r = await fetch(API(`/claim?queue=general&agent_id=${agentId}`), { method: "POST" });
      const j = await r.json();
      if (j.ok) {
        onClaim(j.item.session_id);
        refresh();
      } else {
        alert("Queue is currently empty.");
      }
    } catch (err) {
      alert("Error claiming session.");
    }
  }

  useEffect(() => {
    refresh();
    
    let ws: WebSocket;
    
    async function connectWs() {
      try {
        const tr = await fetch(API(`/token?agent_id=${agentId}`), { method: "POST" });
        const td = await tr.json();
        
        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = window.location.host; 
        ws = new WebSocket(`${wsProtocol}//${wsHost}/api/v1/agent/ws?agent_id=${agentId}&token=${td.token}`);
        
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.type === 'queue_updated' || data.type === 'claimed') {
              refresh();
            }
          } catch (e) {
            console.error("Error parsing WS message", e);
          }
        };
        
        ws.onerror = (e) => console.error("WebSocket error", e);
      } catch (err) {
        console.error("Failed to fetch token or connect websocket", err);
      }
    }
    
    connectWs();
    
    return () => {
      if (ws) ws.close();
    };
  }, [refresh, agentId]);

  return (
    <div className="card" style={{minHeight: '400px'}}>
      <div style={{display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem"}}>
        <div>
          <h3 style={{fontSize: '1.25rem', marginBottom: '0.25rem'}}>Active Queue</h3>
          <p style={{color: 'var(--text-secondary)', fontSize: '0.875rem'}}>
            Monitoring <span style={{color: 'var(--accent-primary)'}}>{queue.length}</span> incoming requests
          </p>
        </div>
        <div style={{display: "flex", gap: "0.75rem"}}>
          <button className="btn btn-secondary" onClick={refresh} disabled={isRefreshing}>
            {isRefreshing ? 'Updating...' : 'Refresh'}
          </button>
          <button className="btn" onClick={claim}>
            Claim Next Call
          </button>
        </div>
      </div>

      <div style={{overflowX: 'auto'}}>
        <table>
          <thead>
            <tr>
              <th>Status</th>
              <th>Session ID</th>
              <th>Live Preview</th>
              <th>Protocol</th>
              <th>Wait Time</th>
            </tr>
          </thead>
          <tbody>
            {queue.length === 0 ? (
              <tr>
                <td colSpan={5} style={{textAlign: 'center', padding: '3rem', color: 'var(--text-secondary)'}}>
                  No active calls in the queue.
                </td>
              </tr>
            ) : (
              queue.map((q, i) => (
                <tr key={q.session_id}>
                  <td>
                    <span className="badge badge-live">LIVE</span>
                  </td>
                  <td style={{fontFamily: 'monospace', fontWeight: 600}}>{q.session_id.substring(0, 12)}...</td>
                  <td>
                    <div className="preview-text">{q.preview || "Customer is speaking..."}</div>
                  </td>
                  <td>
                    <code style={{background: 'rgba(255,255,255,0.05)', padding: '0.2rem 0.4rem', borderRadius: '4px'}}>
                      {q.protocol_id}
                    </code>
                  </td>
                  <td style={{color: 'var(--text-secondary)'}}>
                    {Math.floor((Date.now() / 1000 - q.created_ts) / 60)}m ago
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div style={{marginTop: '2rem', paddingTop: '1rem', borderTop: '1px solid var(--border-color)', display: 'flex', justifyContent: 'space-between'}}>
        <span style={{fontSize: '0.75rem', color: 'var(--text-secondary)'}}>
          Agent ID: <span className="agent-id">{agentId}</span>
        </span>
        <span style={{fontSize: '0.75rem', color: 'var(--text-secondary)'}}>
          Connected to Aether Orchestrator v0.3
        </span>
      </div>
    </div>
  );
}
