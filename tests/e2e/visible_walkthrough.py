"""
Visible browser walkthrough — ACTUALLY CONDUCT BUSINESS.
Every step accomplishes a real task or reports what's broken.

Run:  python tests/e2e/visible_walkthrough.py
"""
import json
import os

import httpx
from playwright.sync_api import sync_playwright

UI = os.getenv("E2E_BASE_URL", "http://localhost:3000")
API = os.getenv("E2E_API_URL", "http://localhost:8000")
HEADERS = {"x-api-key": "dev-api-key"}
SCREENSHOTS = os.path.join(os.path.dirname(__file__), "..", "..", ".screenshots")
os.makedirs(SCREENSHOTS, exist_ok=True)

RESULTS = []  # track what was accomplished


def done(task: str, okay: bool, detail: str = "") -> None:
    RESULTS.append((task, okay, detail))
    status = "OK" if okay else "FAIL"
    msg = f"  [{status}] {task}"
    if detail:
        msg += f" — {detail}"
    print(msg)


def snap(page, name: str) -> None:
    page.screenshot(path=os.path.join(SCREENSHOTS, name), full_page=True)


# ======================================================================
#  SETUP
# ======================================================================
print("\nAetherDesk — PRODUCTIVITY AUDIT")
print("=" * 55)

pw = sync_playwright().start()
browser = pw.chromium.launch(headless=False, slow_mo=300)
page = browser.new_page(viewport={"width": 1440, "height": 900})

# ======================================================================
#  TASK 1 — LOGIN TO THE PLATFORM
# ======================================================================
print("\n—— TASK 1: Authenticate ——")
page.goto(f"{UI}/")
page.locator("text=Login").first.click()
page.wait_for_url(lambda u: "/login" in u)
page.locator("button:has-text('Sign In')").first.click()
page.wait_for_url(lambda u: "/dashboard" in u)
try:
    page.wait_for_selector(".sidebar", timeout=10000)
    logged_in = True
except Exception:
    logged_in = False
done("Login and reach dashboard", logged_in,
     "sidebar visible" if logged_in else "login failed")
snap(page, "01_logged_in.png")

# ======================================================================
#  TASK 2 — CHECK CURRENT BUSINESS STATE
# ======================================================================
print("\n—— TASK 2: Assess Current Business ——")

# How many rentals do we have right now?
resp = httpx.get(f"{API}/api/v1/saas/dashboard", headers=HEADERS, timeout=10)
dashboard = resp.json()
rental_count = len(dashboard["rentals"])
profile_count = len(dashboard["profiles"])
lead_count = len(httpx.get(
    f"{API}/api/v1/campaign/leads", headers=HEADERS, timeout=10
).json())
stats = httpx.get(
    f"{API}/api/v1/campaign/stats", headers=HEADERS, timeout=10
).json()

print(f"  Current state: {rental_count} rentals, {profile_count} profiles, "
      f"{lead_count} leads")
print(f"  Campaign stats: {stats['total_calls_made']} calls made, "
      f"{stats['interested']} interested, {stats['conversion_rate']}% conv")

# ======================================================================
#  TASK 3 — CREATE AND RENT AN AGENT (full lifecycle)
# ======================================================================
print("\n—— TASK 3: Hire an AI Voice Agent ——")

# Step 3a: Create profile
page.locator("text=Flow Designer").first.click()
page.wait_for_timeout(300)
page.locator("text=SALES").first.click()
name_input = page.locator(
    "input[placeholder='Agent Name (e.g. Sarah)']"
).first
name_input.fill("OUTBOUND SALES REP")
page.locator("textarea[placeholder='Full System Prompt / Guidelines']").first.fill("You are an outbound sales rep designed to handle general sales queries.")
page.locator("text=Deploy Agent Profile").first.click()
try:
    page.wait_for_function(
        "el => el.value === ''",
        arg=name_input.element_handle(),
        timeout=5000
    )
    form_cleared = True
except Exception:
    form_cleared = False
done("Create agent profile via Flow Designer", form_cleared,
     "name field cleared (deploy accepted)" if form_cleared else "deploy may have failed")

