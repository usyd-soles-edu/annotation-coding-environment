"""Active-zone indicator tests — body[data-active-zone] toggles between
'source' and 'codebook' as focus moves between the text panel and the
sidebar, and the visual state of the focused row reflects this."""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from .conftest import browser_params

CODE_ROW = ".ace-code-row, .ace-ht-row--code"
FOCUSED_ROW = ".ace-code-row[tabindex=\"0\"], .ace-ht-row[tabindex=\"0\"]"


def _create_folder(page, name: str):
    page.evaluate(
        """
        async (label) => {
          const body = new URLSearchParams({
            name: label,
            current_index: String(window.__aceCurrentIndex || 0),
          });
          const response = await fetch("/api/codes/folder", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body,
          });
          if (!response.ok) throw new Error(`folder create failed: ${response.status}`);
        }
        """,
        name,
    )
    page.reload()


@pytest.mark.parametrize("browser_name", browser_params())
def test_active_zone_toggles_on_focus(ace_server, browser_name):
    """Default = source · click the search input → codebook · click the
    text panel → source again."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount, #code-tree")

            # Default zone is set to "source" by the inline init script in
            # bridge.js (line ~64).
            assert page.evaluate("document.body.dataset.activeZone") == "source"

            # Focus the codebook search input — focusin → _setActiveZone("codebook").
            page.click("#code-search-input")
            assert page.evaluate("document.body.dataset.activeZone") == "codebook"

            # Click back into the source body.
            page.click("#text-panel")
            assert page.evaluate("document.body.dataset.activeZone") == "source"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_focused_row_styles_change_with_zone(ace_server, browser_name):
    """The focused code row gets a quiet highlight only while the codebook
    zone is active. Switching focus to the source clears the background."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(CODE_ROW)

            # Click a row → roving tabindex=0 lands on it AND sidebar gains focus.
            page.click(CODE_ROW)
            # Confirm the active zone flipped to codebook.
            assert page.evaluate("document.body.dataset.activeZone") == "codebook"

            # Background fades in via a CSS transition — poll until it
            # resolves to the quiet selected-row value #f1f1ee.
            page.wait_for_function(
                "(selector) => getComputedStyle(document.querySelector(selector))"
                ".backgroundColor === 'rgb(241, 241, 238)'",
                arg=FOCUSED_ROW,
                timeout=2000,
            )

            # Click into the source body. The codebook row keeps its
            # tabindex="0" (roving focus persists) but loses the background tint.
            page.click("#text-panel")
            assert page.evaluate("document.body.dataset.activeZone") == "source"
            page.wait_for_function(
                "(selector) => getComputedStyle(document.querySelector(selector))"
                ".backgroundColor === 'rgba(0, 0, 0, 0)'",
                arg=FOCUSED_ROW,
                timeout=2000,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_legacy_code_double_click_rename_accepts_typing(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code?tree=legacy")
            page.wait_for_selector(".ace-code-row .ace-code-name")

            page.dblclick(".ace-code-row .ace-code-name")
            page.wait_for_selector(".ace-code-row .ace-code-name[contenteditable='true']")
            page.keyboard.type("Renamed Alpha")
            page.keyboard.press("Enter")

            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('.ace-code-name'))"
                ".some(el => el.textContent.trim() === 'Renamed Alpha')",
                timeout=3000,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_legacy_folder_double_click_rename_accepts_typing(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code?tree=legacy")
            _create_folder(page, "Folder One")
            page.wait_for_selector(".ace-code-folder-row .ace-folder-label")

            page.dblclick(".ace-code-folder-row .ace-folder-label")
            page.wait_for_selector(".ace-folder-label[contenteditable='true']")
            page.keyboard.type("Renamed Folder")
            page.keyboard.press("Enter")

            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('.ace-folder-label'))"
                ".some(el => el.textContent.trim() === 'Renamed Folder')",
                timeout=3000,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_code_double_click_rename_accepts_typing(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-ht-row--code .ace-ht-label")

            page.dblclick(".ace-ht-row--code .ace-ht-label")
            page.wait_for_selector(".ace-ht-rename")
            page.click(".ace-ht-rename", position={"x": 12, "y": 8})
            page.wait_for_selector(".ace-ht-rename")
            assert page.evaluate(
                "() => document.activeElement === document.querySelector('.ace-ht-rename')"
            )
            page.locator(".ace-ht-rename").fill("Renamed Alpha")
            page.keyboard.press("Enter")

            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('.ace-ht-row--code .ace-ht-label'))"
                ".some(el => el.textContent.trim() === 'Renamed Alpha')",
                timeout=3000,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_folder_double_click_rename_accepts_typing(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            _create_folder(page, "Folder One")
            page.wait_for_selector(".ace-ht-row--folder .ace-ht-label")

            page.dblclick(".ace-ht-row--folder .ace-ht-label")
            page.wait_for_selector(".ace-ht-rename")
            page.click(".ace-ht-rename", position={"x": 12, "y": 8})
            page.wait_for_selector(".ace-ht-rename")
            assert page.evaluate(
                "() => document.activeElement === document.querySelector('.ace-ht-rename')"
            )
            page.locator(".ace-ht-rename").fill("Renamed Folder")
            page.keyboard.press("Enter")

            page.wait_for_function(
                "() => Array.from(document.querySelectorAll('.ace-ht-row--folder .ace-ht-label'))"
                ".some(el => el.textContent.trim() === 'Renamed Folder')",
                timeout=3000,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_legacy_inline_rename_click_away_clears_codebook_selection(ace_server, browser_name):
    """Double-click rename should not leave the row visibly selected after
    focus moves outside the codebook."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code?tree=legacy")
            page.wait_for_selector(".ace-code-row")

            page.dblclick(".ace-code-row .ace-code-name")
            page.wait_for_selector(".ace-code-row .ace-code-name[contenteditable='true']")
            assert page.evaluate("document.body.dataset.activeZone") == "codebook"

            page.click("#code-sidebar", position={"x": 12, "y": 520})

            page.wait_for_function(
                "() => !document.querySelector('[contenteditable=\"true\"]')",
                timeout=2000,
            )
            assert page.evaluate("document.body.dataset.activeZone") == "source"
            page.wait_for_function(
                "() => getComputedStyle(document.querySelector('.ace-code-row'))"
                ".backgroundColor === 'rgba(0, 0, 0, 0)'",
                timeout=2000,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_inline_rename_click_away_clears_codebook_selection(ace_server, browser_name):
    """The default headless codebook should also clear its selected-row cue
    when inline rename is cancelled by clicking away."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-ht-row--code")

            page.dblclick(".ace-ht-row--code .ace-ht-label")
            page.wait_for_selector(".ace-ht-rename")
            assert page.evaluate("document.body.dataset.activeZone") == "codebook"

            page.click("#code-sidebar", position={"x": 12, "y": 520})

            page.wait_for_function(
                "() => !document.querySelector('.ace-ht-rename')",
                timeout=2000,
            )
            assert page.evaluate("document.body.dataset.activeZone") == "source"
            page.wait_for_function(
                "() => getComputedStyle(document.querySelector('.ace-ht-row--code'))"
                ".backgroundColor === 'rgba(0, 0, 0, 0)'",
                timeout=2000,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_focused_sentence_thickness_changes_with_zone(ace_server, browser_name):
    """Focused sentence shows 2px underline when source is active, 1.5px
    when codebook is active (the dimmed cue from coding.css L1499–1504)."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")

            # Click first sentence → source zone, sentence gets .ace-sentence--focused.
            page.click(".ace-sentence")
            assert page.evaluate("document.body.dataset.activeZone") == "source"
            page.wait_for_selector(".ace-sentence--focused")

            thickness_source = page.evaluate(
                "() => getComputedStyle("
                "document.querySelector('.ace-sentence--focused')"
                ").textDecorationThickness"
            )
            # Strong cue when source is active. The default rule is 2px.
            assert thickness_source.startswith("2"), (
                f"expected ~2px when source active, got {thickness_source!r}"
            )

            # Switch to codebook by clicking a code row.
            page.click(CODE_ROW)
            assert page.evaluate("document.body.dataset.activeZone") == "codebook"
            thickness_codebook = page.evaluate(
                "() => getComputedStyle("
                "document.querySelector('.ace-sentence--focused')"
                ").textDecorationThickness"
            )
            # Dimmed cue: 1.5px (coding.css L1503).
            assert thickness_codebook.startswith("1.5"), (
                f"expected ~1.5px when codebook active, got {thickness_codebook!r}"
            )
        finally:
            browser.close()
