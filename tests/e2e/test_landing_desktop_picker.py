from __future__ import annotations

import json
import re

import pytest
from playwright.sync_api import expect, sync_playwright

from ace.db.connection import create_project

from .conftest import browser_params


@pytest.mark.parametrize("browser_name", browser_params())
def test_new_project_uses_tauri_folder_picker(ace_server, tmp_path, browser_name):
    folder = tmp_path / "native folder"
    folder.mkdir()

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.add_init_script(
                """
                window.__aceTauriDialogOptions = null;
                window.__TAURI__ = {
                  dialog: {
                    open: async function(options) {
                      window.__aceTauriDialogOptions = options;
                      localStorage.setItem("__aceTauriDialogOptions", JSON.stringify(options));
                      return %s;
                    }
                  }
                };
                """
                % json.dumps(folder.as_uri())
            )
            page.route(
                "**/api/native/pick-folder",
                lambda route: route.fulfill(
                    status=500,
                    content_type="application/json",
                    body='{"path": ""}',
                ),
            )

            page.goto(ace_server)
            page.get_by_role("button", name="New project").click()
            page.locator("#new-project-input").fill("Created from Tauri")
            page.get_by_role("button", name="Choose folder").click()

            expect(page.locator("#new-project-folder-label")).to_contain_text(
                str(folder),
                timeout=5000,
            )
            expect(page.get_by_role("button", name="Create project")).to_be_enabled()

            page.get_by_role("button", name="Create project").click()
            expect(page).to_have_url(re.compile(r".*/import$"), timeout=5000)
            assert (folder / "Created from Tauri.ace").exists()
            options = page.evaluate(
                "JSON.parse(localStorage.getItem('__aceTauriDialogOptions'))"
            )
            assert options["directory"] is True
            assert options["multiple"] is False
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_open_existing_uses_tauri_file_picker(ace_server, tmp_path, browser_name):
    project = tmp_path / "Existing Project.ace"
    conn = create_project(str(project), "Existing Project")
    conn.close()

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.add_init_script(
                """
                window.__aceTauriDialogOptions = null;
                window.__TAURI__ = {
                  dialog: {
                    open: async function(options) {
                      window.__aceTauriDialogOptions = options;
                      localStorage.setItem("__aceTauriDialogOptions", JSON.stringify(options));
                      return %s;
                    }
                  }
                };
                """
                % json.dumps(project.as_uri())
            )
            page.route(
                "**/api/native/pick-file",
                lambda route: route.fulfill(
                    status=500,
                    content_type="application/json",
                    body='{"path": ""}',
                ),
            )

            page.goto(ace_server)
            page.get_by_role("button", name="Open existing").click()

            expect(page).to_have_url(re.compile(r".*/import$"), timeout=5000)
            options = page.evaluate(
                "JSON.parse(localStorage.getItem('__aceTauriDialogOptions'))"
            )
            assert options["multiple"] is False
            assert options["filters"][0]["extensions"][0] == "ace"
        finally:
            browser.close()
