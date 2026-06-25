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
      const onLoginPage = window.location.pathname === '/login'
      localStorage.removeItem('token')
      localStorage.removeItem('tenantId')
      if (!onLoginPage) {
        window.location.href = '/login'
      }
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

export const wfmApi = {
  listShifts: (tenantId, params) => api.get('/wfm/shifts', { params: { tenant_id: tenantId, ...params } }),
  createShift: (data) => api.post('/wfm/shifts', data),
  updateShift: (shiftId, data) => api.put(`/wfm/shifts/${shiftId}`, data),
  deleteShift: (shiftId) => api.delete(`/wfm/shifts/${shiftId}`),
  getSchedule: (tenantId, params) => api.get('/wfm/schedules', { params: { tenant_id: tenantId, ...params } }),
  getForecast: (tenantId, data) => api.post('/wfm/schedules/forecast', { tenant_id: tenantId, ...data }),
  getAdherence: (tenantId, params) => api.get('/wfm/adherence', { params: { tenant_id: tenantId, ...params } }),
}

export const qaApi = {
  listScores: (tenantId, params) => api.get('/wfm/qa/scores', { params: { tenant_id: tenantId, ...params } }),
  createScore: (data) => api.post('/wfm/qa/scores', data),
  listRubrics: (tenantId) => api.get('/wfm/qa/rubrics', { params: { tenant_id: tenantId } }),
  createRubric: (data) => api.post('/wfm/qa/rubrics', data),
  getAgentSummary: (agentId) => api.get(`/wfm/qa/agent-summary/${agentId}`),
}

export const mfaApi = {
  setup: () => api.post('/auth/mfa/setup'),
  verify: (code) => api.post('/auth/mfa/verify', { code }),
  disable: () => api.post('/auth/mfa/disable'),
  login: (sessionToken, code) => api.post('/auth/mfa/login', { session_token: sessionToken, code }),
  backupCode: (code) => api.post('/auth/mfa/backup-code', { code }),
  status: () => api.get('/auth/mfa/status'),
}

export const voiceQualityApi = {
  recordMetric: (data) => api.post('/voice-quality/metrics', data),
  listMetrics: (params) => api.get('/voice-quality/metrics', { params }),
  getSummary: (params) => api.get('/voice-quality/summary', { params }),
  getTrends: (params) => api.get('/voice-quality/trends', { params }),
  getCallQuality: (callId) => api.get(`/voice-quality/calls/${callId}`),
}

export const aiOpsApi = {
  evaluate: (data) => api.post('/ai-ops/evaluate', data),
  getAccuracy: (params) => api.get('/ai-ops/accuracy', { params }),
  createExperiment: (data) => api.post('/ai-ops/experiments', data),
  listExperiments: (params) => api.get('/ai-ops/experiments', { params }),
  getExperiment: (id) => api.get(`/ai-ops/experiments/${id}`),
  stopExperiment: (id) => api.post(`/ai-ops/experiments/${id}/stop`),
  getConfidenceDistribution: (params) => api.get('/ai-ops/confidence/distribution', { params }),
  setConfidenceThresholds: (data) => api.post('/ai-ops/confidence/thresholds', data),
  getConfidenceThresholds: () => api.get('/ai-ops/confidence/thresholds'),
}

export const integrationsApi = {
  createCRMContact: (data) => api.post('/integrations/crm/contacts', data),
  searchCRMContacts: (params) => api.get('/integrations/crm/contacts', { params }),
  getCRMContact: (id) => api.get(`/integrations/crm/contacts/${id}`),
  updateCRMContact: (id, data) => api.put(`/integrations/crm/contacts/${id}`, data),
  syncCRMContacts: () => api.post('/integrations/crm/sync'),
  getCRMHealth: () => api.get('/integrations/crm/health'),
  createTicket: (data) => api.post('/integrations/ticketing/tickets', data),
  listTickets: (params) => api.get('/integrations/ticketing/tickets', { params }),
  getTicket: (id) => api.get(`/integrations/ticketing/tickets/${id}`),
  updateTicket: (id, data) => api.put(`/integrations/ticketing/tickets/${id}`, data),
  syncFromCall: (data) => api.post('/integrations/ticketing/sync-from-call', data),
  getTicketingHealth: () => api.get('/integrations/ticketing/health'),
  getConfigs: () => api.get('/integrations/configs'),
  createConfig: (data) => api.post('/integrations/configs', data),
  getHealth: () => api.get('/integrations/health'),
}

