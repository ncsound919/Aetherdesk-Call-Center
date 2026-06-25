// VibeServe MCP Client for Aetherdesk (Frontend Proxy)
// SECURITY: This client calls the Aetherdesk backend proxy, not VibeServe directly.
// The API key is NEVER exposed to the browser bundle.

const AETHERDESK_API_BASE = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_API_URL) || '';

/** Check VibeServe health via Aetherdesk backend proxy */
export async function checkVibeServeHealth() {
  try {
    const response = await fetch(`${AETHERDESK_API_BASE}/api/v1/integrations/vibeserve/health`, {
      credentials: 'include',
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) return false;
    const data = await response.json();
    return data.reachable === true;
  } catch {
    return false;
  }
}

/** Call a VibeServe MCP tool via Aetherdesk backend proxy */
export async function callVibeServeTool(toolName, args = {}) {
  try {
    const response = await fetch(`${AETHERDESK_API_BASE}/api/v1/integrations/vibeserve/tools/${encodeURIComponent(toolName)}`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(args || {}),
      signal: AbortSignal.timeout(30000),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const errMsg = data?.error || data?.detail || `Backend returned ${response.status}`;
      return { error: errMsg };
    }
    return data;
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'Aetherdesk backend unreachable' };
  }
}

/** List available VibeServe tools via Aetherdesk backend proxy */
export async function listVibeServeTools() {
  try {
    const response = await fetch(`${AETHERDESK_API_BASE}/api/v1/integrations/vibeserve/tools`, {
      credentials: 'include',
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) return [];
    const data = await response.json();
    return Array.isArray(data?.tools) ? data.tools : [];
  } catch {
    return [];
  }
}

/** Integration status for display in Aetherdesk UI */
export async function getIntegrationStatus() {
  const healthy = await checkVibeServeHealth();
  const tools = healthy ? await listVibeServeTools() : [];
  return {
    service: 'VibeServe',
    healthy,
    toolCount: Array.isArray(tools) ? tools.length : 0,
    tools: Array.isArray(tools) ? tools.slice(0, 10) : [],
  };
}