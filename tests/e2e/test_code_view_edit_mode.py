from __future__ import annotations

import pytest
from playwright.sync_api import expect, sync_playwright

from .conftest import browser_params


def _first_code_id(page) -> str:
    return page.evaluate(
        """
        async () => {
          const tree = await fetch("/api/codes/tree").then((r) => r.json());
          const code = Object.values(tree.items).find((item) => item.kind === "code");
          if (!code) throw new Error("no code row in test project");
          return code.id;
        }
        """
    )


def _code_ids(page) -> list[str]:
    return page.evaluate(
        """
        async () => {
          const tree = await fetch("/api/codes/tree").then((r) => r.json());
          return Object.values(tree.items)
            .filter((item) => item.kind === "code")
            .map((item) => item.id);
        }
        """
    )


def _create_folder(page, name: str) -> str:
    return page.evaluate(
        """
        async (name) => {
          const res = await fetch("/api/codes/folder", {
            method: "POST",
            body: new URLSearchParams({ name, codebook_mode: "audit" }),
          });
          if (!res.ok) throw new Error(`folder create failed: ${res.status}`);
          const tree = await fetch("/api/codes/tree").then((r) => r.json());
          const folder = Object.values(tree.items).find(
            (item) => item.kind === "folder" && item.name === name
          );
          if (!folder) throw new Error("folder not found after create");
          return folder.id;
        }
        """,
        name,
    )


def _open_first_code_view(page, ace_server: str) -> str:
    page.goto(f"{ace_server}/code")
    page.wait_for_selector("#ace-headless-tree-mount")
    code_id = _first_code_id(page)
    page.goto(f"{ace_server}/code/{code_id}/view")
    page.wait_for_selector("#code-view")
    return code_id


