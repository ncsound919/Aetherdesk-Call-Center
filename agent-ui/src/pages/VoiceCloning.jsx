import { useState, useRef, useEffect, useCallback } from 'react';
import { Mic, Square, Play, Upload, Check, AlertCircle, Trash2 } from 'lucide-react';

export default function VoiceCloning() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [recordingTime, setRecordingTime] = useState(0);
  const [uploadStatus, setUploadStatus] = useState('idle'); // idle | uploading | success | error
  const [clonedVoiceId, setClonedVoiceId] = useState(null);
  const [error, setError] = useState(null);
  const [voiceName, setVoiceName] = useState('My Voice');
  const [meterLevel, setMeterLevel] = useState(0);

  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const analyserRef = useRef(null);
  const animFrameRef = useRef(null);
  const isMountedRef = useRef(true);

  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (timerRef.current) clearInterval(timerRef.current);
      if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      // Stop any active stream tracks
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(track => track.stop());
        streamRef.current = null;
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        try { mediaRecorderRef.current.stop(); } catch { /* already stopped */ }
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Revoke old audio URL when a new one is created
  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  const startRecording = useCallback(async () => {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 44100,
        }
      });

      if (!isMountedRef.current) {
        stream.getTracks().forEach(t => t.stop());
        return;
      }

      streamRef.current = stream;

      // Setup audio analyser for live meter
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = { audioCtx, analyser };

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      const updateMeter = () => {
        if (!isMountedRef.current) return;
        analyser.getByteFrequencyData(dataArray);
        const avg = dataArray.reduce((a, b) => a + b, 0) / dataArray.length;
        setMeterLevel(Math.min(100, (avg / 128) * 100));
        animFrameRef.current = requestAnimationFrame(updateMeter);
      };
      updateMeter();

      // Determine best supported MIME type
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : '';

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      mediaRecorderRef.current = recorder;
      chunksRef.current = [];

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        if (!isMountedRef.current) return;
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        setAudioBlob(blob);
        setAudioUrl(URL.createObjectURL(blob));
        // Stop all tracks
        stream.getTracks().forEach(track => track.stop());
        streamRef.current = null;
        // Cleanup analyser
        if (analyserRef.current) {
          analyserRef.current.audioCtx.close().catch(() => {});
          analyserRef.current = null;
        }
        if (animFrameRef.current) {
          cancelAnimationFrame(animFrameRef.current);
          animFrameRef.current = null;
        }
        setMeterLevel(0);
      };

      recorder.start(250); // collect data every 250ms
      setIsRecording(true);
      setRecordingTime(0);

      timerRef.current = setInterval(() => {
        if (!isMountedRef.current) return;
        setRecordingTime(prev => prev + 1);
      }, 1000);
    } catch (err) {
      if (isMountedRef.current) {
        setError('Could not access microphone. Please grant permission and ensure you are on HTTPS or localhost.');
      }
    }
  }, []);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    }
  }, []);

  const discardRecording = useCallback(() => {
    if (audioUrl) URL.revokeObjectURL(audioUrl);
    setAudioBlob(null);
    setAudioUrl(null);
    setRecordingTime(0);
    setUploadStatus('idle');
    setError(null);
  }, [audioUrl]);

  const uploadRecording = useCallback(async () => {
    if (!audioBlob) return;

    setUploadStatus('uploading');
    setError(null);

    const controller = new AbortController();

    try {
      const formData = new FormData();
      formData.append('audio', audioBlob, 'voice_sample.webm');
      formData.append('voice_name', voiceName.trim() || 'My Voice');
      formData.append('language', 'en-US');

      const response = await fetch('http://localhost:8000/api/v1/voice/clone', {
        method: 'POST',
        headers: {
          'X-API-Key': 'dev-api-key'
        },
        body: formData,
        signal: controller.signal,
      });

      if (!isMountedRef.current) return;

      if (!response.ok) {
        const errText = await response.text().catch(() => 'Unknown error');
        throw new Error(`Upload failed (${response.status}): ${errText}`);
      }

      const data = await response.json();
      setClonedVoiceId(data.voice_id);
      setUploadStatus('success');
    } catch (err) {
      if (!isMountedRef.current) return;
      if (err.name === 'AbortError') return;
      setError(err.message || 'Failed to upload voice sample');
      setUploadStatus('error');
    }
  }, [audioBlob, voiceName]);

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div>
      <h2 style={{ marginBottom: '0.5rem' }}>Voice Cloning Studio</h2>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '2rem' }}>
        Record your voice to create a custom TTS voice for outbound calls and agent responses.
      </p>

      {/* Recording Card */}
      <div className="glass-card" style={{ marginBottom: '1.5rem' }}>
        <h3 style={{ marginBottom: '1.5rem' }}>Record Voice Sample</h3>

        {/* Mic Visualizer */}
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '3rem 2rem',
          marginBottom: '1.5rem',
          border: '2px dashed var(--border-color)',
          borderRadius: '12px',
          background: isRecording ? 'rgba(239, 68, 68, 0.03)' : 'rgba(99, 102, 241, 0.03)',
          transition: 'all 0.3s ease',
        }}>
          {/* Mic Circle with pulse */}
          <div style={{
            width: '120px',
            height: '120px',
            borderRadius: '50%',
            background: isRecording
              ? `radial-gradient(circle, rgba(239,68,68,0.2) 0%, rgba(239,68,68,0.05) 70%)`
              : 'radial-gradient(circle, rgba(99,102,241,0.15) 0%, rgba(99,102,241,0.03) 70%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '1.5rem',
            position: 'relative',
            transition: 'all 0.3s ease',
            boxShadow: isRecording
              ? `0 0 ${20 + meterLevel * 0.4}px rgba(239,68,68,${0.1 + meterLevel * 0.004})`
              : '0 0 20px rgba(99,102,241,0.1)',
            transform: isRecording ? `scale(${1 + meterLevel * 0.002})` : 'scale(1)',
          }}>
            <Mic
              size={40}
              style={{
                color: isRecording ? '#ef4444' : 'var(--accent-primary)',
                transition: 'color 0.3s ease',
              }}
            />
            {isRecording && (
              <div style={{
                position: 'absolute',
                inset: '-4px',
                borderRadius: '50%',
                border: '2px solid rgba(239,68,68,0.4)',
                animation: 'pulse 2s infinite',
              }} />
            )}
          </div>

          {/* Timer */}
          {isRecording && (
            <div style={{
              fontSize: '2rem',
              fontFamily: 'monospace',
              fontWeight: 700,
              marginBottom: '0.5rem',
              color: recordingTime > 25 ? '#ef4444' : 'var(--text-primary)',
              transition: 'color 0.3s ease',
            }}>
              {formatTime(recordingTime)}
            </div>
          )}

          {/* Level Meter */}
          {isRecording && (
            <div style={{
              width: '200px',
              height: '6px',
              background: 'var(--border-color)',
              borderRadius: '3px',
              marginBottom: '1.5rem',
              overflow: 'hidden',
            }}>
              <div style={{
                width: `${meterLevel}%`,
                height: '100%',
                background: meterLevel > 80 ? '#ef4444' : meterLevel > 50 ? '#f59e0b' : 'var(--success)',
                borderRadius: '3px',
                transition: 'width 0.1s ease, background 0.3s ease',
              }} />
            </div>
          )}

          {/* Controls */}
          <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
            {!isRecording ? (
              <button className="btn-primary" onClick={startRecording} style={{ padding: '0.875rem 2rem', fontSize: '1rem' }}>
                <Mic size={20} /> Start Recording
              </button>
            ) : (
              <button
                onClick={stopRecording}
                style={{
                  padding: '0.875rem 2rem',
                  fontSize: '1rem',
                  background: 'rgba(239, 68, 68, 0.15)',
                  color: '#ef4444',
                  border: '1px solid rgba(239, 68, 68, 0.3)',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  fontWeight: 600,
                }}
              >
                <Square size={18} /> Stop Recording
              </button>
            )}
          </div>

          <p style={{
            marginTop: '1.5rem',
            fontSize: '0.8rem',
            color: 'var(--text-secondary)',
          }}>
            Record 10–30 seconds of clear speech for best results
          </p>
        </div>

        {/* Error */}
        {error && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            padding: '1rem',
            background: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.2)',
            borderRadius: '8px',
            color: '#f87171',
            marginBottom: '1rem',
          }}>
            <AlertCircle size={20} />
            <span style={{ fontSize: '0.9rem' }}>{error}</span>
          </div>
        )}

        {/* Playback + Upload */}
        {audioUrl && !isRecording && (
          <div style={{ borderTop: '1px solid var(--border-color)', paddingTop: '1.5rem' }}>
            <h3 style={{ marginBottom: '1rem' }}>Your Recording</h3>

            {/* Audio player */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '1rem',
              marginBottom: '1.5rem',
              padding: '1rem',
              background: 'rgba(255, 255, 255, 0.02)',
              borderRadius: '8px',
              border: '1px solid var(--border-color)',
            }}>
              <audio
                src={audioUrl}
                controls
                style={{
                  flex: 1,
                  height: '40px',
                  borderRadius: '8px',
                  filter: 'invert(1) hue-rotate(180deg)',
                }}
              />
              <button
                className="btn-outline"
                onClick={discardRecording}
                style={{ padding: '0.5rem 0.75rem', fontSize: '0.8rem' }}
                title="Discard and re-record"
              >
                <Trash2 size={16} /> Discard
              </button>
            </div>

            {/* Voice Name */}
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', display: 'block', marginBottom: '0.25rem' }}>
                Voice Profile Name
              </label>
              <input
                value={voiceName}
                onChange={e => setVoiceName(e.target.value)}
                placeholder="e.g. Sarah Sales Voice"
                style={{ marginBottom: 0 }}
              />
            </div>

            {/* Upload Button */}
            <button
              className="btn-primary"
              onClick={uploadRecording}
              disabled={uploadStatus === 'uploading'}
              style={{
                width: '100%',
                padding: '0.875rem',
                opacity: uploadStatus === 'uploading' ? 0.7 : 1,
              }}
            >
              {uploadStatus === 'uploading' ? (
                <>
                  <div style={{
                    width: '18px',
                    height: '18px',
                    border: '2px solid rgba(255,255,255,0.3)',
                    borderTopColor: '#fff',
                    borderRadius: '50%',
                    animation: 'spin 0.6s linear infinite',
                  }} />
                  Processing Voice Clone...
                </>
              ) : (
                <>
                  <Upload size={18} /> Create Voice Clone
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {/* Success Card */}
      {clonedVoiceId && (
        <div className="glass-card" style={{
          marginBottom: '1.5rem',
          border: '1px solid rgba(16, 185, 129, 0.3)',
          background: 'rgba(16, 185, 129, 0.05)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div style={{
              width: '40px',
              height: '40px',
              borderRadius: '50%',
              background: 'rgba(16, 185, 129, 0.15)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <Check size={20} style={{ color: 'var(--success)' }} />
            </div>
            <div>
              <h3 style={{ color: 'var(--success)', marginBottom: '0.25rem' }}>Voice Cloned Successfully!</h3>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                Voice ID: <code style={{ color: 'var(--accent-primary)', fontFamily: 'monospace' }}>{clonedVoiceId}</code>
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Tips Card */}
      <div className="glass-card" style={{
        background: 'rgba(99, 102, 241, 0.03)',
        borderColor: 'rgba(99, 102, 241, 0.1)',
      }}>
        <h3 style={{ marginBottom: '1rem', fontSize: '1rem' }}>Tips for Best Results</h3>
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '0.75rem',
          fontSize: '0.85rem',
          color: 'var(--text-secondary)',
        }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
            <span style={{ color: 'var(--success)' }}>✓</span> Record in a quiet environment
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
            <span style={{ color: 'var(--success)' }}>✓</span> Speak clearly at normal pace
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
            <span style={{ color: 'var(--success)' }}>✓</span> Include speech variety
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
            <span style={{ color: 'var(--success)' }}>✓</span> Use a quality microphone
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
            <span style={{ color: 'var(--warning)' }}>✗</span> Avoid filler words (um, uh)
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem' }}>
            <span style={{ color: 'var(--warning)' }}>✗</span> Avoid background noise
          </div>
        </div>
      </div>

      {/* Inline keyframes for spin animation */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}