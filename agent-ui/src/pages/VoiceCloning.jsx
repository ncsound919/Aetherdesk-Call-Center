import { useState, useRef, useEffect } from 'react';
import { Mic, Square, Play, Pause, Upload, Check, AlertCircle } from 'lucide-react';

export default function VoiceCloning() {
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [recordingTime, setRecordingTime] = useState(0);
  const [uploadStatus, setUploadStatus] = useState('idle');
  const [clonedVoiceId, setClonedVoiceId] = useState(null);
  const [error, setError] = useState(null);

  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorderRef.current = new MediaRecorder(stream);
      chunksRef.current = [];

      mediaRecorderRef.current.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data);
        }
      };

      mediaRecorderRef.current.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        setAudioBlob(blob);
        setAudioUrl(URL.createObjectURL(blob));
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorderRef.current.start(100);
      setIsRecording(true);
      setRecordingTime(0);
      setError(null);

      timerRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);
    } catch (err) {
      setError('Could not access microphone. Please grant permission.');
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      clearInterval(timerRef.current);
    }
  };

  const playAudio = () => {
    if (audioUrl) {
      const audio = new Audio(audioUrl);
      audio.play();
    }
  };

  const uploadRecording = async () => {
    if (!audioBlob) return;

    setUploadStatus('uploading');
    setError(null);

    try {
      const formData = new FormData();
      formData.append('audio', audioBlob, 'voice_sample.webm');
      formData.append('voice_name', 'My Voice');
      formData.append('language', 'en-US');

      const response = await fetch('/api/v1/voice/clone', {
        method: 'POST',
        body: formData,
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (!response.ok) {
        throw new Error('Failed to upload voice sample');
      }

      const data = await response.json();
      setClonedVoiceId(data.voice_id);
      setUploadStatus('success');
    } catch (err) {
      setError(err.message);
      setUploadStatus('error');
    }
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="max-w-2xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-2">Voice Cloning</h1>
      <p className="text-gray-600 mb-6">
        Record your voice to create a custom TTS voice for outbound calls and agent responses.
      </p>

      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="text-lg font-semibold mb-4">Record Voice Sample</h2>

        <div className="flex flex-col items-center justify-center py-8 mb-4 border-2 border-dashed rounded-lg">
          <div className="w-32 h-32 rounded-full bg-blue-100 flex items-center justify-center mb-4">
            <Mic className={`w-12 h-12 ${isRecording ? 'text-red-500 animate-pulse' : 'text-blue-500'}`} />
          </div>

          {isRecording && (
            <div className="text-2xl font-mono mb-4">{formatTime(recordingTime)}</div>
          )}

          <div className="flex gap-4">
            {!isRecording ? (
              <button
                onClick={startRecording}
                className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex items-center gap-2"
              >
                <Mic className="w-5 h-5" />
                Start Recording
              </button>
            ) : (
              <button
                onClick={stopRecording}
                className="px-6 py-3 bg-red-600 text-white rounded-lg hover:bg-red-700 flex items-center gap-2"
              >
                <Square className="w-5 h-5" />
                Stop Recording
              </button>
            )}
          </div>

          <p className="mt-4 text-sm text-gray-500">
            Record 10-30 seconds of clear speech for best results
          </p>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-50 text-red-700 rounded-lg mb-4">
            <AlertCircle className="w-5 h-5" />
            {error}
          </div>
        )}

        {audioUrl && !isRecording && (
          <div className="border-t pt-4">
            <h3 className="font-medium mb-3">Your Recording</h3>
            <div className="flex items-center gap-4 mb-4">
              <button
                onClick={playAudio}
                className="p-2 bg-gray-100 rounded-full hover:bg-gray-200"
              >
                <Play className="w-5 h-5" />
              </button>
              <audio src={audioUrl} controls className="flex-1" />
            </div>

            <button
              onClick={uploadRecording}
              disabled={uploadStatus === 'uploading'}
              className="w-full py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 flex items-center justify-center gap-2"
            >
              {uploadStatus === 'uploading' ? (
                <>
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Processing...
                </>
              ) : (
                <>
                  <Upload className="w-5 h-5" />
                  Create Voice Clone
                </>
              )}
            </button>
          </div>
        )}
      </div>

      {clonedVoiceId && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 flex items-center gap-3">
          <Check className="w-6 h-6 text-green-600" />
          <div>
            <h3 className="font-medium text-green-800">Voice Cloned Successfully!</h3>
            <p className="text-sm text-green-600">Voice ID: {clonedVoiceId}</p>
          </div>
        </div>
      )}

      <div className="bg-gray-50 rounded-lg p-4 mt-6">
        <h3 className="font-medium mb-2">Tips for Best Results</h3>
        <ul className="text-sm text-gray-600 space-y-1">
          <li>• Record in a quiet environment with no background noise</li>
          <li>• Speak clearly at a normal pace</li>
          <li>• Include variety in your speech (different sentences, emotions)</li>
          <li>• Avoid filler words like "um", "uh", "like"</li>
          <li>• Use a good quality microphone if possible</li>
        </ul>
      </div>
    </div>
  );
}