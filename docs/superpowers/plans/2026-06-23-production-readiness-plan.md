# AetherDesk Production Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve all architectural conflicts, achieve 100% frontend test coverage for critical paths, extract main.py monolith, and add CI/CD frontend checks to reach 100% production readiness.

**Architecture:** The active app is `App.jsx` (JSX, JSX entry point). `App.tsx` is dead code. We will merge the SaaS pages (Billing, Leads, Scripts, Signup, etc.) into the active JSX app, delete dead code, add comprehensive tests, extract main.py routes into router modules, and add frontend CI checks.

**Tech Stack:** React 19.2.7, TypeScript (partial), Vite, Jest 30, @testing-library/react 16, Playwright, FastAPI, Python 3.12, pytest, Alembic

---

## File Structure

### Files to Create
| File | Responsibility |
|------|---------------|
| `apps/api/routers/tenants.py` | Tenant CRUD routes extracted from main.py |
| `apps/api/routers/agent_management.py` | Agent CRUD routes extracted from main.py |
| `apps/api/routers/call_management.py` | Call routes extracted from main.py |
| `apps/api/routers/health.py` | Health check routes extracted from main.py |
| `apps/api/routers/webhooks_fonster.py` | Fonster webhook extracted from main.py |
| `apps/api/routers/usage.py` | Usage analytics routes extracted from main.py |
| `apps/api/models/dto.py` | Pydantic models extracted from main.py |
| `tests/unit/frontend/pages/Login.test.jsx` | Login page tests |
| `tests/unit/frontend/pages/Dashboard.test.jsx` | Dashboard page tests |
| `tests/unit/frontend/pages/AgentManagement.test.jsx` | Agent management tests |
| `tests/unit/frontend/pages/CallLogs.test.jsx` | Call logs tests |
| `tests/unit/frontend/pages/Settings.test.jsx` | Settings page tests |
| `tests/unit/frontend/pages/BillingPage.test.tsx` | Billing page tests |
| `tests/unit/frontend/pages/SignupPage.test.tsx` | Signup page tests |
| `tests/unit/frontend/pages/LeadsPage.test.tsx` | Leads page tests |
| `tests/unit/frontend/pages/ScriptsPage.test.tsx` | Scripts page tests |
| `tests/unit/frontend/services/api.test.js` | Axios API client tests |
| `tests/unit/frontend/lib/api.test.ts` | Fetch API client tests |
| `tests/unit/frontend/context/AuthContext.test.jsx` | Auth context tests |
| `tests/unit/frontend/context/SocketContext.test.jsx` | Socket context tests |
| `tests/unit/frontend/components/Sidebar.test.jsx` | Sidebar tests |
| `tests/unit/frontend/components/StatCard.test.jsx` | StatCard tests |

### Files to Modify
| File | Changes |
|------|---------|
| `agent-ui/src/App.jsx` | Add routes for Billing, Leads, Scripts, Signup, ForgotPassword, ResetPassword, VerifyEmail |
| `agent-ui/src/context/AuthContext.jsx` | Add tenant to context, add login/signup methods |
| `agent-ui/src/services/api.js` | Standardize token key to `access_token`, add missing API methods |
| `agent-ui/src/pages/Settings.jsx` | Wire up settings form to API |
| `apps/api/main.py` | Remove extracted routes, keep only app setup/middleware/lifespan |
| `.github/workflows/ci-cd.yml` | Add frontend lint, test, build, typecheck steps |
| `.gitignore` | Add .env, *.db, coverage/, dist/, logs/ |

### Files to Delete
| File | Reason |
|------|--------|
| `agent-ui/src/App.tsx` | Dead code (active entry is main.jsx → App.jsx) |
| `agent-ui/src/main.tsx` | Dead code |
| `agent-ui/src/components/Dashboard.tsx` | Broken import, dead code |
| `agent-ui/src/components/LandingPage.tsx` | Only imported by dead App.tsx |
| `agent-ui/src/components/SaaSDashboard.tsx` | Only imported by dead App.tsx |
| `agent-ui/src/components/CallDetail.tsx` | Only imported by dead SaaSDashboard |
| `agent-ui/src/components/Inbox.tsx` | Not imported by any routed component |
| `agent-ui/src/components/OnboardingWizard.tsx` | Not imported by any routed component |
| `agent-ui/src/components/onboarding/` | Only used by dead OnboardingWizard |
| `agent-ui/src/lib/api.ts` | Dead code (replaced by services/api.js) |
| `agent-ui/vite.config.ts` | Dead code (active is vite.config.js) |

---

## Task 1: Delete Dead Frontend Code

**Files:**
- Delete: `agent-ui/src/App.tsx`
- Delete: `agent-ui/src/main.tsx`
- Delete: `agent-ui/src/components/Dashboard.tsx`
- Delete: `agent-ui/src/components/LandingPage.tsx`
- Delete: `agent-ui/src/components/SaaSDashboard.tsx`
- Delete: `agent-ui/src/components/CallDetail.tsx`
- Delete: `agent-ui/src/components/Inbox.tsx`
- Delete: `agent-ui/src/components/OnboardingWizard.tsx`
- Delete: `agent-ui/src/components/onboarding/` (entire directory)
- Delete: `agent-ui/src/lib/api.ts`
- Delete: `agent-ui/vite.config.ts`

- [ ] **Step 1: Verify no active code imports these files**

Run: `grep -r "from.*App\.tsx\|from.*main\.tsx\|from.*Dashboard\.tsx\|from.*LandingPage\|from.*SaaSDashboard\|from.*CallDetail\|from.*Inbox\|from.*OnboardingWizard\|from.*lib/api\|from.*vite\.config\.ts" agent-ui/src/ --include="*.jsx" --include="*.tsx" --include="*.js" --include="*.ts"`

Expected: Only matches in the dead files themselves (circular references), not in active code.

- [ ] **Step 2: Delete all dead files**

```bash
rm agent-ui/src/App.tsx agent-ui/src/main.tsx
rm agent-ui/src/components/Dashboard.tsx agent-ui/src/components/LandingPage.tsx
rm agent-ui/src/components/SaaSDashboard.tsx agent-ui/src/components/CallDetail.tsx
rm agent-ui/src/components/Inbox.tsx agent-ui/src/components/OnboardingWizard.tsx
rm -rf agent-ui/src/components/onboarding/
rm agent-ui/src/lib/api.ts agent-ui/vite.config.ts
```

- [ ] **Step 3: Verify build still works**

Run: `cd agent-ui && npx vite build --mode development 2>&1 | head -20`

Expected: Build succeeds with no errors.

- [ ] **Step 4: Commit**

```bash
git add -A agent-ui/src/
git commit -m "chore: delete dead TSX/vite config files and unreachable components"
```

---

## Task 2: Merge SaaS Routes into Active App.jsx

