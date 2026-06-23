import api, { authApi, agentApi, callApi, billingApi, leadApi, scriptApi, settingsApi } from '../../../../agent-ui/src/services/api'

// Mock the api module to avoid import.meta.env issues
jest.mock('../../../../agent-ui/src/services/api', () => {
  const mockAxiosInstance = {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
    delete: jest.fn(),
    patch: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() }
    }
  }
  return {
    __esModule: true,
    default: mockAxiosInstance,
    authApi: {
      login: (data) => mockAxiosInstance.post('/auth/login', data),
      signup: (data) => mockAxiosInstance.post('/auth/signup', data),
      forgotPassword: (email) => mockAxiosInstance.post('/auth/forgot-password', { email }),
      resetPassword: (token, password) => mockAxiosInstance.post('/auth/reset-password', { token, password }),
      verifyEmail: (token) => mockAxiosInstance.post('/auth/verify-email', { token }),
    },
    agentApi: {
      list: (tenantId) => mockAxiosInstance.get(`/tenants/${tenantId}/agents`),
      create: (tenantId, data) => mockAxiosInstance.post(`/tenants/${tenantId}/agents`, data),
      update: (tenantId, agentId, data) => mockAxiosInstance.put(`/tenants/${tenantId}/agents/${agentId}`, data),
      delete: (tenantId, agentId) => mockAxiosInstance.delete(`/tenants/${tenantId}/agents/${agentId}`),
      updateStatus: (agentId, status) => mockAxiosInstance.patch(`/agents/${agentId}/status`, { status }),
    },
    callApi: {
      list: (tenantId, params) => mockAxiosInstance.get('/calls', { params: { tenant_id: tenantId, ...params } }),
      get: (callId) => mockAxiosInstance.get(`/calls/${callId}`),
      create: (data) => mockAxiosInstance.post('/calls', data),
      action: (callId, action) => mockAxiosInstance.post(`/calls/${callId}/action`, { action }),
    },
    billingApi: {
      getSummary: (tenantId) => mockAxiosInstance.get('/billing', { params: { tenant_id: tenantId } }),
    },
    leadApi: {
      list: (tenantId, params) => mockAxiosInstance.get('/leads', { params: { tenant_id: tenantId, ...params } }),
      create: (tenantId, data) => mockAxiosInstance.post('/leads', { tenant_id: tenantId, ...data }),
      import: (tenantId, file) => {
        const formData = new FormData()
        formData.append('file', file)
        formData.append('tenant_id', tenantId)
        return mockAxiosInstance.post('/leads/import', formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      },
    },
    scriptApi: {
      list: (tenantId) => mockAxiosInstance.get('/scripts', { params: { tenant_id: tenantId } }),
      get: (scriptId) => mockAxiosInstance.get(`/scripts/${scriptId}`),
      create: (tenantId, data) => mockAxiosInstance.post('/scripts', { tenant_id: tenantId, ...data }),
      update: (scriptId, data) => mockAxiosInstance.put(`/scripts/${scriptId}`, data),
      delete: (scriptId) => mockAxiosInstance.delete(`/scripts/${scriptId}`),
    },
    settingsApi: {
      getTenant: (tenantId) => mockAxiosInstance.get(`/tenants/${tenantId}`),
      updateTenant: (tenantId, data) => mockAxiosInstance.put(`/tenants/${tenantId}`, data),
    },
  }
})