export const cxApi = {
  createSurvey: (data) => api.post('/cx/csat/surveys', data),
  listSurveys: (params) => api.get('/cx/csat/surveys', { params }),
  getCSATScore: (params) => api.get('/cx/csat/score', { params }),
  getNPS: (params) => api.get('/cx/csat/nps', { params }),
  getResponseRate: (params) => api.get('/cx/csat/response-rate', { params }),
  getSentimentTrends: (params) => api.get('/cx/sentiment/trends', { params }),
  getCustomer360: (customerId, params) => api.get(`/cx/customers/${customerId}/360`, { params }),
  getSummary: (params) => api.get('/cx/summary', { params }),
}

export const omnichannelApi = {
  sendSMS: (data) => api.post('/omnichannel/sms/send', data),
  sendBulkSMS: (data) => api.post('/omnichannel/sms/bulk', data),
  createSMSTemplate: (data) => api.post('/omnichannel/sms/templates', data),
  listSMSTemplates: () => api.get('/omnichannel/sms/templates'),
  getSMSLog: (params) => api.get('/omnichannel/sms/log', { params }),
  createChatSession: (data) => api.post('/omnichannel/chat/sessions', data),
  sendChatMessage: (sessionId, data) => api.post(`/omnichannel/chat/sessions/${sessionId}/messages`, data),
  getChatMessages: (sessionId) => api.get(`/omnichannel/chat/sessions/${sessionId}/messages`),
  assignChat: (sessionId, data) => api.post(`/omnichannel/chat/sessions/${sessionId}/assign`, data),
  closeChat: (sessionId) => api.post(`/omnichannel/chat/sessions/${sessionId}/close`),
  getWaitingChats: () => api.get('/omnichannel/chat/waiting'),
}

export const aiAssistApi = {
  validate: (data) => api.post('/ai-assist/validate', data),
  validateIntent: (data) => api.post('/ai-assist/validate/intent', data),
  fixOutput: (data) => api.post('/ai-assist/validate/fix', data),
  getSchemas: () => api.get('/ai-assist/schemas'),
  getSchema: (name) => api.get(`/ai-assist/schemas/${name}`),
  getSuggestions: (data) => api.post('/ai-assist/suggestions', data),
  searchKnowledge: (params) => api.get('/ai-assist/knowledge', { params }),
  createKnowledge: (data) => api.post('/ai-assist/knowledge', data),
  deleteKnowledge: (id) => api.delete(`/ai-assist/knowledge/${id}`),
  getNextBestAction: (params) => api.get('/ai-assist/nba', { params }),
  getRealtimeStats: (callId) => api.get(`/ai-assist/realtime/${callId}`),
}

export const wfmMetricsApi = {
  trackAHT: (data) => api.post('/wfm-final/metrics/aht', data),
  trackFCR: (data) => api.post('/wfm-final/metrics/fcr', data),
  trackCSAT: (data) => api.post('/wfm-final/metrics/csat', data),
  trackNPS: (data) => api.post('/wfm-final/metrics/nps', data),
  getSummary: (tenantId, params) => api.get('/wfm-final/metrics/summary', { params: { tenant_id: tenantId, ...params } }),
}

export const supervisorApi = {
  getWallboard: (tenantId) => api.get('/wfm-final/wallboard', { params: { tenant_id: tenantId } }),
  getAgents: (tenantId) => api.get('/wfm-final/wallboard/agents', { params: { tenant_id: tenantId } }),
  getTeam: (tenantId, params) => api.get('/wfm-final/wallboard/team', { params: { tenant_id: tenantId, ...params } }),
  getAlerts: (tenantId) => api.get('/wfm-final/wallboard/alerts', { params: { tenant_id: tenantId } }),
}