**Files:**
- Modify: `agent-ui/src/App.jsx:1-49`
- Modify: `agent-ui/src/context/AuthContext.jsx:1-50`
- Modify: `agent-ui/src/services/api.js:1-74`

- [ ] **Step 1: Read current App.jsx, AuthContext.jsx, and api.js**

Read these files to understand current state before modifying.

- [ ] **Step 2: Add missing routes to App.jsx**

Replace the contents of `agent-ui/src/App.jsx` with:

```jsx
import React, { useState, useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'sonner'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import AgentManagement from './pages/AgentManagement'
import CallLogs from './pages/CallLogs'
import Settings from './pages/Settings'
import VoiceCloning from './pages/VoiceCloning'
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
  const [sidebarOpen, setSidebarOpen] = useState(true)

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
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
        <Route path="*" element={<Navigate to="/login" />} />
      </Routes>
    )
  }

  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <main className="flex-1 overflow-y-auto">
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/" element={<Dashboard />} />
          <Route path="/agents" element={<AgentManagement />} />
          <Route path="/calls" element={<CallLogs />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/voice-cloning" element={<VoiceCloning />} />
          <Route path="/billing" element={<BillingPage />} />
          <Route path="/leads" element={<LeadsPage />} />
          <Route path="/leads/import" element={<LeadImportPage />} />
          <Route path="/scripts" element={<ScriptsPage />} />
          <Route path="/scripts/:id" element={<ScriptEditorPage />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
      <Toaster position="top-right" />
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <SocketProvider>
        <AppContent />
      </SocketProvider>
    </AuthProvider>
  )
}
```

- [ ] **Step 3: Update AuthContext.jsx to add missing methods**

Replace the contents of `agent-ui/src/context/AuthContext.jsx` with:

```jsx
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import api from '../services/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [tenant, setTenant] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('token')
    const tenantId = localStorage.getItem('tenantId')
    const userName = localStorage.getItem('userName')
    const userRole = localStorage.getItem('userRole')
    const userEmail = localStorage.getItem('userEmail')
    const userId = localStorage.getItem('userId')
    if (token && tenantId) {
      setUser({ token, name: userName, role: userRole, email: userEmail, userId })
      setTenant({ id: tenantId })
    }
    setLoading(false)
  }, [])

  const login = useCallback(async (email, password) => {
    const response = await api.post('/auth/login', { email, password })
    const { token, tenantId, name, role, userId } = response.data
    const userData = { name, role, userId, email }
    localStorage.setItem('token', token)
    localStorage.setItem('tenantId', tenantId)
    localStorage.setItem('userName', name)
    localStorage.setItem('userRole', role)
    localStorage.setItem('userEmail', email)
    localStorage.setItem('userId', userId)
    setUser(userData)
    setTenant({ id: tenantId })
    return userData
  }, [])

  const signup = useCallback(async (email, password, companyName) => {
    const response = await api.post('/auth/signup', { email, password, company_name: companyName })
    return response.data
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('token')
    localStorage.removeItem('tenantId')
    localStorage.removeItem('userName')
    localStorage.removeItem('userRole')
    localStorage.removeItem('userEmail')
    localStorage.removeItem('userId')
    setUser(null)
    setTenant(null)
  }, [])

  const isAuthenticated = !!user

  return (
    <AuthContext.Provider value={{ user, tenant, loading, isAuthenticated, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
```

- [ ] **Step 4: Add missing API methods to api.js**

Replace the contents of `agent-ui/src/services/api.js` with:

```javascript
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' }
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('tenantId')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

// Auth
export const authApi = {
  login: (data) => api.post('/auth/login', data),
  signup: (data) => api.post('/auth/signup', data),
  forgotPassword: (email) => api.post('/auth/forgot-password', { email }),
  resetPassword: (token, password) => api.post('/auth/reset-password', { token, password }),
  verifyEmail: (token) => api.post('/auth/verify-email', { token }),
}

// Agents
export const agentApi = {
  list: (tenantId) => api.get(`/tenants/${tenantId}/agents`),
  create: (tenantId, data) => api.post(`/tenants/${tenantId}/agents`, data),
  update: (tenantId, agentId, data) => api.put(`/tenants/${tenantId}/agents/${agentId}`, data),
  delete: (tenantId, agentId) => api.delete(`/tenants/${tenantId}/agents/${agentId}`),
  updateStatus: (agentId, status) => api.patch(`/agents/${agentId}/status`, { status }),
}

// Calls
export const callApi = {
  list: (tenantId, params) => api.get(`/calls`, { params: { tenant_id: tenantId, ...params } }),
  get: (callId) => api.get(`/calls/${callId}`),
  create: (data) => api.post('/calls', data),
  action: (callId, action) => api.post(`/calls/${callId}/action`, { action }),
}

// Billing
export const billingApi = {
  getSummary: (tenantId) => api.get(`/billing`, { params: { tenant_id: tenantId } }),
}

// Leads
export const leadApi = {
  list: (tenantId, params) => api.get(`/leads`, { params: { tenant_id: tenantId, ...params } }),
  create: (tenantId, data) => api.post(`/leads`, { tenant_id: tenantId, ...data }),
  import: (tenantId, file) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('tenant_id', tenantId)
    return api.post('/leads/import', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
}

// Scripts
export const scriptApi = {
  list: (tenantId) => api.get(`/scripts`, { params: { tenant_id: tenantId } }),
  get: (scriptId) => api.get(`/scripts/${scriptId}`),
  create: (tenantId, data) => api.post(`/scripts`, { tenant_id: tenantId, ...data }),
  update: (scriptId, data) => api.put(`/scripts/${scriptId}`, data),
  delete: (scriptId) => api.delete(`/scripts/${scriptId}`),
}

// Settings
export const settingsApi = {
  getTenant: (tenantId) => api.get(`/tenants/${tenantId}`),
  updateTenant: (tenantId, data) => api.put(`/tenants/${tenantId}`, data),
}

export default api
```

- [ ] **Step 5: Verify no imports from deleted files remain**

Run: `grep -r "from.*lib/api\|from.*App\.tsx\|from.*components/Dashboard\.tsx\|from.*components/LandingPage\|from.*components/SaaSDashboard" agent-ui/src/ --include="*.jsx" --include="*.tsx" --include="*.js" --include="*.ts"`

Expected: No matches.

- [ ] **Step 6: Verify build works**

Run: `cd agent-ui && npx vite build --mode development 2>&1 | head -20`

Expected: Build succeeds.

- [ ] **Step 7: Commit**

```bash
git add agent-ui/src/App.jsx agent-ui/src/context/AuthContext.jsx agent-ui/src/services/api.js
git commit -m "feat: merge SaaS routes into active JSX app, unify auth and API clients"
```

---

## Task 3: Fix Settings.jsx to Wire Up Form

**Files:**
- Modify: `agent-ui/src/pages/Settings.jsx:18-21`

- [ ] **Step 1: Read Settings.jsx**

Read the file to see the current empty handleSubmit.

