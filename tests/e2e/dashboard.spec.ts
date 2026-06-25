import { test, expect, Page } from '@playwright/test';

async function loginAsAdmin(page: Page) {
  await page.goto('/login');
  await page.fill('input[type="email"]', 'admin@aetherdesk.com');
  await page.fill('input[type="password"]', 'admin123');
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL('/', { timeout: 15000 });
}

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('dashboard renders with stats cards', async ({ page }) => {
    await expect(page.locator('text=ACTIVE CALLS')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('text=TOTAL CALLS TODAY')).toBeVisible();
    await expect(page.locator('text=AVG CALL DURATION')).toBeVisible();
    await expect(page.locator('text=AVAILABLE AGENTS')).toBeVisible();
  });

  test('sidebar navigation is visible', async ({ page }) => {
    await expect(page.locator('nav')).toBeVisible();
    await expect(page.locator('nav >> text=Dashboard')).toBeVisible();
    await expect(page.locator('nav >> text=Agents')).toBeVisible();
    await expect(page.locator('nav >> text=Call Logs')).toBeVisible();
    await expect(page.locator('nav >> text=Analytics')).toBeVisible();
  });

  test('make call button is visible', async ({ page }) => {
    await expect(page.locator('button:has-text("Make a Call")')).toBeVisible({ timeout: 10000 });
  });

  test('recent calls section renders', async ({ page }) => {
    await expect(page.locator('text=Recent Calls')).toBeVisible({ timeout: 10000 });
  });
});
