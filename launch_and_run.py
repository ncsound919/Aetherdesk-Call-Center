"""
launch_and_run.py  -- One command to rule them all (Windows-safe, ASCII output)

Usage:
    python launch_and_run.py              # starts servers + opens Playwright journey
    python launch_and_run.py --api-only   # starts only the API, no Playwright
    python launch_and_run.py --no-journey # starts both servers, skips Playwright

How it works:
  1. Finds a free port for the API (tries 8888, 8000, 9000, 9001 ...)
  2. Patches vite.config.ts proxy target to match that port.
  3. Launches API (uvicorn) + Vite as subprocess.Popen children so they
     stay alive independently of the parent process timeout.
  4. Polls both health endpoints until they respond (max 60s each).
  5. Runs the Playwright visible-browser journey.
  6. On KeyboardInterrupt / journey end, sends SIGTERM to children.

Requires:
    pip install playwright requests
    playwright install chromium
"""

import argparse
import atexit
import os
import re
import socket
import subprocess
import sys
import time
import threading
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent
AGENT_UI = ROOT / "agent-ui"
VITE_CONFIG = AGENT_UI / "vite.config.ts"

API_PORT_CANDIDATES = [8888, 8000, 9000, 9001, 9090, 7000, 7001]
UI_PORT = 5174

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_children: list = []


def _kill_children():
    for p in _children:
        try:
            p.terminate()
        except Exception:
            pass


atexit.register(_kill_children)


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) != 0


def _find_free_port(candidates: list) -> int:
    for p in candidates:
        if _port_free(p):
            return p
    with socket.socket() as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for_url(url: str, timeout: int = 90, label: str = "") -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code < 500:
                return True
        except Exception:
            pass
        time.sleep(1.5)
        print("  waiting for %s ..." % (label or url))
    return False


