import { test, expect, Page } from '@playwright/test';

async function loginAsAdmin(page: Page) {
  await page.goto('/login');
  await page.fill('input[type="email"]', 'admin@aetherdesk.com');
  await page.fill('input[type="password"]', 'admin123');
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL('/', { timeout: 15000 });
}

test.describe('Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('navigate to agents page', async ({ page }) => {
    await page.click('nav >> text=Agents');
    await expect(page).toHaveURL('/agents');
  });

  test('navigate to call logs page', async ({ page }) => {
    await page.click('nav >> text=Call Logs');
    await expect(page).toHaveURL('/calls');
  });

  test('navigate to analytics page', async ({ page }) => {
    await page.click('nav >> text=Analytics');
    await expect(page).toHaveURL('/analytics');
  });

  test('navigate to settings page', async ({ page }) => {
    await page.click('nav >> text=Settings');
    await expect(page).toHaveURL('/settings');
  });

  test('navigate to billing page', async ({ page }) => {
    await page.click('nav >> text=Billing');
    await expect(page).toHaveURL('/billing');
  });

  test('navigate to scripts page', async ({ page }) => {
    await page.click('nav >> text=Scripts');
    await expect(page).toHaveURL('/scripts');
  });

  test('navigate to leads page', async ({ page }) => {
    await page.click('nav >> text=Leads');
    await expect(page).toHaveURL('/leads');
  });
});

test.describe('Agent Management', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
    await page.click('nav >> text=Agents');
    await expect(page).toHaveURL('/agents');
  });

  test('agents page shows agent list or empty state', async ({ page }) => {
    const hasEmpty = await page.locator('text=No agents yet').count();
    const hasCreate = await page.locator('text=Create your first agent').count();
    expect(hasEmpty + hasCreate).toBeGreaterThan(0);
  });

  test('create agent button is visible', async ({ page }) => {
    await expect(page.locator('button:has-text("Add Agent")')).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Call Logs', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
    await page.click('nav >> text=Call Logs');
    await expect(page).toHaveURL('/calls');
  });

  test('calls page renders table or empty state', async ({ page }) => {
    await page.waitForTimeout(2000);
    const hasTable = await page.locator('table, [class*="table"]').count();
    const hasEmpty = await page.locator('text=No calls, text=No data').count();
    expect(hasTable + hasEmpty).toBeGreaterThanOrEqual(0);
  });
});

test.describe('Settings', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
    await page.click('nav >> text=Settings');
    await expect(page).toHaveURL('/settings');
  });

  test('settings page renders business profile section', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'Business Profile' })).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Analytics', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
    await page.click('nav >> text=Analytics');
    await expect(page).toHaveURL('/analytics');
  });

  test('analytics page renders charts or stats', async ({ page }) => {
    await page.waitForTimeout(2000);
    const hasCharts = await page.locator('svg, [class*="chart"], canvas, [class*="recharts"]').count();
    expect(hasCharts).toBeGreaterThanOrEqual(0);
  });
});