export const trainingApi = {
  listCourses: (tenantId) => api.get('/wfm-final/training/courses', { params: { tenant_id: tenantId } }),
  createCourse: (data) => api.post('/wfm-final/training/courses', data),
  enrollAgent: (data) => api.post('/wfm-final/training/enroll', data),
  trackProgress: (data) => api.post('/wfm-final/training/progress', data),
  getCertifications: (agentId, tenantId) => api.get(`/wfm-final/training/certifications/${agentId}`, { params: { tenant_id: tenantId } }),
  createCoaching: (data) => api.post('/wfm-final/training/coaching', data),
  listCoaching: (tenantId, params) => api.get('/wfm-final/training/coaching', { params: { tenant_id: tenantId, ...params } }),
}

export const bcApi = {
  runFailoverTest: (data) => api.post('/business-continuity/failover/test', data),
  listFailoverTests: (tenantId) => api.get('/business-continuity/failover/tests', { params: { tenant_id: tenantId } }),
  getMultiRegionStatus: (tenantId) => api.get('/business-continuity/failover/multi-region', { params: { tenant_id: tenantId } }),
  runChaos: (data) => api.post('/business-continuity/chaos/run', data),
  listChaosExperiments: (tenantId) => api.get('/business-continuity/chaos/experiments', { params: { tenant_id: tenantId } }),
  createContract: (data) => api.post('/business-continuity/contracts', data),
  listContracts: (tenantId) => api.get('/business-continuity/contracts', { params: { tenant_id: tenantId } }),
  getContractAlerts: (tenantId, params) => api.get('/business-continuity/contracts/alerts', { params: { tenant_id: tenantId, ...params } }),
  configureBackupChannel: (data) => api.post('/business-continuity/backup-channels', data),
  testBackupChannel: (channelType) => api.post('/business-continuity/backup-channels/test', null, { params: { channel_type: channelType } }),
  listBackupChannels: (tenantId) => api.get('/business-continuity/backup-channels', { params: { tenant_id: tenantId } }),
}

export const dataGovernanceApi = {
  getRecordLineage: (params) => api.get('/data-governance/lineage/record', { params }),
  getLineageGraph: (params) => api.get('/data-governance/lineage/graph', { params }),
  getColumnLineage: (params) => api.get('/data-governance/lineage/column', { params }),
  getHealthScore: () => api.get('/data-governance/health-score'),
  recordLineage: (data) => api.post('/data-governance/lineage', data),
}

export const failoverApi = {
  runTest: (params) => api.post('/enterprise/failover/test', null, { params }),
  getStatus: (params) => api.get('/enterprise/failover/status', { params }),
  getHistory: (params) => api.get('/enterprise/failover/history', { params }),
  getConfig: (params) => api.get('/enterprise/failover/config', { params }),
}

export const qualityApi = {
  scoreConversation: (data) => api.post('/enterprise/conversation-quality/score', null, { params: { transcript: data.transcript, rubric_name: data.rubric_name, tenant_id: data.tenant_id } }),
  getScores: (params) => api.get('/enterprise/conversation-quality/scores', { params }),
  getTrends: (params) => api.get('/enterprise/conversation-quality/trends', { params }),
  getCoaching: (agentId, params) => api.get('/enterprise/conversation-quality/coaching', { params: { agent_id: agentId, ...params } }),
}

export const versionsApi = {
  list: (params) => api.get('/enterprise/api-versions', { params }),
  deprecate: (version, params) => api.post(`/enterprise/api-versions/${version}/deprecate`, null, { params }),
  getMigrationGuide: (params) => api.get('/enterprise/api-versions/migration-guide', { params }),
  getChangelog: (params) => api.get('/enterprise/api-versions/changelog', { params }),
  getUsageStats: (params) => api.get('/enterprise/api-versions/usage-stats', { params }),
}