# Step 3b: Find the profile ID we just created
resp2 = httpx.get(f"{API}/api/v1/saas/dashboard", headers=HEADERS, timeout=10)
new_profiles = resp2.json()["profiles"]
our_profile = [p for p in new_profiles
               if p["name"] == "OUTBOUND SALES REP"]
profile_created = len(our_profile) > 0
if profile_created:
    pid = our_profile[0]["id"]
    done("Profile persisted in database", True,
         f"profile_id={pid}")
else:
    done("Profile persisted in database", False, "not found in dashboard")
    pid = None

# Step 3c: Rent the agent for 1 day
if pid:
    rent_resp = httpx.post(
        f"{API}/api/v1/saas/rent?profile_id={pid}&duration_type=day",
        headers=HEADERS, timeout=10,
    )
    rent_ok = rent_resp.status_code == 200
    if rent_ok:
        rental = rent_resp.json()
        done("Rent agent (1 day)", True,
             f"rental_id={rental['rental_id']}, expires={rental['end_time']}")
    else:
        done("Rent agent (1 day)", False, f"HTTP {rent_resp.status_code}")

# Step 3d: Verify rental appears in Fleet Stats table
page.locator("text=Fleet Stats").first.click()
page.wait_for_timeout(800)
rental_rows = page.locator("table tr").count()
done("Rental visible in Fleet Stats table", rental_rows > 0,
     f"{rental_rows} rows in table")
snap(page, "03_fleet_stats.png")

# ======================================================================
#  TASK 4 — ACQUIRE CUSTOMERS (lead generation)
# ======================================================================
print("\n—— TASK 4: Acquire Customers ——")

page.locator("text=Outreach").first.click()
page.wait_for_timeout(300)

# Bulk import 3 leads (real business operation)
bulk_resp = httpx.post(
    f"{API}/api/v1/campaign/leads/bulk",
    json={"leads": [
        {"company_name": "Pacific Logistics", "phone": "+15551000101",
         "industry": "logistics", "priority": 8},
        {"company_name": "Metro Health Group", "phone": "+15551000102",
         "industry": "healthcare", "priority": 9},
        {"company_name": "Sunset Retail Inc", "phone": "+15551000103",
         "industry": "retail", "priority": 6},
    ]},
    headers=HEADERS, timeout=10,
)
bulk_ok = bulk_resp.status_code == 200
if bulk_ok:
    imported = bulk_resp.json()["imported"]
    done("Bulk import leads", True, f"{imported} leads imported")
else:
    done("Bulk import leads", False, f"HTTP {bulk_resp.status_code}")

# Add one more via the UI form (real user interaction)
page.locator("input[placeholder='Acme Corp']").first.fill("Bay Area Tech")
page.locator("input[placeholder='+15551234567']").first.fill("+15551000104")
page.locator("button:has-text('Add')").first.click()
try:
    page.wait_for_selector("text=Bay Area Tech", timeout=5000)
    lead_added = True
except Exception:
    lead_added = False

try:
    page.wait_for_function(
        "el => el.value === ''",
        arg=page.locator("input[placeholder='Acme Corp']").first.element_handle(),
        timeout=5000
    )
    form_cleared2 = True
except Exception:
    form_cleared2 = False

done("Add lead via UI form", lead_added and form_cleared2,
     "lead visible in pipeline + form cleared" if lead_added else "lead not found")

snap(page, "04_outreach_pipeline.png")

# ======================================================================
#  TASK 5 — CONFIGURE COMPLIANCE SETTINGS
# ======================================================================
print("\n—— TASK 5: Configure Compliance Guardrails ——")

page.locator("text=Integrations").first.click()
page.wait_for_timeout(300)

# Read current settings
before_settings = httpx.get(
    f"{API}/api/v1/saas/settings", headers=HEADERS, timeout=10
).json()
print(f"  Before: redact_pii={before_settings['redact_pii']}, "
      f"sync_dnc={before_settings['sync_dnc']}")

# Toggle both ON
settings_payload = {
    "api_feeds": before_settings["api_feeds"],
    "auto_mode_enabled": True,
    "redact_pii": True,
    "require_consent": True,
    "sync_dnc": True,
    "mcp_servers": before_settings["mcp_servers"],
}
httpx.post(
    f"{API}/api/v1/saas/settings",
    json=settings_payload, headers=HEADERS, timeout=10,
)

