import React, { useState, useEffect, useRef, useCallback } from 'react'
import api from '../services/api'
import {
  Mic, MicOff, Play, Square, CheckCircle2, XCircle, Loader2,
  Trash2, Star, Volume2, Clock, Music, AlertTriangle, Save,
  Download, FileAudio, Plus, Settings2
} from 'lucide-react'
import { toast } from 'sonner'

export default function VoiceCloning() {
  const [voices, setVoices] = useState([])
  const [loading, setLoading] = useState(true)
  const [recording, setRecording] = useState(false)
  const [recordedBlob, setRecordedBlob] = useState(null)
  const [recordDuration, setRecordDuration] = useState(0)
  const [recordingName, setRecordingName] = useState('')
  const [uploading, setUploading] = useState(false)
  const [playing, setPlaying] = useState(null)
  const [showRecorder, setShowRecorder] = useState(false)

  const mediaRecorderRef = useRef(null)
  const streamRef = useRef(null)
  const timerRef = useRef(null)
  const chunksRef = useRef([])
  const audioRef = useRef(null)

  const fetchVoices = useCallback(async () => {
    try {
      const res = await api.get('/voice/clones')
      setVoices(Array.isArray(res.data?.voices) ? res.data.voices : [])
    } catch { setVoices([]) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchVoices() }, [fetchVoices])

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000, channelCount: 1 } })
      streamRef.current = stream
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
      mediaRecorderRef.current = mediaRecorder
      chunksRef.current = []
      setRecordDuration(0)
      setRecordedBlob(null)

      mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
      mediaRecorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' })
        setRecordedBlob(blob)
        stream.getTracks().forEach(t => t.stop())
        clearInterval(timerRef.current)
      }

      mediaRecorder.start()
      setRecording(true)
      timerRef.current = setInterval(() => {
        setRecordDuration(prev => { if (prev >= 30) { stopRecording(); return 30 }; return prev + 1 })
      }, 1000)
    } catch (err) {
      toast.error('Microphone access denied. Please allow microphone permissions.')
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop()
    }
    setRecording(false)
    clearInterval(timerRef.current)
  }

  const uploadVoice = async () => {
    if (!recordedBlob || !recordingName.trim()) {
      toast.error('Please name your voice and record a sample')
      return
    }
    if (recordDuration < 5) {
      toast.error('Recording must be at least 5 seconds')
      return
    }
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('audio', recordedBlob, 'voice.webm')
      formData.append('voice_name', recordingName.trim())
      formData.append('language', 'en-US')
      await api.post('/voice/clone', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        timeout: 120000,
      })
      toast.success(`Voice "${recordingName}" created!`)
      setShowRecorder(false)
      setRecordingName('')
      setRecordedBlob(null)
      fetchVoices()
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Voice cloning failed')
    } finally { setUploading(false) }
  }

  const deleteVoice = async (voiceId, name) => {
    if (!window.confirm(`Delete voice "${name}"?`)) return
    try {
      await api.delete(`/voice/clones/${voiceId}`)
      toast.success('Voice deleted')
      fetchVoices()
    } catch { toast.error('Failed to delete') }
  }

  const playVoice = async (voiceId) => {
    setPlaying(voiceId)
    // In production, fetch a sample TTS from the cloned voice
    setTimeout(() => setPlaying(null), 1500)
  }

  const formatDuration = (s) => {
    const m = Math.floor(s / 60)
    const sec = s % 60
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  return (
    <div className="p-6 max-w-5xl mx-auto animate-slide-up">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-ink tracking-tight">Voice Cloning</h1>
          <p className="text-sm text-ink-muted mt-0.5">Create and manage custom AI voices for your agents</p>
        </div>
        <button onClick={() => setShowRecorder(true)} className="btn-primary">
          <Mic className="h-4 w-4" />
          New Voice
        </button>
      </div>

      {loading ? (
        <div className="card p-12 text-center">
          <Loader2 className="h-6 w-6 animate-spin mx-auto text-ink-subtle mb-2" />
          <p className="text-sm text-ink-muted">Loading voices...</p>
        </div>
      ) : voices.length === 0 && !showRecorder ? (
        <div className="card p-12 text-center">
          <Mic className="h-10 w-10 mx-auto text-ink-subtle mb-3" />
          <p className="text-sm text-ink-muted">No voice clones yet</p>
          <p className="text-xs text-ink-subtle mt-1">Create a custom voice for your AI agents to use during calls</p>
          <button onClick={() => setShowRecorder(true)} className="btn-primary mt-4">
            <Mic className="h-4 w-4" />
            Record your voice
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {voices.map((voice) => (
            <div key={voice.id} className="card p-4 group hover:border-accent/20 transition-all">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-xl bg-accent-soft flex items-center justify-center">
                    <Music className="h-5 w-5 text-accent" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-ink">{voice.name || 'Unnamed'}</p>
                    <p className="text-xs text-ink-muted">{voice.language || 'en-US'}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  <button onClick={() => playVoice(voice.id)}
                    className="btn-ghost p-1.5">
                    {playing === voice.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Volume2 className="h-4 w-4" />}
                  </button>
                  <button onClick={() => deleteVoice(voice.id, voice.name)}
                    className="btn-ghost p-1.5 text-call-red">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
              <div className="flex items-center gap-3 text-xs text-ink-muted">
                <span className="flex items-center gap-1"><Clock className="h-3 w-3" /> {voice.duration || '30s'}</span>
                <span className="flex items-center gap-1"><FileAudio className="h-3 w-3" /> {voice.format || 'WAV'}</span>
              </div>
              <div className="mt-3 pt-3 border-t border-hairline flex items-center justify-between">
                <span className={`text-xs font-medium ${voice.status === 'ready' ? 'text-call-green' : 'text-call-amber'}`}>
                  {voice.status === 'ready' ? 'Ready' : 'Processing'}
                </span>
              </div>
            </div>
          ))}

          {/* Add new card */}
          <button onClick={() => setShowRecorder(true)}
            className="card p-4 border-dashed border-2 hover:border-accent/30 hover:bg-surface-hover transition-all flex items-center justify-center min-h-[140px] group">
            <div className="text-center">
              <Plus className="h-8 w-8 mx-auto text-ink-subtle group-hover:text-accent transition-colors" />
              <p className="text-sm text-ink-muted mt-2 group-hover:text-accent transition-colors">New Voice</p>
            </div>
          </button>
        </div>
      )}

      {/* Recording Modal */}
      {showRecorder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-xl shadow-modal w-full max-w-lg mx-4 p-6 animate-scale-in">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-lg font-semibold text-ink">Create Voice Clone</h2>
              <button onClick={() => { setShowRecorder(false); setRecordedBlob(null); stopRecording() }}
                className="p-1.5 rounded-lg hover:bg-surface-hover">
                <XCircle className="h-5 w-5 text-ink-muted" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-ink mb-1.5">Voice Name</label>
                <input type="text" value={recordingName} onChange={(e) => setRecordingName(e.target.value)}
                  className="input-field" placeholder="e.g. Professional Female" />
              </div>

              {/* Recorder UI */}
              <div className="bg-surface-hover rounded-xl p-6 text-center">
                {!recording && !recordedBlob && (
                  <>
                    <div className="h-16 w-16 rounded-full bg-accent-soft flex items-center justify-center mx-auto mb-3">
                      <Mic className="h-7 w-7 text-accent" />
                    </div>
                    <p className="text-sm text-ink-muted mb-1">Record a voice sample</p>
                    <p className="text-xs text-ink-muted mb-4">Speak clearly for 10-30 seconds</p>
                    <button onClick={startRecording} className="btn-primary">
                      <Mic className="h-4 w-4" />
                      Start Recording
                    </button>
                  </>
                )}

                {recording && (
                  <>
                    <div className="h-16 w-16 rounded-full bg-call-red-soft flex items-center justify-center mx-auto mb-3 glow-call">
                      <MicOff className="h-7 w-7 text-call-red" />
                    </div>
                    <p className="text-lg font-semibold text-call-red tabular-nums">{formatDuration(recordDuration)}</p>
                    <p className="text-xs text-ink-muted mt-1">Recording... speak clearly</p>
                    <button onClick={stopRecording} className="btn-danger mt-4">
                      <Square className="h-4 w-4" />
                      Stop Recording
                    </button>
                  </>
                )}

                {recordedBlob && !recording && (
                  <>
                    <div className="h-16 w-16 rounded-full bg-call-green-soft flex items-center justify-center mx-auto mb-3">
                      <CheckCircle2 className="h-7 w-7 text-call-green" />
                    </div>
                    <p className="text-sm font-semibold text-call-green">Recording complete!</p>
                    <p className="text-xs text-ink-muted mt-1">{formatDuration(recordDuration)} recorded</p>
                    <div className="flex items-center justify-center gap-2 mt-4">
                      <button onClick={() => { const a = document.createElement('a'); a.href = URL.createObjectURL(recordedBlob); a.download = `${recordingName || 'voice'}.webm`; a.click() }}
                        className="btn-secondary">
                        <Download className="h-4 w-4" />
                        Download
                      </button>
                      <button onClick={() => { setRecordedBlob(null); setRecordDuration(0) }}
                        className="btn-secondary">
                        <Mic className="h-4 w-4" />
                        Re-record
                      </button>
                    </div>
                  </>
                )}
              </div>

              {/* Tips */}
              {!recordedBlob && (
                <div className="bg-call-amber-soft border border-call-amber/20 rounded-xl p-3">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="h-4 w-4 text-call-amber mt-0.5 shrink-0" />
                    <div className="text-xs text-call-amber">
                      <p className="font-semibold mb-0.5">Recording tips:</p>
                      <ul className="space-y-0.5">
                        <li>• Record in a quiet room with no echo</li>
                        <li>• Speak at a natural pace and volume</li>
                        <li>• Minimum 5 seconds, recommended 15-30 seconds</li>
                        <li>• Use a consistent tone throughout</li>
                      </ul>
                    </div>
                  </div>
                </div>
              )}

              <div className="flex gap-3 pt-2">
                <button onClick={() => { setShowRecorder(false); setRecordedBlob(null); stopRecording() }}
                  className="btn-secondary flex-1">Cancel</button>
                <button onClick={uploadVoice} disabled={uploading || !recordedBlob || !recordingName.trim() || recordDuration < 5}
                  className="btn-primary flex-1">
                  {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  {uploading ? 'Creating voice...' : 'Create Voice'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
