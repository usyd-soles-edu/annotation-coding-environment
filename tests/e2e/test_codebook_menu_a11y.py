from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from .conftest import browser_params


@pytest.mark.parametrize("browser_name", browser_params())
def test_codebook_menu_reports_state_and_moves_focus(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")

            menu_button = page.get_by_role("button", name="Settings and shortcuts")
            dropdown = page.locator("#codebook-dropdown")

            assert menu_button.get_attribute("aria-haspopup") == "menu"
            assert menu_button.get_attribute("aria-expanded") == "false"
            assert dropdown.get_attribute("role") == "menu"
            assert dropdown.evaluate("el => el.hidden") is True

            menu_button.click()

            assert menu_button.get_attribute("aria-expanded") == "true"
            assert dropdown.evaluate("el => el.hidden") is False
            assert page.evaluate("document.activeElement.id") == "codebook-menu-shortcuts-btn"

            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "codebook-cues-toggle-btn"

            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "codebook-menu-import-btn"

            page.keyboard.press("ArrowUp")
            assert page.evaluate("document.activeElement.id") == "codebook-cues-toggle-btn"

            page.keyboard.press("End")
            assert page.evaluate("document.activeElement.id") == "fullscreen-btn"

            page.keyboard.press("Home")
            assert page.evaluate("document.activeElement.id") == "codebook-menu-shortcuts-btn"

            page.keyboard.press("Escape")

            assert menu_button.get_attribute("aria-expanded") == "false"
            assert dropdown.evaluate("el => el.hidden") is True
            assert page.evaluate("document.activeElement.id") == "codebook-menu-btn"

            menu_button.click()
            page.get_by_role("button", name="Coding text size and width").click()

            assert menu_button.get_attribute("aria-expanded") == "false"
            assert dropdown.evaluate("el => el.hidden") is True
        finally:
            browser.close()
