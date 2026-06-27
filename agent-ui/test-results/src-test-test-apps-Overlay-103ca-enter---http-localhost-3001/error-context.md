# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: src\test\test-apps.spec.ts >> Overlay365 Apps - User Perspective >> AetherDesk Call Center - http://localhost:3001
- Location: src\test\test-apps.spec.ts:4:3

# Error details

```
Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:3001/
Call log:
  - navigating to "http://localhost:3001/", waiting until "networkidle"

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - generic [ref=e6]:
    - heading "This site can’t be reached" [level=1] [ref=e7]
    - paragraph [ref=e8]:
      - strong [ref=e9]: localhost
      - text: refused to connect.
    - generic [ref=e10]:
      - paragraph [ref=e11]: "Try:"
      - list [ref=e12]:
        - listitem [ref=e13]: Checking the connection
        - listitem [ref=e14]:
          - link "Checking the proxy and the firewall" [ref=e15] [cursor=pointer]:
            - /url: "#buttons"
    - generic [ref=e16]: ERR_CONNECTION_REFUSED
  - generic [ref=e17]:
    - button "Reload" [ref=e19] [cursor=pointer]
    - button "Details" [ref=e20] [cursor=pointer]
```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | test.describe('Overlay365 Apps - User Perspective', () => {
  4  |   test('AetherDesk Call Center - http://localhost:3001', async ({ page }) => {
> 5  |     await page.goto('http://localhost:3001', { waitUntil: 'networkidle', timeout: 30000 });
     |                ^ Error: page.goto: net::ERR_CONNECTION_REFUSED at http://localhost:3001/
  6  |     await page.screenshot({ path: 'aetherdesk-home.png', fullPage: true });
  7  |     console.log('AetherDesk title:', await page.title());
  8  |     console.log('AetherDesk URL:', page.url());
  9  |   });
  10 | 
  11 |   test('BlockLabor - http://localhost:3000', async ({ page }) => {
  12 |     await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 30000 });
  13 |     await page.screenshot({ path: 'blocklabor-home.png', fullPage: true });
  14 |     console.log('BlockLabor title:', await page.title());
  15 |     console.log('BlockLabor URL:', page.url());
  16 |   });
  17 | 
  18 |   test('JobClaw - http://localhost:3002', async ({ page }) => {
  19 |     await page.goto('http://localhost:3002', { waitUntil: 'networkidle', timeout: 30000 });
  20 |     await page.screenshot({ path: 'jobclaw-home.png', fullPage: true });
  21 |     console.log('JobClaw title:', await page.title());
  22 |     console.log('JobClaw URL:', page.url());
  23 |   });
  24 | 
  25 |   test('Landing Page - file://overlay-365-landing/index.html', async ({ page }) => {
  26 |     await page.goto('file:///C:/Users/User/Desktop/Overlay365/overlay-365-landing/index.html', { waitUntil: 'networkidle', timeout: 30000 });
  27 |     await page.screenshot({ path: 'landing-page.png', fullPage: true });
  28 |     console.log('Landing Page title:', await page.title());
  29 |     console.log('Landing Page URL:', page.url());
  30 |   });
  31 | });
```