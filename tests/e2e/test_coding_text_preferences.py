from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from .conftest import browser_params

CODE_ROW = ".ace-code-row, .ace-ht-row--code"


@pytest.mark.parametrize("browser_name", browser_params())
def test_coding_text_size_control_changes_only_coding_text(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")

            sentence_size_before = page.locator(".ace-sentence").first.evaluate(
                "el => getComputedStyle(el).fontSize"
            )
            code_row_size_before = page.locator(CODE_ROW).first.evaluate(
                "el => getComputedStyle(el).fontSize"
            )

            page.get_by_role("button", name="Coding text size").click()
            page.get_by_role("button", name="Larger coding text").click()

            sentence_size_after = page.locator(".ace-sentence").first.evaluate(
                "el => getComputedStyle(el).fontSize"
            )
            code_row_size_after = page.locator(CODE_ROW).first.evaluate(
                "el => getComputedStyle(el).fontSize"
            )

            assert sentence_size_after != sentence_size_before
            assert code_row_size_after == code_row_size_before
            assert page.evaluate('localStorage.getItem("ace-coding-text-size")') == "20"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_coding_text_scrollbar_sits_before_applied_codes(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page(viewport={"width": 1180, "height": 620})
            page.goto(f"{ace_server}/code")
            page.evaluate(
                """
                const body = document.querySelector(".ace-text-body");
                const sentence = document.querySelector(".ace-sentence");
                for (let i = 0; i < 80; i += 1) {
                  const span = sentence.cloneNode(true);
                  span.textContent = ` Extra coding sentence ${i}.`;
                  body.appendChild(span);
                }
                """
            )

            text_scroll_box = page.locator("#text-scroll").bounding_box()
            inspector_box = page.locator("#ace-right-inspector").bounding_box()
            assert text_scroll_box is not None
            assert inspector_box is not None

            scroll_metrics = page.locator("#text-scroll").evaluate(
                "el => ({ scrollHeight: el.scrollHeight, clientHeight: el.clientHeight })"
            )
            assert scroll_metrics["scrollHeight"] > scroll_metrics["clientHeight"]
            assert text_scroll_box["x"] + text_scroll_box["width"] <= inspector_box["x"] + 1
        finally:
            browser.close()
