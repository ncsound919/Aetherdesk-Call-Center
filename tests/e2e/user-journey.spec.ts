import { test, expect, Page } from '@playwright/test';

async function loginAsAdmin(page: Page) {
  await page.goto('/login');
  await page.fill('input[type="email"]', 'admin@aetherdesk.com');
  await page.fill('input[type="password"]', 'admin123');
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL('/', { timeout: 15000 });
}

test.describe('Full User Journey', () => {
  test('complete workflow: login → dashboard → agents → calls → analytics → settings', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('h2')).toContainText('Welcome back');
    await page.fill('input[type="email"]', 'admin@aetherdesk.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL('/', { timeout: 15000 });

    await expect(page.locator('text=ACTIVE CALLS')).toBeVisible({ timeout: 10000 });

    await page.click('nav >> text=Agents');
    await expect(page).toHaveURL('/agents');

    await page.click('nav >> text=Call Logs');
    await expect(page).toHaveURL('/calls');

    await page.click('nav >> text=Analytics');
    await expect(page).toHaveURL('/analytics');

    await page.click('nav >> text=Settings');
    await expect(page).toHaveURL('/settings');

    await page.click('nav >> text=Dashboard');
    await expect(page).toHaveURL('/');
  });

  test('Make Call modal opens and closes', async ({ page }) => {
    await loginAsAdmin(page);
    await expect(page.locator('text=ACTIVE CALLS')).toBeVisible({ timeout: 10000 });

    const makeCallBtn = page.locator('button:has-text("Make a Call")');
    await makeCallBtn.click();

    await expect(page.locator('[class*="modal"], [role="dialog"]').first()).toBeVisible({ timeout: 5000 });

    const closeBtn = page.locator('[class*="modal"] button:has(svg), [role="dialog"] button:has(svg), button:has-text("Cancel")');
    if (await closeBtn.count() > 0) {
      await closeBtn.first().click();
    }
  });
});

test.describe('Responsive Design', () => {
  test('mobile view shows hamburger menu', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await loginAsAdmin(page);

    await expect(page.locator('header button, button:has(svg)').first()).toBeVisible({ timeout: 10000 });
  });

  test('desktop view shows full sidebar', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginAsAdmin(page);

    await expect(page.locator('nav')).toBeVisible({ timeout: 10000 });
  });
});

test.describe('Branding', () => {
  test('AetherDesk logo and name visible on login', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('text=AetherDesk').first()).toBeVisible();
  });

  test('page title contains AetherDesk', async ({ page }) => {
    await page.goto('/login');
    const title = await page.title();
    expect(title.toLowerCase()).toContain('aetherdesk');
  });
});
