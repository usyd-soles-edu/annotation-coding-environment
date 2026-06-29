from __future__ import annotations

import pytest
from playwright.sync_api import expect, sync_playwright

from .conftest import browser_params


def _install_code_cue_fetch_spy(page):
    page.evaluate(
        """
        () => {
          window.__aceCueFetches = [];
          const realFetch = window.fetch.bind(window);
          window.fetch = (url, options = {}) => {
            if (String(url).endsWith("/api/code-cues")) {
              const body = JSON.parse(options.body || "{}");
              return new Promise((resolve) => {
                const record = {
                  body,
                  aborted: false,
                  resolve: (payload, status = 200) => resolve(new Response(JSON.stringify(payload || {}), {
                    status,
                    headers: { "Content-Type": "application/json" },
                  })),
                };
                if (options.signal) {
                  record.aborted = options.signal.aborted;
                  options.signal.addEventListener("abort", () => {
                    record.aborted = true;
                  }, { once: true });
                }
                window.__aceCueFetches.push(record);
              });
            }
            return realFetch(url, options);
          };
        }
        """
    )


def _install_code_cue_init_counter(page):
    page.add_init_script(
        """
        (() => {
          window.__aceCueFetchCount = 0;
          const realFetch = window.fetch.bind(window);
          window.fetch = (url, options = {}) => {
            if (String(url).endsWith("/api/code-cues")) {
              window.__aceCueFetchCount += 1;
              return Promise.resolve(new Response(JSON.stringify({
                request_id: 0,
                current_index: 0,
                sentence_index: -1,
                start: -1,
                end: -1,
                cues: [],
              }), {
                status: 200,
                headers: { "Content-Type": "application/json" },
              }));
            }
            return realFetch(url, options);
          };
        })();
        """
    )


