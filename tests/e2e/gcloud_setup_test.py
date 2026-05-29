import pytest
from playwright.sync_api import sync_playwright
import re


def test_gcloud_install_and_login():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto("https://cloud.google.com/sdk/docs/install-sdk")

        page.wait_for_load_state("networkidle")

        page.screenshot(path=".screenshots/gcloud_main_page.png")

        page.evaluate("window.scrollTo(0, 800)")
        page.wait_for_timeout(2000)

        page.screenshot(path=".screenshots/gcloud_scrolled.png")

        try:
            download_link = page.get_by_text(re.compile(r"Download.*ZIP", re.IGNORECASE)).first
            if download_link.is_visible():
                print("Found download link with regex, clicking...")
                with page.expect_download() as download_info:
                    download_link.click()
                download = download_info.value
                download.save_as("C:/Users/User/Desktop/aetherdesk_scaffold/.downloads/gcloud-sdk.zip")
                print(f"Downloaded: {download.suggested_filename}")
                page.screenshot(path=".screenshots/gcloud_downloaded.png")
        except Exception as e:
            print(f"Regex search failed: {e}")
            print("Dumping page content...")
            content = page.content()
            with open("C:/Users/User/Desktop/aetherdesk_scaffold/.downloads/page_dump.html", "w") as f:
                f.write(content)
            page.screenshot(path=".screenshots/gcloud_no_download.png")

        browser.close()

        print("Test complete")