export const portalApi = {
  getPortalData: (customerId, params) => api.get(`/enterprise/customer-portal/${customerId}`, { params }),
  submitComplaint: (data) => api.post('/enterprise/customer-portal/complaint', null, { params: data }),
  scheduleCallback: (data) => api.post('/enterprise/customer-portal/callback', null, { params: data }),
  updatePreferences: (customerId, data) => api.put(`/enterprise/customer-portal/${customerId}/preferences`, data),
}

export const enterpriseApi = {
  runFailoverTest: (params) => failoverApi.runTest(params),
  getFailoverStatus: (params) => failoverApi.getStatus(params),
  getFailoverHistory: (params) => failoverApi.getHistory(params),
  scoreConversation: (data) => qualityApi.scoreConversation(data),
  getQualityScores: (params) => qualityApi.getScores(params),
  getQualityTrends: (params) => qualityApi.getTrends(params),
  getCoaching: (agentId, params) => qualityApi.getCoaching(agentId, params),
  listAPIVersions: (params) => versionsApi.list(params),
  deprecateVersion: (version, params) => versionsApi.deprecate(version, params),
  getMigrationGuide: (params) => versionsApi.getMigrationGuide(params),
  getChangelog: (params) => versionsApi.getChangelog(params),
  getUsageStats: (params) => versionsApi.getUsageStats(params),
  getPortalData: (customerId, params) => portalApi.getPortalData(customerId, params),
  submitComplaint: (data) => portalApi.submitComplaint(data),
  scheduleCallback: (data) => portalApi.scheduleCallback(data),
}

export const securityApi = {
  runScan: (tenantId, targetUrl) => api.post('/security-hardening/pen-test/scan', null, { params: { tenant_id: tenantId, target_url: targetUrl } }),
  listScans: (tenantId) => api.get('/security-hardening/pen-test/scans', { params: { tenant_id: tenantId } }),
  getScan: (scanId) => api.get(`/security-hardening/pen-test/scans/${scanId}`),
  getWafRules: (tenantId) => api.get('/security-hardening/waf/rules', { params: { tenant_id: tenantId } }),
  updateWafRule: (ruleId, action) => api.put(`/security-hardening/waf/rules/${ruleId}`, null, { params: { action } }),
  getWafEvents: (tenantId, params) => api.get('/security-hardening/waf/events', { params: { tenant_id: tenantId, ...params } }),
  getDataClassification: (tenantId) => api.get('/security-hardening/data-classification', { params: { tenant_id: tenantId } }),
  classifyField: (tenantId, table, column, sensitivity) => api.post('/security-hardening/data-classification', null, { params: { tenant_id: tenantId, table, column, sensitivity } }),
  runRbacAudit: (tenantId) => api.post('/security-hardening/rbac/audit', null, { params: { tenant_id: tenantId } }),
  getRbacAuditResults: (tenantId) => api.get('/security-hardening/rbac/audit-results', { params: { tenant_id: tenantId } }),
  getCredentialAudit: (tenantId) => api.get('/security-hardening/credentials/audit', { params: { tenant_id: tenantId } }),
  forcePasswordReset: (tenantId, userId) => api.post(`/security-hardening/credentials/force-reset/${userId}`, null, { params: { tenant_id: tenantId } }),
}

export const cdpApi = {
  unifyCustomer: (data) => api.post('/cdp/customers/unify', data),
  getProfile: (customerId) => api.get(`/cdp/customers/${customerId}`),
  addTags: (customerId, data) => api.post(`/cdp/customers/${customerId}/tags`, data),
  search: (params) => api.get('/cdp/customers/search', { params }),
  listSegments: (params) => api.get('/cdp/segments', { params }),
  createSegment: (data) => api.post('/cdp/segments', data),
  evaluateSegment: (segmentId) => api.post(`/cdp/segments/${segmentId}/evaluate`),
  getTimeline: (customerId) => api.get(`/cdp/customers/${customerId}/timeline`),
  getRFM: (customerId) => api.get(`/cdp/customers/${customerId}/rfm`),
  getCohort: (params) => api.get('/cdp/analytics/cohort', { params }),
  getChurnRisk: (customerId) => api.get(`/cdp/analytics/churn-risk/${customerId}`),
  getLTV: (customerId) => api.get(`/cdp/analytics/ltv/${customerId}`),
  getOverview: (params) => api.get('/cdp/analytics/overview', { params }),
}

