from __future__ import annotations

import json
import time
from urllib.parse import parse_qs

import pytest
from playwright.sync_api import expect, sync_playwright

from ace.db.connection import checkpoint_and_close, create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code
from ace.models.source import add_source

from .conftest import browser_params


def _make_agreement_file(path, coder_name, code_names):
    conn = create_project(str(path), f"Agreement {coder_name}")
    try:
        conn.execute("UPDATE coder SET name = ? WHERE name = 'default'", (coder_name,))
        conn.commit()
        coder_id = conn.execute("SELECT id FROM coder").fetchone()[0]
        source_id = add_source(conn, "S1", "Shared agreement text", "row")
        code_ids = {
            name: add_code(conn, name, "#00AA00" if name == "Positive" else "#AA0000")
            for name in code_names
        }
        add_annotation(conn, source_id, coder_id, code_ids["Positive"], 0, 6, "Shared")
        if "Negative" in code_ids:
            add_annotation(conn, source_id, coder_id, code_ids["Negative"], 7, 16, "agreement")
    finally:
        checkpoint_and_close(conn)

    return path


@pytest.mark.parametrize("browser_name", browser_params())
def test_agreement_review_removes_file_and_recomputes_match_count(
    ace_server, tmp_path, browser_name
):
    alice = _make_agreement_file(tmp_path / "alice.ace", "Alice", ["Positive", "Negative"])
    bob = _make_agreement_file(tmp_path / "bob.ace", "Bob", ["Positive", "Negative"])
    carol = _make_agreement_file(tmp_path / "carol.ace", "Carol", ["Positive"])
    selected_paths = [str(alice), str(bob), str(carol)]
    compute_posts = []

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.route(
                "**/api/native/pick-files",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"paths": selected_paths}),
                ),
            )

            def handle_compute(route):
                compute_posts.append(route.request.post_data or "")
                time.sleep(0.3)
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body='<h1 id="ace-agreement-results-title" class="ace-agreement-title" tabindex="-1">Computed</h1>',
                )

            page.route("**/api/agreement/compute", handle_compute)

            page.goto(f"{ace_server}/agreement")
            page.get_by_role("button", name="Choose files").click()

            expect(page.get_by_role("heading", name="Review selected files")).to_be_visible(
                timeout=5000
            )
            expect(page.locator("#ace-agreement-title")).to_be_focused()
            expect(page.locator("#agreement-results")).to_contain_text(
                "1 matched code",
                timeout=5000,
            )
            expect(page.locator(".ace-agreement-file-row")).to_have_count(3)
            assert compute_posts == []

            page.get_by_role("button", name="Remove carol.ace").click()

            expect(page.locator(".ace-agreement-file-row")).to_have_count(2, timeout=5000)
            expect(page.locator("#agreement-results")).to_contain_text(
                "2 matched codes",
                timeout=5000,
            )
            expect(page.locator("#agreement-results")).not_to_contain_text("carol.ace")
            expect(page.get_by_role("button", name="Remove bob.ace")).to_be_focused()
            assert compute_posts == []

            page.get_by_role("button", name="Compute agreement").click()

            expect(page.locator("#agreement-results")).to_contain_text("Computed", timeout=5000)
            expect(page.locator("#ace-agreement-results-title")).to_be_focused()
            assert len(compute_posts) == 1
            values = parse_qs(compute_posts[0])
            assert json.loads(values["paths"][0]) == [str(alice), str(bob)]
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_agreement_review_blocks_compute_while_removal_preview_is_pending(
    ace_server, tmp_path, browser_name
):
    alice = _make_agreement_file(tmp_path / "alice.ace", "Alice", ["Positive", "Negative"])
    bob = _make_agreement_file(tmp_path / "bob.ace", "Bob", ["Positive", "Negative"])
    carol = _make_agreement_file(tmp_path / "carol.ace", "Carol", ["Positive"])
    selected_paths = [str(alice), str(bob), str(carol)]
    compute_posts = []
    preview_count = {"n": 0}

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.route(
                "**/api/native/pick-files",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"paths": selected_paths}),
                ),
            )

            def handle_preview(route):
                preview_count["n"] += 1
                if preview_count["n"] == 2:
                    time.sleep(0.4)
                route.continue_()

            def handle_compute(route):
                compute_posts.append(route.request.post_data or "")
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body='<h1 class="ace-agreement-title">Computed</h1>',
                )

            page.route("**/api/agreement/preview", handle_preview)
            page.route("**/api/agreement/compute", handle_compute)

            page.goto(f"{ace_server}/agreement")
            page.get_by_role("button", name="Choose files").click()
            page.get_by_role("heading", name="Review selected files").wait_for(timeout=5000)

            page.get_by_role("button", name="Remove carol.ace").click()
            page.locator("[data-agreement-compute]").dispatch_event("click")

            expect(page.locator(".ace-agreement-file-row")).to_have_count(2, timeout=5000)
            assert compute_posts == []

            page.get_by_role("button", name="Compute agreement").click()

            expect(page.locator("#agreement-results")).to_contain_text("Computed", timeout=5000)
            assert len(compute_posts) == 1
            values = parse_qs(compute_posts[0])
            assert json.loads(values["paths"][0]) == [str(alice), str(bob)]
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_agreement_choose_cancel_preserves_current_review(
    ace_server, tmp_path, browser_name
):
    alice = _make_agreement_file(tmp_path / "alice.ace", "Alice", ["Positive", "Negative"])
    bob = _make_agreement_file(tmp_path / "bob.ace", "Bob", ["Positive", "Negative"])
    selected_paths = [str(alice), str(bob)]
    pick_responses = [selected_paths, []]
    clear_calls = []

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()

            def handle_pick(route):
                paths = pick_responses.pop(0)
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"paths": paths}),
                )

            def handle_clear(route):
                clear_calls.append(1)
                route.continue_()

            page.route("**/api/native/pick-files", handle_pick)
            page.route("**/api/agreement/clear", handle_clear)

            page.goto(f"{ace_server}/agreement")
            page.get_by_role("button", name="Choose files").click()
            expect(page.locator(".ace-agreement-file-row")).to_have_count(2, timeout=5000)
            assert len(clear_calls) == 1

            page.get_by_role("button", name="Choose files").click()

            expect(page.locator(".ace-agreement-file-row")).to_have_count(2, timeout=5000)
            expect(page.locator("#agreement-results")).to_contain_text("alice.ace")
            expect(page.locator("#agreement-results")).to_contain_text("bob.ace")
            expect(page.locator("[data-agreement-choose-again]")).to_be_focused()
            assert len(clear_calls) == 1
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_agreement_review_keeps_compute_disabled_for_invalid_preview(
    ace_server, tmp_path, browser_name
):
    alice = _make_agreement_file(tmp_path / "alice.ace", "Alice", ["Positive"])
    bob = tmp_path / "bob.ace"

    conn = create_project(str(bob), "Agreement Bob")
    try:
        conn.execute("UPDATE coder SET name = ? WHERE name = 'default'", ("Bob",))
        conn.commit()
        coder_id = conn.execute("SELECT id FROM coder").fetchone()[0]
        source_id = add_source(conn, "S2", "Different agreement text", "row")
        code_id = add_code(conn, "Positive", "#00AA00")
        add_annotation(conn, source_id, coder_id, code_id, 0, 9, "Different")
    finally:
        checkpoint_and_close(conn)

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.route(
                "**/api/native/pick-files",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"paths": [str(alice), str(bob)]}),
                ),
            )

            page.goto(f"{ace_server}/agreement")
            page.get_by_role("button", name="Choose files").click()

            expect(page.get_by_role("heading", name="Review selected files")).to_be_visible(
                timeout=5000
            )
            expect(page.locator("#agreement-results")).to_contain_text(
                "These files share no source texts",
                timeout=5000,
            )
            expect(page.locator("[data-agreement-compute]")).to_be_disabled()
        finally:
            browser.close()
