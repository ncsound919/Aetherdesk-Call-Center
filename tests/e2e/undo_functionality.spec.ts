import { test, expect } from '@playwright/test';

test('undo last change to profile', async ({ page }) => {
  await page.goto('/profile/edit');
  await page.fill('input[name="bio"]', 'Initial bio');
  await page.click('button:has-text("Save")');
  await page.waitForSelector('.toast-success');
  
  await page.click('button:has-text("Undo")');
  await expect(page.locator('input[name="bio"]')).toHaveValue('Initial bio');
});
