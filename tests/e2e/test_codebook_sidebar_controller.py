from __future__ import annotations

import pytest
from playwright.sync_api import expect, sync_playwright

from .conftest import browser_params


@pytest.mark.parametrize("browser_name", browser_params())
def test_coding_and_coded_text_views_load_headless_sidebar_controller(
    ace_server, browser_name
):
    """Coding and coded-text views should share the same sidebar renderer."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount [role='treeitem']")

            expect(page.locator("#ace-headless-tree-mount")).to_have_attribute(
                "data-ace-tree-controller", "headless"
            )
            assert page.evaluate("() => !!window.__aceHeadlessTreeController") is True

            code_id = page.locator(".ace-ht-row--code").first.get_attribute("data-code-id")
            assert code_id
            page.goto(f"{ace_server}/code/{code_id}/view")
            page.wait_for_selector("#ace-headless-tree-mount [role='treeitem']")

            assert page.evaluate("() => !!window.__aceHeadlessTreeController") is True
            expect(page.locator("#ace-headless-tree-mount")).to_have_attribute(
                "data-ace-tree-controller", "headless"
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_coded_text_view_codebook_is_read_only(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount [role='treeitem']")
            code_id = page.locator(".ace-ht-row--code").first.get_attribute("data-code-id")
            assert code_id

            page.goto(f"{ace_server}/code/{code_id}/view")
            page.wait_for_selector("#ace-headless-tree-mount .ace-ht-row--code")
            visible_code_row = page.locator(
                "#ace-headless-tree-mount .ace-ht-row--code:not([aria-hidden='true'])"
            ).first
            first_code_id = visible_code_row.get_attribute("data-code-id")
            assert first_code_id

            visible_code_row.locator(".ace-ht-label").dblclick()
            page.wait_for_timeout(200)
            expect(page.locator("[contenteditable='true']")).to_have_count(0)

            visible_code_row.click()
            page.keyboard.press("Delete")
            page.wait_for_timeout(200)

            assert page.evaluate(
                """
                async ({ itemId }) => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  return !!payload.items[itemId];
                }
                """,
                {"itemId": first_code_id},
            )

            visible_code_row.click(button="right")
            expect(page.locator(".ace-context-menu-item", has_text="Rename")).to_have_count(0)
            expect(page.locator(".ace-context-menu-item", has_text="Delete")).to_have_count(0)

            page.locator("#code-search-input").fill("Read only folder")
            page.keyboard.press("Shift+Enter")
            page.wait_for_timeout(200)

            assert page.evaluate(
                """
                async () => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  return !Object.values(payload.items).some(
                    (item) => item.kind === "folder" && item.name === "Read only folder"
                  );
                }
                """
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_codebook_nested_levels_have_visible_depth_guides(ace_server, browser_name):
    """Nested codebook rows should expose depth without adding extra controls."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount")

            ids = page.evaluate(
                """
                async () => {
                  async function createFolder(name, parentId = "") {
                    const body = new URLSearchParams({
                      name,
                      parent_id: parentId,
                      current_index: String(window.__aceCurrentIndex || 0),
                    });
                    const response = await fetch("/api/codes/folder", {
                      method: "POST",
                      headers: { "Content-Type": "application/x-www-form-urlencoded" },
                      body,
                    });
                    if (!response.ok) throw new Error(`folder create failed: ${response.status}`);
                    await response.text();
                    const payload = await fetch("/api/codes/tree").then((r) => r.json());
                    return Object.values(payload.items).find((item) => item.name === name)?.id;
                  }
                  const parent = await createFolder("Depth parent");
                  const child = await createFolder("Depth child", parent);
                  return { parent, child };
                }
                """
            )
            page.reload()
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            parent = page.locator(
                f'#ace-headless-tree-mount .ace-ht-row[data-item-id="{ids["parent"]}"]'
            )
            child = page.locator(
                f'#ace-headless-tree-mount .ace-ht-row[data-item-id="{ids["child"]}"]'
            )
            expect(parent.locator(".ace-ht-level-chip")).to_have_count(0)
            expect(child.locator(".ace-ht-level-chip")).to_have_count(0)
            expect(parent).to_have_attribute("data-level", "1")
            expect(child).to_have_attribute("data-level", "2")
            assert child.evaluate("el => getComputedStyle(el, '::before').borderLeftWidth") == "1px"
        finally:
            browser.close()