@pytest.mark.parametrize("browser_name", browser_params())
def test_audit_mode_switch_is_visible_and_moves_focus(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _open_first_code_view(page, ace_server)

            expect(page.locator(".cv-mode-band")).to_be_visible()
            expect(page.get_by_role("button", name="Review excerpts")).to_have_attribute("aria-pressed", "true")
            expect(page.get_by_role("button", name="Edit code details")).to_have_attribute("aria-pressed", "false")

            page.get_by_role("button", name="Edit code details").click()

            expect(page.get_by_role("button", name="Review excerpts")).to_have_attribute("aria-pressed", "false")
            expect(page.get_by_role("button", name="Edit code details")).to_have_attribute("aria-pressed", "true")
            expect(page.locator("#cv-mode-title")).to_have_text("Edit code details")
            expect(page.locator("#cv-mode-status")).to_have_text("Editing")
            expect(page.locator("#cv-tracks-heading")).to_have_text("Edit code details")
            expect(page.locator("#cv-code-editor")).to_be_visible()
            expect(page.locator("#cv-source-review")).to_be_hidden()
            expect(page.locator("#cv-live")).to_have_text("Edit code details mode")
            assert page.evaluate("document.activeElement?.id") == "cv-code-name"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_audit_mode_switch_keyboard_flow_restores_visible_focus(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _open_first_code_view(page, ace_server)

            page.get_by_role("button", name="Edit code details").focus()
            page.keyboard.press("Enter")
            expect(page.locator("#cv-code-editor")).to_be_visible()
            assert page.evaluate("document.activeElement?.id") == "cv-code-name"

            page.keyboard.press("Escape")
            expect(page.locator("#cv-source-review")).to_be_visible()
            expect(page.locator("#cv-code-editor")).to_be_hidden()
            expect(page.locator("#cv-tracks-heading")).to_have_text("Sources")
            assert page.evaluate("document.activeElement?.id") == "cv-mode-review"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_escape_from_dirty_edit_mode_prompts_before_leaving_editor(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            _open_first_code_view(page, ace_server)

            page.get_by_role("button", name="Edit code details").click()
            page.locator("#cv-code-name").fill("Changed but not saved")

            messages = []

            def dismiss_dialog(dialog):
                messages.append(dialog.message)
                dialog.dismiss()

            page.once("dialog", dismiss_dialog)
            with page.expect_event("dialog") as dialog_info:
                page.keyboard.press("Escape")
            dialog_info.value
            assert messages == ["Discard unsaved code edits?"]

            expect(page.locator("#cv-code-editor")).to_be_visible()
            expect(page.locator("#cv-source-review")).to_be_hidden()
            assert page.evaluate("document.activeElement?.id") == "cv-code-name"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_edit_mode_save_button_persists_code_details(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount")
            folder_id = _create_folder(page, "Review folder")
            code_id = _first_code_id(page)
            page.goto(f"{ace_server}/code/{code_id}/view")
            page.wait_for_selector("#code-view")

            page.get_by_role("button", name="Edit code details").click()
            expect(page.get_by_role("button", name="Save changes")).to_be_visible()

            with page.expect_response(
                lambda response: f"/api/codes/{code_id}/parent" in response.url
                and response.request.method == "PUT"
            ):
                page.locator("#cv-code-folder").select_option(folder_id)

            page.reload(wait_until="networkidle")
            page.get_by_role("button", name="Edit code details").click()
            expect(page.locator("#cv-code-folder")).to_have_value(folder_id)

            page.locator("#cv-code-name").fill("Alpha reviewed")
            page.locator("#cv-code-definition").fill("Definition saved from audit review.")
            with page.expect_response(
                lambda response: f"/api/codes/{code_id}" in response.url
                and "/parent" not in response.url
                and response.request.method == "PUT"
            ):
                page.get_by_role("button", name="Save changes").click()

            expect(page.locator(".cv-code-name")).to_have_text("Alpha reviewed")
            expect(page.locator("#cv-code-name")).to_have_value("Alpha reviewed")
            expect(page.locator("#cv-code-definition")).to_have_value("Definition saved from audit review.")
            expect(page.locator("#cv-code-folder")).to_have_value(folder_id)

            page.reload(wait_until="networkidle")
            page.get_by_role("button", name="Edit code details").click()
            expect(page.locator("#cv-code-name")).to_have_value("Alpha reviewed")
            expect(page.locator("#cv-code-definition")).to_have_value("Definition saved from audit review.")
            expect(page.locator("#cv-code-folder")).to_have_value(folder_id)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_cancelled_dirty_code_switch_restores_current_codebook_focus(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount")
            code_ids = _code_ids(page)
            assert len(code_ids) >= 2
            first_id, second_id = code_ids[:2]
            page.goto(f"{ace_server}/code/{first_id}/view")
            page.wait_for_selector("#code-view")

            page.get_by_role("button", name="Edit code details").click()
            page.locator("#cv-code-name").fill("Dirty but cancelled")

            messages = []

            def dismiss_dialog(dialog):
                messages.append(dialog.message)
                dialog.dismiss()

            page.locator(f'.ace-ht-row--code[data-code-id="{second_id}"]').focus()
            assert page.evaluate(
                "() => document.activeElement?.closest?.('.ace-ht-row--code')?.dataset?.codeId"
            ) == second_id

            page.once("dialog", dismiss_dialog)
            with page.expect_event("dialog") as dialog_info:
                page.evaluate(
                    """
                    (codeId) => document.dispatchEvent(
                      new CustomEvent("ace:view-code", { detail: { codeId } })
                    )
                    """,
                    second_id,
                )
            dialog_info.value

            assert messages == ["Discard unsaved code edits?"]
            expect(page.locator(".cv-code-name")).to_have_text("Alpha")
            expect(page.locator(f'.ace-ht-row--code[data-code-id="{first_id}"]')).to_have_attribute("tabindex", "0")
            assert page.evaluate(
                "() => document.activeElement?.closest?.('.ace-ht-row--code')?.dataset?.codeId"
            ) == first_id
        finally:
            browser.close()
