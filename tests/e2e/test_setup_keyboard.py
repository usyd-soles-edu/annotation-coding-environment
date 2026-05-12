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
def test_import_step_change_moves_focus_to_heading(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/import")

            import_more = page.get_by_role("button", name="Import more data")
            if import_more.is_visible():
                import_more.click()

            page.get_by_role("button", name="CSV or Excel file").click()
            assert page.evaluate("document.activeElement.textContent.trim()") == "Choose your file"
            visible_steps = page.evaluate(
                "() => Array.from(document.querySelectorAll('.ace-wizard-step:not([hidden])')).map(el => el.id)"
            )
            assert visible_steps == ["step-upload"]
        finally:
            browser.close()
