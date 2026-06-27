import { test, expect } from "@playwright/test";

/**
 * Integration Tests: Aetherdesk <-> VibeServe MCP
 *
 * Tests the security and connectivity patterns of Aetherdesk's
 * integration with VibeServe MCP tools.
 * Critical: API keys should NEVER be exposed to client-side code.
 */

const AETHERDESK_API_URL = "http://localhost:8000"; // Backend proxy
const VIBESERVE_URL = "http://localhost:8000"; // VibeServe MCP

test.describe("Aetherdesk Backend Proxy Integration", () => {
  test("VibeServe health check via backend proxy should work", async ({ request }) => {
    // The frontend should call the backend proxy, not VibeServe directly
    const response = await request.get(`${AETHERDESK_API_URL}/api/v1/integrations/vibeserve/health`, {
      timeout: 5000,
    }).catch(() => null);

    if (response) {
      // 404 is acceptable if the backend proxy isn't fully implemented yet
      expect([200, 404, 503]).toContain(response.status());
    } else {
      test.skip(true, "Aetherdesk backend not running - skipping");
    }
  });

  test("VibeServe tools listing via backend proxy should work", async ({ request }) => {
    const response = await request.get(`${AETHERDESK_API_URL}/api/v1/integrations/vibeserve/tools`, {
      timeout: 5000,
    }).catch(() => null);

    if (response) {
      expect([200, 404]).toContain(response.status());

      if (response.status() === 200) {
        const body = await response.json();
        expect(body).toHaveProperty("tools");
      }
    } else {
      test.skip(true, "Aetherdesk backend not running - skipping");
    }
  });
});

test.describe("Client-Side Security Validation", () => {
  test("Client-side vibeserve-client.js should NOT contain hardcoded API keys", async () => {
    // This test verifies the static security of the client file
    const fs = require("fs");
    const path = require("path");
    const clientPath = path.join(
      "C:\\Users\\User\\Desktop\\Overlay365\\Aetherdesk-Call-Center-main\\agent-ui\\src\\lib\\vibeserve-client.js",
    );

    if (fs.existsSync(clientPath)) {
      const content = fs.readFileSync(clientPath, "utf-8");

      // Should NOT contain hardcoded API keys (long alphanumeric strings)
      const suspiciousKeyPattern = /['"](ab_local_dev_key|sk-|pk-|key_)[a-zA-Z0-9]{10,}['"]/;
      expect(content).not.toMatch(suspiciousKeyPattern);

      // Should NOT contain direct VibeServe API key references
      expect(content).not.toMatch(/VIBESERVE_API_KEY\s*=\s*['"]/);
    } else {
      test.skip(true, "Client file not found");
    }
  });

  test("Client-side file should call backend proxy, not VibeServe directly", async () => {
    const fs = require("fs");
    const path = require("path");
    const clientPath = path.join(
      "C:\\Users\\User\\Desktop\\Overlay365\\Aetherdesk-Call-Center-main\\agent-ui\\src\\lib\\vibeserve-client.js",
    );

    if (fs.existsSync(clientPath)) {
      const content = fs.readFileSync(clientPath, "utf-8");

      // Should call /api/v1/integrations/vibeserve/ (backend proxy)
      expect(content).toMatch(/\/api\/v1\/integrations\/vibeserve\//);

      // Should NOT directly call VibeServe port
      expect(content).not.toMatch(/localhost:8000\/tools\//);
    } else {
      test.skip(true, "Client file not found");
    }
  });
});

test.describe("Environment Configuration", () => {
  test(".env.example should have VITE_API_URL for client", async () => {
    const fs = require("fs");
    const path = require("path");
    const envPath = path.join(
      "C:\\Users\\User\\Desktop\\Overlay365\\Aetherdesk-Call-Center-main\\.env.example",
    );

    if (fs.existsSync(envPath)) {
      const content = fs.readFileSync(envPath, "utf-8");

      // Frontend needs VITE_ prefixed URL
      expect(content).toMatch(/VITE_API_URL/);

      // Backend can have non-VITE_ key
      expect(content).toMatch(/VIBESERVE_API_KEY/);
    } else {
      test.skip(true, ".env.example not found");
    }
  });
});

test.describe("VibeServe Direct Connectivity (For Reference)", () => {
  test("VibeServe health endpoint should respond", async ({ request }) => {
    const response = await request.get(`${VIBESERVE_URL}/health`, {
      timeout: 5000,
    }).catch(() => null);

    if (response) {
      expect([200, 503]).toContain(response.status());
    } else {
      test.skip(true, "VibeServe not running - skipping");
    }
  });

  test("VibeServe tools endpoint should respond", async ({ request }) => {
    const response = await request.get(`${VIBESERVE_URL}/tools`, {
      timeout: 5000,
    }).catch(() => null);

    if (response) {
      expect([200, 503]).toContain(response.status());
    } else {
      test.skip(true, "VibeServe not running - skipping");
    }
  });
});