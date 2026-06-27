import { test, expect } from '@playwright/test';

test.describe('Overlay365 Apps - User Perspective', () => {
  test('AetherDesk Call Center - http://localhost:3001', async ({ page }) => {
    await page.goto('http://localhost:3001', { waitUntil: 'networkidle', timeout: 30000 });
    await page.screenshot({ path: 'aetherdesk-home.png', fullPage: true });
    console.log('AetherDesk title:', await page.title());
    console.log('AetherDesk URL:', page.url());
  });

  test('BlockLabor - http://localhost:3000', async ({ page }) => {
    await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 30000 });
    await page.screenshot({ path: 'blocklabor-home.png', fullPage: true });
    console.log('BlockLabor title:', await page.title());
    console.log('BlockLabor URL:', page.url());
  });

  test('JobClaw - http://localhost:3002', async ({ page }) => {
    await page.goto('http://localhost:3002', { waitUntil: 'networkidle', timeout: 30000 });
    await page.screenshot({ path: 'jobclaw-home.png', fullPage: true });
    console.log('JobClaw title:', await page.title());
    console.log('JobClaw URL:', page.url());
  });

  test('Landing Page - file://overlay-365-landing/index.html', async ({ page }) => {
    await page.goto('file:///C:/Users/User/Desktop/Overlay365/overlay-365-landing/index.html', { waitUntil: 'networkidle', timeout: 30000 });
    await page.screenshot({ path: 'landing-page.png', fullPage: true });
    console.log('Landing Page title:', await page.title());
    console.log('Landing Page URL:', page.url());
  });
});