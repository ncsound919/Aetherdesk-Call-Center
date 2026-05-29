import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:3000'

const api = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  timeout: 30000,
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
export const authAPI = {
  login: (data) => api.post('/auth/login', data),
  logout: () => api.post('/auth/logout'),
}

// Tenants
export const tenantAPI = {
  create: (data) => api.post('/tenants', data),
  get: (id) => api.get(`/tenants/${id}`),
  list: () => api.get('/tenants'),
}

// Agents
export const agentAPI = {
  list: (tenantId) => api.get(`/tenants/${tenantId}/agents`),
  create: (tenantId, data) => api.post(`/tenants/${tenantId}/agents`, data),
  get: (tenantId, agentId) => api.get(`/tenants/${tenantId}/agents/${agentId}`),
  updateStatus: (agentId, status) => api.patch(`/agents/${agentId}/status`, status),
}

// Calls
export const callAPI = {
  create: (data) => api.post('/calls', data),
  get: (callId) => api.get(`/calls/${callId}`),
  list: (tenantId, params) => api.get(`/calls?tenant_id=${tenantId}&${new URLSearchParams(params)}`),
  action: (callId, action) => api.post(`/calls/${callId}/action`, action),
}

// Recordings
export const recordingAPI = {
  get: (recordingId) => api.get(`/recordings/${recordingId}`),
}

// Usage
export const usageAPI = {
  get: (tenantId, period) => api.get('/usage', { params: { tenant_id: tenantId, ...period } }),
}

// Health
export const healthAPI = {
  check: () => api.get('/health'),
}

export default api