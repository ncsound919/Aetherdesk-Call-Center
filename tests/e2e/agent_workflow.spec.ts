import { test, expect } from '@playwright/test';

test('user interacts with default agent', async ({ page }) => {
  await page.goto('/agent');

  // Send a message to the agent.
  await page.fill('input[name="message"]', 'Hello, agent');
  await page.click('button:has-text("Send")');

  // The agent should render a response.  Common selectors for chat UIs:
  // a message list, a response bubble, or a container with the reply.
  // We wait for any new text to appear that was not in the initial DOM.
  const responseLocator = page.locator(
    '[data-testid="agent-response"], .chat-message, .agent-reply, .response'
  );
  await expect(responseLocator.first()).toBeVisible({ timeout: 10000 });

  // The response should contain some text (not be empty).
  const text = await responseLocator.first().textContent();
  expect(text).toBeTruthy();
  expect(text!.length).toBeGreaterThan(0);
});
