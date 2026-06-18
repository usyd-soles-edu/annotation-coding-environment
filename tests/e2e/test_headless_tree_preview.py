import sys

import pytest
from playwright.sync_api import expect, sync_playwright

from .conftest import browser_params


def _code_labels(page, selector: str) -> list[str]:
    return page.locator(selector).evaluate_all(
        "(nodes) => nodes.map((node) => node.textContent.trim()).filter(Boolean)"
    )


def _api_code_labels(page) -> list[str]:
    return page.evaluate(
        """
        async () => {
          const payload = await fetch("/api/codes/tree").then((r) => r.json());
          return Object.values(payload.items)
            .filter((item) => item.kind === "code")
            .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
            .map((item) => item.name);
        }
        """
    )


def _pointer_drag_between(page, source, target, *, target_y_fraction: float = 0.5) -> None:
    source.scroll_into_view_if_needed()
    target.scroll_into_view_if_needed()
    source_box = source.bounding_box()
    target_box = target.bounding_box()
    assert source_box is not None
    assert target_box is not None

    start_x = source_box["x"] + source_box["width"] / 2
    start_y = source_box["y"] + source_box["height"] / 2
    end_x = target_box["x"] + min(30, target_box["width"] / 2)
    end_y = target_box["y"] + target_box["height"] * target_y_fraction

    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(start_x, start_y + 8, steps=4)
    page.mouse.move(end_x, end_y, steps=24)


