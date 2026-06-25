// VibeServe MCP Client for Aetherdesk
// Connects to VibeServe MCP tools for AI agent capabilities

const VIBESERVE_URL = (typeof process !== 'undefined' ? process.env.VIBESERVE_URL : '') || 'http://localhost:8000';
const VIBESERVE_API_KEY = (typeof process !== 'undefined' ? process.env.VIBESERVE_API_KEY : '') || '';

function vibeserveHeaders() {
  const headers = { 'Content-Type': 'application/json' };
  if (VIBESERVE_API_KEY) headers['Authorization'] = `Bearer ${VIBESERVE_API_KEY}`;
  return headers;
}

/** Check VibeServe health */
export async function checkVibeServeHealth() {
  try {
    const response = await fetch(`${VIBESERVE_URL}/health`, {
      headers: vibeserveHeaders(),
      signal: AbortSignal.timeout(5000),
    });
    return response.ok;
  } catch {
    return false;
  }
}

/** Call a VibeServe MCP tool */
export async function callVibeServeTool(toolName, args = {}) {
  try {
    const response = await fetch(`${VIBESERVE_URL}/tools/${toolName}`, {
      method: 'POST',
      headers: vibeserveHeaders(),
      body: JSON.stringify(args),
      signal: AbortSignal.timeout(30000),
    });
    if (response.ok) {
      return await response.json();
    }
    return { error: `VibeServe returned ${response.status}` };
  } catch (err) {
    return { error: err instanceof Error ? err.message : 'VibeServe unreachable' };
  }
}

/** List available VibeServe tools */
export async function listVibeServeTools() {
  try {
    const response = await fetch(`${VIBESERVE_URL}/tools`, {
      headers: vibeserveHeaders(),
      signal: AbortSignal.timeout(5000),
    });
    if (response.ok) {
      const data = await response.json();
      return Array.isArray(data) ? data : (data.tools || []);
    }
    return [];
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
    url: VIBESERVE_URL,
    healthy,
    toolCount: Array.isArray(tools) ? tools.length : 0,
    tools: Array.isArray(tools) ? tools.slice(0, 10) : [],
  };
}