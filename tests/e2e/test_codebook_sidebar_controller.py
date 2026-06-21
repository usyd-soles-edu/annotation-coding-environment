from __future__ import annotations

import pytest
from playwright.sync_api import expect, sync_playwright

from .conftest import browser_params


def _headless_row_style(page, selector: str) -> dict[str, str]:
    return page.locator(selector).evaluate(
        """
        (row) => {
          const label = row.querySelector(".ace-ht-label");
          const rowStyle = getComputedStyle(row);
          const labelStyle = getComputedStyle(label);
          return {
            backgroundColor: rowStyle.backgroundColor,
            color: rowStyle.color,
            boxShadow: rowStyle.boxShadow,
            labelColor: labelStyle.color,
            labelFontWeight: labelStyle.fontWeight,
          };
        }
        """
    )


def _focused_headless_codebook_row(page) -> dict[str, str]:
    return page.locator(
        '#ace-headless-tree-mount [role="treeitem"][tabindex="0"]'
    ).evaluate(
        """
        (row) => {
          const label = row.querySelector(".ace-ht-label");
          const style = getComputedStyle(row);
          return {
            label: label ? label.textContent.trim() : "",
            outlineStyle: style.outlineStyle,
          };
        }
        """
    )


def _wait_for_focused_headless_label(page, label: str) -> None:
    page.wait_for_function(
        """
        (label) => document.querySelector(
          '#ace-headless-tree-mount [role="treeitem"][tabindex="0"] .ace-ht-label'
        )?.textContent.trim() === label
        """,
        arg=label,
        timeout=2000,
    )


def _apply_annotation(page, code_id: str, start: int, end: int, text: str) -> None:
    page.evaluate(
        """
        async ({ codeId, start, end, text }) => {
          await window.htmx.ajax("POST", "/api/code/apply", {
            target: "#text-panel",
            swap: "outerHTML",
            values: {
              code_id: codeId,
              start_offset: start,
              end_offset: end,
              selected_text: text,
              current_index: window.__aceCurrentIndex || 0,
            },
          });
        }
        """,
        {"codeId": code_id, "start": start, "end": end, "text": text},
    )


def _coded_text_row_style(page, selector: str) -> dict[str, str]:
    return page.locator(selector).evaluate(
        """
        (row) => {
          const idx = row.querySelector(".idx");
          const text = row.querySelector(".txt, .ct");
          const rowStyle = getComputedStyle(row);
          const idxStyle = getComputedStyle(idx);
          const textStyle = getComputedStyle(text);
          return {
            backgroundColor: rowStyle.backgroundColor,
            color: rowStyle.color,
            boxShadow: rowStyle.boxShadow,
            idxColor: idxStyle.color,
            textColor: textStyle.color,
          };
        }
        """
    )


def _record_apply_requests(page) -> list[str]:
    requests: list[str] = []

    def record(route):
        requests.append(route.request.url)
        route.continue_()

    page.route("**/api/code/apply**", record)
    return requests


