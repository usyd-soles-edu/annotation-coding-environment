from __future__ import annotations

import json
from urllib.parse import parse_qs

import pytest
from playwright.sync_api import expect, sync_playwright

from .conftest import browser_params


@pytest.mark.parametrize("browser_name", browser_params())
def test_import_spreadsheet_uses_native_file_picker(ace_server, tmp_path, browser_name):
    csv_path = tmp_path / "responses with spaces.csv"
    csv_path.write_text("id,text\none,First response\n", encoding="utf-8")

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.route(
                "**/api/native/pick-file",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"path": str(csv_path)}),
                ),
            )

            page.goto(f"{ace_server}/import")
            page.get_by_role("button", name="Import more data").click()
            page.get_by_role("button", name="Import a spreadsheet").click()

            page.get_by_role(
                "heading",
                name="Choose source labels and coding text",
            ).wait_for(timeout=5000)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_import_folder_uses_native_folder_picker(ace_server, tmp_path, browser_name):
    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")
    (folder / "two.md").write_text("Second document", encoding="utf-8")

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.route(
                "**/api/native/pick-folder",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"path": str(folder)}),
                ),
            )

            page.goto(f"{ace_server}/import")
            page.get_by_role("button", name="Import more data").click()
            page.get_by_role("button", name="Import a folder").click()

            page.get_by_role(
                "heading",
                name="Check imported text files",
            ).wait_for(timeout=5000)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_import_folder_accepts_file_uri_from_native_picker(ace_server, tmp_path, browser_name):
    folder = tmp_path / "texts with spaces"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.route(
                "**/api/native/pick-folder",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"path": folder.as_uri()}),
                ),
            )

            page.goto(f"{ace_server}/import")
            page.get_by_role("button", name="Import more data").click()
            page.get_by_role("button", name="Import a folder").click()

            page.get_by_role(
                "heading",
                name="Check imported text files",
            ).wait_for(timeout=5000)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_import_folder_posts_normalized_file_uri_from_native_picker(ace_server, tmp_path, browser_name):
    folder = tmp_path / "texts with spaces"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")
    captured = {}

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.route(
                "**/api/native/pick-folder",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"path": folder.as_uri()}),
                ),
            )

            def handle_import(route):
                captured["body"] = route.request.post_data or ""
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body='<h1 class="ace-wizard-title" tabindex="-1">Check imported text files</h1>',
                )

            page.route("**/api/import/folder", handle_import)

            page.goto(f"{ace_server}/import")
            page.get_by_role("button", name="Import more data").click()
            page.get_by_role("button", name="Import a folder").click()

            page.get_by_role(
                "heading",
                name="Check imported text files",
            ).wait_for(timeout=5000)
            values = parse_qs(captured["body"])
            assert values["path"] == [str(folder)]
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_import_folder_shows_native_picker_errors(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.route("**/api/native/pick-folder", lambda route: route.abort("failed"))

            page.goto(f"{ace_server}/import")
            page.get_by_role("button", name="Import more data").click()
            page.get_by_role("button", name="Import a folder").click()

            expect(page.locator("#import-message")).to_contain_text(
                "Could not open the folder picker.",
                timeout=5000,
            )
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_import_folder_shows_http_errors(ace_server, tmp_path, browser_name):
    folder = tmp_path / "texts"
    folder.mkdir()

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.route(
                "**/api/native/pick-folder",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps({"path": str(folder)}),
                ),
            )
            page.route(
                "**/api/import/folder",
                lambda route: route.fulfill(
                    status=403,
                    content_type="text/plain",
                    body="CSRF origin rejected",
                ),
            )

            page.goto(f"{ace_server}/import")
            page.get_by_role("button", name="Import more data").click()
            page.get_by_role("button", name="Import a folder").click()

            expect(page.locator("#import-message")).to_have_text(
                "Import failed. Try again.",
                timeout=5000,
            )
        finally:
            browser.close()