- [ ] **Step 2: Implement handleSubmit**

Replace the `handleSubmit` function in `agent-ui/src/pages/Settings.jsx` (around line 18-21) with:

```javascript
const handleSubmit = async (e) => {
  e.preventDefault()
  if (!tenant?.id) return
  try {
    await settingsApi.updateTenant(tenant.id, {
      name: formData.companyName,
      settings: {
        timezone: formData.timezone,
        max_concurrent_calls: parseInt(formData.maxConcurrentCalls),
      }
    })
    toast.success('Settings saved successfully')
  } catch (err) {
    toast.error(err.response?.data?.detail || 'Failed to save settings')
  }
}
```

Add the import at the top of the file:

```javascript
import { settingsApi } from '../services/api'
import { useAuth } from '../context/AuthContext'
import { toast } from 'sonner'
```

And update the component to use `useAuth`:

```javascript
const { tenant } = useAuth()
```

- [ ] **Step 3: Commit**

```bash
git add agent-ui/src/pages/Settings.jsx
git commit -m "feat: wire Settings form to API backend"
```

---

## Task 4: Add Frontend Tests — Auth Flow

**Files:**
- Create: `tests/unit/frontend/context/AuthContext.test.jsx`
- Create: `tests/unit/frontend/pages/Login.test.jsx`

- [ ] **Step 1: Write AuthContext tests**

Create `tests/unit/frontend/context/AuthContext.test.jsx`:

```jsx
import React from 'react'
import { render, screen, act, waitFor } from '@testing-library/react'
import { AuthProvider, useAuth } from '../../../agent-ui/src/context/AuthContext'
import api from '../../../agent-ui/src/services/api'

jest.mock('../../../agent-ui/src/services/api')

function TestComponent() {
  const { user, tenant, loading, isAuthenticated, login, logout } = useAuth()
  return (
    <div>
      <span data-testid="loading">{loading.toString()}</span>
      <span data-testid="authenticated">{isAuthenticated.toString()}</span>
      <span data-testid="user">{user ? user.name : 'null'}</span>
      <span data-testid="tenant">{tenant ? tenant.id : 'null'}</span>
      <button onClick={() => login('test@example.com', 'password123')}>Login</button>
      <button onClick={logout}>Logout</button>
    </div>
  )
}

describe('AuthContext', () => {
  beforeEach(() => {
    localStorage.clear()
    jest.clearAllMocks()
  })

  test('initializes with loading true then false', async () => {
    render(<AuthProvider><TestComponent /></AuthProvider>)
    expect(screen.getByTestId('loading').textContent).toBe('true')
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
  })

  test('restores user from localStorage', async () => {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('tenantId', 'TENANT-123')
    localStorage.setItem('userName', 'Test User')
    localStorage.setItem('userRole', 'admin')
    localStorage.setItem('userEmail', 'test@example.com')
    localStorage.setItem('userId', 'user-1')

    render(<AuthProvider><TestComponent /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('authenticated').textContent).toBe('true')
    expect(screen.getByTestId('user').textContent).toBe('Test User')
    expect(screen.getByTestId('tenant').textContent).toBe('TENANT-123')
  })

  test('login stores user data and sets authenticated', async () => {
    api.post.mockResolvedValue({
      data: { token: 'new-token', tenantId: 'T-456', name: 'Jane', role: 'agent', userId: 'u-2' }
    })

    render(<AuthProvider><TestComponent /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))

    await act(async () => {
      screen.getByText('Login').click()
    })

    expect(api.post).toHaveBeenCalledWith('/auth/login', { email: 'test@example.com', password: 'password123' })
    expect(screen.getByTestId('authenticated').textContent).toBe('true')
    expect(screen.getByTestId('user').textContent).toBe('Jane')
    expect(localStorage.getItem('token')).toBe('new-token')
    expect(localStorage.getItem('tenantId')).toBe('T-456')
  })

  test('logout clears user data', async () => {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('tenantId', 'T-123')
    localStorage.setItem('userName', 'Test')
    localStorage.setItem('userRole', 'admin')
    localStorage.setItem('userEmail', 'test@test.com')
    localStorage.setItem('userId', 'u-1')

    render(<AuthProvider><TestComponent /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('authenticated').textContent).toBe('true')

    await act(async () => {
      screen.getByText('Logout').click()
    })

    expect(screen.getByTestId('authenticated').textContent).toBe('false')
    expect(localStorage.getItem('token')).toBeNull()
  })

  test('login throws on API error', async () => {
    api.post.mockRejectedValue(new Error('Invalid credentials'))

    render(<AuthProvider><TestComponent /></AuthProvider>)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))

    await expect(async () => {
      await act(async () => {
        screen.getByText('Login').click()
      })
    }).rejects.toThrow('Invalid credentials')
  })
})
```

- [ ] **Step 2: Write Login page tests**

Create `tests/unit/frontend/pages/Login.test.jsx`:

```jsx
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import Login from '../../../agent-ui/src/pages/Login'
import { AuthProvider } from '../../../agent-ui/src/context/AuthContext'
import api from '../../../agent-ui/src/services/api'

jest.mock('../../../agent-ui/src/services/api')

function renderLogin() {
  return render(
    <BrowserRouter>
      <AuthProvider>
        <Login />
      </AuthProvider>
    </BrowserRouter>
  )
}

describe('Login Page', () => {
  beforeEach(() => {
    localStorage.clear()
    jest.clearAllMocks()
  })

  test('renders email and password inputs', () => {
    renderLogin()
    expect(screen.getByPlaceholderText(/email/i)).toBeTruthy()
    expect(screen.getByPlaceholderText(/password/i)).toBeTruthy()
  })

  test('renders login button', () => {
    renderLogin()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeTruthy()
  })

  test('shows error on failed login', async () => {
    api.post.mockRejectedValue({ response: { data: { detail: 'Invalid credentials' } } })

    renderLogin()
    fireEvent.change(screen.getByPlaceholderText(/email/i), { target: { value: 'test@test.com' } })
    fireEvent.change(screen.getByPlaceholderText(/password/i), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByText(/invalid credentials/i)).toBeTruthy()
    })
  })

  test('calls API with correct credentials', async () => {
    api.post.mockResolvedValue({
      data: { token: 'tok', tenantId: 'T-1', name: 'User', role: 'admin', userId: 'u-1' }
    })

    renderLogin()
    fireEvent.change(screen.getByPlaceholderText(/email/i), { target: { value: 'a@b.com' } })
    fireEvent.change(screen.getByPlaceholderText(/password/i), { target: { value: 'pass' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/auth/login', { email: 'a@b.com', password: 'pass' })
    })
  })
})
```

- [ ] **Step 3: Run tests**

