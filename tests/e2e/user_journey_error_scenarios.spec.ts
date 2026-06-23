import { test, expect } from '@playwright/test';

test('displays actionable error for invalid input', async ({ page }) => {
  await page.goto('/profile/edit');
  await page.fill('input[name="email"]', 'invalid-email');
  await page.press('input[name="email"]', 'Tab');
  await expect(page.locator('.error-message')).toContainText('Please check your input');
});
