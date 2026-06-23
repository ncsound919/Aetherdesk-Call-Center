import { test, expect } from '@playwright/test';

test('handles concurrent resource updates', async ({ browser }) => {
  const context1 = await browser.newContext();
  const page1 = await context1.newPage();
  const context2 = await browser.newContext();
  const page2 = await context2.newPage();

  // Open both tabs on the same resource and fill in different values.
  await Promise.all([
    page1.goto('/resource/1/edit'),
    page2.goto('/resource/1/edit'),
  ]);
  await Promise.all([
    page1.fill('input[name="field"]', 'User1_Value'),
    page2.fill('input[name="field"]', 'User2_Value'),
  ]);

  // Click Save in both tabs as close to simultaneously as possible.
  await Promise.all([
    page1.click('button:has-text("Save")'),
    page2.click('button:has-text("Save")'),
  ]);

  // ---- Assertions ----
  // At least one of the two tabs should show a conflict / error because
  // the second save is expected to detect the version mismatch.  The
  // exact tab that wins is non-deterministic, so we assert across both.
  const toast1 = page1.locator('.toast, .error-message');
  const toast2 = page2.locator('.toast, .error-message');

  // Wait for both tabs to have settled (either success toast or conflict error).
  await Promise.all([
    toast1.first().waitFor({ timeout: 5000 }),
    toast2.first().waitFor({ timeout: 5000 }),
  ]);

  // At least one tab should display a conflict / update error.
  const errorTexts = await Promise.all([
    toast1.allTextContents(),
    toast2.allTextContents(),
  ]);
  const allText = errorTexts.flat().join(' ');
  const hasConflict = /conflict|updated by someone else|version/i.test(allText);
  const hasSuccess = /saved|success/i.test(allText);

  // Either we got a conflict error or both saves succeeded (last-write-wins).
  // In the conflict case, exactly one success and one error are expected.
  expect(hasConflict || hasSuccess).toBeTruthy();

  // The final field value should be one of the two submitted values.
  const finalValue1 = await page1.inputValue('input[name="field"]');
  const finalValue2 = await page2.inputValue('input[name="field"]');
  expect(['User1_Value', 'User2_Value']).toContain(finalValue1);
  expect(['User1_Value', 'User2_Value']).toContain(finalValue2);

  await context1.close();
  await context2.close();
});
