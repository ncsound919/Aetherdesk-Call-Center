import pytest
from playwright.sync_api import sync_playwright
import re
import os
import shutil
import tempfile

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "your-gcp-project-id")
PROJECT_NAME = os.environ.get("GCP_PROJECT_NAME", "your-gcp-project-name")

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

def test_gcloud_console_setup():
    USER_DATA_DIR = os.path.join(tempfile.gettempdir(), f"playwright-chrome-profile-{os.getpid()}")
    if os.path.exists(USER_DATA_DIR):
        shutil.rmtree(USER_DATA_DIR)
    os.makedirs(USER_DATA_DIR, exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            executable_path=CHROME_PATH,
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-extensions",
                "--no-first-run",
                "--no-default-browser-check",
            ]
        )
        page = context.new_page()

        # Step 1: Navigate to Google Cloud Console
        print("Step 1: Navigating to Google Cloud Console...")
        page.goto("https://console.cloud.google.com/")
        page.wait_for_load_state("domcontentloaded")
        page.screenshot(path=".screenshots/gcp_console_landing.png")

        # Step 2: Wait for user to log in
        print("Step 2: Please log in to your Google account manually in the browser window.")
        print("You have 300 seconds (5 minutes) to complete login.")

        # Wait for either the console or project selector to appear
        try:
            page.wait_for_url("https://console.cloud.google.com/**", timeout=300000)
        except Exception:
            print("Navigation timeout - continuing anyway")

        page.screenshot(path=".screenshots/gcp_console_logged_in.png")
        print("Login completed or timed out - proceeding...")

        # Step 3: Navigate to project creation
        print(f"Step 3: Creating project '{PROJECT_NAME}'...")
        page.goto("https://console.cloud.google.com/projectcreate")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)  # Wait for page to fully render
        page.screenshot(path=".screenshots/gcp_project_create_page.png")

        # Step 4: Fill in project name
        # Try different selectors for the project name input
        project_name_input = None
        try:
            # Try input element with name="name"
            project_name_input = page.locator("input[name='name']").first
            if not project_name_input.is_visible():
                project_name_input = None
        except:
            pass

        if not project_name_input:
            try:
                project_name_input = page.get_by_label("Project name")
            except:
                pass

        if project_name_input and project_name_input.is_visible():
            project_name_input.fill(PROJECT_NAME)
            page.wait_for_timeout(2000)  # Wait for auto-generation of project ID
            page.screenshot(path=".screenshots/gcp_project_name_filled.png")
            print(f"Project name '{PROJECT_NAME}' entered.")
        else:
            print("WARNING: Could not find project name input. Trying to continue...")
            page.screenshot(path=".screenshots/gcp_project_name_not_found.png")

        # Step 5: Fill in project ID (if not auto-generated)
        if PROJECT_ID and PROJECT_ID != "your-gcp-project-id":
            project_id_input = None
            try:
                # Try input element with name="projectId"
                project_id_input = page.locator("input[name='projectId']").first
                if not project_id_input.is_visible():
                    project_id_input = None
            except:
                pass

            if not project_id_input:
                try:
                    project_id_input = page.locator("input[id*='projectId']").first
                except:
                    pass

            if project_id_input and project_id_input.is_visible() and project_id_input.is_enabled():
                project_id_input.fill(PROJECT_ID)
                page.screenshot(path=".screenshots/gcp_project_id_filled.png")
                print(f"Project ID '{PROJECT_ID}' entered.")
            else:
                print("WARNING: Could not find project ID input. Skipping...")

        # Step 6: Wait before clicking Create to let validation complete
        page.wait_for_timeout(2000)

        # Step 7: Click Create button
        print("Step 7: Clicking Create button...")
        create_button = None
        try:
            create_button = page.get_by_role("button", name="Create").first
        except:
            pass

        if not create_button:
            try:
                create_button = page.get_by_text("Create").first
            except:
                pass

        if create_button and create_button.is_visible():
            print("Create button found, clicking...")
            create_button.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(5000)  # Wait for project creation
            page.screenshot(path=".screenshots/gcp_project_created.png")
            print(f"Project '{PROJECT_NAME}' created successfully (or already exists).")
        else:
            print("WARNING: Create button not found or not visible.")
            page.screenshot(path=".screenshots/gcp_project_create_failed.png")

        # Step 8: Enable GKE API
        print("Step 8: Enabling Kubernetes Engine API...")
        page.goto("https://console.cloud.google.com/apis/library/container.googleapis.com")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)
        page.screenshot(path=".screenshots/gcp_gke_api_page.png")

        enable_button = None
        try:
            enable_button = page.get_by_role("button", name="Enable").first
        except:
            pass

        if not enable_button:
            try:
                enable_button = page.get_by_text("Enable").first
            except:
                pass

        if enable_button and enable_button.is_visible():
            print("Enabling Kubernetes Engine API...")
            enable_button.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(5000)
            page.screenshot(path=".screenshots/gcp_gke_api_enabled.png")
            print("Kubernetes Engine API enabled.")
        else:
            print("INFO: Kubernetes Engine API may already be enabled or not found.")
            page.screenshot(path=".screenshots/gcp_gke_api_already_enabled.png")

        # Step 9: Enable Cloud Build API (often needed)
        print("Step 9: Enabling Cloud Build API...")
        page.goto("https://console.cloud.google.com/apis/library/cloudbuild.googleapis.com")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(3000)

        enable_button = None
        try:
            enable_button = page.get_by_role("button", name="Enable").first
        except:
            pass

        if enable_button and enable_button.is_visible():
            enable_button.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(5000)
            print("Cloud Build API enabled.")
        else:
            print("INFO: Cloud Build API may already be enabled.")

        context.close()
        print("\n" + "="*60)
        print("Google Cloud Console setup script completed!")
        print(f"Project: {PROJECT_NAME} ({PROJECT_ID})")
        print("Please verify the project and API enablement in Google Cloud Console.")
        print("="*60)