const mockApi = {
  post: jest.fn(),
  get: jest.fn(),
  put: jest.fn(),
  delete: jest.fn(),
  patch: jest.fn(),
  interceptors: {
    request: { use: jest.fn() },
    response: { use: jest.fn() }
  }
}

export const authApi = {
  login: jest.fn(),
  signup: jest.fn(),
  forgotPassword: jest.fn(),
  resetPassword: jest.fn(),
  verifyEmail: jest.fn(),
}

export const agentApi = {
  list: jest.fn(),
  create: jest.fn(),
  update: jest.fn(),
  delete: jest.fn(),
  updateStatus: jest.fn(),
}

export const callApi = {
  list: jest.fn(),
  get: jest.fn(),
  create: jest.fn(),
  action: jest.fn(),
}

export const billingApi = {
  getSummary: jest.fn(),
}

export const leadApi = {
  list: jest.fn(),
  create: jest.fn(),
  import: jest.fn(),
}

export const scriptApi = {
  list: jest.fn(),
  get: jest.fn(),
  create: jest.fn(),
  update: jest.fn(),
  delete: jest.fn(),
}

export const settingsApi = {
  getTenant: jest.fn(),
  updateTenant: jest.fn(),
}

export default mockApi
