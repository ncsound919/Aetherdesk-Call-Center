import { test, expect } from '@playwright/test';

const UI = 'http://127.0.0.1:3001';

test.describe('Business User Journey', () => {

  test('01 - Landing page loads', async ({ page }) => {
    await page.goto(UI);
    await expect(page.getByText('AetherDesk')).toBeVisible({ timeout: 10000 });
  });

  test('02 - Login flow', async ({ page }) => {
    await page.goto(`${UI}/login`);
    await page.fill('input[type="email"]', 'admin@aetherdesk.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button:has-text("Sign in")');
    await expect(page).toHaveURL(/dashboard/, { timeout: 10000 });
  });

  test('03 - Dashboard shows metrics', async ({ page }) => {
    await page.goto(`${UI}/login`);
    await page.fill('input[type="email"]', 'admin@aetherdesk.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button:has-text("Sign in")');
    await page.waitForURL(/dashboard/, { timeout: 10000 });
    await expect(page.getByText('Dashboard')).toBeVisible();
    await expect(page.getByText('Active Calls')).toBeVisible();
    await expect(page.getByText('Available Agents')).toBeVisible();
  });

  test('04 - Sidebar navigation', async ({ page }) => {
    await page.goto(`${UI}/login`);
    await page.fill('input[type="email"]', 'admin@aetherdesk.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button:has-text("Sign in")');
    await page.waitForURL(/dashboard/, { timeout: 10000 });

    for (const section of ['Call Logs', 'Agents', 'Voice Cloning', 'Settings']) {
      await page.click(`button:has-text("${section}")`);
      await page.waitForTimeout(500);
    }
  });

  test('05 - Agent management page', async ({ page }) => {
    await page.goto(`${UI}/login`);
    await page.fill('input[type="email"]', 'admin@aetherdesk.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button:has-text("Sign in")');
    await page.waitForURL(/dashboard/, { timeout: 10000 });
    await page.click('button:has-text("Agents")');
    await page.waitForTimeout(1000);
  });

  test('06 - Logout flow', async ({ page }) => {
    await page.goto(`${UI}/login`);
    await page.fill('input[type="email"]', 'admin@aetherdesk.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button:has-text("Sign in")');
    await page.waitForURL(/dashboard/, { timeout: 10000 });
    await page.click('button:has-text("Sign Out")');
    await expect(page).toHaveURL(/login/, { timeout: 10000 });
  });
});