Run: `cd agent-ui && npx jest tests/unit/frontend/context/AuthContext.test.jsx tests/unit/frontend/pages/Login.test.jsx --no-coverage 2>&1 | tail -20`

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/frontend/context/AuthContext.test.jsx tests/unit/frontend/pages/Login.test.jsx
git commit -m "test: add AuthContext and Login page unit tests"
```

---

## Task 5: Add Frontend Tests — API Clients

**Files:**
- Create: `tests/unit/frontend/services/api.test.js`

- [ ] **Step 1: Write API client tests**

Create `tests/unit/frontend/services/api.test.js`:

```javascript
import api, { authApi, agentApi, callApi, billingApi, leadApi, scriptApi, settingsApi } from '../../../agent-ui/src/services/api'

describe('API Client', () => {
  beforeEach(() => {
    localStorage.clear()
    jest.clearAllMocks()
  })

  test('adds Authorization header when token exists', async () => {
    localStorage.setItem('token', 'test-token-123')
    const config = {}
    const result = api.interceptors.request.handlers[0].fulfilled(config)
    expect(result.headers.Authorization).toBe('Bearer test-token-123')
  })

  test('does not add Authorization header when no token', () => {
    const config = { headers: {} }
    const result = api.interceptors.request.handlers[0].fulfilled(config)
    expect(result.headers.Authorization).toBeUndefined()
  })

  test('redirects to /login on 401 response', async () => {
    const error = { response: { status: 401 } }
    const rejectFn = jest.fn()
    const resolveFn = jest.fn()
    api.interceptors.response.handlers[0].rejected(error).catch(rejectFn)
    expect(localStorage.getItem('token')).toBeNull()
  })

  describe('authApi', () => {
    test('login calls correct endpoint', async () => {
      const mockPost = jest.spyOn(api, 'post').mockResolvedValue({ data: {} })
      await authApi.login({ email: 'a@b.com', password: 'pass' })
      expect(mockPost).toHaveBeenCalledWith('/auth/login', { email: 'a@b.com', password: 'pass' })
    })

    test('signup calls correct endpoint', async () => {
      const mockPost = jest.spyOn(api, 'post').mockResolvedValue({ data: {} })
      await authApi.signup({ email: 'a@b.com', password: 'pass' })
      expect(mockPost).toHaveBeenCalledWith('/auth/signup', { email: 'a@b.com', password: 'pass' })
    })

    test('forgotPassword calls correct endpoint', async () => {
      const mockPost = jest.spyOn(api, 'post').mockResolvedValue({ data: {} })
      await authApi.forgotPassword('a@b.com')
      expect(mockPost).toHaveBeenCalledWith('/auth/forgot-password', { email: 'a@b.com' })
    })
  })

  describe('agentApi', () => {
    test('list calls correct endpoint', async () => {
      const mockGet = jest.spyOn(api, 'get').mockResolvedValue({ data: [] })
      await agentApi.list('T-1')
      expect(mockGet).toHaveBeenCalledWith('/tenants/T-1/agents')
    })

    test('create calls correct endpoint', async () => {
      const mockPost = jest.spyOn(api, 'post').mockResolvedValue({ data: {} })
      await agentApi.create('T-1', { name: 'Agent 1' })
      expect(mockPost).toHaveBeenCalledWith('/tenants/T-1/agents', { name: 'Agent 1' })
    })

    test('delete calls correct endpoint', async () => {
      const mockDelete = jest.spyOn(api, 'delete').mockResolvedValue({ data: {} })
      await agentApi.delete('T-1', 'A-1')
      expect(mockDelete).toHaveBeenCalledWith('/tenants/T-1/agents/A-1')
    })
  })

  describe('callApi', () => {
    test('list calls correct endpoint with params', async () => {
      const mockGet = jest.spyOn(api, 'get').mockResolvedValue({ data: [] })
      await callApi.list('T-1', { status: 'completed' })
      expect(mockGet).toHaveBeenCalledWith('/calls', { params: { tenant_id: 'T-1', status: 'completed' } })
    })

    test('get calls correct endpoint', async () => {
      const mockGet = jest.spyOn(api, 'get').mockResolvedValue({ data: {} })
      await callApi.get('C-1')
      expect(mockGet).toHaveBeenCalledWith('/calls/C-1')
    })
  })

  describe('billingApi', () => {
    test('getSummary calls correct endpoint', async () => {
      const mockGet = jest.spyOn(api, 'get').mockResolvedValue({ data: {} })
      await billingApi.getSummary('T-1')
      expect(mockGet).toHaveBeenCalledWith('/billing', { params: { tenant_id: 'T-1' } })
    })
  })

  describe('settingsApi', () => {
    test('updateTenant calls correct endpoint', async () => {
      const mockPut = jest.spyOn(api, 'put').mockResolvedValue({ data: {} })
      await settingsApi.updateTenant('T-1', { name: 'New Name' })
      expect(mockPut).toHaveBeenCalledWith('/tenants/T-1', { name: 'New Name' })
    })
  })
})
```

- [ ] **Step 2: Run tests**

Run: `cd agent-ui && npx jest tests/unit/frontend/services/api.test.js --no-coverage 2>&1 | tail -20`

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/frontend/services/api.test.js
git commit -m "test: add API client unit tests for all endpoints"
```

---

## Task 6: Add Frontend Tests — Dashboard, AgentManagement, CallLogs

**Files:**
- Create: `tests/unit/frontend/pages/Dashboard.test.jsx`
- Create: `tests/unit/frontend/pages/AgentManagement.test.jsx`
- Create: `tests/unit/frontend/pages/CallLogs.test.jsx`

- [ ] **Step 1: Write Dashboard tests**

Create `tests/unit/frontend/pages/Dashboard.test.jsx`:

```jsx
import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import Dashboard from '../../../agent-ui/src/pages/Dashboard'
import { AuthProvider } from '../../../agent-ui/src/context/AuthContext'
import api from '../../../agent-ui/src/services/api'

jest.mock('../../../agent-ui/src/services/api')

function renderDashboard() {
  return render(
    <BrowserRouter>
      <AuthProvider>
        <Dashboard />
      </AuthProvider>
    </BrowserRouter>
  )
}

describe('Dashboard Page', () => {
  beforeEach(() => {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('tenantId', 'T-123')
    localStorage.setItem('userName', 'Test User')
    localStorage.setItem('userRole', 'admin')
    localStorage.setItem('userEmail', 'test@test.com')
    localStorage.setItem('userId', 'u-1')
    jest.clearAllMocks()
  })

  test('renders dashboard heading', async () => {
    api.get.mockResolvedValue({ data: { total_calls: 0, active_agents: 0 } })
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByText(/dashboard/i)).toBeTruthy()
    })
  })

  test('displays call statistics', async () => {
    api.get.mockResolvedValue({
      data: { total_calls: 150, active_agents: 5, avg_duration: 120 }
    })
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByText('150')).toBeTruthy()
    })
  })

  test('handles API error gracefully', async () => {
    api.get.mockRejectedValue(new Error('Network error'))
    renderDashboard()
    await waitFor(() => {
      expect(screen.getByText(/dashboard/i)).toBeTruthy()
    })
  })
})
```

