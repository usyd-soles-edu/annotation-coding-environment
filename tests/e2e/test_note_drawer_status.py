from __future__ import annotations

import pytest
from playwright.sync_api import expect, sync_playwright

from .conftest import browser_params


@pytest.mark.parametrize("browser_name", browser_params())
def test_long_note_warning_clears_after_trimming(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#note-pill")

            page.locator("#note-pill").click()
            page.locator("#note-pill").click()
            expect(page.locator("#note-textarea")).to_be_focused()

            page.locator("#note-textarea").evaluate(
                """
                (textarea) => {
                  textarea.value = "x".repeat(5001);
                  textarea.dispatchEvent(new Event("input", { bubbles: true }));
                }
                """
            )
            expect(page.locator("#note-status")).to_have_text(
                "Long note (over 5,000 characters)"
            )

            page.locator("#note-textarea").evaluate(
                """
                (textarea) => {
                  textarea.value = "x".repeat(4999);
                  textarea.dispatchEvent(new Event("input", { bubbles: true }));
                }
                """
            )
            expect(page.locator("#note-status")).to_have_text("")
        finally:
            browser.close()