export const verticalsApi = {
  list: () => api.get('/verticals/'),
  getConfig: (verticalId) => api.get(`/verticals/${verticalId}`),
  apply: (verticalId, data) => api.post(`/verticals/${verticalId}/apply`, data),
  getCompliance: (verticalId) => api.get(`/verticals/${verticalId}/compliance`),
  getScripts: (verticalId) => api.get(`/verticals/${verticalId}/scripts`),
}

export const platformOpsApi = {
  getBranding: (tenantId) => api.get('/platform/branding', { params: { tenant_id: tenantId } }),
  updateBranding: (tenantId, data) => api.put('/platform/branding', { tenant_id: tenantId, ...data }),
  getDomain: (tenantId) => api.get('/platform/domain', { params: { tenant_id: tenantId } }),
  setDomain: (tenantId, domain) => api.put('/platform/domain', { tenant_id: tenantId, domain, ssl_status: 'pending' }),
  verifyDomain: (tenantId, domain) => api.post('/platform/domain/verify', null, { params: { tenant_id: tenantId, domain } }),
  signup: (data) => api.post('/platform/signup', data),
  getOnboardingStatus: (tenantId) => api.get('/platform/onboarding/status', { params: { tenant_id: tenantId } }),
  completeOnboardingStep: (tenantId, step) => api.post('/platform/onboarding/step', { tenant_id: tenantId, step }),
  getQuickstart: (tenantId) => api.get('/platform/onboarding/quickstart', { params: { tenant_id: tenantId } }),
  provisionNumber: (tenantId, areaCode) => api.post('/platform/provision/number', { tenant_id: tenantId, area_code: areaCode }),
  runHealthCheck: (tenantId) => api.post('/platform/health-check', null, { params: { tenant_id: tenantId } }),  // handled by self_serve
  getSetupProgress: (tenantId) => api.get('/platform/setup/progress', { params: { tenant_id: tenantId } }),
}

export const reliabilityApi = {
  getCircuitBreakers: (tenantId) => api.get('/reliability/circuit-breakers', { params: { tenant_id: tenantId } }),
  resetCircuitBreaker: (tenantId, name) => api.post(`/reliability/circuit-breakers/${name}/reset`, null, { params: { tenant_id: tenantId } }),
  getRateLimits: (tenantId) => api.get('/reliability/rate-limits', { params: { tenant_id: tenantId } }),
  setRateLimit: (tenantId, targetTenantId, routeKey, maxRequests, windowSeconds) => api.put(`/reliability/rate-limits/${targetTenantId}`, null, { params: { tenant_id: tenantId, route_key: routeKey, max_requests: maxRequests, window_seconds: windowSeconds } }),
  getDrStatus: (tenantId) => api.get('/reliability/dr/status', { params: { tenant_id: tenantId } }),
  runDrTest: (tenantId, testType) => api.post('/reliability/dr/test', null, { params: { tenant_id: tenantId, test_type: testType } }),
  getDrConfig: (tenantId) => api.get('/reliability/dr/config', { params: { tenant_id: tenantId } }),
  getCacheStats: (tenantId) => api.get('/reliability/cache/stats', { params: { tenant_id: tenantId } }),
  warmCache: (tenantId, key, value, ttl) => api.post('/reliability/cache/warm', null, { params: { tenant_id: tenantId, key, value, ttl } }),
}

