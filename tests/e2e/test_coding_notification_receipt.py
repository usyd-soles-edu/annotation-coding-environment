from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from .conftest import browser_params
from .test_applied_code_removal import _annotation_data, _apply_annotation


@pytest.mark.parametrize("browser_name", browser_params())
def test_status_receipt_handles_client_success_and_error(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-notification-receipt", state="attached")

            receipt = page.locator("#ace-notification-receipt")
            page.evaluate("window._setStatus('Exported', 'ok')")
            assert receipt.is_visible()
            assert "Exported" in receipt.text_content()

            page.evaluate("window._setStatus('Choose a code first', 'err')")
            assert receipt.is_visible()
            assert "Choose a code first" in receipt.text_content()
            assert "ace-notification-receipt--err" in (receipt.get_attribute("class") or "")
            assert "Choose a code first" in page.locator("#ace-live-region-assertive").text_content()
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_undoable_delete_uses_receipt_button(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-text-body")

            _apply_annotation(page, 0, 0, 15, "First sentence.")
            page.wait_for_selector(".ace-applied-code-row")
            assert len(_annotation_data(page)) == 1

            page.click(".ace-applied-annotation-remove")
            page.wait_for_selector(".ace-applied-code-row", state="detached")

            receipt = page.locator("#ace-notification-receipt")
            assert receipt.is_visible()
            assert "Removed code" in receipt.text_content()
            page.wait_for_function(
                "() => document.querySelector('#ace-notification-receipt')"
                "?.classList.contains('ace-notification-receipt--undo')"
            )
            assert "ace-notification-receipt--undo" in (receipt.get_attribute("class") or "")
            assert receipt.get_by_role("button", name="Undo last action").is_visible()
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_receipt_is_bottom_centred_in_text_panel(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-notification-receipt", state="attached")

            page.evaluate("window._setStatus('Choose a code first', 'err')")
            receipt_box = page.locator("#ace-notification-receipt").bounding_box()
            panel_box = page.locator("#text-panel").bounding_box()
            assert receipt_box is not None
            assert panel_box is not None

            receipt_centre = receipt_box["x"] + receipt_box["width"] / 2
            panel_centre = panel_box["x"] + panel_box["width"] / 2
            assert abs(receipt_centre - panel_centre) < 8
            assert receipt_box["y"] > panel_box["y"] + panel_box["height"] * 0.65
        finally:
            browser.close()
