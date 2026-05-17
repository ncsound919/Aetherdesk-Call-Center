/**
 * Auth setup for Playwright E2E tests.
 * Logs in once and saves auth state for reuse across tests.
 */
import { test as setup, expect } from '@playwright/test';
import path from 'path';

const authFile = path.join(__dirname, '../../test-results/.auth/user.json');
const UI_URL = process.env.UI_URL || 'http://127.0.0.1:5173';

setup('authenticate as admin', async ({ page }) => {
  await page.goto(`${UI_URL}/login`);
  await page.locator('input[type="email"]').fill('admin@aetherdesk.com');
  await page.locator('input[type="password"]').fill('admin123');
  await page.locator('button:has-text("Sign in")').first().click();
  
  // Wait for sidebar and user-menu to confirm successful login
  await page.waitForSelector('[data-testid="sidebar"]', { timeout: 15000 });
  await page.waitForSelector('[data-testid="user-menu"]', { timeout: 10000 });
  
  // Save auth state
  await page.context().storageState({ path: authFile });
});
