const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

interface ApiOptions {
  method?: string;
  body?: any;
  headers?: Record<string, string>;
  requireAuth?: boolean;
}

class ApiClient {
  private getToken(): string | null {
    return localStorage.getItem('access_token');
  }

  private setToken(token: string) {
    localStorage.setItem('access_token', token);
  }

  private clearToken() {
    localStorage.removeItem('access_token');
  }

  async request<T = any>(endpoint: string, options: ApiOptions = {}): Promise<T> {
    const { method = 'GET', body, headers = {}, requireAuth = true } = options;

    const requestHeaders: Record<string, string> = {
      'Content-Type': 'application/json',
      ...headers,
    };

    if (requireAuth) {
      const token = this.getToken();
      if (token) {
        requestHeaders['Authorization'] = `Bearer ${token}`;
      }
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      method,
      headers: requestHeaders,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (response.status === 401) {
      this.clearToken();
      window.location.href = '/login';
      throw new Error('Unauthorized');
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  }

  // Auth
  async register(email: string, password: string, fullName: string, companyName?: string) {
    return this.request('/api/v1/auth/register', {
      method: 'POST',
      body: { email, password, full_name: fullName, company_name: companyName },
      requireAuth: false,
    });
  }

  async login(email: string, password: string) {
    const data = await this.request('/api/v1/auth/login', {
      method: 'POST',
      body: { email, password },
      requireAuth: false,
    });
    this.setToken(data.access_token);
    return data;
  }

  async logout() {
    try {
      await this.request('/api/v1/auth/logout', { method: 'POST' });
    } finally {
      this.clearToken();
    }
  }

  async getMe() {
    return this.request('/api/v1/auth/me');
  }

  async verifyEmail(token: string) {
    return this.request('/api/v1/auth/verify-email', {
      method: 'POST',
      body: { token },
      requireAuth: false,
    });
  }

  async forgotPassword(email: string) {
    return this.request('/api/v1/auth/forgot-password', {
      method: 'POST',
      body: { email },
      requireAuth: false,
    });
  }

  async resetPassword(token: string, newPassword: string) {
    return this.request('/api/v1/auth/reset-password', {
      method: 'POST',
      body: { token, new_password: newPassword },
      requireAuth: false,
    });
  }

  // Onboarding
  async saveBusinessInfo(info: { company_name: string; industry: string; timezone: string; phone_number?: string }) {
    return this.request('/api/v1/onboarding/business-info', {
      method: 'POST',
      body: info,
    });
  }

  async importLeads(file: File, mapping: Record<string, string>) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('mapping', JSON.stringify(mapping));

    const token = this.getToken();
    const response = await fetch(`${API_BASE}/api/v1/onboarding/import-leads`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Import failed' }));
      throw new Error(error.detail || 'Import failed');
    }

    return response.json();
  }

  async saveScript(script: { name: string; content: string; variables: any[] }) {
    return this.request('/api/v1/onboarding/save-script', {
      method: 'POST',
      body: script,
    });
  }

  async completeOnboarding() {
    return this.request('/api/v1/onboarding/complete', { method: 'POST' });
  }

  async getOnboardingStatus() {
    return this.request('/api/v1/onboarding/status');
  }

  // Dashboard
  async getDashboard() {
    return this.request('/api/v1/saas/dashboard');
  }

  async getCampaignStats() {
    return this.request('/api/v1/campaign/stats');
  }

  // Billing
  async getSubscription() {
    return this.request('/api/v1/billing/subscription');
  }

  async createCheckout(plan: string) {
    return this.request('/api/v1/billing/checkout', {
      method: 'POST',
      body: { plan },
    });
  }

  async createPortal() {
    return this.request('/api/v1/billing/portal', { method: 'POST' });
  }

  async reportUsage(metric: string, quantity: number) {
    return this.request('/api/v1/billing/usage', {
      method: 'POST',
      body: { metric, quantity },
    });
  }

  // Leads
  async listLeads(params: { status?: string; industry?: string; limit?: number; offset?: number } = {}) {
    const searchParams = new URLSearchParams();
    if (params.status) searchParams.set('status', params.status);
    if (params.industry) searchParams.set('industry', params.industry);
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.offset) searchParams.set('offset', String(params.offset));
    const qs = searchParams.toString();
    return this.request(`/api/v1/leads${qs ? '?' + qs : ''}`);
  }

  async getLead(id: string) {
    return this.request(`/api/v1/leads/${id}`);
  }

  async createLead(data: any) {
    return this.request('/api/v1/leads', {
      method: 'POST',
      body: data,
    });
  }

  async updateLead(id: string, data: any) {
    return this.request(`/api/v1/leads/${id}`, {
      method: 'PATCH',
      body: data,
    });
  }

