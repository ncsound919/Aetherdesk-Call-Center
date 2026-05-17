"""
voice_recording_journey.py

Run via the top-level launcher (recommended):
    python launch_and_run.py

Or standalone if servers are already up:
    python tests/e2e/voice_recording_journey.py

Defaults to UI on http://localhost:5174 and API on http://localhost:8888.
Override via env vars:
    UI_URL=http://localhost:5174  API_URL=http://localhost:8888
"""

import os
import time

UI_URL = os.environ.get("UI_URL", "http://localhost:5174")
API_URL = os.environ.get("API_URL", "http://localhost:8888")


def main():
    from playwright.sync_api import sync_playwright

    print("=" * 60)
    print("AetherDesk Voice Recording Journey")
    print(f"UI  → {UI_URL}")
    print(f"API → {API_URL}")
    print("=" * 60)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            slow_mo=500,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        page = context.new_page()

        # ── 1 · Open app ────────────────────────────────────────────────────
        print("\n[1/6] Opening app…")
        page.goto(UI_URL, wait_until="networkidle", timeout=30_000)
        print(f"      ✓ {page.url}")

        # ── 2 · Login if needed ──────────────────────────────────────────────
        print("\n[2/6] Login check…")
        email_sel = "input[type='email'], input[name='email']"
        if page.locator(email_sel).first.is_visible(timeout=3000):
            page.fill(email_sel, "admin@aetherdesk.ai")
            page.fill("input[type='password'], input[name='password']", "Admin1234!")
            page.keyboard.press("Enter")
            page.wait_for_load_state("networkidle", timeout=15_000)
            print("      ✓ logged in")
        else:
            print("      ✓ already authenticated")

        # ── 3 · Voice Cloning ───────────────────────────────────────────────
        print("\n[3/6] Voice Cloning…")
        vc_link = page.locator("text=Voice Cloning, a[href*='voice']").first
        if vc_link.is_visible(timeout=5000):
            vc_link.click()
            page.wait_for_load_state("networkidle")
            time.sleep(1)

            rec_btn = page.locator(
                "button:has-text('Start Recording'), button:has-text('Record')"
            ).first
            if rec_btn.is_visible(timeout=3000):
                rec_btn.click()
                print("      ✓ recording started — waiting 12 s (speak now)")
                time.sleep(12)

                stop = page.locator(
                    "button:has-text('Stop Recording'), button:has-text('Stop')"
                ).first
                if stop.is_visible(timeout=5000):
                    stop.click()
                    print("      ✓ recording stopped")

                clone_btn = page.locator(
                    "button:has-text('Create Voice Clone'), button:has-text('Clone')"
                ).first
                if clone_btn.is_visible(timeout=5000):
                    clone_btn.click()
                    print("      ✓ clone submitted")
                    page.wait_for_timeout(3000)
                    if page.locator("text=Voice Cloned Successfully").is_visible(timeout=6000):
                        print("      ✓ clone SUCCESS")
                    else:
                        print("      ⚠  success toast not seen")
            else:
                print("      ℹ  no recording button — skipping")
        else:
            print("      ℹ  Voice Cloning nav not found — skipping")

        # ── 4 · Agents ───────────────────────────────────────────────────────
        print("\n[4/6] Agents page…")
        agents = page.locator("text=Agents, a[href*='agent']").first
        if agents.is_visible(timeout=5000):
            agents.click()
            page.wait_for_load_state("networkidle")
            time.sleep(1)

            add = page.locator(
                "text=Add Agent, button:has-text('New Agent'), button:has-text('Create Agent')"
            ).first
            if add.is_visible(timeout=3000):
                add.click()
                time.sleep(1)
                name_field = page.locator("input[type='text']").first
                if name_field.is_visible(timeout=3000):
                    name_field.fill("Voice Journey Agent")

                # Try to pick the cloned voice from a dropdown
                voice_drop = page.locator("select, [data-testid='voice-select']").first
                if voice_drop.is_visible(timeout=2000):
                    voice_drop.select_option(index=1)  # first non-default
                    print("      ✓ voice selected")

                submit = page.locator(
                    "button[type='submit'], button:has-text('Create'), button:has-text('Save')"
                ).first
                if submit.is_visible(timeout=3000):
                    submit.click()
                    page.wait_for_timeout(2000)
                    print("      ✓ agent submitted")

                if page.locator("text=Voice Journey Agent").is_visible(timeout=6000):
                    print("      ✓ agent confirmed in list")
                else:
                    print("      ⚠  agent not yet in list")
            else:
                print("      ℹ  Add Agent button not found")
        else:
            print("      ℹ  Agents nav not found — skipping")

        # ── 5 · Dashboard KPIs ───────────────────────────────────────────────
        print("\n[5/6] Dashboard…")
        dash = page.locator("text=Dashboard, a[href*='dashboard']").first
        if dash.is_visible(timeout=5000):
            dash.click()
            page.wait_for_load_state("networkidle")
            print(f"      ✓ {page.url}")
        else:
            print("      ℹ  Dashboard nav not found")

        # ── 6 · Done ─────────────────────────────────────────────────────────
        print("\n[6/6] Journey done!")
        print("      Browser stays open. Press Enter to close…")
        try:
            input()
        except EOFError:
            pass

        browser.close()


if __name__ == "__main__":
    main()
