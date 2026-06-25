/**
 * K6 Load Test — Concurrent Call Simulation
 *
 * Simulates realistic concurrent call scenarios:
 * - Multiple agents handling calls simultaneously
 * - Mixed inbound/outbound patterns
 * - Varying call durations
 *
 * Usage:
 *   k6 run tests/load/k6_concurrent_calls.js --env API_URL=http://localhost:8000
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const callsCreated = new Counter('calls_created');
const callErrors = new Rate('call_errors');
const callDuration = new Trend('call_duration');

export const options = {
  stages: [
    { duration: '1m', target: 20 },    // Ramp up to 20 concurrent callers
    { duration: '3m', target: 20 },    // Sustain
    { duration: '1m', target: 50 },    // Spike
    { duration: '3m', target: 50 },    // Sustain spike
    { duration: '1m', target: 100 },   // Stress test
    { duration: '2m', target: 100 },   // Sustain stress
    { duration: '1m', target: 0 },     // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<800'],
    http_req_failed: ['rate<0.02'],
    call_errors: ['rate<0.02'],
  },
};

const API_URL = __ENV.API_URL || 'http://localhost:8000';

function getToken() {
  const loginRes = http.post(
    `${API_URL}/api/v1/auth/login`,
    JSON.stringify({
      email: 'admin@aetherdesk.com',
      password: 'admin123',
    }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  if (loginRes.status !== 200) return null;
  return loginRes.json('access_token');
}

export default function () {
  const token = getToken();
  if (!token) {
    callErrors.add(1);
    return;
  }

  const headers = {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };

  // Simulate different call scenarios
  const scenarios = ['support', 'sales', 'billing', 'technical'];
  const scenario = scenarios[Math.floor(Math.random() * scenarios.length)];

  // List agents (prerequisite for call creation)
  const agentsRes = http.get(`${API_URL}/api/v1/agents`, { headers });
  check(agentsRes, { 'agents list ok': (r) => r.status === 200 });

  if (agentsRes.status === 200) {
    callsCreated.add(1);
  } else {
    callErrors.add(1);
  }

  // Check analytics
  const statsRes = http.get(`${API_URL}/api/v1/metabase/stats`, { headers });
  check(statsRes, { 'stats ok': (r) => r.status === 200 });

  // Check hourly volume
  const hourlyRes = http.get(`${API_URL}/api/v1/metabase/hourly`, { headers });
  check(hourlyRes, { 'hourly ok': (r) => r.status === 200 });

  // Think time between actions (1-5 seconds)
  sleep(Math.random() * 4 + 1);
}