- [ ] **Step 2: Write AgentManagement tests**

Create `tests/unit/frontend/pages/AgentManagement.test.jsx`:

```jsx
import React from 'react'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import AgentManagement from '../../../agent-ui/src/pages/AgentManagement'
import { AuthProvider } from '../../../agent-ui/src/context/AuthContext'
import api from '../../../agent-ui/src/services/api'

jest.mock('../../../agent-ui/src/services/api')

function renderAgentManagement() {
  return render(
    <BrowserRouter>
      <AuthProvider>
        <AgentManagement />
      </AuthProvider>
    </BrowserRouter>
  )
}

describe('AgentManagement Page', () => {
  beforeEach(() => {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('tenantId', 'T-123')
    localStorage.setItem('userName', 'Test User')
    localStorage.setItem('userRole', 'admin')
    localStorage.setItem('userEmail', 'test@test.com')
    localStorage.setItem('userId', 'u-1')
    jest.clearAllMocks()
  })

  test('renders agent list', async () => {
    api.get.mockResolvedValue({
      data: [
        { id: 'A-1', name: 'Agent 1', status: 'available' },
        { id: 'A-2', name: 'Agent 2', status: 'busy' }
      ]
    })
    renderAgentManagement()
    await waitFor(() => {
      expect(screen.getByText('Agent 1')).toBeTruthy()
      expect(screen.getByText('Agent 2')).toBeTruthy()
    })
  })

  test('shows add agent button', async () => {
    api.get.mockResolvedValue({ data: [] })
    renderAgentManagement()
    await waitFor(() => {
      expect(screen.getByText(/add agent/i)).toBeTruthy()
    })
  })

  test('handles empty agent list', async () => {
    api.get.mockResolvedValue({ data: [] })
    renderAgentManagement()
    await waitFor(() => {
      expect(screen.getByText(/no agents/i)).toBeTruthy()
    })
  })
})
```

- [ ] **Step 3: Write CallLogs tests**

Create `tests/unit/frontend/pages/CallLogs.test.jsx`:

```jsx
import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import CallLogs from '../../../agent-ui/src/pages/CallLogs'
import { AuthProvider } from '../../../agent-ui/src/context/AuthContext'
import api from '../../../agent-ui/src/services/api'

jest.mock('../../../agent-ui/src/services/api')

function renderCallLogs() {
  return render(
    <BrowserRouter>
      <AuthProvider>
        <CallLogs />
      </AuthProvider>
    </BrowserRouter>
  )
}

describe('CallLogs Page', () => {
  beforeEach(() => {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('tenantId', 'T-123')
    localStorage.setItem('userName', 'Test User')
    localStorage.setItem('userRole', 'admin')
    localStorage.setItem('userEmail', 'test@test.com')
    localStorage.setItem('userId', 'u-1')
    jest.clearAllMocks()
  })

  test('renders call logs table', async () => {
    api.get.mockResolvedValue({
      data: [
        { id: 'C-1', caller: '+1234567890', status: 'completed', duration: 120 },
        { id: 'C-2', caller: '+0987654321', status: 'missed', duration: 0 }
      ]
    })
    renderCallLogs()
    await waitFor(() => {
      expect(screen.getByText('+1234567890')).toBeTruthy()
      expect(screen.getByText('+0987654321')).toBeTruthy()
    })
  })

  test('shows empty state when no calls', async () => {
    api.get.mockResolvedValue({ data: [] })
    renderCallLogs()
    await waitFor(() => {
      expect(screen.getByText(/no calls/i)).toBeTruthy()
    })
  })
})
```

- [ ] **Step 4: Run all three test files**

Run: `cd agent-ui && npx jest tests/unit/frontend/pages/Dashboard.test.jsx tests/unit/frontend/pages/AgentManagement.test.jsx tests/unit/frontend/pages/CallLogs.test.jsx --no-coverage 2>&1 | tail -30`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add tests/unit/frontend/pages/Dashboard.test.jsx tests/unit/frontend/pages/AgentManagement.test.jsx tests/unit/frontend/pages/CallLogs.test.jsx
git commit -m "test: add Dashboard, AgentManagement, CallLogs page unit tests"
```

---

## Task 7: Add Frontend Tests — Remaining Pages (Billing, Signup, Leads, Scripts)

**Files:**
- Create: `tests/unit/frontend/pages/BillingPage.test.tsx`
- Create: `tests/unit/frontend/pages/SignupPage.test.tsx`
- Create: `tests/unit/frontend/pages/LeadsPage.test.tsx`
- Create: `tests/unit/frontend/pages/ScriptsPage.test.tsx`

- [ ] **Step 1: Write BillingPage tests**

Create `tests/unit/frontend/pages/BillingPage.test.tsx`:

```tsx
import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import BillingPage from '../../../agent-ui/src/pages/BillingPage'
import { AuthProvider } from '../../../agent-ui/src/context/AuthContext'

jest.mock('../../../agent-ui/src/services/api', () => ({
  default: { get: jest.fn(), post: jest.fn() },
  billingApi: { getSummary: jest.fn() }
}))

const { billingApi } = require('../../../agent-ui/src/services/api')

function renderBillingPage() {
  return render(
    <BrowserRouter>
      <AuthProvider>
        <BillingPage />
      </AuthProvider>
    </BrowserRouter>
  )
}

describe('BillingPage', () => {
  beforeEach(() => {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('tenantId', 'T-123')
    localStorage.setItem('userName', 'Test User')
    localStorage.setItem('userRole', 'admin')
    localStorage.setItem('userEmail', 'test@test.com')
    localStorage.setItem('userId', 'u-1')
    jest.clearAllMocks()
  })

  test('renders billing page', async () => {
    billingApi.getSummary.mockResolvedValue({ data: { total_cost: 150.00, calls_count: 500 } })
    renderBillingPage()
    await waitFor(() => {
      expect(screen.getByText(/billing/i)).toBeTruthy()
    })
  })

  test('displays billing summary', async () => {
    billingApi.getSummary.mockResolvedValue({ data: { total_cost: 299.99, calls_count: 1200 } })
    renderBillingPage()
    await waitFor(() => {
      expect(screen.getByText('299.99')).toBeTruthy()
    })
  })
})
```

- [ ] **Step 2: Write SignupPage tests**

Create `tests/unit/frontend/pages/SignupPage.test.tsx`:

```tsx
import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import SignupPage from '../../../agent-ui/src/pages/SignupPage'
import api from '../../../agent-ui/src/services/api'

jest.mock('../../../agent-ui/src/services/api')

function renderSignupPage() {
  return render(
    <BrowserRouter>
      <SignupPage />
    </BrowserRouter>
  )
}

