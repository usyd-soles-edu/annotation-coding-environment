from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from .conftest import browser_params


SPIKE_PAGE = (
    Path(__file__).resolve().parents[2]
    / "spikes"
    / "headless-tree"
    / "index.html"
)


def _open_spike(page):
    page.goto(SPIKE_PAGE.as_uri())
    expect(page.locator("#ace-headless-tree-spike")).to_be_visible()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_spike_handles_focus_collapse_and_rename(browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        page = browser.new_page()
        _open_spike(page)

        tree = page.get_by_role("tree", name="Headless Tree codebook spike")
        expect(tree).to_be_visible()

        first = page.get_by_role("treeitem", name="Used, positive feedback")
        first.focus()
        expect(first).to_be_focused()

        page.keyboard.press("ArrowDown")
        suggestions = page.get_by_role("treeitem", name="Suggestions", exact=True)
        expect(suggestions).to_be_focused()

        page.keyboard.press("ArrowLeft")
        expect(suggestions).to_have_attribute("aria-expanded", "false")
        expect(page.get_by_role("treeitem", name="Specific improvements")).to_be_hidden()

        page.keyboard.press("F2")
        rename = page.get_by_label("Rename Suggestions")
        expect(rename).to_be_visible()
        rename.fill("Actionable feedback")
        rename.press("Enter")
        expect(page.get_by_role("treeitem", name="Actionable feedback")).to_be_visible()

        browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_spike_builds_from_ace_shaped_rows(browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        page = browser.new_page()
        _open_spike(page)

        snapshot = page.evaluate("() => window.__aceHeadlessTreeSpike.snapshot()")
        assert snapshot["rootChildren"] == [
            "folder-positive",
            "code-literature",
            "code-draft",
        ]
        assert snapshot["positiveChildren"] == [
            "folder-suggestions",
            "code-structure",
        ]
        assert snapshot["suggestionsChildren"] == [
            "code-specific",
            "code-clarity",
        ]

        converted = page.evaluate(
            """
            () => window.__aceHeadlessTreeSpike.itemsFromAceRows([
              {
                id: "folder-a",
                name: "A",
                kind: "folder",
                children: [
                  { id: "code-1", name: "One", kind: "code", colour: "#111111" },
                  {
                    id: "folder-b",
                    name: "B",
                    kind: "folder",
                    children: [
                      { id: "code-2", name: "Two", kind: "code", colour: "#222222" },
                    ],
                  },
                ],
              },
            ])
            """
        )
        assert converted["root"]["children"] == ["folder-a"]
        assert converted["folder-a"]["children"] == ["code-1", "folder-b"]
        assert converted["folder-b"]["children"] == ["code-2"]

        browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_spike_reorders_and_reparents_with_library_state(browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        page = browser.new_page()
        _open_spike(page)

        page.get_by_role("button", name="Move Literature into Suggestions").click()
        moved = page.get_by_role("treeitem", name="Feedback on literature")
        expect(moved).to_be_visible()
        assert moved.get_attribute("aria-level") == "3"

        page.get_by_role("button", name="Move Literature to top of Suggestions").click()
        names = page.locator(
            '[role="treeitem"][aria-level="3"] .ace-spike-label'
        ).evaluate_all("(nodes) => nodes.map((node) => node.textContent.trim())")
        assert names[:2] == ["Feedback on literature", "Specific improvements"]

        operations = page.locator("#ace-spike-operations").inner_text()
        assert (
            "move-parent:code-literature->folder-suggestions:"
            "[code-specific,code-clarity,code-literature]"
        ) in operations
        assert (
            "reorder-scope:folder-suggestions:"
            "[code-literature,code-specific,code-clarity]"
        ) in operations

        browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_headless_tree_spike_maps_cross_parent_drop_to_ace_contract(browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        page = browser.new_page()
        _open_spike(page)

        page.evaluate("() => window.__aceHeadlessTreeSpike.moveDraftIntoPositiveMiddle()")
        page.wait_for_function(
            """
            () => {
              const snapshot = window.__aceHeadlessTreeSpike.snapshot();
              return snapshot.positiveChildren[1] === "code-draft";
            }
            """
        )

        snapshot = page.evaluate("() => window.__aceHeadlessTreeSpike.snapshot()")
        assert snapshot["rootChildren"] == ["folder-positive", "code-literature"]
        assert snapshot["positiveChildren"] == [
            "folder-suggestions",
            "code-draft",
            "code-structure",
        ]
        assert snapshot["operations"] == [
            {
                "type": "move-parent",
                "itemId": "code-draft",
                "parentId": "folder-positive",
                "targetOrderIds": [
                    "folder-suggestions",
                    "code-draft",
                    "code-structure",
                ],
            }
        ]

        browser.close()