describe('API Client', () => {
  beforeEach(() => {
    localStorage.clear()
    jest.clearAllMocks()
  })

  describe('authApi', () => {
    test('login calls correct endpoint', async () => {
      await authApi.login({ email: 'a@b.com', password: 'pass' })
      expect(api.post).toHaveBeenCalledWith('/auth/login', { email: 'a@b.com', password: 'pass' })
    })

    test('signup calls correct endpoint', async () => {
      await authApi.signup({ email: 'a@b.com', password: 'pass' })
      expect(api.post).toHaveBeenCalledWith('/auth/signup', { email: 'a@b.com', password: 'pass' })
    })

    test('forgotPassword calls correct endpoint', async () => {
      await authApi.forgotPassword('a@b.com')
      expect(api.post).toHaveBeenCalledWith('/auth/forgot-password', { email: 'a@b.com' })
    })

    test('resetPassword calls correct endpoint', async () => {
      await authApi.resetPassword('tok', 'newpass')
      expect(api.post).toHaveBeenCalledWith('/auth/reset-password', { token: 'tok', password: 'newpass' })
    })

    test('verifyEmail calls correct endpoint', async () => {
      await authApi.verifyEmail('tok')
      expect(api.post).toHaveBeenCalledWith('/auth/verify-email', { token: 'tok' })
    })
  })

  describe('agentApi', () => {
    test('list calls correct endpoint', async () => {
      await agentApi.list('T-1')
      expect(api.get).toHaveBeenCalledWith('/tenants/T-1/agents')
    })

    test('create calls correct endpoint', async () => {
      await agentApi.create('T-1', { name: 'Agent 1' })
      expect(api.post).toHaveBeenCalledWith('/tenants/T-1/agents', { name: 'Agent 1' })
    })

    test('update calls correct endpoint', async () => {
      await agentApi.update('T-1', 'A-1', { name: 'Updated' })
      expect(api.put).toHaveBeenCalledWith('/tenants/T-1/agents/A-1', { name: 'Updated' })
    })

    test('delete calls correct endpoint', async () => {
      await agentApi.delete('T-1', 'A-1')
      expect(api.delete).toHaveBeenCalledWith('/tenants/T-1/agents/A-1')
    })

    test('updateStatus calls correct endpoint', async () => {
      await agentApi.updateStatus('A-1', 'busy')
      expect(api.patch).toHaveBeenCalledWith('/agents/A-1/status', { status: 'busy' })
    })
  })

  describe('callApi', () => {
    test('list calls correct endpoint with params', async () => {
      await callApi.list('T-1', { status: 'completed' })
      expect(api.get).toHaveBeenCalledWith('/calls', { params: { tenant_id: 'T-1', status: 'completed' } })
    })

    test('get calls correct endpoint', async () => {
      await callApi.get('C-1')
      expect(api.get).toHaveBeenCalledWith('/calls/C-1')
    })

    test('create calls correct endpoint', async () => {
      await callApi.create({ tenant_id: 'T-1', caller_number: '+123' })
      expect(api.post).toHaveBeenCalledWith('/calls', { tenant_id: 'T-1', caller_number: '+123' })
    })

    test('action calls correct endpoint', async () => {
      await callApi.action('C-1', 'hangup')
      expect(api.post).toHaveBeenCalledWith('/calls/C-1/action', { action: 'hangup' })
    })
  })

  describe('billingApi', () => {
    test('getSummary calls correct endpoint', async () => {
      await billingApi.getSummary('T-1')
      expect(api.get).toHaveBeenCalledWith('/billing', { params: { tenant_id: 'T-1' } })
    })
  })

  describe('leadApi', () => {
    test('list calls correct endpoint', async () => {
      await leadApi.list('T-1')
      expect(api.get).toHaveBeenCalledWith('/leads', { params: { tenant_id: 'T-1' } })
    })

    test('create calls correct endpoint', async () => {
      await leadApi.create('T-1', { name: 'John' })
      expect(api.post).toHaveBeenCalledWith('/leads', { tenant_id: 'T-1', name: 'John' })
    })

    test('import sends FormData', async () => {
      const file = new File(['test'], 'test.csv', { type: 'text/csv' })
      await leadApi.import('T-1', file)
      expect(api.post).toHaveBeenCalledWith('/leads/import', expect.any(FormData), {
        headers: { 'Content-Type': 'multipart/form-data' }
      })
    })
  })

  describe('scriptApi', () => {
    test('list calls correct endpoint', async () => {
      await scriptApi.list('T-1')
      expect(api.get).toHaveBeenCalledWith('/scripts', { params: { tenant_id: 'T-1' } })
    })

    test('get calls correct endpoint', async () => {
      await scriptApi.get('S-1')
      expect(api.get).toHaveBeenCalledWith('/scripts/S-1')
    })

    test('create calls correct endpoint', async () => {
      await scriptApi.create('T-1', { name: 'Script 1' })
      expect(api.post).toHaveBeenCalledWith('/scripts', { tenant_id: 'T-1', name: 'Script 1' })
    })

    test('update calls correct endpoint', async () => {
      await scriptApi.update('S-1', { name: 'Updated' })
      expect(api.put).toHaveBeenCalledWith('/scripts/S-1', { name: 'Updated' })
    })

    test('delete calls correct endpoint', async () => {
      await scriptApi.delete('S-1')
      expect(api.delete).toHaveBeenCalledWith('/scripts/S-1')
    })
  })

  describe('settingsApi', () => {
    test('getTenant calls correct endpoint', async () => {
      await settingsApi.getTenant('T-1')
      expect(api.get).toHaveBeenCalledWith('/tenants/T-1')
    })

    test('updateTenant calls correct endpoint', async () => {
      await settingsApi.updateTenant('T-1', { name: 'New Name' })
      expect(api.put).toHaveBeenCalledWith('/tenants/T-1', { name: 'New Name' })
    })
  })
})