  async deleteLead(id: string) {
    return this.request(`/api/v1/leads/${id}`, {
      method: 'DELETE',
    });
  }

  async bulkUpdateLeads(lead_ids: string[], updates: any) {
    return this.request('/api/v1/leads/bulk-update', {
      method: 'POST',
      body: { lead_ids, updates },
    });
  }

  async bulkDeleteLeads(lead_ids: string[]) {
    return this.request('/api/v1/leads/bulk-delete', {
      method: 'POST',
      body: { lead_ids },
    });
  }

  async uploadLeadsCsv(file: File) {
    const formData = new FormData();
    formData.append('file', file);
    const token = this.getToken();
    const response = await fetch(`${API_BASE}/api/v1/leads/upload`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: formData,
    });
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Upload failed' }));
      throw new Error(error.detail || 'Upload failed');
    }
    return response.json();
  }

  async importLeadsFromRows(mapping: Record<string, string>, rows: any[]) {
    return this.request('/api/v1/leads/import', {
      method: 'POST',
      body: { mapping, rows },
    });
  }

  // Scripts
  async listScripts(params: { is_active?: boolean; limit?: number; offset?: number } = {}) {
    const searchParams = new URLSearchParams();
    if (params.is_active !== undefined) searchParams.set('is_active', String(params.is_active));
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.offset) searchParams.set('offset', String(params.offset));
    const qs = searchParams.toString();
    return this.request(`/api/v1/scripts${qs ? '?' + qs : ''}`);
  }

  async getScript(id: string) {
    return this.request(`/api/v1/scripts/${id}`);
  }

  async createScript(data: any) {
    return this.request('/api/v1/scripts', {
      method: 'POST',
      body: data,
    });
  }

  async updateScript(id: string, data: any) {
    return this.request(`/api/v1/scripts/${id}`, {
      method: 'PATCH',
      body: data,
    });
  }

  async deleteScript(id: string) {
    return this.request(`/api/v1/scripts/${id}`, {
      method: 'DELETE',
    });
  }

  async listTemplates(params: { industry?: string; limit?: number; offset?: number } = {}) {
    const searchParams = new URLSearchParams();
    if (params.industry) searchParams.set('industry', params.industry);
    if (params.limit) searchParams.set('limit', String(params.limit));
    if (params.offset) searchParams.set('offset', String(params.offset));
    const qs = searchParams.toString();
    return this.request(`/api/v1/scripts/templates/list${qs ? '?' + qs : ''}`, { requireAuth: false });
  }

  async cloneTemplate(templateId: string) {
    return this.request(`/api/v1/scripts/templates/clone/${templateId}`, {
      method: 'POST',
    });
  }

  // SaaS
  async getSaasApprovals() {
    return this.request('/api/v1/saas/approvals');
  }

  async approveSaasRequest(id: string) {
    return this.request(`/api/v1/saas/approvals/${id}?status=approved`, { method: 'POST' });
  }

  async rejectSaasRequest(id: string) {
    return this.request(`/api/v1/saas/approvals/${id}?status=rejected`, { method: 'POST' });
  }

  async getSaasRecordings() {
    return this.request('/api/v1/saas/recordings');
  }

  async getSaasSettings() {
    return this.request('/api/v1/saas/settings');
  }

  async updateSaasSettings(settings: any) {
    return this.request('/api/v1/saas/settings', { method: 'POST', body: settings });
  }

  async createSaasProfile(name: string, prompt: string) {
    return this.request(`/api/v1/saas/profile?name=${encodeURIComponent(name)}&prompt=${encodeURIComponent(prompt)}`, {
      method: 'POST',
      body: { tools: ['lookup_invoice', 'search_knowledge_base'] },
    });
  }

  async generateScript(objective: string) {
    return this.request('/api/v1/saas/generate-script', {
      method: 'POST',
      body: { objective },
    });
  }

  // Campaign
  async getCampaignStats() {
    return this.request('/api/v1/campaign/stats');
  }

  async getCampaignLeads() {
    return this.request('/api/v1/campaign/leads');
  }

  async getCampaignCalls() {
    return this.request('/api/v1/campaign/calls');
  }

  async launchCampaign(config: { profile_id: string; max_concurrent: number; delay_between_calls: number }) {
    return this.request('/api/v1/campaign/launch', {
      method: 'POST',
      body: config,
    });
  }

  async addCampaignLead(lead: { company_name: string; contact_name: string; phone: string; industry: string }) {
    return this.request('/api/v1/campaign/leads', {
      method: 'POST',
      body: lead,
    });
  }
}

export const api = new ApiClient();