export const developerApi = {
  createAPIKey: (data) => api.post('/developer/api-keys', data),
  listAPIKeys: () => api.get('/developer/api-keys'),
  revokeAPIKey: (keyId) => api.delete(`/developer/api-keys/${keyId}`),
  rotateAPIKey: (keyId) => api.post(`/developer/api-keys/${keyId}/rotate`),
  getAPIKeyUsage: (keyId, params) => api.get(`/developer/api-keys/${keyId}/usage`, { params }),
  registerWebhook: (data) => api.post('/developer/webhooks', data),
  listWebhooks: () => api.get('/developer/webhooks'),
  unregisterWebhook: (webhookId) => api.delete(`/developer/webhooks/${webhookId}`),
  testWebhook: (webhookId) => api.post(`/developer/webhooks/${webhookId}/test`),
  getWebhookLogs: (webhookId, params) => api.get(`/developer/webhooks/${webhookId}/logs`, { params }),
  retryWebhookDelivery: (logId) => api.post(`/developer/webhooks/logs/${logId}/retry`),
  getEventCatalog: () => api.get('/developer/events'),
}

export const platformApi = {
  collectTrainingData: (params) => api.post('/ai-platform/training/collect', null, { params }),
  createTrainingJob: (data) => api.post('/ai-platform/training/jobs', data),
  listTrainingJobs: (params) => api.get('/ai-platform/training/jobs', { params }),
  getTrainingJob: (id) => api.get(`/ai-platform/training/jobs/${id}`),
  exportTrainingData: (params) => api.get('/ai-platform/training/export', { params, responseType: 'blob' }),
  // Datasets
  createDataset: (data) => api.post('/ai-platform/datasets', data),
  listDatasets: (params) => api.get('/ai-platform/datasets', { params }),
  getDataset: (datasetId) => api.get(`/ai-platform/datasets/${datasetId}`),
  // Turns & Labels
  listTurns: (datasetId, params) => api.get(`/ai-platform/datasets/${datasetId}/turns`, { params }),
  createLabel: (turnId, data) => api.post(`/ai-platform/turns/${turnId}/labels`, data),
  listLabels: (turnId) => api.get(`/ai-platform/turns/${turnId}/labels`),
  // External Jobs
  submitExternalJob: (data) => api.post('/ai-platform/training/external-jobs', data),
  getExternalJobStatus: (jobId) => api.get(`/ai-platform/training/external-jobs/${jobId}`),
  cancelExternalJob: (jobId) => api.post(`/ai-platform/training/external-jobs/${jobId}/cancel`),
  // Eval Metrics
  ingestEvalMetrics: (data) => api.post('/ai-platform/models/eval-metrics', data),
  getEvalMetrics: (modelId, version) => api.get(`/ai-platform/models/${modelId}/eval-metrics/${version}`),
  // Model Audit
  getModelAuditLog: (modelId) => api.get(`/ai-platform/models/${modelId}/audit-log`),
  // Model Family
  getModelFamily: (family, params) => api.get(`/ai-platform/models/family/${family}`, { params }),
  // Model External Jobs
  listModelExternalJobs: (modelId, params) => api.get(`/ai-platform/models/${modelId}/external-jobs`, { params }),
  // Transition
  transitionModelState: (modelId, version, newState, params) => api.post(`/ai-platform/models/${modelId}/versions/${version}/transition`, null, { params: { new_state: newState, ...params } }),
  // Models
  registerModel: (data) => api.post('/ai-platform/models', data),
  listModels: (params) => api.get('/ai-platform/models', { params }),
  getModelVersions: (modelId) => api.get(`/ai-platform/models/${modelId}/versions`),
  promoteModel: (modelId, version) => api.post(`/ai-platform/models/${modelId}/versions/${version}/promote`),
  rollbackModel: (modelId, version) => api.post(`/ai-platform/models/${modelId}/versions/${version}/rollback`),
  getActiveModels: () => api.get('/ai-platform/models/active'),
  compareModels: (params) => api.get('/ai-platform/models/compare', { params }),
  createVoiceProfile: (data) => api.post('/ai-platform/voice-profiles', data),
  listVoiceProfiles: (params) => api.get('/ai-platform/voice-profiles', { params }),
  identifySpeaker: (data) => api.post('/ai-platform/voice-profiles/identify', data),
  detectEmotion: (data) => api.post('/ai-platform/voice-profiles/emotion', data),
  getEmotionTrends: (callId) => api.get(`/ai-platform/voice-profiles/emotion-trends/${callId}`),
}

export default api