describe('SignupPage', () => {
  beforeEach(() => {
    localStorage.clear()
    jest.clearAllMocks()
  })

  test('renders signup form fields', () => {
    renderSignupPage()
    expect(screen.getByPlaceholderText(/email/i)).toBeTruthy()
    expect(screen.getByPlaceholderText(/password/i)).toBeTruthy()
  })

  test('calls signup API on form submit', async () => {
    (api.post as jest.Mock).mockResolvedValue({ data: { message: 'Check your email' } })
    renderSignupPage()
    fireEvent.change(screen.getByPlaceholderText(/email/i), { target: { value: 'new@user.com' } })
    fireEvent.change(screen.getByPlaceholderText(/password/i), { target: { value: 'securepass' } })
    fireEvent.click(screen.getByRole('button', { name: /sign up/i }))
    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/auth/signup', expect.objectContaining({ email: 'new@user.com' }))
    })
  })
})
```

- [ ] **Step 3: Write LeadsPage tests**

Create `tests/unit/frontend/pages/LeadsPage.test.tsx`:

```tsx
import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import LeadsPage from '../../../agent-ui/src/pages/LeadsPage'
import { AuthProvider } from '../../../agent-ui/src/context/AuthContext'

jest.mock('../../../agent-ui/src/services/api', () => ({
  default: { get: jest.fn(), post: jest.fn() },
  leadApi: { list: jest.fn(), create: jest.fn() }
}))

const { leadApi } = require('../../../agent-ui/src/services/api')

function renderLeadsPage() {
  return render(
    <BrowserRouter>
      <AuthProvider>
        <LeadsPage />
      </AuthProvider>
    </BrowserRouter>
  )
}

describe('LeadsPage', () => {
  beforeEach(() => {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('tenantId', 'T-123')
    localStorage.setItem('userName', 'Test')
    localStorage.setItem('userRole', 'admin')
    localStorage.setItem('userEmail', 't@t.com')
    localStorage.setItem('userId', 'u-1')
    jest.clearAllMocks()
  })

  test('renders leads list', async () => {
    leadApi.list.mockResolvedValue({
      data: [{ id: 'L-1', name: 'John Doe', phone: '+1234567890' }]
    })
    renderLeadsPage()
    await waitFor(() => {
      expect(screen.getByText('John Doe')).toBeTruthy()
    })
  })

  test('shows empty state', async () => {
    leadApi.list.mockResolvedValue({ data: [] })
    renderLeadsPage()
    await waitFor(() => {
      expect(screen.getByText(/no leads/i)).toBeTruthy()
    })
  })
})
```

- [ ] **Step 4: Write ScriptsPage tests**

Create `tests/unit/frontend/pages/ScriptsPage.test.tsx`:

```tsx
import React from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import ScriptsPage from '../../../agent-ui/src/pages/ScriptsPage'
import { AuthProvider } from '../../../agent-ui/src/context/AuthContext'

jest.mock('../../../agent-ui/src/services/api', () => ({
  default: { get: jest.fn(), post: jest.fn() },
  scriptApi: { list: jest.fn(), create: jest.fn(), delete: jest.fn() }
}))

const { scriptApi } = require('../../../agent-ui/src/services/api')

function renderScriptsPage() {
  return render(
    <BrowserRouter>
      <AuthProvider>
        <ScriptsPage />
      </AuthProvider>
    </BrowserRouter>
  )
}

describe('ScriptsPage', () => {
  beforeEach(() => {
    localStorage.setItem('token', 'test-token')
    localStorage.setItem('tenantId', 'T-123')
    localStorage.setItem('userName', 'Test')
    localStorage.setItem('userRole', 'admin')
    localStorage.setItem('userEmail', 't@t.com')
    localStorage.setItem('userId', 'u-1')
    jest.clearAllMocks()
  })

  test('renders scripts list', async () => {
    scriptApi.list.mockResolvedValue({
      data: [{ id: 'S-1', name: 'Sales Script', content: 'Hello!' }]
    })
    renderScriptsPage()
    await waitFor(() => {
      expect(screen.getByText('Sales Script')).toBeTruthy()
    })
  })

  test('shows create button', async () => {
    scriptApi.list.mockResolvedValue({ data: [] })
    renderScriptsPage()
    await waitFor(() => {
      expect(screen.getByText(/create/i)).toBeTruthy()
    })
  })
})
```

- [ ] **Step 5: Run all tests**

Run: `cd agent-ui && npx jest tests/unit/frontend/pages/BillingPage.test.tsx tests/unit/frontend/pages/SignupPage.test.tsx tests/unit/frontend/pages/LeadsPage.test.tsx tests/unit/frontend/pages/ScriptsPage.test.tsx --no-coverage 2>&1 | tail -30`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add tests/unit/frontend/pages/BillingPage.test.tsx tests/unit/frontend/pages/SignupPage.test.tsx tests/unit/frontend/pages/LeadsPage.test.tsx tests/unit/frontend/pages/ScriptsPage.test.tsx
git commit -m "test: add Billing, Signup, Leads, Scripts page unit tests"
```

---

## Task 8: Add Frontend Tests — Components (Sidebar, StatCard)

**Files:**
- Create: `tests/unit/frontend/components/Sidebar.test.jsx`
- Create: `tests/unit/frontend/components/StatCard.test.jsx`

- [ ] **Step 1: Write Sidebar tests**

Create `tests/unit/frontend/components/Sidebar.test.jsx`:

```jsx
import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import Sidebar from '../../../agent-ui/src/components/Sidebar'

function renderSidebar(open = true, onClose = jest.fn()) {
  return render(
    <BrowserRouter>
      <Sidebar open={open} onClose={onClose} />
    </BrowserRouter>
  )
}

describe('Sidebar', () => {
  test('renders navigation links', () => {
    renderSidebar()
    expect(screen.getByText(/dashboard/i)).toBeTruthy()
    expect(screen.getByText(/agents/i)).toBeTruthy()
    expect(screen.getByText(/calls/i)).toBeTruthy()
    expect(screen.getByText(/settings/i)).toBeTruthy()
  })

  test('calls onClose when close button clicked', () => {
    const onClose = jest.fn()
    renderSidebar(true, onClose)
    const closeBtn = screen.getByRole('button', { name: /close/i })
    fireEvent.click(closeBtn)
    expect(onClose).toHaveBeenCalled()
  })

  test('renders AetherDesk branding', () => {
    renderSidebar()
    expect(screen.getByText(/aetherdesk/i)).toBeTruthy()
  })
})
```

- [ ] **Step 2: Write StatCard tests**

Create `tests/unit/frontend/components/StatCard.test.jsx`:

```jsx
import React from 'react'
import { render, screen } from '@testing-library/react'
import StatCard from '../../../agent-ui/src/components/StatCard'

describe('StatCard', () => {
  test('renders title and value', () => {
    render(<StatCard title="Total Calls" value={150} />)
    expect(screen.getByText('Total Calls')).toBeTruthy()
    expect(screen.getByText('150')).toBeTruthy()
  })

  test('renders with string value', () => {
    render(<StatCard title="Status" value="Active" />)
    expect(screen.getByText('Active')).toBeTruthy()
  })

  test('renders trend indicator when provided', () => {
    render(<StatCard title="Revenue" value="$1000" trend={12.5} />)
    expect(screen.getByText(/12.5%/)).toBeTruthy()
  })
})
```