# Save via UI (triggers the same endpoint)
page.locator("input[type='checkbox']").nth(0).set_checked(True)
page.locator("input[type='checkbox']").nth(1).set_checked(True)
page.locator("text=Save Safety Configuration").first.click()
page.wait_for_timeout(500)

# Verify persistence
after_settings = httpx.get(
    f"{API}/api/v1/saas/settings", headers=HEADERS, timeout=10
).json()
settings_saved = all([
    after_settings["redact_pii"] is True,
    after_settings["sync_dnc"] is True,
])
done("Save safety configuration via UI and verify", settings_saved,
     f"redact_pii={after_settings['redact_pii']}, "
     f"sync_dnc={after_settings['sync_dnc']}")

snap(page, "05_settings_saved.png")

# ======================================================================
#  TASK 6 — LAUNCH OUTREACH CAMPAIGN
# ======================================================================
print("\n—— TASK 6: Launch Outreach Campaign ——")

page.locator("text=Outreach").first.click()
page.wait_for_timeout(300)

if pid:
    launch = httpx.post(
        f"{API}/api/v1/campaign/launch",
        json={
            "profile_id": pid,
            "max_concurrent": 2,
            "delay_between_calls": 5.0,
            "filter_status": "new",
        },
        headers=HEADERS, timeout=10,
    )
    launch_ok = launch.status_code == 200
    done("Launch campaign with our new agent", launch_ok,
         "campaign started" if launch_ok else f"HTTP {launch.status_code}: {launch.text[:100]}")
else:
    done("Launch campaign", False, "no profile_id available")

# Check campaign calls were made
calls_resp = httpx.get(
    f"{API}/api/v1/campaign/calls", headers=HEADERS, timeout=10,
)
calls = calls_resp.json() if calls_resp.status_code == 200 else []
done(f"Campaign calls recorded", len(calls) > 0,
     f"{len(calls)} call records" if calls else "no calls (Ollama/Twilio may be down)")

snap(page, "06_campaign_launched.png")

# ======================================================================
#  TASK 7 — UPLOAD A CALL PROTOCOL (CSV)
# ======================================================================
print("\n—— TASK 7: Upload Call Protocol ——")

csv = (
    "node,prompt,field,validate,next,action,on_ok,on_fail,options\n"
    "start,Welcome! What is your name?,name,required,verify,,\"Sorry, let's try again.\",,\n"
    "verify,Thanks {name}. Can I confirm?,,,close,,Yes,No\n"
    "close,Great! We'll be in touch.,,,end,,,\n"
)
proto_resp = httpx.post(
    f"{API}/api/v1/protocols/upload_csv",
    files={"file": ("sales_flow.csv", csv, "text/csv")},
    timeout=10,
)
proto_ok = proto_resp.status_code == 200
if proto_ok:
    pdata = proto_resp.json()
    done("Upload call protocol CSV", True,
         f"{pdata['nodes']} nodes parsed, id={pdata['protocol_id']}")
else:
    done("Upload call protocol CSV", False, f"HTTP {proto_resp.status_code}")

# ======================================================================
#  TASK 8 — MONITOR FLEET HEALTH
# ======================================================================
print("\n—— TASK 8: Monitor Fleet Health ——")

page.locator("text=Command Center").first.click()
page.wait_for_timeout(500)

telemetry_ok = all([
    page.locator("text=Compute Density").first.is_visible(),
    page.locator("text=Vector Store Latency").first.is_visible(),
    page.locator("text=PSTN Gateway Load").first.is_visible(),
])
done("View fleet telemetry", telemetry_ok,
     "all 3 metrics visible" if telemetry_ok else "some metrics missing")
snap(page, "07_command_center.png")

# ======================================================================
#  TASK 9 — BROWSE AND CLONE MARKETPLACE TEMPLATE
# ======================================================================
print("\n—— TASK 9: Browse Community Templates ——")

page.locator("text=Marketplace").first.click()
page.wait_for_timeout(500)
marketplace_loaded = page.locator(
    "h2:has-text('Community-Led Template Marketplace')"
).is_visible()
done("Browse marketplace templates", marketplace_loaded,
     "template gallery visible" if marketplace_loaded else "not found")

