import { test, expect } from '@playwright/test';

test('displays connection error when offline', async ({ page }) => {
  await page.emulateNetworkConditions({ offline: true });
  // Assuming a route that triggers an API call
  await page.goto('/dashboard'); 
  await expect(page.locator('.error-message')).toContainText('Connection Error');
  await page.emulateNetworkConditions({ offline: false });
});
