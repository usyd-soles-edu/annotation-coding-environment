"""Context-menu tests for the codebook sidebar.

The single contextmenu dispatcher in bridge.js (around L2236) routes
right-clicks on code rows / folder rows / empty tree to three different
item lists. These tests confirm:

  * Right-click on a code row opens the menu with the expected items.
  * Outside-click and Esc both dismiss the menu.

Submenu navigation (Move to folder ▸ …) is not exercised — keyboard
gestures already cover the underlying move actions, and submenu opening
is sensitive to mouse-hover timing across engines.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from .conftest import browser_params


_EXPECTED_CODE_ITEMS = [
    "Convert to folder",
    "Cut",
    "Paste here",
    "Rename",
    "Change colour",
    "Delete",
]
CODE_ROW = ".ace-ht-row--code"
CODE_NAME = ".ace-ht-label"
FOLDER_ROW = ".ace-ht-row--folder"
FOLDER_NAME = ".ace-ht-label"


@pytest.mark.parametrize("browser_name", browser_params())
def test_right_click_on_code_row_opens_menu_with_expected_items(
    ace_server, browser_name
):
    """Right-click on a code row → .ace-context-menu appears containing
    Cut, Paste here, Rename, and Delete entries."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(CODE_ROW)

            row = page.query_selector(CODE_ROW)
            assert row is not None
            row.click(button="right")

            page.wait_for_selector(".ace-context-menu", timeout=2000)
            labels = page.evaluate(
                "() => Array.from(document.querySelectorAll("
                "  '.ace-context-menu .ace-context-menu-item'"
                ")).map(el => el.textContent.trim())"
            )
            for expected in _EXPECTED_CODE_ITEMS:
                assert any(expected in label for label in labels), (
                    f"expected '{expected}' in context menu, got {labels!r}"
                )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_context_menu_convert_code_to_folder(ace_server, browser_name):
    """Code-row context menu exposes the conversion action and applies it."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(CODE_ROW)

            row = page.locator(CODE_ROW).first
            code_name = row.locator(CODE_NAME).inner_text().strip()
            row.click(button="right")
            page.wait_for_selector(".ace-context-menu", timeout=2000)
            page.locator(".ace-context-menu .ace-context-menu-item", has_text="Convert to folder").click()

            page.wait_for_function(
                "([label, folderRow, folderName]) => Array.from(document.querySelectorAll(folderRow))"
                "      .some(r => r.querySelector(folderName)?.textContent.trim() === label)",
                arg=[code_name, FOLDER_ROW, FOLDER_NAME],
                timeout=3000,
            )
            assert page.evaluate(
                "([label, codeRow, codeName]) => Array.from(document.querySelectorAll(codeRow))"
                "      .every(r => r.querySelector(codeName)?.textContent.trim() !== label)",
                [code_name, CODE_ROW, CODE_NAME],
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_context_menu_change_colour_updates_headless_code_row(ace_server, browser_name):
    """Change colour opens from a headless row and applies the selected swatch."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(CODE_ROW)

            row = page.locator(CODE_ROW).first
            code_id = row.get_attribute("data-code-id")
            assert code_id
            before = row.evaluate("el => el.style.getPropertyValue('--row-colour').trim()")

            row.click(button="right")
            page.wait_for_selector(".ace-context-menu", timeout=2000)
            page.locator(
                ".ace-context-menu .ace-context-menu-item",
                has_text="Change colour",
            ).click()
            page.wait_for_selector(".ace-colour-popover", timeout=2000)

            swatch = page.locator(".ace-colour-popover .ace-colour-swatch").nth(1)
            target_colour = swatch.evaluate("el => getComputedStyle(el).backgroundColor")
            swatch.click()

            page.wait_for_function(
                """
                async ({ codeId, before }) => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  const colour = payload.items[codeId]?.colour || "";
                  const row = document.querySelector(
                    `.ace-ht-row--code[data-code-id="${codeId}"]`
                  );
                  const stripe = row?.style.getPropertyValue("--row-colour").trim() || "";
                  return colour && colour !== before && stripe.toLowerCase() === colour.toLowerCase();
                }
                """,
                arg={"codeId": code_id, "before": before},
                timeout=3000,
            )
            assert target_colour
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_row_actions_button_opens_context_menu_by_click(ace_server, browser_name):
    """The row actions button exposes the same menu without requiring right-click."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(CODE_ROW)

            row = page.locator(CODE_ROW).first
            row.hover()
            row.locator(".ace-ht-row-menu").click()

            page.wait_for_selector(".ace-context-menu", timeout=2000)
            labels = page.evaluate(
                """
                () => Array.from(document.querySelectorAll(
                  ".ace-context-menu .ace-context-menu-item"
                )).map((el) => el.textContent.trim())
                """
            )
            assert any("Move to" in label for label in labels), labels
            assert any("Cut" in label for label in labels), labels
            assert any("Paste here" in label for label in labels), labels
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_context_menu_move_to_root_is_single_pointer_path(ace_server, browser_name):
    """A child code can be moved back to root through pointer menu actions."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(CODE_ROW)

            page.evaluate(
                """
                async () => {
                  let payload = await fetch("/api/codes/tree").then((r) => r.json());
                  let folder = Object.values(payload.items).find(
                    (item) => item.kind === "folder" && item.id !== "root"
                  );
                  if (!folder) {
                    const create = await fetch("/api/codes/folder", {
                      method: "POST",
                      headers: { "Content-Type": "application/x-www-form-urlencoded" },
                      body: new URLSearchParams({
                        name: "Menu target",
                        current_index: String(window.__aceCurrentIndex || 0),
                      }),
                    });
                    if (!create.ok) throw new Error(`folder create failed: ${create.status}`);
                    await create.text();
                    payload = await fetch("/api/codes/tree").then((r) => r.json());
                    folder = Object.values(payload.items).find(
                      (item) => item.kind === "folder" && item.name === "Menu target"
                    );
                  }
                  const rootCode = payload.items.root.children
                    .map((id) => payload.items[id])
                    .find((item) => item?.kind === "code");
                  if (!rootCode || !folder) throw new Error("missing root code or folder");
                  const move = await fetch(`/api/codes/${rootCode.id}/parent`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: new URLSearchParams({
                      parent_id: folder.id,
                      target_order_ids: JSON.stringify([rootCode.id]),
                      current_index: String(window.__aceCurrentIndex || 0),
                    }),
                  });
                  const moveText = await move.text();
                  if (!move.ok) throw new Error(`move failed: ${move.status}: ${moveText}`);
                }
                """
            )
            page.reload()
            page.wait_for_selector("#ace-headless-tree-mount .ace-ht-row--code[aria-level='2']")

            child = page.locator("#ace-headless-tree-mount .ace-ht-row--code[aria-level='2']").first
            child_name = child.locator(CODE_NAME).inner_text().strip()
            child.locator(".ace-ht-row-menu").click()
            page.wait_for_selector(".ace-context-menu", timeout=2000)
            page.locator(".ace-context-menu .ace-context-menu-item", has_text="Move to root").click()

            page.wait_for_function(
                """
                (label) => Array.from(document.querySelectorAll(
                  "#ace-headless-tree-mount .ace-ht-row--code[aria-level='1'] .ace-ht-label"
                )).some((el) => el.textContent.trim() === label)
                """,
                arg=child_name,
                timeout=3000,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_outside_click_dismisses_context_menu(ace_server, browser_name):
    """Clicking anywhere outside the menu closes it."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(CODE_ROW)

            row = page.query_selector(CODE_ROW)
            assert row is not None
            row.click(button="right")
            page.wait_for_selector(".ace-context-menu", timeout=2000)
            # _renderContextMenu registers its outside-click + Esc listeners
            # via setTimeout(..., 0) — give the JS event loop a tick to flush
            # before we try to trigger them. Otherwise the Esc/click that
            # follows beats the listener registration and the menu sticks.
            page.wait_for_timeout(50)

            # Click somewhere clearly outside the menu — the text panel
            # is the safest target since it's not a sidebar interactive.
            page.click("#text-panel")
            page.wait_for_selector(".ace-context-menu", state="detached", timeout=2000)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_escape_dismisses_context_menu(ace_server, browser_name):
    """Esc dismisses the context menu (handler bound at capture phase)."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(CODE_ROW)

            row = page.query_selector(CODE_ROW)
            assert row is not None
            row.click(button="right")
            page.wait_for_selector(".ace-context-menu", timeout=2000)
            # See the outside-click test above for why we wait. The Esc
            # handler is added via setTimeout(..., 0) inside
            # _renderContextMenu — without this the keypress beats the
            # listener registration.
            page.wait_for_timeout(50)

            page.keyboard.press("Escape")
            page.wait_for_selector(".ace-context-menu", state="detached", timeout=2000)
        finally:
            browser.close()
