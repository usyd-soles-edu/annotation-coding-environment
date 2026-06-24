from __future__ import annotations

import pytest
from playwright.sync_api import expect, sync_playwright

from .conftest import browser_params
from .test_applied_code_removal import _annotation_data, _apply_annotation


def _focused_sentence_index(page) -> int:
    return page.evaluate("() => window.__aceFocusIndex")


def _click_source_sentence(page, index: int = 0) -> None:
    page.locator(".ace-sentence").nth(index).click()
    page.wait_for_function("() => document.activeElement?.id === 'text-panel'")
    assert page.evaluate("document.body.dataset.activeZone") == "source"


@pytest.mark.parametrize("browser_name", browser_params())
def test_source_left_right_switch_zones_not_sentences(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")

            _click_source_sentence(page)
            assert _focused_sentence_index(page) == 0
            page.keyboard.press("ArrowDown")
            assert _focused_sentence_index(page) == 1

            page.keyboard.press("ArrowLeft")
            page.wait_for_function(
                "() => document.activeElement?.matches("
                "\"#ace-headless-tree-mount [role='treeitem']\")"
            )
            assert _focused_sentence_index(page) == 1

            page.keyboard.press("Escape")
            page.wait_for_function("() => document.body.dataset.activeZone === 'source'")
            assert _focused_sentence_index(page) == 1

            page.keyboard.press("ArrowLeft")
            page.wait_for_function(
                "() => document.activeElement?.matches("
                "\"#ace-headless-tree-mount [role='treeitem']\")"
            )
            assert _focused_sentence_index(page) == 1
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_source_right_enters_applied_codes_and_left_returns_to_sentence(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")
            _apply_annotation(page, 0, 0, 15, "First sentence.")
            page.wait_for_selector(".ace-applied-code-row")

            _click_source_sentence(page)
            assert _focused_sentence_index(page) == 0
            page.keyboard.press("ArrowRight")
            page.wait_for_function(
                "() => document.activeElement?.matches('.ace-applied-code-row')"
            )
            assert page.evaluate("document.body.dataset.activeZone") == "applied"

            page.keyboard.press("ArrowLeft")
            page.wait_for_function("() => document.body.dataset.activeZone === 'source'")
            assert _focused_sentence_index(page) == 0
            assert page.locator(".ace-applied-row--keyboard").count() == 0
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_source_right_focuses_applied_rail_when_collapsed(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")
            _apply_annotation(page, 0, 0, 15, "First sentence.")
            page.wait_for_selector(".ace-applied-code-row")
            page.evaluate("localStorage.setItem('ace-applied-codes-collapsed', '1')")
            page.reload()
            page.wait_for_selector(".ace-sentence")
            page.wait_for_selector("#ace-applied-codes-rail")

            _click_source_sentence(page)
            page.keyboard.press("ArrowRight")
            expect(page.locator(".ace-applied-rail-toggle")).to_be_focused()
            assert page.evaluate("document.body.dataset.activeZone") == "applied"
            expect(page.locator("#ace-applied-codes-panel")).to_have_attribute(
                "aria-hidden", "true"
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_enter_on_applied_rail_expands_and_focuses_first_row(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")
            _apply_annotation(page, 0, 0, 15, "First sentence.")
            page.wait_for_selector(".ace-applied-code-row")
            page.evaluate("localStorage.setItem('ace-applied-codes-collapsed', '1')")
            page.reload()
            page.wait_for_selector(".ace-sentence")

            _click_source_sentence(page)
            page.keyboard.press("ArrowRight")
            expect(page.locator(".ace-applied-rail-toggle")).to_be_focused()
            page.keyboard.press("Enter")
            expect(page.locator("#ace-applied-codes-panel")).to_have_attribute(
                "aria-hidden", "false"
            )
            expect(page.locator(".ace-applied-code-row").first).to_be_focused()
            assert page.evaluate(
                "localStorage.getItem('ace-applied-codes-collapsed')"
            ) is None
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_collapsed_applied_rail_refreshes_after_keyboard_coding(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")
            page.locator(".ace-applied-codes-toggle").click()
            page.wait_for_function(
                "() => document.documentElement.dataset.aceAppliedCodesCollapsed === '1'"
            )
            expect(page.locator(".ace-applied-rail-total")).to_have_text("0")

            _click_source_sentence(page)
            page.keyboard.press("1")
            expect(page.locator(".ace-applied-rail-total")).to_have_text("1")
            expect(page.locator(".ace-applied-rail-tick:not(.ace-applied-rail-tick--empty)")).to_have_count(1)
            expect(page.locator("#ace-applied-codes-panel")).to_have_attribute(
                "aria-hidden", "true"
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_bracket_toggles_applied_codes_panel_without_conflicting_with_search(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")
            _apply_annotation(page, 0, 0, 15, "First sentence.")
            page.wait_for_selector(".ace-applied-code-row")

            _click_source_sentence(page)
            page.keyboard.press("]")
            page.wait_for_function(
                "() => document.documentElement.dataset.aceAppliedCodesCollapsed === '1'"
            )
            expect(page.locator(".ace-applied-rail-toggle")).to_be_focused()

            page.keyboard.press("]")
            page.wait_for_function(
                "() => document.documentElement.dataset.aceAppliedCodesCollapsed !== '1'"
            )
            expect(page.locator(".ace-applied-code-row").first).to_be_focused()

            page.keyboard.press("ArrowLeft")
            page.keyboard.press("/")
            expect(page.locator("#code-search-input")).to_be_focused()
            page.keyboard.press("]")
            expect(page.locator("#code-search-input")).to_be_focused()
            expect(page.locator("#code-search-input")).to_have_value("]")
            page.evaluate("document.getElementById('code-search-input').value = ''")
            expect(page.locator("#ace-applied-codes-panel")).to_have_attribute(
                "aria-hidden", "false"
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_applied_up_arrow_reaches_collapse_button(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")
            _apply_annotation(page, 0, 0, 15, "First sentence.")
            page.wait_for_selector(".ace-applied-code-row")

            _click_source_sentence(page)
            page.keyboard.press("ArrowRight")
            expect(page.locator(".ace-applied-code-row").first).to_be_focused()
            page.keyboard.press("ArrowUp")
            expect(page.locator(".ace-applied-codes-toggle")).to_be_focused()
            page.keyboard.press("ArrowDown")
            expect(page.locator(".ace-applied-code-row").first).to_be_focused()
            page.keyboard.press("ArrowUp")
            page.keyboard.press("Enter")
            page.wait_for_function(
                "() => document.documentElement.dataset.aceAppliedCodesCollapsed === '1'"
            )
            expect(page.locator(".ace-applied-rail-toggle")).to_be_focused()
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_codebook_enter_applies_and_returns_to_source(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")

            _click_source_sentence(page)
            page.keyboard.press("ArrowLeft")
            page.wait_for_function(
                "() => document.activeElement?.matches("
                "\"#ace-headless-tree-mount .ace-ht-row--code\")"
            )
            page.keyboard.press("Enter")
            page.wait_for_function(
                "() => JSON.parse("
                "document.getElementById('ace-ann-data').dataset.annotations || '[]'"
                ").length === 1"
            )
            page.wait_for_function("() => document.body.dataset.activeZone === 'source'")
            assert _focused_sentence_index(page) == 0
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_codebook_right_returns_to_source_without_applying(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")

            _click_source_sentence(page)
            page.keyboard.press("ArrowDown")
            assert _focused_sentence_index(page) == 1
            page.keyboard.press("ArrowLeft")
            page.wait_for_function(
                "() => document.activeElement?.matches("
                "\"#ace-headless-tree-mount .ace-ht-row--code\")"
            )

            page.keyboard.press("ArrowRight")
            page.wait_for_function("() => document.body.dataset.activeZone === 'source'")
            assert _focused_sentence_index(page) == 1
            assert _annotation_data(page) == []
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_codebook_left_restores_single_previous_code_focus(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")

            _click_source_sentence(page)
            page.keyboard.press("ArrowLeft")
            page.wait_for_function("() => document.body.dataset.activeZone === 'codebook'")
            page.keyboard.press("ArrowDown")
            page.wait_for_function(
                "() => document.activeElement?.querySelector('.ace-ht-label')"
                "?.textContent?.trim() === 'Bravo'"
            )

            page.keyboard.press("ArrowRight")
            page.wait_for_function("() => document.body.dataset.activeZone === 'source'")
            page.keyboard.press("ArrowLeft")
            page.wait_for_function("() => document.body.dataset.activeZone === 'codebook'")

            focused_labels = page.evaluate(
                """
                () => Array.from(
                  document.querySelectorAll("#ace-headless-tree-mount .ace-ht-row[tabindex='0']")
                ).map((row) => row.querySelector(".ace-ht-label")?.textContent?.trim())
                """
            )
            assert focused_labels == ["Bravo"]
            assert page.evaluate(
                "() => document.activeElement?.querySelector('.ace-ht-label')"
                "?.textContent?.trim()"
            ) == "Bravo"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_codebook_right_returns_to_source_from_folder(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")
            page.evaluate(
                """
                async () => {
                  const body = new URLSearchParams({
                    name: "Folder",
                    current_index: String(window.__aceCurrentIndex || 0),
                  });
                  const response = await fetch("/api/codes/folder", {
                    method: "POST",
                    headers: {"Content-Type": "application/x-www-form-urlencoded"},
                    body,
                  });
                  if (!response.ok) throw new Error(`folder create failed: ${response.status}`);
                }
                """
            )
            page.reload()
            page.wait_for_selector(".ace-ht-row--folder")

            _click_source_sentence(page, 1)
            page.locator(".ace-ht-row--folder").first.click()
            page.wait_for_function("() => document.body.dataset.activeZone === 'codebook'")
            page.keyboard.press("ArrowRight")
            page.wait_for_function("() => document.body.dataset.activeZone === 'source'")
            assert _focused_sentence_index(page) == 1
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_applied_codes_keyboard_navigation_and_delete(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")
            _apply_annotation(page, 0, 0, 15, "First sentence.")
            _apply_annotation(page, 0, 16, 32, "Second sentence.")
            page.locator(".ace-applied-code-count", has_text="2").wait_for()

            _click_source_sentence(page)
            page.keyboard.press("ArrowRight")
            page.wait_for_function(
                "() => document.activeElement?.matches('.ace-applied-code-row')"
            )
            page.keyboard.press("ArrowRight")
            page.wait_for_function(
                "() => document.activeElement?.matches('.ace-applied-annotation-row')"
            )
            page.keyboard.press("ArrowDown")
            expect(page.locator(".ace-applied-annotation-row").nth(1)).to_be_focused()
            page.keyboard.press("Delete")
            page.locator(".ace-applied-code-count", has_text="1").wait_for()

            remaining = _annotation_data(page)
            assert len(remaining) == 1
            assert remaining[0]["start"] == 0
            assert remaining[0]["end"] == 15
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_source_delete_enters_delete_pick_for_multiple_annotations(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")
            _apply_annotation(page, 0, 0, 15, "First sentence.")
            _apply_annotation(page, 1, 0, 15, "First sentence.")
            page.wait_for_selector(".ace-applied-code-row")

            _click_source_sentence(page)
            page.keyboard.press("Delete")
            page.wait_for_function(
                "() => document.activeElement?.matches("
                "'.ace-applied-code-row, .ace-applied-annotation-row')"
            )
            assert page.locator(".ace-applied-delete-candidate").count() == 2
            assert len(_annotation_data(page)) == 2

            page.keyboard.press("Escape")
            page.wait_for_function("() => document.body.dataset.activeZone === 'source'")
            assert len(_annotation_data(page)) == 2
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_source_delete_removes_single_annotation(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")
            _apply_annotation(page, 0, 0, 15, "First sentence.")
            page.wait_for_selector(".ace-applied-code-row")

            _click_source_sentence(page)
            page.keyboard.press("Delete")
            page.wait_for_selector(".ace-applied-code-row", state="detached")
            assert _annotation_data(page) == []
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_source_shortcuts_do_not_fire_while_typing_in_search(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")

            _click_source_sentence(page)
            page.keyboard.press("/")
            expect(page.locator("#code-search-input")).to_be_focused()
            page.keyboard.press("ArrowRight")
            expect(page.locator("#code-search-input")).to_be_focused()
        finally:
            browser.close()
