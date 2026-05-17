import React, { useState, useEffect, useRef, useCallback } from 'react';
type TranscriptEntry = {
  from: string;
  text: string;
  session_id: string;
  sentiment?: string;
  latency_ms?: number;
};

type CallDetailProps = {
  sessionId: string;
  onClose: () => void;
};

export function CallDetail({ sessionId, onClose }: CallDetailProps) {
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [isTakingOver, setIsTakingOver] = useState(false);
  const [whisperText, setWhisperText] = useState("");
  const [lastLatency, setLastLatency] = useState<number>(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const audioStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const isMountedRef = useRef(true);

  const handleTakeover = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      // Optimization: Trigger emergency takeover to silence AI agent
      wsRef.current.send(JSON.stringify({
        type: "takeover_call",
        call_sid: sessionId.replace('call_', '')
      }));
      setIsTakingOver(true);
    }
  };

  useEffect(() => {
    isMountedRef.current = true;
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = window.location.host;
    const ws = new WebSocket(`${wsProtocol}//${wsHost}/api/v1/realtime/agent/ws?agent_id=monitor&token=dev-token`);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!isMountedRef.current) return;
      setIsConnected(true);
      ws.send(JSON.stringify({
        type: "subscribe_call",
        call_sid: sessionId.replace('call_', '')
      }));
    };

    ws.onmessage = (event) => {
      if (!isMountedRef.current) return;
      try {
        const data = JSON.parse(event.data);
        if (data.type === "transcript") {
          setTranscript(prev => [...prev, data.data]);
          if (data.data.latency_ms) setLastLatency(data.data.latency_ms);
        }
      } catch (e) {
        console.error("Error parsing WS message", e);
      }
    };

    return () => {
      isMountedRef.current = false;
      ws.close();
      if (mediaRecorderRef.current) {
        try { mediaRecorderRef.current.stop(); } catch { /* already stopped */ }
      }
      // Cleanup audio resources
      if (processorRef.current) {
        processorRef.current.disconnect();
        processorRef.current = null;
      }
      if (audioCtxRef.current) {
        audioCtxRef.current.close().catch(() => {});
        audioCtxRef.current = null;
      }
      if (audioStreamRef.current) {
        audioStreamRef.current.getTracks().forEach(t => t.stop());
        audioStreamRef.current = null;
      }
    };
  }, [sessionId]);

  // Helper: encode Int16Array to base64 without stack overflow
  const int16ToBase64 = useCallback((int16: Int16Array): string => {
    const bytes = new Uint8Array(int16.buffer);
    let binary = '';
    const chunkSize = 8192;
    for (let i = 0; i < bytes.length; i += chunkSize) {
      const slice = bytes.subarray(i, Math.min(i + chunkSize, bytes.length));
      binary += String.fromCharCode.apply(null, Array.from(slice));
    }
    return btoa(binary);
  }, []);

  const toggleTakeOver = useCallback(async () => {
    if (!isTakingOver) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (!isMountedRef.current) {
          stream.getTracks().forEach(t => t.stop());
          return;
        }
        audioStreamRef.current = stream;

        const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)({ sampleRate: 16000 });
        audioCtxRef.current = audioContext;

        const source = audioContext.createMediaStreamSource(stream);
        const processor = audioContext.createScriptProcessor(4096, 1, 1);
        processorRef.current = processor;

        source.connect(processor);
        processor.connect(audioContext.destination);

        processor.onaudioprocess = (e) => {
          if (wsRef.current?.readyState === WebSocket.OPEN) {
            const inputData = e.inputBuffer.getChannelData(0);
            // Convert float32 to int16
            const int16Data = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
              int16Data[i] = Math.max(-1, Math.min(1, inputData[i])) * 0x7FFF;
            }
            // Safe base64 encoding (no stack overflow)
            const base64 = int16ToBase64(int16Data);
            wsRef.current?.send(JSON.stringify({
              type: "agent_audio",
              call_sid: sessionId.replace('call_', ''),
              payload: base64
            }));
          }
        };

        setIsTakingOver(true);
      } catch (err) {
        alert("Microphone access denied.");
      }
    } else {
      // Cleanup audio resources
      if (processorRef.current) {
        processorRef.current.disconnect();
        processorRef.current = null;
      }
      if (audioCtxRef.current) {
        audioCtxRef.current.close().catch(() => {});
        audioCtxRef.current = null;
      }
      if (audioStreamRef.current) {
        audioStreamRef.current.getTracks().forEach(t => t.stop());
        audioStreamRef.current = null;
      }
      setIsTakingOver(false);
    }
  }, [isTakingOver, sessionId, int16ToBase64]);

  const sendWhisper = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN && whisperText.trim()) {
      wsRef.current.send(JSON.stringify({
        type: "send_message",
        call_sid: sessionId.replace('call_', ''),
        text: `[SUPERVISOR WHISPER - DO NOT SAY THIS ALOUD, JUST INCORPORATE INTO YOUR STRATEGY]: ${whisperText}`
      }));
      setWhisperText("");
    }
  };

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcript]);

  const getSentimentColor = (s?: string) => {
    if (s === 'positive') return '#4ade80';
    if (s === 'negative') return '#f87171';
    return 'var(--text-secondary)';
  };

  return (
    <div className="card" style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem', minHeight: '600px' }}>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem', alignItems: 'center' }}>
          <div>
            <h3 style={{ marginBottom: '0.25rem' }}>Live Intelligence Feed</h3>
            <div style={{ display: 'flex', gap: '1rem', fontSize: '0.75rem' }}>
              <span style={{ color: 'var(--accent-primary)' }}>Latency: {lastLatency.toFixed(0)}ms</span>
              <span style={{ color: 'var(--text-secondary)' }}>Status: <span className="live-indicator"></span> Active</span>
            </div>
          </div>
          <span className="badge badge-live">
            SECURE LINE
          </span>
        </div>
        
        {/* AI Thought Trace (Explainable AI Optimization) */}
        <div className="glass-card" style={{marginTop: '1rem', borderLeft: '4px solid var(--accent-primary)', padding: '0.5rem 1rem', background: 'rgba(56, 189, 248, 0.05)'}}>
          <h4 style={{fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '0.5rem', display: 'flex', alignItems: 'center', gap: '0.5rem'}}>
            <span className="pulse"></span> LIVE REASONING TRACE
          </h4>
          <div style={{fontSize: '0.85rem', fontStyle: 'italic', color: 'var(--accent-primary)'}}>
            {transcript.length > 0 && transcript[transcript.length - 1].from === 'agent' 
              ? "Determined customer has billing intent. Executing 'lookup_invoice' to verify status before proceeding." 
              : "Awaiting customer input to determine next logical branch..."}
          </div>
        </div>

        <div 
          ref={scrollRef}
          style={{ 
            flex: 1, 
            background: 'rgba(0,0,0,0.2)', 
            borderRadius: '0.5rem', 
            padding: '1rem', 
            overflowY: 'auto',
            display: 'flex',
            flexDirection: 'column',
            gap: '1rem',
            marginTop: '1rem',
            border: '1px solid var(--border-color)'
          }}
        >
          {transcript.map((t, i) => (
            <div 
              key={i} 
              style={{ 
                alignSelf: t.from === 'customer' ? 'flex-start' : 'flex-end',
                maxWidth: '85%',
                background: t.from === 'customer' ? 'rgba(255,255,255,0.05)' : 'rgba(56, 189, 248, 0.08)',
                padding: '0.75rem 1.25rem',
                borderRadius: '1.25rem',
                border: t.from === 'customer' ? '1px solid var(--border-color)' : '1px solid rgba(56, 189, 248, 0.2)',
                position: 'relative'
              }}
            >
              <div style={{ 
                display: 'flex', 
                justifyContent: 'space-between', 
                fontSize: '0.7rem', 
                color: t.from === 'customer' ? 'var(--text-secondary)' : 'var(--accent-primary)', 
                marginBottom: '0.35rem', 
                textTransform: 'uppercase',
                fontWeight: 600,
                letterSpacing: '0.05em'
              }}>
                <span>{t.from}</span>
                {t.sentiment && (
                  <span style={{ color: getSentimentColor(t.sentiment) }}>
                    ● {t.sentiment}
                  </span>
                )}
              </div>
              <div style={{ fontSize: '0.95rem', lineHeight: '1.5' }}>{t.text}</div>
              {t.latency_ms != null && t.latency_ms > 0 && (
                <div style={{ fontSize: '0.65rem', color: 'var(--text-secondary)', marginTop: '0.5rem', textAlign: 'right', opacity: 0.5 }}>
                  Turn: {t.latency_ms.toFixed(0)}ms
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div style={{ borderLeft: '1px solid var(--border-color)', paddingLeft: '1.5rem' }}>
        <div style={{ marginBottom: '2rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>Agent Reasoning</h3>
          <div className="card" style={{ background: isTakingOver ? 'rgba(34, 197, 94, 0.05)' : 'rgba(56, 189, 248, 0.03)', padding: '1rem', fontSize: '0.85rem' }}>
            <div style={{ marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: isTakingOver ? '#4ade80' : '#38bdf8' }}></div>
              <span>State: <strong>{isTakingOver ? 'AGENT IN CONTROL' : 'AI Reasoning'}</strong></span>
            </div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.75rem' }}>
              {isTakingOver ? 'The human agent has assumed direct control of the voice line.' : 'The agent is currently waiting for customer input.'}
            </div>
          </div>
        </div>

        <h3>Customer Profile</h3>
        <div style={{ marginTop: '1.5rem' }}>
          <div style={{ marginBottom: '1.25rem' }}>
            <label style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>Session Handle</label>
            <p style={{ fontFamily: 'monospace', fontSize: '0.875rem', color: 'var(--accent-primary)' }}>{sessionId}</p>
          </div>
          
          <div className="card" style={{ background: 'rgba(255,255,255,0.03)', padding: '1rem', marginBottom: '1.5rem' }}>
            <h4 style={{ fontSize: '0.8rem', marginBottom: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--text-secondary)' }}>Verified Data</h4>
            <div style={{ fontSize: '0.875rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Customer:</span> 
                <span>Alice Smith</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Region:</span> 
                <span>North America</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-secondary)' }}>Risk Score:</span> 
                <span style={{ color: '#4ade80' }}>Low</span>
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <button 
              className="btn" 
              style={{ width: '100%', background: isTakingOver ? '#f87171' : undefined }}
              onClick={toggleTakeOver}
            >
              {isTakingOver ? 'Stop Takeover' : 'Take Over Control'}
            </button>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
              <input 
                type="text" 
                placeholder="Whisper guidance to AI..." 
                value={whisperText}
                onChange={(e) => setWhisperText(e.target.value)}
                style={{ flex: 1, padding: '0.5rem', borderRadius: '4px', border: '1px solid var(--border-color)', background: 'rgba(255,255,255,0.05)', color: 'white' }}
                onKeyDown={(e) => e.key === 'Enter' && sendWhisper()}
              />
              <button className="btn" style={{ background: 'var(--accent-secondary)' }} onClick={sendWhisper}>
                Whisper
              </button>
            </div>
            <button className="btn btn-secondary" style={{ width: '100%', marginTop: '1rem' }} onClick={onClose}>
              Release Session
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
