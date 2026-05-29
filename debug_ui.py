import asyncio
from playwright.sync_api import sync_playwright

def main():
    with sync_playwright() as p:
        # Launch browser in headed mode so we can see what happens
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check"
            ]
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        print("1. Going to UI at http://127.0.0.1:3001/")
        try:
            page.goto("http://127.0.0.1:3001/", wait_until="domcontentloaded", timeout=10000)
            print(f"   Title: {page.title()}")
            print(f"   URL: {page.url}")
            page.screenshot(path=".screenshots/ui_page.png", full_page=True)
            print("   Screenshot saved to .screenshots/ui_page.png")
        except Exception as e:
            print(f"   Error loading UI: {e}")
            page.screenshot(path=".screenshots/ui_error.png", full_page=True)

        print("\n2. Checking if API is reachable")
        try:
            page.goto("http://127.0.0.1:8000/health", wait_until="domcontentloaded", timeout=10000)
            print(f"   Title: {page.title()}")
            print(f"   URL: {page.url}")
            content = page.content()
            print(f"   Response: {content[:500]}")
        except Exception as e:
            print(f"   Error loading API: {e}")

        print("\n3. Checking if dev server is running on port 3001")
        try:
            page.goto("http://127.0.0.1:3001/", wait_until="networkidle", timeout=5000)
            print(f"   Title: {page.title()}")
        except Exception as e:
            print(f"   Error: {e}")

        print("\n4. Trying localhost instead")
        try:
            page.goto("http://localhost:3001/", wait_until="networkidle", timeout=5000)
            print(f"   Title: {page.title()}")
            page.screenshot(path=".screenshots/ui_localhost.png", full_page=True)
        except Exception as e:
            print(f"   Error: {e}")

        input("Press Enter to close browser...")
        browser.close()

if __name__ == "__main__":
    main()