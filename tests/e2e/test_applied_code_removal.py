from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from .conftest import browser_params


def _apply_annotation(page, code_index: int, start: int, end: int, text: str):
    page.evaluate(
        """
        async ({ codeIndex, start, end, text }) => {
          const codes = window.__aceCodes.filter((code) => code.kind !== "folder");
          const code = codes[codeIndex];
          await window.htmx.ajax("POST", "/api/code/apply", {
            target: "#text-panel",
            swap: "outerHTML",
            values: {
              code_id: code.id,
              start_offset: start,
              end_offset: end,
              selected_text: text,
              current_index: window.__aceCurrentIndex || 0,
            },
          });
        }
        """,
        {"codeIndex": code_index, "start": start, "end": end, "text": text},
    )


def _annotation_data(page):
    return page.evaluate(
        """
        () => JSON.parse(
          document.getElementById("ace-ann-data").dataset.annotations || "[]"
        )
        """
    )


@pytest.mark.parametrize("browser_name", browser_params())
def test_applied_code_remove_button_removes_single_annotation(ace_server, browser_name):
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
            assert _annotation_data(page) == []
            assert "Applied code removed" in page.locator("#ace-statusbar-event").text_content()

            page.keyboard.press("Z")
            page.wait_for_selector(".ace-applied-code-row")
            assert len(_annotation_data(page)) == 1
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_applied_code_group_expands_and_removes_chosen_occurrence(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-text-body")

            _apply_annotation(page, 0, 0, 15, "First sentence.")
            _apply_annotation(page, 0, 16, 32, "Second sentence.")
            page.locator(".ace-applied-code-count", has_text="2").wait_for()

            page.click(".ace-applied-code-toggle")
            page.wait_for_selector(".ace-applied-annotation-row")
            assert page.locator(".ace-applied-annotation-row").count() == 2

            page.locator(
                ".ace-applied-annotation-line",
                has_text="Second sentence.",
            ).locator(".ace-applied-annotation-remove").click()
            page.locator(".ace-applied-code-count", has_text="1").wait_for()

            remaining = _annotation_data(page)
            assert len(remaining) == 1
            assert remaining[0]["start"] == 0
            assert remaining[0]["end"] == 15
        finally:
            browser.close()