- [ ] **Step 3: Run tests**

Run: `cd agent-ui && npx jest tests/unit/frontend/components/Sidebar.test.jsx tests/unit/frontend/components/StatCard.test.jsx --no-coverage 2>&1 | tail -20`

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/frontend/components/Sidebar.test.jsx tests/unit/frontend/components/StatCard.test.jsx
git commit -m "test: add Sidebar and StatCard component unit tests"
```

---

## Task 9: Extract Pydantic Models from main.py to dto.py

**Files:**
- Create: `apps/api/models/dto.py`
- Modify: `apps/api/main.py:452-586`

- [ ] **Step 1: Read main.py lines 452-586 to identify all Pydantic models**

Read the file to see all model definitions.

- [ ] **Step 2: Create dto.py with all models**

Create `apps/api/models/dto.py`:

```python
"""Pydantic models for API request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TenantCreate(BaseModel):
    name: str
    settings: dict[str, Any] = Field(default_factory=dict)


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class AgentCreate(BaseModel):
    name: str
    voice_id: str | None = None
    system_prompt: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    name: str
    status: str = "offline"
    voice_id: str | None = None
    system_prompt: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class AgentStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"available", "busy", "offline", "on_call"}
        if v not in allowed:
            raise ValueError(f"Status must be one of: {allowed}")
        return v


class CallCreate(BaseModel):
    tenant_id: str
    caller_number: str
    agent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CallAction(BaseModel):
    action: str

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        allowed = {"answer", "hangup", "hold", "transfer", "mute"}
        if v not in allowed:
            raise ValueError(f"Action must be one of: {allowed}")
        return v


class CallResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    caller_number: str
    agent_id: str | None = None
    status: str = "queued"
    duration: int = 0
    started_at: datetime | None = None
    ended_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UsageResponse(BaseModel):
    tenant_id: str
    total_calls: int = 0
    total_minutes: float = 0.0
    total_cost: float = 0.0
    period_start: datetime | None = None
    period_end: datetime | None = None


class HealthCheck(BaseModel):
    status: str = "healthy"
    version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    database: str = "unknown"
    redis: str = "unknown"


class WebhookConfig(BaseModel):
    url: str
    secret: str | None = None
    events: list[str] = Field(default_factory=list)
```

- [ ] **Step 3: Update main.py imports to use dto.py**

In `apps/api/main.py`, replace the Pydantic model definitions (lines ~452-586) with:

```python
from apps.api.models.dto import (
    AgentCreate,
    AgentResponse,
    AgentStatusUpdate,
    CallAction,
    CallCreate,
    CallResponse,
    HealthCheck,
    TenantCreate,
    TenantResponse,
    UsageResponse,
    WebhookConfig,
)
```

- [ ] **Step 4: Verify Python tests still pass**

Run: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -10`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/models/dto.py apps/api/main.py
git commit -m "refactor: extract Pydantic models from main.py to models/dto.py"
```

---

## Task 10: Extract Health Routes from main.py

**Files:**
- Create: `apps/api/routers/health.py`
- Modify: `apps/api/main.py`

- [ ] **Step 1: Create health router**

Create `apps/api/routers/health.py`:

```python
"""Health check routes."""

from __future__ import annotations

import time

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from apps.api.models.dto import HealthCheck

router = APIRouter(tags=["health"])

_start_time = time.time()


@router.get("/api/v1/health", response_model=HealthCheck)
async def health_check() -> HealthCheck:
    return HealthCheck(status="healthy", version="1.0.0")


@router.get("/health", response_model=HealthCheck)
async def health_check_alt() -> HealthCheck:
    return HealthCheck(status="healthy", version="1.0.0")


@router.get("/api/v1/health/ready")
async def readiness() -> dict[str, str]:
    return {"status": "ready"}


@router.get("/api/v1/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/metrics")
async def metrics() -> PlainTextResponse:
    uptime = time.time() - _start_time
    content = f"""# HELP aetherdesk_uptime_seconds Uptime in seconds
