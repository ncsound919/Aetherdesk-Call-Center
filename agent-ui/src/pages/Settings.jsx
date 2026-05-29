import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'

export default function Settings() {
  const { tenant, user, logout } = useAuth()
  const [activeTab, setActiveTab] = useState('general')
  const [formData, setFormData] = useState({
    companyName: 'AetherDesk',
    timezone: 'America/New_York',
    language: 'en-US',
    notificationEmail: '',
    maxConcurrentCalls: 10,
    recordingRetention: 365,
    gdprConsent: true,
    hipaaConsent: true,
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    // In production, update tenant settings via API
    console.log('Settings updated:', formData)
  }

  const tabs = [
    { id: 'general', label: 'General' },
    { id: 'compliance', label: 'Compliance' },
    { id: 'billing', label: 'Billing' },
    { id: 'integrations', label: 'Integrations' },
    { id: 'security', label: 'Security' },
  ]

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-gray-900">Settings</h1>
        <p className="text-gray-600">Manage your platform configuration</p>
      </div>

      <div className="bg-white rounded-lg shadow">
        <div className="border-b border-gray-200">
          <nav className="flex space-x-8 px-6" aria-label="Tabs">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </div>

        <div className="p-6">
          {activeTab === 'general' && (
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                <div>
                  <label className="block text-sm font-medium text-gray-700">Company Name</label>
                  <input
                    type="text"
                    value={formData.companyName}
                    onChange={(e) => setFormData({ ...formData, companyName: e.target.value })}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Timezone</label>
                  <select
                    value={formData.timezone}
                    onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                  >
                    <option value="America/New_York">Eastern Time (ET)</option>
                    <option value="America/Chicago">Central Time (CT)</option>
                    <option value="America/Denver">Mountain Time (MT)</option>
                    <option value="America/Los_Angeles">Pacific Time (PT)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Language</label>
                  <select
                    value={formData.language}
                    onChange={(e) => setFormData({ ...formData, language: e.target.value })}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                  >
                    <option value="en-US">English (US)</option>
                    <option value="es-US">Spanish (US)</option>
                    <option value="fr-FR">French</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700">Max Concurrent Calls</label>
                  <input
                    type="number"
                    value={formData.maxConcurrentCalls}
                    onChange={(e) => setFormData({ ...formData, maxConcurrentCalls: e.target.value })}
                    className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
                  />
                </div>
              </div>
              <div className="flex justify-end">
                <button
                  type="submit"
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                >
                  Save Changes
                </button>
              </div>
            </form>
          )}

          {activeTab === 'compliance' && (
            <div className="space-y-6">
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div>
                  <h3 className="text-sm font-medium text-gray-900">GDPR Compliance</h3>
                  <p className="text-sm text-gray-500">Ensure EU data protection compliance</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" checked={formData.gdprConsent} readOnly className="sr-only peer" />
                  <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:bg-blue-600 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-5 after:w-5 after:transition-all"></div>
                </label>
              </div>
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div>
                  <h3 className="text-sm font-medium text-gray-900">HIPAA Compliance</h3>
                  <p className="text-sm text-gray-500">Healthcare data protection compliance</p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input type="checkbox" checked={formData.hipaaConsent} readOnly className="sr-only peer" />
                  <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:bg-blue-600 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-5 after:w-5 after:transition-all"></div>
                </label>
              </div>
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div>
                  <h3 className="text-sm font-medium text-gray-900">Data Residency</h3>
                  <p className="text-sm text-gray-500">Data stored in US-East1 (GCP)</p>
                </div>
                <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm">US-East1</span>
              </div>
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div>
                  <h3 className="text-sm font-medium text-gray-900">Encryption at Rest</h3>
                  <p className="text-sm text-gray-500">AES-256 encryption for all stored data</p>
                </div>
                <span className="px-3 py-1 bg-green-100 text-green-800 rounded-full text-sm">Enabled</span>
              </div>
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
                <div>
                  <h3 className="text-sm font-medium text-gray-900">Call Recording Retention</h3>
                  <p className="text-sm text-gray-500">How long recordings are retained</p>
                </div>
                <span className="text-sm text-gray-600">{formData.recordingRetention} days</span>
              </div>
            </div>
          )}

          {activeTab === 'billing' && (
            <div className="text-center py-12">
              <p className="text-gray-500">Billing information managed through your subscription portal</p>
            </div>
          )}

          {activeTab === 'integrations' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 border rounded-lg">
                <div>
                  <h3 className="font-medium">Fonoster Voice Platform</h3>
                  <p className="text-sm text-gray-500">Core telephony engine</p>
                </div>
                <span className="px-2 py-1 bg-green-100 text-green-800 rounded-full text-xs">Connected</span>
              </div>
              <div className="flex items-center justify-between p-4 border rounded-lg">
                <div>
                  <h3 className="font-medium">FreeSWITCH Media Server</h3>
                  <p className="text-sm text-gray-500">SIP/RTP media handling</p>
                </div>
                <span className="px-2 py-1 bg-green-100 text-green-800 rounded-full text-xs">Connected</span>
              </div>
              <div className="flex items-center justify-between p-4 border rounded-lg">
                <div>
                  <h3 className="font-medium">Deepgram STT</h3>
                  <p className="text-sm text-gray-500">Speech-to-text engine</p>
                </div>
                <span className="px-2 py-1 bg-yellow-100 text-yellow-800 rounded-full text-xs">Configurable</span>
              </div>
              <div className="flex items-center justify-between p-4 border rounded-lg">
                <div>
                  <h3 className="font-medium">Chatterbox TTS</h3>
                  <p className="text-sm text-gray-500">Text-to-speech (self-hosted, free)</p>
                </div>
                <span className="px-2 py-1 bg-green-100 text-green-800 rounded-full text-xs">Primary</span>
              </div>
              <div className="flex items-center justify-between p-4 border rounded-lg">
                <div>
                  <h3 className="font-medium">Qwen3-TTS (1.7B)</h3>
                  <p className="text-sm text-gray-500">Fallback TTS (requires GPU)</p>
                </div>
                <span className="px-2 py-1 bg-yellow-100 text-yellow-800 rounded-full text-xs">Fallback</span>
              </div>
              <div className="flex items-center justify-between p-4 border rounded-lg">
                <div>
                  <h3 className="font-medium">Groq LLM</h3>
                  <p className="text-sm text-gray-500">AI inference engine</p>
                </div>
                <span className="px-2 py-1 bg-yellow-100 text-yellow-800 rounded-full text-xs">Configurable</span>
              </div>
            </div>
          )}

          {activeTab === 'security' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-medium text-gray-900 mb-2">Change Password</h3>
                <div className="space-y-2">
                  <input type="password" placeholder="Current password" className="w-full rounded-md border-gray-300 shadow-sm" />
                  <input type="password" placeholder="New password" className="w-full rounded-md border-gray-300 shadow-sm" />
                  <input type="password" placeholder="Confirm password" className="w-full rounded-md border-gray-300 shadow-sm" />
                </div>
                <button className="mt-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm">
                  Update Password
                </button>
              </div>
              <div className="border-t pt-4">
                <button
                  onClick={logout}
                  className="text-red-600 hover:text-red-800 text-sm font-medium"
                >
                  Sign Out
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}