@pytest.mark.parametrize("browser_name", browser_params())
def test_coding_cheat_sheet_lists_v_as_reserved_shortcut(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#text-panel")

            page.keyboard.press("Shift+/")
            sheet = page.locator("#ace-cheat-sheet")
            expect(sheet).to_be_visible()
            expect(sheet).to_contain_text("1 – 9, 0, a–y (not q v x z n)")
            expect(sheet).to_contain_text("V")
            expect(sheet).to_contain_text("View coded text")
        finally:
            browser.close()


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
def test_main_codebook_arrow_keys_move_one_row_without_extra_outline(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount [role='treeitem']")

            page.locator(
                "#ace-headless-tree-mount .ace-ht-row--code",
                has_text="Alpha",
            ).click()
            assert _focused_headless_codebook_row(page)["label"] == "Alpha"

            page.keyboard.press("ArrowDown")
            _wait_for_focused_headless_label(page, "Bravo")
            focused = _focused_headless_codebook_row(page)
            assert focused["label"] == "Bravo"
            assert focused["outlineStyle"] == "none"

            page.keyboard.press("ArrowDown")
            _wait_for_focused_headless_label(page, "Charlie")
            assert _focused_headless_codebook_row(page)["label"] == "Charlie"

            page.keyboard.press("ArrowUp")
            _wait_for_focused_headless_label(page, "Bravo")
            assert _focused_headless_codebook_row(page)["label"] == "Bravo"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_coded_text_view_current_code_row_is_quieter_than_keyboard_focus(
    ace_server, browser_name
):
    """The loaded code and keyboard cursor should not look like two selections."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount [role='treeitem']")

            coding_row = page.locator(
                "#ace-headless-tree-mount .ace-ht-row--code",
                has_text="Bravo",
            ).first
            code_id = coding_row.get_attribute("data-code-id")
            assert code_id
            coding_row.click()
            assert page.evaluate("document.body.dataset.activeZone") == "codebook"
            coding_selector = (
                f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{code_id}"]'
            )
            assert page.locator(
                '#ace-headless-tree-mount [role="treeitem"][tabindex="0"]'
            ).count() == 1
            assert page.locator(
                '#ace-headless-tree-mount [role="treeitem"][aria-selected]'
            ).count() == 0
            assert page.locator(
                '#ace-headless-tree-mount [role="treeitem"][aria-current]'
            ).count() == 0
            page.wait_for_function(
                """
                (selector) => getComputedStyle(document.querySelector(selector))
                  .backgroundColor === "rgb(241, 241, 238)"
                """,
                arg=coding_selector,
                timeout=2000,
            )
            coding_style = _headless_row_style(page, coding_selector)

            page.goto(f"{ace_server}/code/{code_id}/view")
            view_selector = (
                '#code-sidebar .ace-ht-row--code.ace-ht-row--current'
                f'[aria-current="page"][data-code-id="{code_id}"]'
            )
            page.wait_for_selector(view_selector)

            assert page.locator(
                '#code-sidebar .ace-ht-row--code[aria-current="page"]'
            ).count() == 1
            assert page.locator(
                "#code-sidebar .ace-ht-row--folder[aria-current]"
            ).count() == 0
            assert page.locator(
                '#code-sidebar [role="treeitem"][aria-selected]'
            ).count() == 0
            view_style = _headless_row_style(page, view_selector)
            assert view_style["backgroundColor"] == "rgba(0, 0, 0, 0)"
            assert view_style["boxShadow"] == "none"
            assert view_style["labelFontWeight"] == coding_style["labelFontWeight"]

            page.locator(view_selector).click()
            current_clicked_style = _headless_row_style(
                page,
                '#code-sidebar .ace-ht-row--code[tabindex="0"]',
            )
            assert current_clicked_style["backgroundColor"] == coding_style["backgroundColor"]
            assert current_clicked_style["boxShadow"] == coding_style["boxShadow"]

            page.locator(
                "#code-sidebar .ace-ht-row--code",
                has_text="Charlie",
            ).click()
            focused_style = _headless_row_style(
                page,
                '#code-sidebar .ace-ht-row--code[tabindex="0"]',
            )
            assert focused_style["backgroundColor"] == coding_style["backgroundColor"]
            assert focused_style["boxShadow"] == coding_style["boxShadow"]
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_coded_text_view_arrow_navigation_does_not_crossfade_codebook(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount [role='treeitem']")
            code_id = page.locator(
                "#ace-headless-tree-mount .ace-ht-row--code",
                has_text="Alpha",
            ).first.get_attribute("data-code-id")
            assert code_id

            page.goto(f"{ace_server}/code/{code_id}/view")
            page.wait_for_selector("#code-sidebar .ace-ht-row--code")
            page.evaluate(
                """
                () => {
                  window.__aceViewTransitionCount = 0;
                  document.startViewTransition = (callback) => {
                    window.__aceViewTransitionCount += 1;
                    callback();
                    return {
                      ready: Promise.resolve(),
                      finished: Promise.resolve(),
                      updateCallbackDone: Promise.resolve(),
                    };
                  };
                }
                """
            )

            page.locator(
                "#code-sidebar .ace-ht-row--code",
                has_text="Alpha",
            ).click()
            page.keyboard.press("ArrowDown")
            page.wait_for_function(
                """
                () => document.querySelector(
                  '#code-sidebar .ace-ht-row--code[tabindex="0"] .ace-ht-label'
                )?.textContent.trim() === 'Bravo'
                """
            )
            page.wait_for_function(
                """
                () => document.querySelector(
                  '#code-sidebar .ace-ht-row--code[aria-current="page"] .ace-ht-label'
                )?.textContent.trim() === 'Bravo'
                """
            )
            assert page.evaluate("window.__aceViewTransitionCount") == 0
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_coded_text_view_selected_rows_keep_text_readable(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount [role='treeitem']")
            code_id = page.locator(
                "#ace-headless-tree-mount .ace-ht-row--code",
                has_text="Alpha",
            ).first.get_attribute("data-code-id")
            assert code_id

            _apply_annotation(page, code_id, 0, 15, "First sentence.")
            _apply_annotation(page, code_id, 16, 32, "Second sentence.")

            page.goto(f"{ace_server}/code/{code_id}/view")
            page.wait_for_selector(".cv-track-row")
            page.wait_for_selector(".cv-row")

            page.locator(".cv-track-row").first.click()
            page.wait_for_selector(".cv-track-row.selected")
            track_style = _coded_text_row_style(page, ".cv-track-row.selected")
            assert track_style["backgroundColor"] == "rgb(241, 241, 238)"
            assert track_style["color"] == "rgb(0, 0, 0)"
            assert track_style["idxColor"] == "rgb(0, 0, 0)"
            assert track_style["textColor"] == "rgb(0, 0, 0)"

            page.locator(".cv-track-row .tick").first.click()
            page.wait_for_selector(".cv-row.selected")
            excerpt_style = _coded_text_row_style(page, ".cv-row.selected")
            assert excerpt_style["backgroundColor"] == "rgb(241, 241, 238)"
            assert excerpt_style["color"] == "rgb(0, 0, 0)"
            assert excerpt_style["idxColor"] == "rgb(0, 0, 0)"
            assert excerpt_style["textColor"] == "rgb(0, 0, 0)"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_coded_text_view_codebook_supports_editing_without_text_apply(
    ace_server, browser_name
):
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

            apply_requests = _record_apply_requests(page)

            visible_code_row.locator(".ace-ht-label").dblclick()
            page.wait_for_selector(".ace-ht-rename")
            rename = page.locator(".ace-ht-rename")
            rename.fill("Alpha View Rename")
            rename.press("Enter")

            page.wait_for_function(
                """
                async ({ itemId }) => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  return payload.items[itemId]?.name === "Alpha View Rename";
                }
                """,
                arg={"itemId": first_code_id},
            )

            page.locator("#code-search-input").fill("View Editable Folder")
            page.keyboard.press("Shift+Enter")
            page.wait_for_function(
                """
                async () => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  return Object.values(payload.items).some(
                    (item) => item.kind === "folder" && item.name === "View Editable Folder"
                  );
                }
                """
            )

            page.locator(
                "#ace-headless-tree-mount .ace-ht-row--folder",
                has_text="View Editable Folder",
            ).click()
            page.keyboard.press("Delete")

            page.wait_for_function(
                """
                async () => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  return !Object.values(payload.items).some(
                    (item) => item.kind === "folder" && item.name === "View Editable Folder"
                  );
                }
                """
            )

            page.keyboard.press("1")
            page.evaluate(
                """
                (codeId) => {
                  document.dispatchEvent(new CustomEvent("ace:apply-code", {
                    detail: { codeId, codeName: "Alpha View Rename" },
                  }));
                }
                """,
                first_code_id,
            )
            page.wait_for_timeout(200)
            assert apply_requests == []
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_audit_current_code_rename_updates_header_without_full_page_corruption(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount .ace-ht-row--code")
            alpha_row = page.locator(
                "#ace-headless-tree-mount .ace-ht-row--code",
                has_text="Alpha",
            ).first
            alpha_id = alpha_row.get_attribute("data-code-id")
            assert alpha_id

            page.goto(f"{ace_server}/code/{alpha_id}/view")
            page.wait_for_selector("#ace-headless-tree-mount .ace-ht-row--current")
            expect(page.locator(".cv-code-name")).to_have_text("Alpha")

            current_row = page.locator(
                f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{alpha_id}"]'
            )
            current_row.locator(".ace-ht-label").dblclick()
            rename = page.locator(
                f'#ace-headless-tree-mount .ace-ht-rename[data-item-id="{alpha_id}"]'
            )
            expect(rename).to_be_visible()
            rename.fill("Alpha Audit Rename")
            rename.press("Enter")

            expect(page.locator(".cv-code-name")).to_have_text("Alpha Audit Rename")
            expect(page.locator("#cv-tracks")).to_be_visible()
            expect(page.locator("#ace-headless-tree-mount")).to_have_attribute(
                "data-codebook-mode", "audit"
            )
            expect(page.locator("#text-panel")).to_have_count(0)
            expect(page).to_have_url(f"{ace_server}/code/{alpha_id}/view")
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_coded_text_view_codebook_enter_renames_and_space_views_focused_code(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount .ace-ht-row--code")
            code_rows = page.locator("#ace-headless-tree-mount .ace-ht-row--code")
            alpha_id = code_rows.nth(0).get_attribute("data-code-id")
            bravo_id = code_rows.nth(1).get_attribute("data-code-id")
            charlie_id = code_rows.nth(2).get_attribute("data-code-id")
            assert alpha_id
            assert bravo_id
            assert charlie_id

            page.goto(f"{ace_server}/code/{alpha_id}/view")
            page.wait_for_selector("#ace-headless-tree-mount .ace-ht-row--code")
            assert page.evaluate(
                """
                () => ({
                  mode: window.__aceHeadlessTreeController?.getMode?.(),
                  policy: window.__aceHeadlessTreeController?.modePolicy?.(),
                })
                """
            ) == {
                "mode": "audit",
                "policy": {
                    "enterOnCode": "rename",
                    "enterOnFolder": "toggle",
                    "spaceOnCode": "view",
                    "autoViewOnFocus": True,
                    "editingDisabled": False,
                },
            }

            bravo_row = page.locator(
                f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{bravo_id}"]'
            )
            bravo_row.focus()
            page.keyboard.press("Enter")
            expect(
                page.locator(
                    f'#ace-headless-tree-mount .ace-ht-rename[data-item-id="{bravo_id}"]'
                )
            ).to_be_visible()
            expect(page).to_have_url(f"{ace_server}/code/{alpha_id}/view")
            page.keyboard.press("Escape")
            expect(page.locator(".ace-ht-rename")).to_have_count(0)

            charlie_row = page.locator(
                f'#ace-headless-tree-mount .ace-ht-row--code[data-code-id="{charlie_id}"]'
            )
            charlie_row.focus()
            page.keyboard.press(" ")
            page.wait_for_url(f"{ace_server}/code/{charlie_id}/view")
            page.wait_for_function(
                """
                (codeId) => document.querySelector(
                  '#code-sidebar .ace-ht-row--code[aria-current="page"]'
                )?.dataset.codeId === codeId
                """,
                arg=charlie_id,
            )

            page.evaluate(
                """
                (codeId) => {
                  const row = document.querySelector(
                    `#ace-headless-tree-mount .ace-ht-row--code[data-code-id="${codeId}"]`
                  );
                  window.__aceHeadlessTreeController.focusTreeItem(row);
                }
                """,
                arg=bravo_id,
            )
            page.wait_for_url(f"{ace_server}/code/{bravo_id}/view")
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
