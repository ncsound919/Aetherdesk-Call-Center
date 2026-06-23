import { test, expect } from '@playwright/test';

test('user interacts with default agent', async ({ page }) => {
  await page.goto('/agent'); // Assume an agent interface route
  await page.fill('input[name="message"]', 'Hello, agent');
  await page.click('button:has-text("Send")');
  // Assert agent response is visible
});
