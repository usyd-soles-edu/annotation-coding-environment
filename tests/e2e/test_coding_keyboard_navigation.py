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
