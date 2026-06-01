from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from .conftest import browser_params

CODE_ROW = ".ace-code-row, .ace-ht-row--code"
CODING_TEXT_SIZES = ["15", "17", "19", "20", "21", "24"]


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
            page.get_by_role("button", name="Largest coding text").click()

            sentence_size_after = page.locator(".ace-sentence").first.evaluate(
                "el => getComputedStyle(el).fontSize"
            )
            code_row_size_after = page.locator(CODE_ROW).first.evaluate(
                "el => getComputedStyle(el).fontSize"
            )

            assert sentence_size_after != sentence_size_before
            assert code_row_size_after == code_row_size_before
            assert page.evaluate('localStorage.getItem("ace-coding-text-size")') == "24"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_coding_text_size_control_supports_reader_scale(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.get_by_role("button", name="Coding text size").click()

            sizes = page.locator(".ace-coding-text-option").evaluate_all(
                "(nodes) => nodes.map((node) => node.dataset.codingTextSize)"
            )
            assert sizes == CODING_TEXT_SIZES

            for size in CODING_TEXT_SIZES:
                option = page.locator(f'.ace-coding-text-option[data-coding-text-size="{size}"]')
                option.click()
                sentence_size = page.locator(".ace-sentence").first.evaluate(
                    "el => getComputedStyle(el).fontSize"
                )
                assert sentence_size == f"{size}px"
                assert page.evaluate('localStorage.getItem("ace-coding-text-size")') == size
                assert option.get_attribute("aria-pressed") == "true"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_coding_text_size_slider_syncs_with_reader_scale(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.get_by_role("button", name="Coding text size").click()

            slider = page.get_by_role("slider", name="Coding text scale")
            assert slider.get_attribute("min") == "0"
            assert slider.get_attribute("max") == str(len(CODING_TEXT_SIZES) - 1)
            assert slider.get_attribute("aria-valuetext") == "17 px"

            slider.evaluate(
                "(el) => {"
                " el.value = '5';"
                " el.dispatchEvent(new Event('input', { bubbles: true }));"
                " }"
            )

            assert page.evaluate('localStorage.getItem("ace-coding-text-size")') == "24"
            assert slider.get_attribute("aria-valuetext") == "24 px"
            assert page.locator(".ace-sentence").first.evaluate(
                "el => getComputedStyle(el).fontSize"
            ) == "24px"
            assert page.locator(
                '.ace-coding-text-option[data-coding-text-size="24"]'
            ).get_attribute("aria-pressed") == "true"
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
