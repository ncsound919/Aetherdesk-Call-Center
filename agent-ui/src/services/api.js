import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1',
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

export const authApi = {
  login: (data) => api.post('/auth/login', data),
  signup: (data) => api.post('/auth/signup', data),
  forgotPassword: (email) => api.post('/auth/forgot-password', { email }),
  resetPassword: (token, password) => api.post('/auth/reset-password', { token, password }),
  verifyEmail: (token) => api.post('/auth/verify-email', { token }),
}

export const agentApi = {
  list: (tenantId) => api.get(`/tenants/${tenantId}/agents`),
  create: (tenantId, data) => api.post(`/tenants/${tenantId}/agents`, data),
  update: (tenantId, agentId, data) => api.put(`/tenants/${tenantId}/agents/${agentId}`, data),
  delete: (tenantId, agentId) => api.delete(`/tenants/${tenantId}/agents/${agentId}`),
  updateStatus: (agentId, status) => api.patch(`/agents/${agentId}/status`, { status }),
}

export const callApi = {
  list: (tenantId, params) => api.get('/calls', { params: { tenant_id: tenantId, ...params } }),
  get: (callId) => api.get(`/calls/${callId}`),
  create: (data) => api.post('/calls', data),
  action: (callId, action) => api.post(`/calls/${callId}/action`, { action }),
}

export const billingApi = {
  getSummary: (tenantId) => api.get('/billing', { params: { tenant_id: tenantId } }),
}

export const leadApi = {
  list: (tenantId, params) => api.get('/leads', { params: { tenant_id: tenantId, ...params } }),
  create: (tenantId, data) => api.post('/leads', { tenant_id: tenantId, ...data }),
  import: (tenantId, file) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('tenant_id', tenantId)
    return api.post('/leads/import', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
}

export const scriptApi = {
  list: (tenantId) => api.get('/scripts', { params: { tenant_id: tenantId } }),
  get: (scriptId) => api.get(`/scripts/${scriptId}`),
  create: (tenantId, data) => api.post('/scripts', { tenant_id: tenantId, ...data }),
  update: (scriptId, data) => api.put(`/scripts/${scriptId}`, data),
  delete: (scriptId) => api.delete(`/scripts/${scriptId}`),
}

export const settingsApi = {
  getTenant: (tenantId) => api.get(`/tenants/${tenantId}`),
  updateTenant: (tenantId, data) => api.put(`/tenants/${tenantId}`, data),
}

export default api
