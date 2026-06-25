from __future__ import annotations

import json

import pytest
from playwright.sync_api import expect, sync_playwright

from .conftest import browser_params


def _open_import_dialog(page, csv_path: str) -> None:
    page.evaluate(
        """
        async (path) => {
          window._aceCodebookImportReturnFocus = document.getElementById("codebook-menu-btn");
          await window.htmx.ajax("POST", "/api/codes/import/preview-path", {
            values: {
              path,
              current_index: String(window.__aceCurrentIndex || 0),
            },
            target: "#modal-container",
            swap: "innerHTML",
          });
        }
        """,
        arg=csv_path,
    )
    page.wait_for_selector("dialog.ace-codebook-import-ledger[open]")


def _api_code_names(page) -> list[str]:
    return page.evaluate(
        """
        async () => {
          const payload = await fetch("/api/codes/tree").then((r) => r.json());
          return Object.values(payload.items)
            .filter((item) => item.kind === "code")
            .map((item) => item.name);
        }
        """
    )


@pytest.mark.parametrize("browser_name", browser_params())
def test_codebook_import_ledger_keyboard_refresh_import_and_undo(
    ace_server, browser_name, tmp_path
):
    csv_path = tmp_path / "codebook.csv"
    csv_path.write_text(
        "Code Label,Theme,Dictionary Definition,Empty\n"
        "Access,Equity,Barriers to using feedback,\n"
        "Alpha,Existing,Already present,\n"
        ",Workflow,Missing name,\n"
        "Reflection,Workflow,Reflective revision,\n",
        encoding="utf-8",
    )

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#codebook-menu-btn")

            _open_import_dialog(page, str(csv_path))
            expect(page.locator("#codebook-import-title")).to_be_focused()
            expect(page.locator("[data-codebook-import-counts]")).to_contain_text(
                "2 new"
            )

            page.locator("#codebook-import-tab-match").focus()
            page.keyboard.press("ArrowRight")
            expect(page.locator("#codebook-import-tab-review")).to_be_focused()
            expect(page.locator("#codebook-import-panel-review")).to_be_visible()

            page.keyboard.press("ArrowRight")
            expect(page.locator("#codebook-import-tab-skipped")).to_be_focused()
            expect(page.locator("#codebook-import-panel-skipped")).to_be_visible()
            expect(page.locator("#codebook-import-skipped")).to_contain_text(
                "missing code name"
            )

            page.locator("#codebook-map-name").select_option(label="Empty")
            expect(page.locator("[data-codebook-import-counts]")).to_contain_text(
                "0 new"
            )
            expect(page.locator("#codebook-import-commit")).to_be_disabled()

            page.locator("#codebook-map-name").select_option(label="Code Label")
            expect(page.locator("[data-codebook-import-counts]")).to_contain_text(
                "2 new"
            )
            expect(page.locator("#codebook-import-commit")).to_be_enabled()
            codes_json = page.locator("#codebook-import-commit").get_attribute(
                "data-codes"
            )
            assert codes_json is not None
            assert [code["name"] for code in json.loads(codes_json)] == [
                "Access",
                "Reflection",
            ]

            page.keyboard.press("Escape")
            expect(page.locator("dialog.ace-codebook-import-ledger")).to_have_count(0)
            expect(page.locator("#codebook-menu-btn")).to_be_focused()

            _open_import_dialog(page, str(csv_path))
            page.locator("#codebook-import-commit").click()
            page.wait_for_function(
                """
                async () => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  const names = Object.values(payload.items)
                    .filter((item) => item.kind === "code")
                    .map((item) => item.name);
                  return names.includes("Access") && names.includes("Reflection");
                }
                """
            )
            assert "Access" in _api_code_names(page)
            assert "Reflection" in _api_code_names(page)

            page.evaluate(
                """
                async () => {
                  await window.htmx.ajax("POST", "/api/undo", {
                    target: "#text-panel",
                    swap: "outerHTML",
                    values: { current_index: String(window.__aceCurrentIndex || 0) },
                  });
                }
                """
            )
            page.wait_for_function(
                """
                async () => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  const names = Object.values(payload.items)
                    .filter((item) => item.kind === "code")
                    .map((item) => item.name);
                  return !names.includes("Access") && !names.includes("Reflection");
                }
                """
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_codebook_import_ledger_has_no_horizontal_scroll_on_narrow_viewport(
    ace_server, browser_name, tmp_path
):
    csv_path = tmp_path / "codebook.csv"
    csv_path.write_text(
        "Code Label,Theme,Dictionary Definition\n"
        "Very long imported code name that should not force horizontal scrolling,"
        "Long folder,"
        "Long definition text that should remain contained inside the modal\n",
        encoding="utf-8",
    )

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page(viewport={"width": 390, "height": 700})
            page.goto(f"{ace_server}/code")
            before_scroll_width = page.evaluate(
                "() => document.documentElement.scrollWidth"
            )
            _open_import_dialog(page, str(csv_path))
            scroll_state = page.evaluate(
                """
                () => {
                  const dialog = document.querySelector("dialog.ace-codebook-import-ledger");
                  return {
                    documentScrollWidth: document.documentElement.scrollWidth,
                    dialogScrollWidth: dialog.scrollWidth,
                    dialogClientWidth: dialog.clientWidth,
                  };
                }
                """
            )
            assert scroll_state["documentScrollWidth"] <= before_scroll_width
            assert scroll_state["dialogScrollWidth"] <= scroll_state["dialogClientWidth"]
        finally:
            browser.close()