@pytest.mark.parametrize("browser_name", browser_params())
def test_wording_cues_menu_item_toggles_and_persists(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.evaluate("localStorage.removeItem('ace-codebook-cues-enabled')")
            page.reload()

            menu_button = page.get_by_role("button", name="Settings and shortcuts")
            menu_button.click()

            toggle = page.get_by_role("menuitemcheckbox", name="Show wording cues")
            expect(toggle).to_be_visible()
            expect(toggle).to_have_attribute("aria-checked", "false")
            expect(page.locator("#codebook-cues-toggle-btn .ace-codebook-dropdown-help")).to_have_text(
                "Highlight rows with matching words."
            )

            toggle.click()

            expect(toggle).to_have_attribute("aria-checked", "true")
            assert page.evaluate("localStorage.getItem('ace-codebook-cues-enabled')") == "1"

            page.reload()
            page.get_by_role("button", name="Settings and shortcuts").click()
            toggle = page.get_by_role("menuitemcheckbox", name="Show wording cues")
            expect(toggle).to_have_attribute("aria-checked", "true")

            toggle.focus()
            page.keyboard.press("Space")

            expect(toggle).to_have_attribute("aria-checked", "false")
            assert page.evaluate("localStorage.getItem('ace-codebook-cues-enabled')") == "0"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_wording_cues_fetch_after_focus_and_stop_when_disabled(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.evaluate("localStorage.setItem('ace-codebook-cues-enabled', '0')")
            _install_code_cue_fetch_spy(page)

            page.locator(".ace-sentence").nth(0).click()
            page.wait_for_timeout(250)

            assert page.evaluate("window.__aceCueFetches.length") == 0

            alpha_id = page.locator("#ace-headless-tree-mount .ace-ht-row--code").nth(0).get_attribute("data-code-id")
            page.evaluate("localStorage.setItem('ace-codebook-cues-enabled', '1')")
            page.locator(".ace-sentence").nth(1).click()
            page.wait_for_function("window.__aceCueFetches.length === 1")
            request = page.evaluate("window.__aceCueFetches[0].body")

            assert request["current_index"] == 0
            assert request["sentence_index"] == 1
            assert request["text"] == "Second sentence."

            page.evaluate(
                """
                (codeId) => {
                  const request = window.__aceCueFetches[0].body;
                  window.__aceCueFetches[0].resolve({
                    request_id: request.request_id,
                    current_index: request.current_index,
                    sentence_index: request.sentence_index,
                    start: request.start,
                    end: request.end,
                    cues: [{ code_id: codeId, rank: 0.25, matched_terms: ["second"] }],
                  });
                }
                """,
                alpha_id,
            )

            page.wait_for_selector(
                f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{alpha_id}"].ace-code-row--cue'
            )

            page.evaluate("localStorage.setItem('ace-codebook-cues-enabled', '0')")
            page.locator(".ace-sentence").nth(0).click()
            page.wait_for_timeout(250)

            assert page.evaluate("window.__aceCueFetches.length") == 1
            expect(
                page.locator(
                    f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{alpha_id}"].ace-code-row--cue'
                )
            ).to_have_count(0)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_wording_cues_clear_and_stop_while_codebook_filter_is_active(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            _install_code_cue_fetch_spy(page)
            page.evaluate("localStorage.setItem('ace-codebook-cues-enabled', '1')")

            alpha_id = page.locator("#ace-headless-tree-mount .ace-ht-row--code").nth(0).get_attribute("data-code-id")

            page.locator(".ace-sentence").nth(0).click()
            page.wait_for_function("window.__aceCueFetches.length === 1")
            page.evaluate(
                """
                (codeId) => {
                  const request = window.__aceCueFetches[0].body;
                  window.__aceCueFetches[0].resolve({
                    request_id: request.request_id,
                    current_index: request.current_index,
                    sentence_index: request.sentence_index,
                    start: request.start,
                    end: request.end,
                    cues: [{ code_id: codeId, rank: 0.5, matched_terms: ["first"] }],
                  });
                }
                """,
                alpha_id,
            )
            page.wait_for_selector(
                f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{alpha_id}"].ace-code-row--cue'
            )

            search = page.locator("#code-search-input")
            search.fill("alp")

            expect(
                page.locator(
                    f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{alpha_id}"].ace-code-row--cue'
                )
            ).to_have_count(0)

            page.locator(".ace-sentence").nth(1).click()
            page.wait_for_timeout(250)

            assert page.evaluate("window.__aceCueFetches.length") == 1

            search.fill("")
            page.wait_for_function("window.__aceCueFetches.length === 2")
            page.evaluate(
                """
                (codeId) => {
                  const request = window.__aceCueFetches[1].body;
                  window.__aceCueFetches[1].resolve({
                    request_id: request.request_id,
                    current_index: request.current_index,
                    sentence_index: request.sentence_index,
                    start: request.start,
                    end: request.end,
                    cues: [{ code_id: codeId, rank: 0.5, matched_terms: ["second"] }],
                  });
                }
                """,
                alpha_id,
            )
            page.wait_for_selector(
                f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{alpha_id}"].ace-code-row--cue'
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_wording_cues_discard_stale_responses(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            _install_code_cue_fetch_spy(page)
            page.evaluate("localStorage.setItem('ace-codebook-cues-enabled', '1')")

            rows = page.locator("#ace-headless-tree-mount .ace-ht-row--code")
            alpha_id = rows.nth(0).get_attribute("data-code-id")
            bravo_id = rows.nth(1).get_attribute("data-code-id")

            page.locator(".ace-sentence").nth(0).click()
            page.wait_for_function("window.__aceCueFetches.length === 1")
            page.locator(".ace-sentence").nth(1).click()
            page.wait_for_function("window.__aceCueFetches.length === 2")
            assert page.evaluate("window.__aceCueFetches[0].aborted") is True

            page.evaluate(
                """
                (codeId) => {
                  const request = window.__aceCueFetches[1].body;
                  window.__aceCueFetches[1].resolve({
                    request_id: request.request_id,
                    current_index: request.current_index,
                    sentence_index: request.sentence_index,
                    start: request.start,
                    end: request.end,
                    cues: [{ code_id: codeId, rank: 0.8, matched_terms: ["second"] }],
                  });
                }
                """,
                bravo_id,
            )
            page.wait_for_selector(
                f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{bravo_id}"].ace-code-row--cue'
            )

            page.evaluate(
                """
                (codeId) => {
                  const request = window.__aceCueFetches[0].body;
                  window.__aceCueFetches[0].resolve({
                    request_id: request.request_id,
                    current_index: request.current_index,
                    sentence_index: request.sentence_index,
                    start: request.start,
                    end: request.end,
                    cues: [{ code_id: codeId, rank: 0.9, matched_terms: ["first"] }],
                  });
                }
                """,
                alpha_id,
            )
            page.wait_for_timeout(100)

            expect(
                page.locator(
                    f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{alpha_id}"].ace-code-row--cue'
                )
            ).to_have_count(0)
            expect(
                page.locator(
                    f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{bravo_id}"].ace-code-row--cue'
                )
            ).to_have_count(1)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_wording_cues_clear_on_source_navigation_event(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            _install_code_cue_fetch_spy(page)
            page.evaluate("localStorage.setItem('ace-codebook-cues-enabled', '1')")

            alpha_id = page.locator("#ace-headless-tree-mount .ace-ht-row--code").nth(0).get_attribute("data-code-id")
            page.locator(".ace-sentence").nth(0).click()
            page.wait_for_function("window.__aceCueFetches.length === 1")
            page.evaluate(
                """
                (codeId) => {
                  const request = window.__aceCueFetches[0].body;
                  window.__aceCueFetches[0].resolve({
                    request_id: request.request_id,
                    current_index: request.current_index,
                    sentence_index: request.sentence_index,
                    start: request.start,
                    end: request.end,
                    cues: [{ code_id: codeId, rank: 0.5, matched_terms: ["first"] }],
                  });
                }
                """,
                alpha_id,
            )
            page.wait_for_selector(
                f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{alpha_id}"].ace-code-row--cue'
            )

            page.evaluate(
                """
                () => document.dispatchEvent(new CustomEvent("ace-navigate", {
                  detail: { index: 0, total: 1 },
                }))
                """
            )

            expect(
                page.locator(
                    f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{alpha_id}"].ace-code-row--cue'
                )
            ).to_have_count(0)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_wording_cues_discard_response_after_focus_changes_before_next_request(
    ace_server,
    browser_name,
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            _install_code_cue_fetch_spy(page)
            page.evaluate("localStorage.setItem('ace-codebook-cues-enabled', '1')")

            rows = page.locator("#ace-headless-tree-mount .ace-ht-row--code")
            alpha_id = rows.nth(0).get_attribute("data-code-id")

            page.locator(".ace-sentence").nth(0).click()
            page.wait_for_function("window.__aceCueFetches.length === 1")
            page.locator(".ace-sentence").nth(1).click()
            page.evaluate(
                """
                (codeId) => {
                  const request = window.__aceCueFetches[0].body;
                  window.__aceCueFetches[0].resolve({
                    request_id: request.request_id,
                    current_index: request.current_index,
                    sentence_index: request.sentence_index,
                    start: request.start,
                    end: request.end,
                    cues: [{ code_id: codeId, rank: 0.9, matched_terms: ["first"] }],
                  });
                }
                """,
                alpha_id,
            )
            page.wait_for_timeout(80)

            expect(
                page.locator(
                    f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{alpha_id}"].ace-code-row--cue'
                )
            ).to_have_count(0)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_wording_cues_clear_on_failed_response(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            _install_code_cue_fetch_spy(page)
            page.evaluate("localStorage.setItem('ace-codebook-cues-enabled', '1')")

            alpha_id = page.locator("#ace-headless-tree-mount .ace-ht-row--code").nth(0).get_attribute("data-code-id")

            page.locator(".ace-sentence").nth(0).click()
            page.wait_for_function("window.__aceCueFetches.length === 1")
            page.evaluate(
                """
                (codeId) => {
                  const request = window.__aceCueFetches[0].body;
                  window.__aceCueFetches[0].resolve({
                    request_id: request.request_id,
                    current_index: request.current_index,
                    sentence_index: request.sentence_index,
                    start: request.start,
                    end: request.end,
                    cues: [{ code_id: codeId, rank: 0.5, matched_terms: ["first"] }],
                  });
                }
                """,
                alpha_id,
            )
            page.wait_for_selector(
                f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{alpha_id}"].ace-code-row--cue'
            )

            page.locator(".ace-sentence").nth(1).click()
            page.wait_for_function("window.__aceCueFetches.length === 2")
            page.evaluate("window.__aceCueFetches[1].resolve({}, 500)")

            expect(
                page.locator(
                    f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{alpha_id}"].ace-code-row--cue'
                )
            ).to_have_count(0)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_wording_cues_do_not_focus_scroll_or_apply_codes(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            apply_calls = []

            def record_apply(route):
                apply_calls.append(route.request.url)
                route.continue_()

            page.route("**/api/code/apply**", record_apply)
            page.goto(f"{ace_server}/code")
            _install_code_cue_fetch_spy(page)
            page.evaluate("localStorage.setItem('ace-codebook-cues-enabled', '1')")

            rows = page.locator("#ace-headless-tree-mount .ace-ht-row--code")
            focused_id = rows.nth(0).get_attribute("data-code-id")
            cued_id = rows.nth(1).get_attribute("data-code-id")
            rows.nth(0).focus()
            page.evaluate("document.getElementById('ace-headless-tree-mount').scrollTop = 12")
            before_scroll = page.evaluate("document.getElementById('ace-headless-tree-mount').scrollTop")

            page.evaluate("window.aceFocusSentence(0)")
            page.wait_for_function("window.__aceCueFetches.length === 1")
            page.evaluate(
                """
                (codeId) => {
                  const request = window.__aceCueFetches[0].body;
                  window.__aceCueFetches[0].resolve({
                    request_id: request.request_id,
                    current_index: request.current_index,
                    sentence_index: request.sentence_index,
                    start: request.start,
                    end: request.end,
                    cues: [{ code_id: codeId, rank: 0.8, matched_terms: ["first"] }],
                  });
                }
                """,
                cued_id,
            )
            page.wait_for_selector(
                f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{cued_id}"].ace-code-row--cue'
            )

            assert page.evaluate("document.activeElement.getAttribute('data-code-id')") == focused_id
            assert page.evaluate("document.getElementById('ace-headless-tree-mount').scrollTop") == before_scroll
            assert apply_calls == []

            style = page.evaluate(
                """
                (codeId) => {
                  const row = document.querySelector(`#ace-headless-tree-mount .ace-ht-row--code[data-code-id="${codeId}"]`);
                  const base = getComputedStyle(row);
                  const marker = getComputedStyle(row, "::after");
                  return {
                    background: base.backgroundColor,
                    markerWidth: marker.width,
                    markerBackground: marker.backgroundColor,
                  };
                }
                """,
                cued_id,
            )
            assert style["background"] != "rgba(0, 0, 0, 0)"
            assert style["markerWidth"] == "2px"
            assert style["markerBackground"] != "rgba(0, 0, 0, 0)"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_wording_cues_do_not_request_on_coded_text_view(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            _install_code_cue_init_counter(page)
            page.goto(f"{ace_server}/code")
            code_id = page.locator("#ace-headless-tree-mount .ace-ht-row--code").first.get_attribute("data-code-id")
            page.evaluate("localStorage.setItem('ace-codebook-cues-enabled', '1')")

            page.goto(f"{ace_server}/code/{code_id}/view")
            page.wait_for_selector("#code-view")
            page.wait_for_timeout(250)

            assert page.evaluate("window.__aceCueFetchCount") == 0
        finally:
            browser.close()
