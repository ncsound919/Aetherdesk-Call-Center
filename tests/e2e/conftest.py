import os

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")
API_URL = os.getenv("E2E_API_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def browser() -> Browser:
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False, slow_mo=300)
    yield browser
    browser.close()
    pw.stop()


@pytest.fixture
def context(browser: Browser) -> BrowserContext:
    ctx = browser.new_context(
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        timezone_id="America/New_York",
    )
    yield ctx
    ctx.close()


@pytest.fixture
def page(context: BrowserContext) -> Page:
    pg = context.new_page()
    yield pg
    pg.close()


@pytest.fixture
def api_url() -> str:
    return API_URL


@pytest.fixture
def ui_url() -> str:
    return BASE_URL
