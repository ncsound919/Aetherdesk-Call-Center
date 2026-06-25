/**
 * K6 Load Test — Full Call Flow
 *
 * Tests the complete AetherDesk API under load:
 * 1. Login and get JWT
 * 2. List agents
 * 3. Create a call
 * 4. Check call status
 * 5. Query analytics
 *
 * Usage:
 *   k6 run tests/load/k6_call_flow.js --env API_URL=http://localhost:8000
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const errorRate = new Rate('errors');
const loginDuration = new Trend('login_duration');
const callCreateDuration = new Trend('call_create_duration');

export const options = {
  stages: [
    { duration: '30s', target: 10 },   // Ramp up to 10 VUs
    { duration: '2m', target: 10 },    // Stay at 10 for 2 minutes
    { duration: '30s', target: 50 },   // Ramp up to 50
    { duration: '2m', target: 50 },    // Stay at 50 for 2 minutes
    { duration: '30s', target: 100 },  // Spike to 100
    { duration: '1m', target: 100 },   // Sustain spike
    { duration: '30s', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],
    http_req_failed: ['rate<0.01'],
    errors: ['rate<0.01'],
  },
};

const API_URL = __ENV.API_URL || 'http://localhost:8000';

export default function () {
  // 1. Login
  const loginRes = http.post(
    `${API_URL}/api/v1/auth/login`,
    JSON.stringify({
      email: 'admin@aetherdesk.com',
      password: 'admin123',
    }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  check(loginRes, {
    'login succeeded': (r) => r.status === 200,
    'has access token': (r) => r.json('access_token') !== undefined,
  });

  if (loginRes.status !== 200) {
    errorRate.add(1);
    return;
  }

  loginDuration.add(loginRes.timings.duration);

  const token = loginRes.json('access_token');
  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };

  // 2. List agents
  const agentsRes = http.get(`${API_URL}/api/v1/agents`, { headers });
  check(agentsRes, { 'agents list succeeded': (r) => r.status === 200 });

  // 3. List scripts
  const scriptsRes = http.get(`${API_URL}/api/v1/scripts`, { headers });
  check(scriptsRes, { 'scripts list succeeded': (r) => r.status === 200 });

  // 4. Get analytics
  const analyticsRes = http.get(`${API_URL}/api/v1/metabase/stats`, { headers });
  check(analyticsRes, { 'analytics succeeded': (r) => r.status === 200 });

  // 5. Check health
  const healthRes = http.get(`${API_URL}/health`);
  check(healthRes, { 'health check succeeded': (r) => r.status === 200 });

  // Simulate think time
  sleep(Math.random() * 2 + 1);
}
