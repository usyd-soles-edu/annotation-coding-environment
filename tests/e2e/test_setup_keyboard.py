from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from .conftest import browser_params


def _press_forward_tab(page, browser_name):
    key = "Alt+Tab" if browser_name == "webkit" else "Tab"
    page.keyboard.press(key)


@pytest.mark.parametrize("browser_name", browser_params())
def test_landing_tab_order_skips_hidden_project_form(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/")
            _press_forward_tab(page, browser_name)
            assert page.evaluate("document.activeElement.id") == "new-project-link"
            _press_forward_tab(page, browser_name)
            assert page.evaluate("document.activeElement.id") == "open-existing-btn"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_landing_dismisses_last_recent_project(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/")
            page.evaluate(
                """
                localStorage.setItem(
                  "ace-recent-files",
                  JSON.stringify([{ path: "/tmp/example.ace", openedAt: 1 }])
                );
                """
            )
            page.reload()

            resume = page.locator("#resume-link")
            assert resume.is_visible()

            page.locator(".ace-home-resume-close").click()

            assert not resume.is_visible()
            assert page.evaluate('localStorage.getItem("ace-recent-files")') is None
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_import_choice_screen_uses_direct_route_rows(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/import")

            import_more = page.get_by_role("button", name="Import more data")
            if import_more.is_visible():
                import_more.click()

            assert page.locator(".ace-route-list").is_visible()
            assert page.locator(".ace-route-row").count() == 2
            assert page.locator("#step-folder").count() == 0
            assert page.get_by_role("button", name="Import a spreadsheet").is_visible()
            assert page.get_by_role("button", name="Import a folder").is_visible()
        finally:
            browser.close()
