/**
 * Global setup for Playwright E2E tests.
 * Starts the API and UI servers before running tests.
 * Cross-platform compatible (Windows, macOS, Linux).
 */
import { spawn, spawnSync } from 'child_process';
import path from 'path';
import fs from 'fs';

const ROOT = path.resolve(__dirname, '../..');
const API_URL = process.env.API_URL || 'http://127.0.0.1:8080';
const UI_URL = process.env.UI_URL || 'http://127.0.0.1:5173';
const HEALTH_TIMEOUT = 90_000;
const HEALTH_INTERVAL = 2_000;

function log(msg: string) {
  console.log(`[global-setup] ${msg}`);
}

function env(): NodeJS.ProcessEnv {
  return {
    ...process.env,
    DATABASE_URL: 'sqlite:///./aetherdesk.db',
    USE_POSTGRES: 'false',
    ENCRYPTION_KEY: 'SkYXQ9OlgNAkCoikdZW9NQLYhRbdgQSrV7vfrnCjxLA=',
    JWT_SECRET: 'test-websocket-secret',
    WEBSOCKET_SECRET_KEY: 'test-websocket-secret',
    DEV_USERS_CONFIGURED: 'true',
    DEV_ADMIN_PASSWORD: 'admin123',
    DEV_AGENT_PASSWORD: 'agent123',
    INTERNAL_API_KEY: 'dev-api-key',
    DEV_API_KEY: 'dev-api-key',
    APP_ENV: 'development',
  };
}

async function waitForUrl(url: string, timeout: number, interval: number): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      const res = await fetch(url, { method: 'HEAD' });
      if (res.ok || res.status === 200) return true;
    } catch {
      // Server not ready yet
    }
    await new Promise(r => setTimeout(r, interval));
  }
  return false;
}

export default async function globalSetup() {
  log('Starting servers...');

  // Clean old DB
  const dbPath = path.join(ROOT, 'aetherdesk.db');
  try { fs.unlinkSync(dbPath); } catch { /* ignore */ }

  // Start API server
  const pythonExe = process.env.PYTHON || 'python';
  const apiProc = spawn(
    pythonExe,
    ['-m', 'uvicorn', 'apps.api.main:app', '--host', '127.0.0.1', '--port', '8080', '--log-level', 'info'],
    { cwd: ROOT, env: env(), stdio: ['ignore', 'pipe', 'pipe'], detached: true }
  );
  apiProc.unref();
  log(`API PID: ${apiProc.pid}`);

  // Log API startup errors
  apiProc.stderr?.on('data', (data) => {
    const msg = data.toString().trim();
    if (msg) log(`API stderr: ${msg.substring(0, 200)}`);
  });

  // Start UI server
  const isWindows = process.platform === 'win32';
  const uiProc = spawn(
    'npx',
    ['vite', 'dev', '--host', '127.0.0.1', '--port', '5173'],
    { cwd: path.join(ROOT, 'agent-ui'), env: env(), stdio: 'ignore', detached: true, shell: isWindows }
  );
  uiProc.unref();
  log(`UI PID: ${uiProc.pid}`);

  // Wait for servers
  log('Waiting for API...');
  const apiReady = await waitForUrl(`${API_URL}/health`, HEALTH_TIMEOUT, HEALTH_INTERVAL);
  if (!apiReady) throw new Error('API server did not start in time');
  log('API ready');

  log('Waiting for UI...');
  const uiReady = await waitForUrl(UI_URL, HEALTH_TIMEOUT, HEALTH_INTERVAL);
  if (!uiReady) throw new Error('UI server did not start in time');
  log('UI ready');

  // Store PIDs for teardown (optional)
  const statePath = path.join(ROOT, 'test-results', '.server-pids.json');
  fs.mkdirSync(path.dirname(statePath), { recursive: true });
  fs.writeFileSync(statePath, JSON.stringify({ api: apiProc.pid, ui: uiProc.pid }));

  log('Servers started successfully');
}
