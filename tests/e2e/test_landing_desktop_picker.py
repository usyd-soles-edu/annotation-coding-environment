from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect, sync_playwright

from ace.db.connection import create_project
from .conftest import browser_params


@pytest.mark.parametrize("browser_name", browser_params())
def test_new_project_uses_native_folder_picker(ace_server, tmp_path, browser_name):
    folder = tmp_path / "native folder"
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
                    body='{"path": "%s"}' % str(folder).replace('\\', '\\\\'),
                ),
            )

            page.goto(ace_server)
            page.get_by_role("link", name="New project").click()
            page.locator("#new-project-input").fill("Created from picker")
            page.get_by_role("button", name="Choose folder").click()

            expect(page.locator("#new-project-folder-label")).to_contain_text(
                str(folder),
                timeout=5000,
            )
            expect(page.get_by_role("button", name="Create project")).to_be_enabled()

            page.get_by_role("button", name="Create project").click()
            expect(page).to_have_url(re.compile(r".*/import$"), timeout=5000)
            assert (folder / "Created from picker.ace").exists()
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_open_existing_uses_native_file_picker(ace_server, tmp_path, browser_name):
    project = tmp_path / "Existing Project.ace"
    conn = create_project(str(project), "Existing Project")
    conn.close()

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.route(
                "**/api/native/pick-file",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"path": "%s"}' % str(project).replace('\\', '\\\\'),
                ),
            )

            page.goto(ace_server)
            page.get_by_role("button", name="Open project").click()

            expect(page).to_have_url(re.compile(r".*/import$"), timeout=5000)
        finally:
            browser.close()
