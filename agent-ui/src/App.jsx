import React, { useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'sonner'
import { Menu } from 'lucide-react'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import AgentManagement from './pages/AgentManagement'
import CallLogs from './pages/CallLogs'
import Settings from './pages/Settings'
import VoiceCloning from './pages/VoiceCloning'
import Analytics from './pages/Analytics'
import Login from './pages/Login'
import SignupPage from './pages/SignupPage'
import ForgotPasswordPage from './pages/ForgotPasswordPage'
import ResetPasswordPage from './pages/ResetPasswordPage'
import VerifyEmailPage from './pages/VerifyEmailPage'
import BillingPage from './pages/BillingPage'
import LeadsPage from './pages/LeadsPage'
import ScriptsPage from './pages/ScriptsPage'
import ScriptEditorPage from './pages/ScriptEditorPage'
import LeadImportPage from './pages/LeadImportPage'
import { AuthProvider, useAuth } from './context/AuthContext'
import { SocketProvider } from './context/SocketContext'

function AppContent() {
  const { isAuthenticated, loading } = useAuth()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-canvas">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 rounded-xl bg-accent flex items-center justify-center">
            <div className="h-4 w-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
          </div>
          <p className="text-sm text-ink-muted">Loading...</p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />
        <Route path="/verify-email" element={<VerifyEmailPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    )
  }

  return (
    <div className="flex h-screen overflow-hidden bg-canvas">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex-1 flex flex-col min-w-0">
        {/* Mobile header */}
        <header className="lg:hidden flex items-center h-14 px-4 border-b border-hairline bg-white">
          <button onClick={() => setSidebarOpen(true)} className="p-2 -ml-2 rounded-lg hover:bg-surface-hover">
            <Menu className="h-5 w-5 text-ink" />
          </button>
          <div className="ml-3 flex items-center gap-2">
            <div className="h-6 w-6 rounded-md bg-accent flex items-center justify-center">
              <div className="h-3 w-3 border-2 border-white rounded-sm" />
            </div>
            <span className="font-semibold text-sm text-ink">AetherDesk</span>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/analytics" element={<Analytics />} />
            <Route path="/agents" element={<AgentManagement />} />
            <Route path="/calls" element={<CallLogs />} />
            <Route path="/voice-cloning" element={<VoiceCloning />} />
            <Route path="/billing" element={<BillingPage />} />
            <Route path="/leads" element={<LeadsPage />} />
            <Route path="/leads/import" element={<LeadImportPage />} />
            <Route path="/scripts" element={<ScriptsPage />} />
            <Route path="/scripts/new" element={<ScriptEditorPage />} />
            <Route path="/scripts/:id" element={<ScriptEditorPage />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<SignupPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
            <Route path="/verify-email" element={<VerifyEmailPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
      <Toaster
        position="top-right"
        toastOptions={{
          style: { fontFamily: 'Inter, sans-serif', borderRadius: '12px', border: '1px solid #e2e8f0', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.06)' },
        }}
      />
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <SocketProvider>
        <Routes>
          <Route path="/*" element={<AppContent />} />
        </Routes>
      </SocketProvider>
    </AuthProvider>
  )
}
