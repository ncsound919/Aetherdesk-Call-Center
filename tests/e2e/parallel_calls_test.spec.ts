import { test, expect } from '@playwright/test';

test('handles concurrent resource updates', async ({ browser }) => {
  const context1 = await browser.newContext();
  const page1 = await context1.newPage();
  await page1.goto('/resource/1/edit');
  await page1.fill('input[name="field"]', 'User1_Value');
  await page1.click('button:has-text("Save")');

  const context2 = await browser.newContext();
  const page2 = await context2.newPage();
  await page2.goto('/resource/1/edit');
  await page2.fill('input[name="field"]', 'User2_Value');
  await page2.click('button:has-text("Save")');

  // Assertions to check data consistency and error handling (e.g., version conflict message or final state)
});