def _drag_slot_state(page):
    return page.evaluate(
        """
        () => {
          const slot = document.querySelector(
            "#ace-headless-tree-mount .ace-ht-drag-slot:not([hidden])"
          );
          if (!slot) return null;
          const itemId = (node) => node?.getAttribute?.("data-item-id") || "";
          const itemLabel = (node) => node?.querySelector?.(".ace-ht-label")?.textContent.trim() || "";
          return {
            text: slot.textContent.trim(),
            target: slot.dataset.dragTarget || "",
            parentId: slot.dataset.parentId || "",
            beforeId: slot.dataset.beforeId || "",
            afterId: slot.dataset.afterId || "",
            ariaHidden: slot.getAttribute("aria-hidden"),
            position: getComputedStyle(slot).position,
            display: getComputedStyle(slot).display,
            height: Math.round(slot.getBoundingClientRect().height),
            previousId: itemId(slot.previousElementSibling),
            previousLabel: itemLabel(slot.previousElementSibling),
            nextId: itemId(slot.nextElementSibling),
            nextLabel: itemLabel(slot.nextElementSibling),
            sourceDimmed: !!document.querySelector(".ace-ht-row--drag-source"),
          };
        }
        """
    )


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_is_default_and_legacy_query_is_ignored(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            expect(page.locator("#ace-headless-tree-preview")).to_be_visible()
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            api = _api_code_labels(page)
            preview = _code_labels(page, "#ace-headless-tree-mount .ace-ht-row--code .ace-ht-label")
            assert preview == api

            page.goto(f"{ace_server}/code?tree=legacy")
            expect(page.locator("#ace-headless-tree-preview")).to_be_visible()
            expect(page.locator("#ace-headless-tree-mount")).to_be_visible()
            expect(page.locator("#code-tree")).to_have_count(0)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_preview_renders_nested_codebook_data(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount")
            folder_id = page.evaluate(
                """
                async () => {
                  const form = new URLSearchParams({
                    name: "Nested group",
                    current_index: String(window.__aceCurrentIndex || 0),
                  });
                  const create = await fetch("/api/codes/folder", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: form,
                  });
                  if (!create.ok) throw new Error(`folder create failed: ${create.status}`);
                  await create.text();

                  const tree = await fetch("/api/codes/tree").then((r) => r.json());
                  const rootChildren = tree.items.root.children;
                  const folder = Object.values(tree.items)
                    .find((item) => item.kind === "folder" && item.name === "Nested group");
                  const alpha = rootChildren.find((id) => tree.items[id]?.name === "Alpha");
                  const bravo = rootChildren.find((id) => tree.items[id]?.name === "Bravo");
                  for (const [index, id] of [alpha, bravo].entries()) {
                    const body = new URLSearchParams({
                      parent_id: folder.id,
                      target_order_ids: JSON.stringify([alpha, bravo].slice(0, index + 1)),
                      current_index: String(window.__aceCurrentIndex || 0),
                    });
                    const move = await fetch(`/api/codes/${id}/parent`, {
                      method: "PUT",
                      headers: { "Content-Type": "application/x-www-form-urlencoded" },
                      body,
                    });
                    if (!move.ok) throw new Error(`move failed: ${move.status}`);
                    await move.text();
                  }
                  return folder.id;
                }
                """
            )

            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            folder = page.locator(
                f'#ace-headless-tree-mount .ace-ht-row[data-item-id="{folder_id}"]'
            )
            expect(folder).to_be_visible()
            expect(folder).to_have_attribute("aria-level", "1")

            nested_names = page.locator(
                '#ace-headless-tree-mount .ace-ht-row[aria-level="2"] .ace-ht-label'
            ).evaluate_all("(nodes) => nodes.map((node) => node.textContent.trim())")
            assert nested_names[:2] == ["Alpha", "Bravo"]

            snapshot = page.evaluate("() => window.__aceHeadlessTreePreview.snapshot()")
            assert folder_id in snapshot["rootChildren"]
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_definition_uses_single_expanding_peek(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount")
            definition = (
                "Participants describe barriers to accessing a service, including time, "
                "cost, transport, uncertainty about eligibility, or discomfort asking for help. "
            ) * 3
            page.evaluate(
                """
                async (definition) => {
                  const codes = [{
                    name: "Dictionary access",
                    colour: "#123456",
                    group_name: "",
                    definition,
                  }];
                  const response = await fetch("/api/codes/import", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: new URLSearchParams({
                      codes_json: JSON.stringify(codes),
                      current_index: String(window.__aceCurrentIndex || 0),
                    }),
                  });
                  if (!response.ok) throw new Error(`import failed: ${response.status}`);
                  await response.text();
                }
                """,
                definition,
            )

            page.goto(f"{ace_server}/code")
            row = page.locator(
                '#ace-headless-tree-mount .ace-ht-row--code:has-text("Dictionary access")'
            ).first
            expect(row).to_have_attribute("data-definition", definition)
            assert row.get_attribute("title") is None

            row.scroll_into_view_if_needed()
            box = row.bounding_box()
            assert box is not None
            page.mouse.move(box["x"] + 20, box["y"] + box["height"] / 2)

            peek = page.locator(".ace-code-peek.ace-code-peek--visible")
            expect(peek).to_have_count(1)
            expect(page.locator("#ace-code-definition-popover")).to_have_count(0)
            expect(peek).to_contain_text("Dictionary access")
            expect(peek).to_contain_text("Participants describe barriers")
            overflow_y = peek.locator(".ace-code-peek-definition").evaluate(
                "(node) => getComputedStyle(node).overflowY"
            )
            assert overflow_y == "visible"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_preview_marks_folder_levels_and_paths(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount")
            ids = page.evaluate(
                """
                async () => {
                  async function createFolder(name, parent_id = "") {
                    const response = await fetch("/api/codes/folder", {
                      method: "POST",
                      headers: { "Content-Type": "application/x-www-form-urlencoded" },
                      body: new URLSearchParams({
                        name,
                        parent_id,
                        current_index: String(window.__aceCurrentIndex || 0),
                      }),
                    });
                    if (!response.ok) throw new Error(`folder create failed: ${response.status}`);
                    await response.text();
                    const payload = await fetch("/api/codes/tree").then((r) => r.json());
                    return Object.values(payload.items).find((item) => item.name === name)?.id;
                  }
                  const parent = await createFolder("Level parent");
                  const child = await createFolder("Level child", parent);
                  return { parent, child };
                }
                """
            )

            page.goto(f"{ace_server}/code")
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
            expect(child).to_have_attribute("data-path", "Level parent / Level child")
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_highlights_parent_chain_for_focused_nested_item(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount")
            ids = page.evaluate(
                """
                async () => {
                  async function createFolder(name, parent_id = "") {
                    const response = await fetch("/api/codes/folder", {
                      method: "POST",
                      headers: { "Content-Type": "application/x-www-form-urlencoded" },
                      body: new URLSearchParams({
                        name,
                        parent_id,
                        current_index: String(window.__aceCurrentIndex || 0),
                      }),
                    });
                    if (!response.ok) throw new Error(`folder create failed: ${response.status}`);
                    await response.text();
                    const payload = await fetch("/api/codes/tree").then((r) => r.json());
                    return Object.values(payload.items).find((item) => item.name === name)?.id;
                  }
                  const parent = await createFolder("Path parent");
                  const child = await createFolder("Path child", parent);
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  const alpha = Object.values(payload.items).find((item) => item.name === "Alpha").id;
                  const move = await fetch(`/api/codes/${alpha}/parent`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: new URLSearchParams({
                      parent_id: child,
                      target_order_ids: JSON.stringify([alpha]),
                      current_index: String(window.__aceCurrentIndex || 0),
                    }),
                  });
                  if (!move.ok) throw new Error(`move failed: ${move.status}`);
                  await move.text();
                  return { parent, child, alpha };
                }
                """
            )

            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )
            page.locator(
                f'#ace-headless-tree-mount .ace-ht-row[data-item-id="{ids["alpha"]}"]'
            ).click()

            state = page.evaluate(
                """
                (ids) => {
                  function hasClass(id, className) {
                    return document
                      .querySelector(`#ace-headless-tree-mount .ace-ht-row[data-item-id="${id}"]`)
                      ?.classList.contains(className);
                  }
                  return {
                    parent: hasClass(ids.parent, "ace-ht-row--path-parent"),
                    child: hasClass(ids.child, "ace-ht-row--path-parent"),
                    focused: hasClass(ids.alpha, "ace-ht-row--path-parent"),
                  };
                }
                """,
                ids,
            )
            assert state == {"parent": True, "child": True, "focused": False}
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_preview_survives_sidebar_oob_swap(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            expect(page.locator("#ace-headless-tree-preview")).to_be_visible()
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            page.evaluate(
                """
                () => new Promise((resolve, reject) => {
                  const timeout = setTimeout(
                    () => reject(new Error("sidebar swap timed out")),
                    4000
                  );
                  document.body.addEventListener("htmx:afterSettle", () => {
                    clearTimeout(timeout);
                    resolve();
                  }, { once: true });
                  window.htmx.ajax("POST", "/api/codes/folder", {
                    target: "#text-panel",
                    swap: "outerHTML",
                    values: {
                      name: "Preview persists",
                      current_index: window.__aceCurrentIndex || 0,
                    },
                  });
                })
                """
            )

            expect(page.locator("#ace-headless-tree-preview")).to_be_visible()
            page.wait_for_function(
                """
                () => Object.values(window.__aceHeadlessTreePreview?.items || {})
                  .some((item) => item.name === "Preview persists")
                """
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_preview_applies_focused_code(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector(".ace-sentence")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            page.click(".ace-sentence")
            row = page.locator("#ace-headless-tree-mount .ace-ht-row--code").first
            row.click()
            page.keyboard.press("Enter")

            page.wait_for_function(
                """
                () => JSON.parse(
                  document.getElementById("ace-ann-data")?.dataset.annotations || "[]"
                ).length > 0
                """
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_preview_renames_item_through_ace_api(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            row = page.locator("#ace-headless-tree-mount .ace-ht-row--code").first
            item_id = row.get_attribute("data-item-id")
            assert item_id
            row.click()
            page.keyboard.press("F2")
            rename = page.locator("#ace-headless-tree-mount .ace-ht-rename")
            expect(rename).to_be_visible()
            rename.fill("Renamed from candidate")
            page.keyboard.press("Enter")

            expect(
                page.locator(
                    f'#ace-headless-tree-mount .ace-ht-row[data-item-id="{item_id}"] .ace-ht-label'
                )
            ).to_have_text(
                "Renamed from candidate"
            )
            page.wait_for_function(
                """
                async ({ itemId }) => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  return payload.items[itemId]?.name === "Renamed from candidate";
                }
                """,
                arg={"itemId": item_id},
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_candidate_is_primary_tree_in_gated_mode(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            expect(page.locator("#ace-headless-tree-preview")).to_be_visible()
            expect(page.locator("#ace-headless-tree-mount")).to_be_visible()
            expect(page.locator("#code-tree")).to_have_count(0)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_candidate_filters_from_search_input(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            page.locator("#code-search-input").fill("brav")
            labels = page.locator("#ace-headless-tree-mount .ace-ht-label").evaluate_all(
                "(nodes) => nodes.map((node) => node.textContent.trim())"
            )
            assert labels == ["Bravo"]
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_search_arrows_navigate_filtered_codes(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            page.locator("#text-panel").focus()
            page.keyboard.press("/")
            expect(page.locator("#code-search-input")).to_be_focused()
            page.keyboard.type("a")
            page.keyboard.press("ArrowDown")
            page.wait_for_function(
                """
                () => document.activeElement?.matches(".ace-ht-row--code") &&
                      document.activeElement?.textContent.includes("Alpha")
                """
            )
            page.keyboard.press("ArrowDown")
            page.wait_for_function(
                """
                () => document.activeElement?.matches(".ace-ht-row--code") &&
                      document.activeElement?.textContent.includes("Bravo")
                """
            )
            page.keyboard.press("Enter")

            expect(
                page.locator(".ace-applied-code-row", has_text="Bravo")
            ).to_be_visible()
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_candidate_tab_cycles_into_tree(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            page.locator("#text-panel").focus()
            page.keyboard.press("Tab")
            expect(page.locator("#code-search-input")).to_be_focused()
            page.keyboard.press("Tab")

            assert page.evaluate(
                """
                () => document.activeElement?.matches(
                  "#ace-headless-tree-mount .ace-ht-row[role='treeitem']"
                )
                """
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_candidate_creates_code_from_empty_search(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            page.locator("#code-search-input").fill("New candidate code")
            page.keyboard.press("Enter")

            expect(
                page.locator(
                    "#ace-headless-tree-mount .ace-ht-row--code",
                    has_text="New candidate code",
                )
            ).to_be_visible()
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_default_slash_commands_create_items(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            search = page.locator("#code-search-input")
            search.fill("/folder Headless folder")
            search.press("Enter")
            expect(
                page.locator(
                    "#ace-headless-tree-mount .ace-ht-row--folder",
                    has_text="Headless folder",
                )
            ).to_be_visible()
            page.wait_for_function("document.getElementById('code-search-input')?.value === ''")

            search.fill("/Code Headless code")
            search.press("Enter")
            expect(
                page.locator(
                    "#ace-headless-tree-mount .ace-ht-row--code",
                    has_text="Headless code",
                )
            ).to_be_visible()
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_candidate_bridge_reorder_shortcut_persists(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )
            before_colours = page.evaluate(
                """
                () => Object.fromEntries(
                  Array.from(document.querySelectorAll(".ace-ht-row--code")).map((row) => [
                    row.querySelector(".ace-ht-label")?.textContent.trim(),
                    row.style.getPropertyValue("--row-colour").trim(),
                  ])
                )
                """
            )

            page.locator(
                "#ace-headless-tree-mount .ace-ht-row--code",
                has_text="Charlie",
            ).click()
            page.evaluate("window.__aceTextPanelBeforeReorder = document.getElementById('text-panel')")
            page.keyboard.press("Alt+Shift+ArrowUp")

            page.wait_for_function(
                """
                async () => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  const names = payload.items.root.children
                    .map((id) => payload.items[id]?.name)
                    .filter(Boolean);
                  return JSON.stringify(names) === JSON.stringify(["Alpha", "Charlie", "Bravo"]);
                }
                """
            )
            page.wait_for_function(
                """
                () => {
                  const labels = Array.from(
                    document.querySelectorAll("#ace-headless-tree-mount .ace-ht-row--code .ace-ht-label")
                  ).map((node) => node.textContent.trim());
                  return JSON.stringify(labels.slice(0, 3)) === JSON.stringify(["Alpha", "Charlie", "Bravo"]);
                }
                """
            )
            assert page.evaluate(
                "window.__aceTextPanelBeforeReorder === document.getElementById('text-panel')"
            )
            after_colours = page.evaluate(
                """
                () => Object.fromEntries(
                  Array.from(document.querySelectorAll(".ace-ht-row--code")).map((row) => [
                    row.querySelector(".ace-ht-label")?.textContent.trim(),
                    row.style.getPropertyValue("--row-colour").trim(),
                  ])
                )
                """
            )
            for name in ["Alpha", "Bravo", "Charlie"]:
                assert after_colours[name] == before_colours[name]
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_plain_arrows_navigate_without_reordering(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )
            before = page.evaluate(
                """
                async () => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  return payload.items.root.children
                    .map((id) => payload.items[id]?.name)
                    .filter(Boolean);
                }
                """
            )

            first = page.locator("#ace-headless-tree-mount [role='treeitem']").first
            first.focus()
            first_label = page.locator(
                "#ace-headless-tree-mount [role='treeitem'][tabindex='0'] .ace-ht-label"
            ).inner_text()
            page.keyboard.press("ArrowDown")
            moved_label = page.locator(
                "#ace-headless-tree-mount [role='treeitem'][tabindex='0'] .ace-ht-label"
            ).inner_text()
            assert moved_label != first_label
            page.keyboard.press("ArrowUp")
            restored_label = page.locator(
                "#ace-headless-tree-mount [role='treeitem'][tabindex='0'] .ace-ht-label"
            ).inner_text()
            assert restored_label == first_label

            after = page.evaluate(
                """
                async () => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  return payload.items.root.children
                    .map((id) => payload.items[id]?.name)
                    .filter(Boolean);
                }
                """
            )
            assert after == before
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_candidate_cut_paste_shortcut_moves_into_folder(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )
            ids = page.evaluate(
                """
                async () => {
                  const create = await fetch("/api/codes/folder", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: new URLSearchParams({
                      name: "Shortcut folder",
                      current_index: String(window.__aceCurrentIndex || 0),
                    }),
                  });
                  if (!create.ok) throw new Error(`folder create failed: ${create.status}`);
                  await create.text();
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  const byName = (name) => Object.values(payload.items)
                    .find((item) => item.name === name)?.id;
                  return {
                    folder: byName("Shortcut folder"),
                    bravo: byName("Bravo"),
                  };
                }
                """
            )

            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )
            page.wait_for_function(
                """
                ({ folder }) => !!document.querySelector(
                  `#ace-headless-tree-mount .ace-ht-row[data-item-id="${folder}"]`
                )
                """,
                arg=ids,
            )
            page.locator(
                f'#ace-headless-tree-mount .ace-ht-row[data-item-id="{ids["bravo"]}"]'
            ).click()
            modifier = "Meta" if sys.platform == "darwin" else "Control"
            page.keyboard.press(f"{modifier}+X")
            page.locator(
                f'#ace-headless-tree-mount .ace-ht-row[data-item-id="{ids["folder"]}"]'
            ).click()
            page.keyboard.press(f"{modifier}+V")

            page.wait_for_function(
                """
                async ({ folder, bravo }) => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  return (payload.items[folder]?.children || []).includes(bravo);
                }
                """,
                arg=ids,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_candidate_deletes_focused_item(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            row = page.locator("#ace-headless-tree-mount .ace-ht-row--code").first
            item_id = row.get_attribute("data-item-id")
            assert item_id
            row.click()
            page.keyboard.press("Delete")

            expect(
                page.locator(f'#ace-headless-tree-mount .ace-ht-row[data-item-id="{item_id}"]')
            ).to_have_count(0)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_candidate_v_opens_focused_code_view(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            row = page.locator(
                "#ace-headless-tree-mount .ace-ht-row--code",
                has_text="Bravo",
            )
            item_id = row.get_attribute("data-item-id")
            assert item_id
            row.click()
            page.keyboard.press("v")

            page.wait_for_url(f"**/code/{item_id}/view")
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_candidate_persists_drop_at_exact_order(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_selector("#ace-headless-tree-mount")
            ids = page.evaluate(
                """
                async () => {
                  const create = await fetch("/api/codes/folder", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: new URLSearchParams({
                      name: "Drop target",
                      current_index: String(window.__aceCurrentIndex || 0),
                    }),
                  });
                  if (!create.ok) throw new Error(`folder create failed: ${create.status}`);
                  await create.text();

                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  const items = payload.items;
                  const byName = (name) => Object.values(items).find((item) => item.name === name)?.id;
                  const folder = byName("Drop target");
                  const alpha = byName("Alpha");
                  const bravo = byName("Bravo");
                  const charlie = byName("Charlie");
                  for (const [id, order] of [
                    [alpha, [alpha]],
                    [charlie, [alpha, charlie]],
                  ]) {
                    const move = await fetch(`/api/codes/${id}/parent`, {
                      method: "PUT",
                      headers: { "Content-Type": "application/x-www-form-urlencoded" },
                      body: new URLSearchParams({
                        parent_id: folder,
                        target_order_ids: JSON.stringify(order),
                        current_index: String(window.__aceCurrentIndex || 0),
                      }),
                    });
                    if (!move.ok) throw new Error(`move failed: ${move.status}`);
                    await move.text();
                  }
                  return { folder, alpha, bravo, charlie };
                }
                """
            )

            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            page.evaluate(
                """
                async ({ folder, bravo }) => {
                  const api = window.__aceHeadlessTreePreview;
                  await api.tree.getConfig().onDrop(
                    [api.tree.getItemInstance(bravo)],
                    {
                      item: api.tree.getItemInstance(folder),
                      childIndex: 1,
                      insertionIndex: 1,
                      dragLineIndex: 0,
                      dragLineLevel: 2,
                    }
                  );
                }
                """,
                ids,
            )

            page.wait_for_function(
                """
                async ({ folder, alpha, bravo, charlie }) => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  const children = payload.items[folder]?.children || [];
                  return JSON.stringify(children) === JSON.stringify([alpha, bravo, charlie]);
                }
                """,
                arg=ids,
            )
            page.wait_for_function(
                """
                ({ folder, alpha, bravo, charlie }) => {
                  const children = window.__aceHeadlessTreePreview?.items?.[folder]?.children || [];
                  return JSON.stringify(children) === JSON.stringify([alpha, bravo, charlie]);
                }
                """,
                arg=ids,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_candidate_browser_drag_reorders_root_codes(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            source = page.locator(
                "#ace-headless-tree-mount .ace-ht-row--code",
                has_text="Charlie",
            )
            target = page.locator(
                "#ace-headless-tree-mount .ace-ht-row--code",
                has_text="Bravo",
            )
            _pointer_drag_between(page, source, target, target_y_fraction=0.1)
            page.wait_for_function(
                """
                () => {
                  const slot = document.querySelector(
                    "#ace-headless-tree-mount .ace-ht-drag-slot:not([hidden])"
                  );
                  return !!slot && slot.dataset.dragTarget && slot.getAttribute("aria-hidden") === "true";
                }
                """
            )
            slot_state = _drag_slot_state(page)
            assert slot_state is not None
            assert slot_state["target"] in {"root-position", "before-root-code", "after-root-code"}
            assert slot_state["text"] == "Charlie"
            assert slot_state["ariaHidden"] == "true"
            assert slot_state["position"] == "relative"
            assert slot_state["height"] >= 24
            assert slot_state["sourceDimmed"] is True
            if slot_state["beforeId"]:
                assert slot_state["nextId"] == slot_state["beforeId"]
            else:
                assert slot_state["previousId"] == slot_state["afterId"]
            page.mouse.up()

            page.wait_for_function(
                """
                async () => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  const names = payload.items.root.children
                    .map((id) => payload.items[id]?.name)
                    .filter(Boolean);
                  return JSON.stringify(names) === JSON.stringify(["Alpha", "Charlie", "Bravo"]);
                }
                """
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_candidate_uses_native_drag_payload_and_tiny_image(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )

            drag_state = page.locator(
                "#ace-headless-tree-mount .ace-ht-row--code",
                has_text="Charlie",
            ).evaluate(
                """
                (row) => {
                  const imageCalls = [];
                  const dataCalls = [];
                  const dataTransfer = {
                    effectAllowed: "all",
                    dropEffect: "move",
                    setData(format, data) {
                      dataCalls.push({ format, data });
                    },
                    setDragImage(node, x, y) {
                      const box = node.getBoundingClientRect();
                      imageCalls.push({
                        className: node.className,
                        tagName: node.tagName,
                        width: box.width,
                        height: box.height,
                        x,
                        y,
                      });
                    },
                  };
                  const event = new DragEvent("dragstart", {
                    bubbles: true,
                    cancelable: true,
                  });
                  Object.defineProperty(event, "dataTransfer", { value: dataTransfer });
                  row.dispatchEvent(event);
                  return {
                    dragImage: imageCalls[0] || null,
                    dataCalls,
                    effectAllowed: dataTransfer.effectAllowed,
                    dropEffect: dataTransfer.dropEffect,
                  };
                }
                """
            )

            drag_image = drag_state["dragImage"]
            assert drag_image is not None
            assert "ace-ht-drag-image" in drag_image["className"]
            assert drag_image["tagName"] == "IMG"
            assert drag_image["width"] <= 4
            assert drag_image["height"] <= 4
            assert drag_state["dataCalls"] == [
                {"format": "text/plain", "data": "Charlie"}
            ]
            assert drag_state["effectAllowed"] == "move"
            assert drag_state["dropEffect"] == "move"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_candidate_direct_folder_drop_moves_inside(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )
            ids = page.evaluate(
                """
                async () => {
                  const create = await fetch("/api/codes/folder", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: new URLSearchParams({
                      name: "Direct folder",
                      current_index: String(window.__aceCurrentIndex || 0),
                    }),
                  });
                  if (!create.ok) throw new Error(`folder create failed: ${create.status}`);
                  await create.text();

                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  const byName = (name) => Object.values(payload.items)
                    .find((item) => item.name === name)?.id;
                  const folder = byName("Direct folder");
                  const alpha = byName("Alpha");
                  const bravo = byName("Bravo");
                  const move = await fetch(`/api/codes/${alpha}/parent`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: new URLSearchParams({
                      parent_id: folder,
                      target_order_ids: JSON.stringify([alpha]),
                      current_index: String(window.__aceCurrentIndex || 0),
                    }),
                  });
                  if (!move.ok) throw new Error(`move failed: ${move.status}`);
                  await move.text();
                  return { folder, alpha, bravo };
                }
                """
            )

            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )
            source = page.locator(
                f'#ace-headless-tree-mount .ace-ht-row[data-item-id="{ids["bravo"]}"]'
            )
            target = page.locator(
                f'#ace-headless-tree-mount .ace-ht-row[data-item-id="{ids["folder"]}"]'
            )
            _pointer_drag_between(page, source, target, target_y_fraction=0.65)
            page.wait_for_function(
                """
                ({ folder }) => {
                  const slot = document.querySelector(
                    "#ace-headless-tree-mount .ace-ht-drag-slot:not([hidden])"
                  );
                  return document.body.dataset.codebookDragging === "1" &&
                    slot?.dataset.dragTarget === "inside-folder" &&
                    slot?.dataset.parentId === folder &&
                    slot.textContent.trim() === "Bravo";
                }
                """,
                arg=ids,
            )
            slot_state = _drag_slot_state(page)
            assert slot_state is not None
            assert slot_state["target"] == "inside-folder"
            assert slot_state["parentId"] == str(ids["folder"])
            assert slot_state["text"] == "Bravo"
            assert slot_state["sourceDimmed"] is True
            folder_wells = page.evaluate(
                """
                () => Array.from(document.querySelectorAll(
                  "#ace-headless-tree-mount .ace-ht-row--folder"
                )).filter((row) => parseFloat(getComputedStyle(row).marginBottom) >= 20).length
                """
            )
            assert folder_wells == 0
            page.mouse.up()

            page.wait_for_function(
                """
                async ({ folder, alpha, bravo }) => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  const children = payload.items[folder]?.children || [];
                  return JSON.stringify(children) === JSON.stringify([alpha, bravo]);
                }
                """,
                arg=ids,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_candidate_folder_body_accepts_inside_drop(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )
            ids = page.evaluate(
                """
                async () => {
                  const create = await fetch("/api/codes/folder", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: new URLSearchParams({
                      name: "Folder body target",
                      current_index: String(window.__aceCurrentIndex || 0),
                    }),
                  });
                  if (!create.ok) throw new Error(`folder create failed: ${create.status}`);
                  await create.text();

                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  const byName = (name) => Object.values(payload.items)
                    .find((item) => item.name === name)?.id;
                  const folder = byName("Folder body target");
                  const alpha = byName("Alpha");
                  const bravo = byName("Bravo");
                  const move = await fetch(`/api/codes/${alpha}/parent`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: new URLSearchParams({
                      parent_id: folder,
                      target_order_ids: JSON.stringify([alpha]),
                      current_index: String(window.__aceCurrentIndex || 0),
                    }),
                  });
                  if (!move.ok) throw new Error(`move failed: ${move.status}`);
                  await move.text();
                  return { folder, alpha, bravo };
                }
                """
            )

            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )
            source = page.locator(
                f'#ace-headless-tree-mount .ace-ht-row[data-item-id="{ids["bravo"]}"]'
            )
            folder = page.locator(
                f'#ace-headless-tree-mount .ace-ht-row[data-item-id="{ids["folder"]}"]'
            )
            _pointer_drag_between(page, source, folder, target_y_fraction=0.40)

            page.wait_for_function(
                """
                ({ folder }) => {
                  const slot = document.querySelector(
                    "#ace-headless-tree-mount .ace-ht-drag-slot:not([hidden])"
                  );
                  return document.body.dataset.codebookDragging === "1" &&
                    slot?.dataset.dragTarget === "inside-folder" &&
                    slot?.dataset.parentId === folder &&
                    slot.textContent.trim() === "Bravo";
                }
                """,
                arg=ids,
            )
            page.mouse.up()

            page.wait_for_function(
                """
                async ({ folder, alpha, bravo }) => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  const children = payload.items[folder]?.children || [];
                  return JSON.stringify(children) === JSON.stringify([alpha, bravo]);
                }
                """,
                arg=ids,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_candidate_highlights_drop_receiver_folder(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )
            ids = page.evaluate(
                """
                async () => {
                  const create = await fetch("/api/codes/folder", {
                    method: "POST",
                    headers: { "Content-Type": "application/x-www-form-urlencoded" },
                    body: new URLSearchParams({
                      name: "Receiver folder",
                      current_index: String(window.__aceCurrentIndex || 0),
                    }),
                  });
                  if (!create.ok) throw new Error(`folder create failed: ${create.status}`);
                  await create.text();

                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  const byName = (name) => Object.values(payload.items)
                    .find((item) => item.name === name)?.id;
                  const folder = byName("Receiver folder");
                  const alpha = byName("Alpha");
                  const bravo = byName("Bravo");
                  const charlie = byName("Charlie");
                  for (const [id, order] of [
                    [alpha, [alpha]],
                    [charlie, [alpha, charlie]],
                  ]) {
                    const move = await fetch(`/api/codes/${id}/parent`, {
                      method: "PUT",
                      headers: { "Content-Type": "application/x-www-form-urlencoded" },
                      body: new URLSearchParams({
                        parent_id: folder,
                        target_order_ids: JSON.stringify(order),
                        current_index: String(window.__aceCurrentIndex || 0),
                      }),
                    });
                    if (!move.ok) throw new Error(`move failed: ${move.status}`);
                    await move.text();
                  }
                  return { folder, alpha, bravo, charlie };
                }
                """
            )

            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )
            source = page.locator(
                f'#ace-headless-tree-mount .ace-ht-row[data-item-id="{ids["bravo"]}"]'
            )
            folder = page.locator(
                f'#ace-headless-tree-mount .ace-ht-row[data-item-id="{ids["folder"]}"]'
            )
            charlie = page.locator(
                f'#ace-headless-tree-mount .ace-ht-row[data-item-id="{ids["charlie"]}"]'
            )
            _pointer_drag_between(page, source, folder, target_y_fraction=0.65)
            page.wait_for_function(
                """
                ({ folder }) => {
                  const slot = document.querySelector(
                    "#ace-headless-tree-mount .ace-ht-drag-slot:not([hidden])"
                  );
                  return document.body.dataset.codebookDragging === "1" &&
                    slot?.dataset.dragTarget === "inside-folder" &&
                    slot?.dataset.parentId === folder &&
                    slot.textContent.trim() === "Bravo";
                }
                """,
                arg=ids,
            )
            slot_state = _drag_slot_state(page)
            assert slot_state is not None
            assert slot_state["target"] == "inside-folder"
            assert slot_state["parentId"] == str(ids["folder"])
            assert slot_state["text"] == "Bravo"
            assert slot_state["ariaHidden"] == "true"
            assert slot_state["position"] == "relative"
            assert slot_state["height"] >= 24
            assert slot_state["sourceDimmed"] is True

            charlie.scroll_into_view_if_needed()
            charlie_box = charlie.bounding_box()
            assert charlie_box is not None
            page.mouse.move(charlie_box["x"] + 30, charlie_box["y"] + 2, steps=24)
            state = page.wait_for_function(
                """
                ({ folder }) => {
                  const receivers = Array.from(document.querySelectorAll(
                    "#ace-headless-tree-mount .ace-ht-row--drop-receiver"
                  ));
                  const slot = document.querySelector(
                    "#ace-headless-tree-mount .ace-ht-drag-slot:not([hidden])"
                  );
                  if (
                    receivers.length !== 1 ||
                    !slot ||
                    !["folder-child-position", "before-folder-child", "after-folder-child"]
                      .includes(slot.dataset.dragTarget || "")
                  ) {
                    return null;
                  }
                  const style = getComputedStyle(receivers[0]);
                  return {
                    receiverId: receivers[0].dataset.itemId,
                    receiverIsFolder: receivers[0].dataset.kind === "folder",
                    receiverHasVisualTreatment: style.boxShadow !== "none",
                    slotTarget: slot.dataset.dragTarget || "",
                    slotAriaHidden: slot.getAttribute("aria-hidden"),
                  };
                }
                """,
                arg=ids,
            ).json_value()
            assert state["receiverId"] == ids["folder"]
            assert state["receiverIsFolder"] is True
            assert state["receiverHasVisualTreatment"] is True
            assert state["slotAriaHidden"] == "true"
            assert state["slotTarget"] in {
                "folder-child-position",
                "before-folder-child",
                "after-folder-child",
            }

            page.mouse.up()
            page.wait_for_function(
                """
                async ({ folder, alpha, bravo, charlie }) => {
                  const payload = await fetch("/api/codes/tree").then((r) => r.json());
                  const children = payload.items[folder]?.children || [];
                  return JSON.stringify(children) === JSON.stringify([alpha, bravo, charlie]);
                }
                """,
                arg=ids,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_candidate_announces_keyboard_drag_state(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/code")
            page.wait_for_function(
                "() => window.__aceHeadlessTreePreview?.snapshot().itemCount > 1"
            )
            page.locator(
                "#ace-headless-tree-mount .ace-ht-row--code",
                has_text="Charlie",
            ).click()

            page.keyboard.press("Control+Shift+D")

            expect(page.locator("#ace-ht-dnd-announcer")).to_contain_text(
                "Moving Charlie"
            )
            expect(page.locator("#ace-ht-dnd-announcer")).to_contain_text(
                "Enter to move"
            )
        finally:
            browser.close()
