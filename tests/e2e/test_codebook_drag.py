"""Drag-and-drop tests for the codebook sidebar.

WebKit's headless drag-and-drop pipeline does not emit the same dragenter
/ dragover sequence that Sortable.js relies on, so the WebKit case is
skipped — coverage on Chromium and Firefox is sufficient for the gesture.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from .conftest import browser_params


def _webkit_params():
    out = []
    for entry in browser_params():
        name = entry.values[0] if hasattr(entry, "values") else entry
        if name == "webkit":
            out.append(entry)
    return out


def _drag_param_names():
    """Drop WebKit from the parametrize set since headless drag is flaky.

    We still want a missing-engine to skip cleanly, so we re-walk
    browser_params() and rewrite WebKit's mark to a skip.
    """
    out = []
    for entry in browser_params():
        # entry is either a plain string ("chromium") or a pytest.param
        name = entry.values[0] if hasattr(entry, "values") else entry
        if name == "webkit":
            out.append(
                pytest.param(
                    "webkit",
                    marks=pytest.mark.skip(
                        reason="WebKit headless drag-and-drop is flaky with Sortable.js"
                    ),
                )
            )
        else:
            out.append(entry)
    return out


def _leave_inline_rename(page) -> None:
    page.wait_for_timeout(120)
    page.keyboard.press("Escape")
    page.evaluate(
        "() => document.querySelectorAll('[contenteditable=\"true\"]')"
        "  .forEach(el => { el.contentEditable = 'false'; })"
    )


def _pointer_drag_to(page, source, target, target_y_fraction: float = 0.9) -> None:
    source_box = source.bounding_box()
    target_box = target.bounding_box()
    assert source_box is not None
    assert target_box is not None

    start_x = source_box["x"] + source_box["width"] / 2
    start_y = source_box["y"] + source_box["height"] / 2
    end_x = target_box["x"] + target_box["width"] / 2
    end_y = target_box["y"] + target_box["height"] * target_y_fraction

    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x, start_y + 12, steps=4)
    page.mouse.move(end_x, end_y, steps=24)
    page.mouse.up()


@pytest.mark.parametrize("browser_name", _drag_param_names())
def test_drag_code_into_folder(ace_server, browser_name):
    """Create a folder, then drag Alpha onto its header → Alpha lands inside."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code?tree=legacy")
            page.wait_for_selector("#code-tree")

            # Create a folder by wrapping Alpha + Bravo (⌥⇧→). This gives
            # us a folder with at least one code already in it — a non-empty
            # children container is a more reliable drag target than an
            # empty role="group", because Sortable measures the destination
            # by hit-testing existing siblings.
            rows = page.query_selector_all(".ace-code-row")
            assert len(rows) >= 3, "fixture needs at least 3 codes (Alpha/Bravo/Charlie)"
            rows[1].click()  # Bravo
            page.keyboard.press("Alt+Shift+ArrowRight")
            page.wait_for_selector(".ace-code-folder-row", timeout=3000)
            _leave_inline_rename(page)

            # Now there's a folder containing Alpha + Bravo, and Charlie at
            # root. Drag Charlie INTO the folder by dropping onto an existing
            # code inside it (a known-good Sortable hit target).
            charlie_loc = page.locator(
                '#code-tree > .ace-code-row[data-code-id]'
            ).last  # last root-level code row (Charlie)
            target_loc = page.locator(
                '[role="group"] .ace-code-row[data-code-id]'
            ).first  # any existing child of the folder
            charlie_loc.wait_for(timeout=2000)
            target_loc.wait_for(timeout=2000)

            _pointer_drag_to(page, charlie_loc, target_loc)

            # All three codes should now live inside the folder.
            page.wait_for_function(
                "() => document.querySelectorAll("
                "  '[role=\"group\"] .ace-code-row[data-code-id]'"
                ").length >= 3",
                timeout=4000,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_codebook_drag_labels_do_not_select_text(ace_server, browser_name):
    """Dragging code rows should not leave selected sidebar label text behind."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code?tree=legacy")
            page.wait_for_selector("#code-tree")

            assert page.locator(".ace-code-row").first.evaluate(
                "(el) => getComputedStyle(el).userSelect || getComputedStyle(el).webkitUserSelect"
            ) == "none"
            assert page.locator(".ace-code-name").first.evaluate(
                "(el) => getComputedStyle(el).userSelect || getComputedStyle(el).webkitUserSelect"
            ) == "none"

            rows = page.query_selector_all(".ace-code-row")
            rows[1].click()
            page.keyboard.press("Alt+Shift+ArrowRight")
            page.wait_for_selector(".ace-code-folder-row", timeout=3000)
            _leave_inline_rename(page)

            assert page.locator(".ace-folder-label").first.evaluate(
                "(el) => getComputedStyle(el).userSelect || getComputedStyle(el).webkitUserSelect"
            ) == "none"

            page.locator(".ace-code-row").first.click()
            page.keyboard.press("F2")

            assert page.locator('.ace-code-name[contenteditable="true"]').first.evaluate(
                "(el) => getComputedStyle(el).userSelect || getComputedStyle(el).webkitUserSelect"
            ) == "text"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", _drag_param_names())
def test_codebook_drag_shows_drop_line(ace_server, browser_name):
    """Dragging between codebook rows should show a precise insertion line."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code?tree=legacy")
            page.wait_for_selector("#code-tree")

            rows = page.locator(".ace-code-row")
            assert rows.count() >= 2
            source_box = rows.nth(0).bounding_box()
            target_box = rows.nth(1).bounding_box()
            assert source_box is not None
            assert target_box is not None

            start_x = source_box["x"] + source_box["width"] / 2
            start_y = source_box["y"] + source_box["height"] / 2
            end_x = target_box["x"] + target_box["width"] / 2
            end_y = target_box["y"] + target_box["height"] - 2

            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(start_x, start_y + 12, steps=4)
            page.mouse.move(end_x, end_y, steps=12)

            page.wait_for_selector(".ace-codebook-drop-line.is-visible", timeout=2000)
            line_box = page.locator(".ace-codebook-drop-line").bounding_box()
            assert line_box is not None
            assert line_box["height"] >= 2
            assert line_box["width"] > 40

            page.mouse.up()
            page.wait_for_function(
                "() => !document.querySelector('.ace-codebook-drop-line.is-visible')",
                timeout=2000,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_codebook_drag_reorder_animation_is_disabled(ace_server, browser_name):
    """The drop line is the movement cue; sibling rows should not animate."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code?tree=legacy")
            page.wait_for_selector("#code-tree")

            assert page.evaluate(
                """
                () => Sortable
                  .get(document.getElementById("code-tree"))
                  .option("animation")
                """
            ) == 0
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", _drag_param_names())
def test_codebook_drag_uses_line_without_folder_preview(ace_server, browser_name):
    """Dragging into a folder should show only the insertion line."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code?tree=legacy")
            page.wait_for_selector("#code-tree")

            rows = page.query_selector_all(".ace-code-row")
            assert len(rows) >= 3
            rows[1].click()
            page.keyboard.press("Alt+Shift+ArrowRight")
            page.wait_for_selector(".ace-code-folder-row", timeout=3000)
            _leave_inline_rename(page)

            source = page.locator('#code-tree > .ace-code-row[data-code-id]').last
            target = page.locator('[role="group"] .ace-code-row[data-code-id]').first
            source_box = source.bounding_box()
            target_box = target.bounding_box()
            assert source_box is not None
            assert target_box is not None

            start_x = source_box["x"] + source_box["width"] / 2
            start_y = source_box["y"] + source_box["height"] / 2
            end_x = target_box["x"] + target_box["width"] / 2
            end_y = target_box["y"] + target_box["height"] - 2

            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(start_x, start_y + 12, steps=4)
            page.mouse.move(end_x, end_y, steps=12)

            page.wait_for_selector(".ace-codebook-drop-line.is-visible", timeout=2000)
            assert page.locator(".ace-code-folder-row--drop-target").count() == 0

            page.mouse.up()
            page.wait_for_function(
                "() => !document.querySelector('.ace-codebook-drop-line.is-visible')",
                timeout=2000,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", _drag_param_names())
def test_drag_folder_into_folder_preserves_drop_line_order(ace_server, browser_name):
    """Cross-folder drops must persist the exact sibling position at the line."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code?tree=legacy")
            page.wait_for_selector("#code-tree")

            rows = page.query_selector_all(".ace-code-row")
            assert len(rows) >= 3
            rows[1].click()
            page.keyboard.press("Alt+Shift+ArrowRight")
            page.wait_for_selector(".ace-code-folder-row", timeout=3000)
            _leave_inline_rename(page)

            source_folder_id = page.evaluate(
                """
                async () => {
                  const body = new URLSearchParams({
                    name: "Nested folder",
                    current_index: String(window.__aceCurrentIndex || 0),
                  });
                  const response = await fetch("/api/codes/folder", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body,
                  });
                  if (!response.ok) throw new Error(`folder create failed: ${response.status}`);
                  const html = await response.text();
                  htmx.process(document.body);
                  return html.match(/data-folder-id="([^"]+)"/)?.[1] || null;
                }
                """
            )
            page.reload()
            page.wait_for_selector("#code-tree")
            source_folder_id = page.evaluate(
                """
                () => Array.from(document.querySelectorAll(".ace-folder-block"))
                  .find((block) => block.querySelector(".ace-folder-label")?.textContent.trim() === "Nested folder")
                  ?.getAttribute("data-folder-id")
                """
            )
            assert source_folder_id

            source = page.locator(f'.ace-folder-block[data-folder-id="{source_folder_id}"]')
            target = page.locator(
                '.ace-folder-block:not([data-folder-id="%s"]) [role="group"] .ace-code-row[data-code-id]' % source_folder_id
            ).first
            source_box = source.locator(".ace-code-folder-row").bounding_box()
            target_box = target.bounding_box()
            assert source_box is not None
            assert target_box is not None

            start_x = source_box["x"] + source_box["width"] / 2
            start_y = source_box["y"] + source_box["height"] / 2
            end_x = target_box["x"] + target_box["width"] / 2
            end_y = target_box["y"] + target_box["height"] - 2

            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(start_x, start_y + 12, steps=4)
            page.mouse.move(end_x, end_y, steps=20)
            page.wait_for_selector(".ace-codebook-drop-line.is-visible", timeout=2000)
            page.mouse.up()

            page.wait_for_function(
                """
                (sourceId) => {
                  const moved = document.querySelector(`.ace-folder-block[data-folder-id="${sourceId}"]`);
                  return moved && moved.parentElement?.getAttribute("role") === "group";
                }
                """,
                arg=source_folder_id,
                timeout=4000,
            )
            names = page.evaluate(
                """
                (sourceId) => {
                  const moved = document.querySelector(`.ace-folder-block[data-folder-id="${sourceId}"]`);
                  const group = moved.parentElement;
                  return Array.from(group.children).map((child) =>
                    child.querySelector(".ace-code-name, .ace-folder-label")?.textContent.trim()
                  );
                }
                """,
                source_folder_id,
            )
            assert names[:3] == ["Alpha", "Nested folder", "Bravo"]
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", _drag_param_names())
def test_drag_nonempty_folder_into_folder_preserves_middle_position(ace_server, browser_name):
    """A folder's contents must not make the folder jump to the top of the target."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code?tree=legacy")
            page.wait_for_selector("#code-tree")

            rows = page.query_selector_all(".ace-code-row")
            assert len(rows) >= 3
            rows[1].click()
            page.keyboard.press("Alt+Shift+ArrowRight")
            page.wait_for_selector(".ace-code-folder-row", timeout=3000)
            _leave_inline_rename(page)

            page.evaluate(
                """
                async () => {
                  const current_index = String(window.__aceCurrentIndex || 0);
                  const folderBody = new URLSearchParams({
                    name: "Source folder",
                    current_index,
                  });
                  const folderResponse = await fetch("/api/codes/folder", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: folderBody,
                  });
                  if (!folderResponse.ok) throw new Error(`folder create failed: ${folderResponse.status}`);
                  await folderResponse.text();
                }
                """
            )
            page.reload()
            page.wait_for_selector("#code-tree")
            source_folder_id = page.evaluate(
                """
                () => Array.from(document.querySelectorAll(".ace-folder-block"))
                  .find((block) => block.querySelector(".ace-folder-label")?.textContent.trim() === "Source folder")
                  ?.getAttribute("data-folder-id")
                """
            )
            assert source_folder_id
            page.evaluate(
                """
                async (folderId) => {
                  const current_index = String(window.__aceCurrentIndex || 0);
                  const codeBody = new URLSearchParams({
                    name: "Nested child",
                    parent_id: folderId,
                    current_index,
                  });
                  const codeResponse = await fetch("/api/codes", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: codeBody,
                  });
                  if (!codeResponse.ok) throw new Error(`code create failed: ${codeResponse.status}`);
                  await codeResponse.text();
                }
                """,
                source_folder_id,
            )
            page.reload()
            page.wait_for_selector("#code-tree")

            source = page.locator(f'.ace-folder-block[data-folder-id="{source_folder_id}"]')
            target = page.locator(
                '.ace-folder-block:not([data-folder-id="%s"]) [role="group"] .ace-code-row[data-code-id]' % source_folder_id
            ).first
            source_box = source.locator(".ace-code-folder-row").bounding_box()
            target_box = target.bounding_box()
            assert source_box is not None
            assert target_box is not None

            start_x = source_box["x"] + source_box["width"] / 2
            start_y = source_box["y"] + source_box["height"] / 2
            end_x = target_box["x"] + target_box["width"] / 2
            end_y = target_box["y"] + target_box["height"] - 2

            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(start_x, start_y + 12, steps=4)
            page.mouse.move(end_x, end_y, steps=24)
            page.wait_for_selector(".ace-codebook-drop-line.is-visible", timeout=2000)
            page.mouse.up()

            page.wait_for_function(
                """
                (sourceId) => {
                  const moved = document.querySelector(`.ace-folder-block[data-folder-id="${sourceId}"]`);
                  return moved && moved.parentElement?.getAttribute("role") === "group";
                }
                """,
                arg=source_folder_id,
                timeout=4000,
            )
            result = page.evaluate(
                """
                (sourceId) => {
                  const moved = document.querySelector(`.ace-folder-block[data-folder-id="${sourceId}"]`);
                  const group = moved.parentElement;
                  const directNames = Array.from(group.children).map((child) =>
                    child.querySelector(".ace-code-name, .ace-folder-label")?.textContent.trim()
                  );
                  const movedChildNames = Array.from(
                    moved.querySelectorAll(':scope > [role="group"] > .ace-code-row .ace-code-name')
                  ).map((el) => el.textContent.trim());
                  return { directNames, movedChildNames };
                }
                """,
                source_folder_id,
            )
            assert result["directNames"][:3] == ["Alpha", "Source folder", "Bravo"]
            assert result["movedChildNames"] == ["Nested child"]
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", _drag_param_names())
def test_drag_nested_folder_above_first_code_keeps_first_child_position(
    ace_server, browser_name
):
    """A nested folder can move to the first child slot under its parent folder."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code?tree=legacy")
            page.wait_for_selector("#code-tree")

            rows = page.query_selector_all(".ace-code-row")
            assert len(rows) >= 3
            rows[1].click()
            page.keyboard.press("Alt+Shift+ArrowRight")
            page.wait_for_selector(".ace-code-folder-row", timeout=3000)
            _leave_inline_rename(page)

            parent_id = page.locator(".ace-folder-block").first.get_attribute("data-folder-id")
            assert parent_id
            page.evaluate(
                """
                async (parentId) => {
                  const current_index = String(window.__aceCurrentIndex || 0);
                  const folderBody = new URLSearchParams({
                    name: "Not used",
                    parent_id: parentId,
                    current_index,
                  });
                  const folderResponse = await fetch("/api/codes/folder", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: folderBody,
                  });
                  if (!folderResponse.ok) throw new Error(`folder create failed: ${folderResponse.status}`);
                  await folderResponse.text();
                }
                """,
                parent_id,
            )
            page.reload()
            page.wait_for_selector("#code-tree")
            source_folder_id = page.evaluate(
                """
                () => Array.from(document.querySelectorAll(".ace-folder-block"))
                  .find((block) => block.querySelector(".ace-folder-label")?.textContent.trim() === "Not used")
                  ?.getAttribute("data-folder-id")
                """
            )
            assert source_folder_id
            page.evaluate(
                """
                async (folderId) => {
                  const current_index = String(window.__aceCurrentIndex || 0);
                  for (const name of [
                    "Prefer not to use AI",
                    "AI replacing humans",
                    "Do not use AI at all",
                    "Not reliable or trustworthy",
                    "Privacy of data",
                    "Transparency or regulation",
                  ]) {
                    const codeBody = new URLSearchParams({
                      name,
                      parent_id: folderId,
                      current_index,
                    });
                    const codeResponse = await fetch("/api/codes", {
                      method: "POST",
                      headers: { "Content-Type": "application/x-www-form-urlencoded" },
                      body: codeBody,
                    });
                    if (!codeResponse.ok) throw new Error(`code create failed: ${codeResponse.status}`);
                    await codeResponse.text();
                  }
                }
                """,
                source_folder_id,
            )
            page.reload()
            page.wait_for_selector("#code-tree")

            source = page.locator(f'.ace-folder-block[data-folder-id="{source_folder_id}"]')
            first_code = page.locator(
                '.ace-folder-block[data-folder-id="%s"] > [role="group"] > .ace-code-row[data-code-id]' % parent_id
            ).first
            source_box = source.locator(".ace-code-folder-row").bounding_box()
            target_box = first_code.bounding_box()
            assert source_box is not None
            assert target_box is not None

            start_x = source_box["x"] + source_box["width"] / 2
            start_y = source_box["y"] + source_box["height"] / 2
            end_x = target_box["x"] + target_box["width"] / 2
            end_y = target_box["y"] + 2

            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(start_x, start_y + 12, steps=4)
            page.mouse.move(end_x, end_y, steps=24)
            page.wait_for_selector(".ace-codebook-drop-line.is-visible", timeout=2000)
            page.mouse.up()

            result = page.evaluate(
                """
                ({ parentId, sourceId }) => {
                  const parent = document.querySelector(`.ace-folder-block[data-folder-id="${parentId}"]`);
                  const moved = document.querySelector(`.ace-folder-block[data-folder-id="${sourceId}"]`);
                  const group = parent.querySelector(':scope > [role="group"]');
                  const directNames = Array.from(group.children).map((child) =>
                    child.querySelector(".ace-code-name, .ace-folder-label")?.textContent.trim()
                  );
                  const movedChildNames = Array.from(
                    moved.querySelectorAll(':scope > [role="group"] > .ace-code-row .ace-code-name')
                  ).map((el) => el.textContent.trim());
                  return { directNames, movedChildNames };
                }
                """,
                {"parentId": parent_id, "sourceId": source_folder_id},
            )
            assert result["directNames"][:3] == ["Not used", "Alpha", "Bravo"]
            assert result["movedChildNames"][:2] == ["Prefer not to use AI", "AI replacing humans"]
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", _webkit_params())
def test_tauri_drag_does_not_create_native_text_selection(ace_server, browser_name):
    """Fallback desktop drags should not create a sidebar text selection."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.add_init_script("window.__TAURI__ = { dialog: {} };")
            page.goto(f"{ace_server}/code?tree=legacy")
            page.wait_for_selector("#code-tree")
            page.evaluate(
                """
                () => {
                  window.__aceLastMouseDownDefaultPrevented = null;
                  document.addEventListener("mousedown", (event) => {
                    if (event.target.closest(".ace-code-row")) {
                      window.__aceLastMouseDownDefaultPrevented = event.defaultPrevented;
                    }
                  });
                }
                """
            )

            row = page.locator(".ace-code-row").first
            box = row.bounding_box()
            assert box is not None
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2

            page.mouse.move(x, y)
            page.mouse.down()
            assert page.evaluate("window.__aceLastMouseDownDefaultPrevented") is True
            page.mouse.move(x, y + 12, steps=4)

            assert page.evaluate("window.getSelection().toString()") == ""
            page.mouse.up()
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", _webkit_params())
def test_tauri_webkit_codebook_uses_sortable_fallback_drag(ace_server, browser_name):
    """The desktop app should not rely on WKWebView native HTML5 drag events."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.add_init_script("window.__TAURI__ = { dialog: {} };")
            page.goto(f"{ace_server}/code?tree=legacy")
            page.wait_for_selector("#code-tree")

            assert page.evaluate(
                """
                () => Sortable
                  .get(document.getElementById("code-tree"))
                  .option("forceFallback")
                """
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", _webkit_params())
def test_webkit_drag_code_into_folder_with_pointer_gesture(ace_server, browser_name):
    """Desktop WebKit must support the pointer gesture used in the macOS app."""
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code?tree=legacy")
            page.wait_for_selector("#code-tree")

            rows = page.query_selector_all(".ace-code-row")
            assert len(rows) >= 3
            rows[1].click()
            page.keyboard.press("Alt+Shift+ArrowRight")
            page.wait_for_selector(".ace-code-folder-row", timeout=3000)
            _leave_inline_rename(page)

            source = page.locator('#code-tree > .ace-code-row[data-code-id]').last
            target = page.locator('[role="group"] .ace-code-row[data-code-id]').first
            source.wait_for(timeout=2000)
            target.wait_for(timeout=2000)

            source_box = source.bounding_box()
            target_box = target.bounding_box()
            assert source_box is not None
            assert target_box is not None

            start_x = source_box["x"] + source_box["width"] / 2
            start_y = source_box["y"] + source_box["height"] / 2
            end_x = target_box["x"] + target_box["width"] / 2
            end_y = target_box["y"] + target_box["height"] - 2

            page.mouse.move(start_x, start_y)
            page.mouse.down()
            page.mouse.move(start_x, start_y + 12, steps=4)
            page.mouse.move(end_x, end_y, steps=24)
            page.wait_for_timeout(200)
            page.mouse.up()

            page.wait_for_function(
                "() => document.querySelectorAll("
                "  '[role=\"group\"] .ace-code-row[data-code-id]'"
                ").length >= 3",
                timeout=4000,
            )
        finally:
            browser.close()
