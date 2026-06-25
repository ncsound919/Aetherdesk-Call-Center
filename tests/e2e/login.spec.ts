import { test, expect } from '@playwright/test';

test.describe('AetherDesk Login', () => {
  test('login page renders correctly', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('h2')).toContainText('Welcome back');
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toContainText('Sign in');
  });

  test('shows error on invalid credentials', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', 'wrong@example.com');
    await page.fill('input[type="password"]', 'wrongpassword');
    await page.click('button[type="submit"]');
    await expect(page.locator('.bg-call-red-soft')).toBeVisible({ timeout: 10000 });
  });

  test('successful login redirects to dashboard', async ({ page }) => {
    await page.goto('/login');
    await page.fill('input[type="email"]', 'admin@aetherdesk.com');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');
    await expect(page).toHaveURL('/', { timeout: 15000 });
  });

  test('signup link is visible', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('a:has-text("Sign up")')).toBeVisible();
  });

  test('forgot password link is visible', async ({ page }) => {
    await page.goto('/login');
    await expect(page.locator('a:has-text("Forgot password")')).toBeVisible();
  });

  test('password toggle shows/hides password', async ({ page }) => {
    await page.goto('/login');
    const pwInput = page.locator('input[type="password"]');
    await expect(pwInput).toBeVisible();
    // Click the eye icon to show password
    await page.locator('button:has(svg)').last().click();
    await expect(page.locator('input[type="text"]')).toBeVisible();
  });
});