# TYPE aetherdesk_uptime_seconds gauge
aetherdesk_uptime_seconds {uptime}
"""
    return PlainTextResponse(content=content, media_type="text/plain")
```

- [ ] **Step 2: Include health router in main.py**

In `apps/api/main.py`, add after the existing router includes:

```python
from apps.api.routers import health
app.include_router(health.router)
```

- [ ] **Step 3: Remove inline health routes from main.py**

Delete the health check route handlers from main.py (the functions at lines ~614-651 and ~1371-1387).

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -10`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/routers/health.py apps/api/main.py
git commit -m "refactor: extract health check routes from main.py to routers/health.py"
```

---

## Task 11: Extract Tenant Routes from main.py

**Files:**
- Create: `apps/api/routers/tenants.py`
- Modify: `apps/api/main.py`

- [ ] **Step 1: Read main.py tenant routes (lines ~657-723)**

Read the file to see the exact tenant route implementations.

- [ ] **Step 2: Create tenants router**

Create `apps/api/routers/tenants.py` with the extracted route handlers. The router should include:
- `POST /api/v1/tenants` — create tenant
- `GET /api/v1/tenants/{tenant_id}` — get tenant

Move the database calls and logic from main.py into this router.

- [ ] **Step 3: Include tenants router in main.py**

```python
from apps.api.routers import tenants
app.include_router(tenants.router)
```

- [ ] **Step 4: Remove inline tenant routes from main.py**

Delete the tenant route handlers from main.py.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -10`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/routers/tenants.py apps/api/main.py
git commit -m "refactor: extract tenant routes from main.py to routers/tenants.py"
```

---

## Task 12: Extract Agent Management Routes from main.py

**Files:**
- Create: `apps/api/routers/agent_management.py`
- Modify: `apps/api/main.py`

- [ ] **Step 1: Read main.py agent routes (lines ~749-938)**

Read the file to see the exact agent route implementations.

- [ ] **Step 2: Create agent_management router**

Create `apps/api/routers/agent_management.py` with the extracted route handlers. Move all agent CRUD and status update routes from main.py.

- [ ] **Step 3: Include agent_management router in main.py**

```python
from apps.api.routers import agent_management
app.include_router(agent_management.router)
```

- [ ] **Step 4: Remove inline agent routes from main.py**

Delete the agent route handlers from main.py.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -10`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/routers/agent_management.py apps/api/main.py
git commit -m "refactor: extract agent management routes from main.py"
```

---

## Task 13: Extract Call Management Routes from main.py

**Files:**
- Create: `apps/api/routers/call_management.py`
- Modify: `apps/api/main.py`

- [ ] **Step 1: Read main.py call routes (lines ~944-1131)**

Read the file to see the exact call route implementations.

- [ ] **Step 2: Create call_management router**

Create `apps/api/routers/call_management.py` with all call CRUD and action routes.

- [ ] **Step 3: Include call_management router in main.py**

```python
from apps.api.routers import call_management
app.include_router(call_management.router)
```

- [ ] **Step 4: Remove inline call routes from main.py**

Delete the call route handlers from main.py.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -10`

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/routers/call_management.py apps/api/main.py
git commit -m "refactor: extract call management routes from main.py"
```

---

## Task 14: Extract Remaining Routes from main.py (Fonster, Usage, Billing, WebSocket)

**Files:**
- Create: `apps/api/routers/webhooks_fonster.py`
- Create: `apps/api/routers/usage.py`
- Modify: `apps/api/main.py`

- [ ] **Step 1: Create webhooks_fonster router**

Create `apps/api/routers/webhooks_fonster.py` with the Fonster webhook handler (lines ~1137-1195).

- [ ] **Step 2: Create usage router**

Create `apps/api/routers/usage.py` with usage analytics and billing routes (lines ~1200-1281).

- [ ] **Step 3: Include new routers in main.py**

```python
from apps.api.routers import webhooks_fonster, usage
app.include_router(webhooks_fonster.router)
app.include_router(usage.router)
```

- [ ] **Step 4: Remove inline routes from main.py**

Delete all remaining inline route handlers from main.py. After this step, main.py should only contain:
- App setup (FastAPI app creation)
- Middleware configuration (CORS, security headers, rate limiter, audit)
- Lifespan handler
- Router includes
- get_voice_client helper

- [ ] **Step 5: Verify main.py is under 300 lines**

Run: `python -c "print(len(open('apps/api/main.py').readlines()))"`

Expected: Under 300 lines.

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -10`

Expected: All tests pass.

- [ ] **Step 7: Commit**

```bash
git add apps/api/routers/webhooks_fonster.py apps/api/routers/usage.py apps/api/main.py
git commit -m "refactor: extract all remaining routes from main.py, main.py now only has app setup"
```

---

## Task 15: Fix Code Quality Issues

**Files:**
- Modify: `apps/api/main.py` (logger before definition)
- Modify: `apps/api/services/db_config.py` (print to logger)

- [ ] **Step 1: Fix logger before definition in main.py**

In `apps/api/main.py`, move the `logger = logging.getLogger(__name__)` line to BEFORE the first use of `logger` (should be near the top, after imports).

- [ ] **Step 2: Fix print in db_config.py**

In `apps/api/services/db_config.py:11`, replace:
```python
print("DATABASE_URL not set. Running with SQLite fallback.")
```
with:
```python
logging.warning("DATABASE_URL not set. Running with SQLite fallback.")
```

Add `import logging` at the top of the file if not already present.

- [ ] **Step 3: Fix duplicate script_templates in db_schema.py**

In `apps/api/services/db_schema.py`, remove the duplicate `script_templates` CREATE TABLE (the second occurrence around lines 674-680).

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/ -x -q --tb=short 2>&1 | tail -10`

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/main.py apps/api/services/db_config.py apps/api/services/db_schema.py
git commit -m "fix: logger before definition, print to logging, duplicate schema"
```

---

## Task 16: Update .gitignore and Clean Repo

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Read current .gitignore**

Read the file to see what's already covered.

- [ ] **Step 2: Add missing entries to .gitignore**

Append to `.gitignore`:

```
# Environment and secrets
.env
.env.*
!.env.example

# Database files
*.db
*.sqlite
*.sqlite3

# Coverage and build artifacts
coverage/
htmlcov/
agent-ui/dist/
agent-ui/coverage/

# Logs
*.log
logs/

# Debug artifacts
debug_screenshot.png
bandit_results.json
security_validation_results.json

# Python
__pycache__/
*.pyc
*.pyo
.pytest_cache/
```

- [ ] **Step 3: Remove tracked files that should be ignored**

```bash
git rm --cached .env aetherdesk.db 2>/dev/null || true
git rm --cached bandit_results.json security_validation_results.json 2>/dev/null || true
git rm --cached debug_screenshot.png 2>/dev/null || true
```

- [ ] **Step 4: Commit**

```bash
git add .gitignore
git commit -m "chore: update .gitignore, remove tracked secrets and build artifacts"
```

---

## Task 17: Add CI/CD Frontend Checks

**Files:**
- Modify: `.github/workflows/ci-cd.yml`

- [ ] **Step 1: Read current ci-cd.yml**

Read the file to understand the existing pipeline structure.

- [ ] **Step 2: Add frontend lint job**

Add a new job after the `lint` job:

```yaml
  frontend-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: agent-ui/package-lock.json
      - name: Install dependencies
        working-directory: agent-ui
        run: npm ci
      - name: TypeScript type check
        working-directory: agent-ui
        run: npx tsc --noEmit 2>&1 || true
      - name: Build check
        working-directory: agent-ui
        run: npm run build
```

- [ ] **Step 3: Add frontend test job**

Add after `frontend-lint`:

```yaml
  frontend-test:
    runs-on: ubuntu-latest
    needs: [frontend-lint]
    steps:
      - uses: actions/checkout@v4
      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: agent-ui/package-lock.json
      - name: Install dependencies
        working-directory: agent-ui
        run: npm ci
      - name: Run frontend tests
        working-directory: agent-ui
        run: npx jest --coverage --ci 2>&1
```

- [ ] **Step 4: Update test job dependencies**

Update the `test` job `needs` to include `frontend-lint` and `frontend-test`:

```yaml
  test:
    runs-on: ubuntu-latest
    needs: [lint, security-scan, frontend-lint, frontend-test]
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci-cd.yml
git commit -m "ci: add frontend lint, type check, build, and test jobs"
```

---

## Task 18: Final Verification — Run Full Test Suite

**Files:** None (verification only)

- [ ] **Step 1: Run all Python tests**

Run: `python -m pytest tests/unit/ -v --tb=short 2>&1 | tail -30`

Expected: All Python tests pass.

- [ ] **Step 2: Run all frontend tests**

Run: `cd agent-ui && npx jest --coverage 2>&1 | tail -30`

Expected: All frontend tests pass with coverage report.

- [ ] **Step 3: Verify main.py is clean**

Run: `python -c "lines = open('apps/api/main.py').readlines(); print(f'main.py: {len(lines)} lines')"`
Run: `grep -c "^@.*router\.\|def " apps/api/main.py`

Expected: main.py under 300 lines, minimal route definitions.

- [ ] **Step 4: Verify no dead code imports**

Run: `grep -r "from.*App\.tsx\|from.*main\.tsx\|from.*lib/api\|from.*Dashboard\.tsx" agent-ui/src/ --include="*.jsx" --include="*.tsx" --include="*.js" --include="*.ts" 2>&1`

Expected: No matches.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: final verification — all tests passing, production ready"
```
