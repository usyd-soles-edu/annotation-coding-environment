"""Drag-and-drop tests for the codebook sidebar.

WebKit's headless drag-and-drop pipeline does not emit the same dragenter
/ dragover sequence that Sortable.js relies on, so the WebKit case is
skipped — coverage on Chromium and Firefox is sufficient for the gesture.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from .conftest import browser_params


def _webkit_params():
    out = []
    for entry in browser_params():
        name = entry.values[0] if hasattr(entry, "values") else entry
        if name == "webkit":
            out.append(entry)
    return out


def _drag_param_names():
    """Drop WebKit from the parametrize set since headless drag is flaky.

    We still want a missing-engine to skip cleanly, so we re-walk
    browser_params() and rewrite WebKit's mark to a skip.
    """
    out = []
    for entry in browser_params():
        # entry is either a plain string ("chromium") or a pytest.param
        name = entry.values[0] if hasattr(entry, "values") else entry
        if name == "webkit":
            out.append(
                pytest.param(
                    "webkit",
                    marks=pytest.mark.skip(
                        reason="WebKit headless drag-and-drop is flaky with Sortable.js"
                    ),
                )
            )
        else:
            out.append(entry)
    return out


def _leave_inline_rename(page) -> None:
    page.wait_for_timeout(120)
    page.keyboard.press("Escape")
    page.evaluate(
        "() => document.querySelectorAll('[contenteditable=\"true\"]')"
        "  .forEach(el => { el.contentEditable = 'false'; })"
    )


@pytest.mark.parametrize("browser_name", _drag_param_names())
def test_drag_code_into_folder(ace_server, browser_name):
    """Create a folder, then drag Alpha onto its header → Alpha lands inside."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#code-tree")

            # Create a folder by wrapping Alpha + Bravo (⌥⇧→). This gives
            # us a folder with at least one code already in it — a non-empty
            # children container is a more reliable drag target than an
            # empty role="group", because Sortable measures the destination
            # by hit-testing existing siblings.
            rows = page.query_selector_all(".ace-code-row")
            assert len(rows) >= 3, "fixture needs at least 3 codes (Alpha/Bravo/Charlie)"
            rows[1].click()  # Bravo
            page.keyboard.press("Alt+Shift+ArrowRight")
            page.wait_for_selector(".ace-code-folder-row", timeout=3000)
            _leave_inline_rename(page)

            # Now there's a folder containing Alpha + Bravo, and Charlie at
            # root. Drag Charlie INTO the folder by dropping onto an existing
            # code inside it (a known-good Sortable hit target).
            charlie_loc = page.locator(
                '#code-tree > .ace-code-row[data-code-id]'
            ).last  # last root-level code row (Charlie)
            target_loc = page.locator(
                '[role="group"] .ace-code-row[data-code-id]'
            ).first  # any existing child of the folder
            charlie_loc.wait_for(timeout=2000)
            target_loc.wait_for(timeout=2000)

            charlie_loc.drag_to(target_loc)

            # All three codes should now live inside the folder.
            page.wait_for_function(
                "() => document.querySelectorAll("
                "  '[role=\"group\"] .ace-code-row[data-code-id]'"
                ").length >= 3",
                timeout=4000,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_codebook_drag_labels_do_not_select_text(ace_server, browser_name):
    """Dragging code rows should not leave selected sidebar label text behind."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#code-tree")

            assert page.locator(".ace-code-row").first.evaluate(
                "(el) => getComputedStyle(el).userSelect || getComputedStyle(el).webkitUserSelect"
            ) == "none"
            assert page.locator(".ace-code-name").first.evaluate(
                "(el) => getComputedStyle(el).userSelect || getComputedStyle(el).webkitUserSelect"
            ) == "none"

            rows = page.query_selector_all(".ace-code-row")
            rows[1].click()
            page.keyboard.press("Alt+Shift+ArrowRight")
            page.wait_for_selector(".ace-code-folder-row", timeout=3000)
            _leave_inline_rename(page)

            assert page.locator(".ace-folder-label").first.evaluate(
                "(el) => getComputedStyle(el).userSelect || getComputedStyle(el).webkitUserSelect"
            ) == "none"

            page.locator(".ace-code-row").first.click()
            page.keyboard.press("F2")

            assert page.locator('.ace-code-name[contenteditable="true"]').first.evaluate(
                "(el) => getComputedStyle(el).userSelect || getComputedStyle(el).webkitUserSelect"
            ) == "text"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", _webkit_params())
def test_tauri_drag_does_not_create_native_text_selection(ace_server, browser_name):
    """Fallback desktop drags should not create a sidebar text selection."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.add_init_script("window.__TAURI__ = { dialog: {} };")
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#code-tree")
            page.evaluate(
                """
                () => {
                  window.__aceLastMouseDownDefaultPrevented = null;
                  document.addEventListener("mousedown", (event) => {
                    if (event.target.closest(".ace-code-row")) {
                      window.__aceLastMouseDownDefaultPrevented = event.defaultPrevented;
                    }
                  });
                }
                """
            )

            row = page.locator(".ace-code-row").first
            box = row.bounding_box()
            assert box is not None
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2

            page.mouse.move(x, y)
            page.mouse.down()
            assert page.evaluate("window.__aceLastMouseDownDefaultPrevented") is True
            page.mouse.move(x, y + 12, steps=4)

            assert page.evaluate("window.getSelection().toString()") == ""
            page.mouse.up()
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", _webkit_params())
def test_tauri_webkit_codebook_uses_sortable_fallback_drag(ace_server, browser_name):
    """The desktop app should not rely on WKWebView native HTML5 drag events."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.add_init_script("window.__TAURI__ = { dialog: {} };")
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#code-tree")

            assert page.evaluate(
                """
                () => Sortable
                  .get(document.getElementById("code-tree"))
                  .option("forceFallback")
                """
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", _webkit_params())
def test_webkit_drag_code_into_folder_with_pointer_gesture(ace_server, browser_name):
    """Desktop WebKit must support the pointer gesture used in the macOS app."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#code-tree")

            rows = page.query_selector_all(".ace-code-row")
            assert len(rows) >= 3
            rows[1].click()
            page.keyboard.press("Alt+Shift+ArrowRight")
            page.wait_for_selector(".ace-code-folder-row", timeout=3000)
            _leave_inline_rename(page)

            source = page.locator('#code-tree > .ace-code-row[data-code-id]').last
            target = page.locator('[role="group"] .ace-code-row[data-code-id]').first
            source.wait_for(timeout=2000)
            target.wait_for(timeout=2000)

            source_box = source.bounding_box()
            target_box = target.bounding_box()
            assert source_box is not None
            assert target_box is not None

            start_x = source_box["x"] + source_box["width"] / 2
            start_y = source_box["y"] + source_box["height"] / 2
            end_x = target_box["x"] + target_box["width"] / 2
            end_y = target_box["y"] + target_box["height"] / 2

            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(start_x, start_y + 12, steps=4)
            page.mouse.move(end_x, end_y, steps=24)
            page.mouse.up()

            page.wait_for_function(
                "() => document.querySelectorAll("
                "  '[role=\"group\"] .ace-code-row[data-code-id]'"
                ").length >= 3",
                timeout=4000,
            )
        finally:
            browser.close()