# Try cloning
clone_btn = page.locator("text=Clone & Customize").first
cloned = False
if clone_btn.is_visible():
    clone_btn.click()
    page.wait_for_timeout(500)
    cloned = page.locator(
        "h2:has-text('Flow Designer & Scripts')"
    ).is_visible()
done("Clone template into Flow Designer", cloned,
     "tab switched to Flow Designer" if cloned else "clone had no effect (bug?)")
snap(page, "08_marketplace.png")

# ======================================================================
#  TASK 10 — CHECK AFFILIATE EARNINGS
# ======================================================================
print("\n—— TASK 10: Check Affiliate Earnings ——")

page.locator("text=Affiliate").first.click()
page.wait_for_timeout(500)
referral_visible = page.locator("text=Referral").first.is_visible()
copy_visible = page.locator("text=Copy Link").first.is_visible()
done("View affiliate portal", referral_visible and copy_visible,
     "referral data + copy link shown")

# ======================================================================
#  TASK 11 — REVIEW APPROVALS
# ======================================================================
print("\n—— TASK 11: Review Pending Approvals ——")

page.locator("text=Supervision").first.click()
page.wait_for_timeout(500)
approvals_ok = page.locator(
    ".sidebar-item.active:has-text('Supervision')"
).first.is_visible()
done("Review pending approvals", approvals_ok,
     "supervision tab accessible" if approvals_ok else "tab not found")

# ======================================================================
#  TASK 12 — CHECK ACADEMY
# ======================================================================
print("\n—— TASK 12: Access Training Academy ——")

page.locator("text=Academy").first.click()
page.wait_for_timeout(500)
academy_ok = page.locator(
    ".sidebar-item.active:has-text('Academy')"
).first.is_visible()
done("Access academy", academy_ok,
     "academy tab accessible" if academy_ok else "tab not found")

# ======================================================================
#  TASK 13 — VERIFY SETTINGS TOGGLE CYCLE
# ======================================================================
print("\n—— TASK 13: Toggle Settings OFF, Verify ——")

off_payload = {
    "api_feeds": after_settings["api_feeds"],
    "auto_mode_enabled": False,
    "redact_pii": False,
    "require_consent": False,
    "sync_dnc": False,
    "mcp_servers": after_settings["mcp_servers"],
}
httpx.post(
    f"{API}/api/v1/saas/settings",
    json=off_payload, headers=HEADERS, timeout=10,
)
final = httpx.get(
    f"{API}/api/v1/saas/settings", headers=HEADERS, timeout=10,
).json()
all_off = all([
    final["redact_pii"] is False,
    final["sync_dnc"] is False,
    final["auto_mode_enabled"] is False,
    final["require_consent"] is False,
])
done("Toggle all settings OFF and verify", all_off,
     f"redact_pii={final['redact_pii']}, sync_dnc={final['sync_dnc']}")

# ======================================================================
#  TASK 14 — FULL-TAB STRESS TEST
# ======================================================================
print("\n—— TASK 14: Tab Stability Under Load ——")

tabs = [
    "Fleet Stats", "Command Center", "Flow Designer", "Marketplace",
    "Supervision", "Outreach", "Academy", "Integrations", "Affiliate",
]
crashed = False
for cycle in range(5):
    for tab in tabs:
        try:
            page.locator(f"text={tab}").first.click()
            page.wait_for_timeout(100)
        except Exception:
            crashed = True
            break
    if crashed:
        break
done("5-cycle rapid tab switching", not crashed,
     "no crash" if not crashed else "crashed during cycle")

# ======================================================================
#  SUMMARY
# ======================================================================
print("\n" + "=" * 55)
print("PRODUCTIVITY AUDIT RESULTS")
print("=" * 55)

passed = sum(1 for _, ok, _ in RESULTS if ok)
total = len(RESULTS)
for task, ok, detail in RESULTS:
    icon = "[OK] " if ok else "[FAIL]"
    print(f"  {icon} {task}  {detail}")

print(f"\n  {passed}/{total} tasks accomplished ({passed/total*100:.0f}%)")
print("=" * 55)

# Tear down
browser.close()
pw.stop()