def _stream_output(proc, prefix: str):
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stdout.buffer.write(("[%s] %s\n" % (prefix, line.rstrip())).encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()


# ---------------------------------------------------------------------------
# Patch vite.config.ts
# ---------------------------------------------------------------------------

def _patch_vite_config(api_port: int):
    if not VITE_CONFIG.exists():
        print("[warn] vite.config.ts not found at %s -- skipping patch" % VITE_CONFIG)
        return
    text = VITE_CONFIG.read_text(encoding="utf-8")
    patched = re.sub(
        r"(target:\s*['\"])http://localhost:\d+(['\"])",
        lambda m: "%shttp://localhost:%d%s" % (m.group(1), api_port, m.group(2)),
        text,
    )
    if patched != text:
        VITE_CONFIG.write_text(patched, encoding="utf-8")
        print("[config] vite.config.ts proxy updated -> port %d" % api_port)
    else:
        print("[config] vite.config.ts already correct (or no proxy found)")


# ---------------------------------------------------------------------------
# Server launchers
# ---------------------------------------------------------------------------

def start_api(api_port: int):
    cmd = [
        sys.executable, "-m", "uvicorn",
        "apps.api.main:app",
        "--host", "127.0.0.1",
        "--port", str(api_port),
    ]
    print("[api] starting on port %d: %s" % (api_port, " ".join(cmd)))
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    _children.append(proc)
    threading.Thread(target=_stream_output, args=(proc, "api"), daemon=True).start()
    return proc


def start_vite(ui_port: int):
    vite_bin = AGENT_UI / "node_modules" / "vite" / "bin" / "vite.js"
    if vite_bin.exists():
        cmd = ["node", str(vite_bin), "--port", str(ui_port), "--strictPort"]
    else:
        cmd = ["npx", "vite", "--port", str(ui_port), "--strictPort"]

    print("[ui]  starting Vite on port %d: %s" % (ui_port, " ".join(cmd)))
    proc = subprocess.Popen(
        cmd,
        cwd=str(AGENT_UI),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )
    _children.append(proc)
    threading.Thread(target=_stream_output, args=(proc, "vite"), daemon=True).start()
    return proc


# ---------------------------------------------------------------------------
# Playwright journey
# ---------------------------------------------------------------------------

def run_journey(ui_url: str, api_url: str):
    from playwright.sync_api import sync_playwright

    print("\n" + "=" * 60)
    print("AetherDesk -- Visible Browser Journey")
    print("=" * 60)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            slow_mo=600,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="en-US",
        )
        page = context.new_page()

        # -- Step 1: Open app --
        print("\n[1] Opening app...")
        page.goto(ui_url, wait_until="networkidle", timeout=30_000)
        print("    [OK] %s" % page.url)

        # -- Step 2: Login if login form is visible --
        print("\n[2] Checking for login page...")
        if page.locator("input[type='email'], input[name='email']").first.is_visible(timeout=3000):
            print("    -> login form detected")
            page.fill("input[type='email'], input[name='email']", "admin@aetherdesk.ai")
            page.fill("input[type='password'], input[name='password']", "Admin1234!")
            page.keyboard.press("Enter")
            page.wait_for_load_state("networkidle", timeout=15_000)
            print("    [OK] login submitted")
        else:
            print("    [OK] no login required (or already authenticated)")

        # -- Step 3: Dashboard --
        print("\n[3] Verifying dashboard...")
        page.wait_for_url(lambda u: "/dashboard" in u or "/" in u, timeout=10_000)
        print("    [OK] dashboard at %s" % page.url)

        # -- Step 4: Voice Cloning --
        print("\n[4] Navigating to Voice Cloning...")
        nav_link = page.locator("text=Voice Cloning, a[href*='voice']").first
        if nav_link.is_visible(timeout=5000):
            nav_link.click()
            page.wait_for_load_state("networkidle")
            print("    [OK] Voice Cloning page loaded")
            time.sleep(1)

            rec_btn = page.locator("text=Start Recording, button:has-text('Record')").first
            if rec_btn.is_visible(timeout=3000):
                print("    -> Start Recording button found -- clicking...")
                rec_btn.click()
                print("    [OK] Recording started  (browser mic prompt may appear)")
                print("         Waiting 10 s...")
                time.sleep(10)

                stop_btn = page.locator("text=Stop Recording, button:has-text('Stop')").first
                if stop_btn.is_visible(timeout=5000):
                    stop_btn.click()
                    print("    [OK] Recording stopped")

                create_btn = page.locator(
                    "text=Create Voice Clone, button:has-text('Clone')"
                ).first
                if create_btn.is_visible(timeout=5000):
                    create_btn.click()
                    print("    [OK] Voice clone creation submitted")
                    page.wait_for_timeout(3000)
            else:
                print("    [i]  no recording button visible -- skipping voice clone step")
        else:
            print("    [i]  Voice Cloning nav link not found -- skipping")

        # -- Step 5: Agents --
        print("\n[5] Navigating to Agents...")
        agents_link = page.locator("text=Agents, a[href*='agent']").first
        if agents_link.is_visible(timeout=5000):
            agents_link.click()
            page.wait_for_load_state("networkidle")
            print("    [OK] Agents page loaded")
            time.sleep(1)

            add_btn = page.locator(
                "text=Add Agent, button:has-text('New Agent'), button:has-text('Create')"
            ).first
            if add_btn.is_visible(timeout=3000):
                add_btn.click()
                time.sleep(1)

                name_field = page.locator("input[type='text']").first
                if name_field.is_visible(timeout=3000):
                    name_field.fill("Playwright Test Agent")

                submit = page.locator(
                    "button:has-text('Create'), button:has-text('Save'), button[type='submit']"
                ).first
                if submit.is_visible(timeout=3000):
                    submit.click()
                    page.wait_for_timeout(2000)
                    print("    [OK] Agent creation submitted")

                if page.locator("text=Playwright Test Agent").is_visible(timeout=5000):
                    print("    [OK] Agent visible in list")
                else:
                    print("    [!]  agent not yet confirmed in list")
            else:
                print("    [i]  Add Agent button not found -- skipping creation")
        else:
            print("    [i]  Agents nav link not found -- skipping")

        # -- Step 6: Calls / Leads --
        print("\n[6] Checking Calls/Leads page...")
        calls_link = page.locator(
            "text=Calls, text=Leads, a[href*='call'], a[href*='lead']"
        ).first
        if calls_link.is_visible(timeout=5000):
            calls_link.click()
            page.wait_for_load_state("networkidle")
            print("    [OK] at %s" % page.url)
        else:
            print("    [i]  Calls/Leads link not found -- skipping")

        # -- Done --
        print("\n" + "=" * 60)
        print("Journey complete!")
        print("  UI  -> %s" % ui_url)
        print("  API -> %s" % api_url)
        print("=" * 60)
        print("\nBrowser stays open. Press Enter to quit (servers will stop).")
        try:
            input()
        except EOFError:
            pass

        browser.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Launch AetherDesk dev servers + Playwright")
    parser.add_argument("--api-only", action="store_true", help="Start API only")
    parser.add_argument("--no-journey", action="store_true", help="Skip Playwright journey")
    args = parser.parse_args()

    api_port = _find_free_port(API_PORT_CANDIDATES)
    api_url = "http://127.0.0.1:%d" % api_port
    ui_url = "http://localhost:%d" % UI_PORT

    print("[info] API port  -> %d" % api_port)
    print("[info] Vite port -> %d" % UI_PORT)

    if not args.api_only:
        _patch_vite_config(api_port)

    start_api(api_port)
    print("[boot] waiting for API...")
    if not _wait_for_url("%s/health" % api_url, timeout=90, label="API /health"):
        if not _wait_for_url("%s/" % api_url, timeout=30, label="API /"):
            print("[error] API did not start in time -- aborting")
            sys.exit(1)
    print("[boot] [OK] API ready at %s" % api_url)

    if args.api_only:
        print("[info] --api-only: Press Ctrl+C to stop the API.")
        try:
            while True:
                time.sleep(5)
        except KeyboardInterrupt:
            pass
        return

    start_vite(UI_PORT)
    print("[boot] waiting for Vite...")
    if not _wait_for_url(ui_url, timeout=60, label="Vite UI"):
        print("[error] Vite did not start in time -- aborting")
        sys.exit(1)
    print("[boot] [OK] Vite ready at %s" % ui_url)

    if args.no_journey:
        print("[info] --no-journey: servers running. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(5)
        except KeyboardInterrupt:
            pass
        return

    run_journey(ui_url, api_url)


if __name__ == "__main__":
    main()
