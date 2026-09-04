from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect, sync_playwright

from ace.db.connection import create_project, open_project
from ace.models.project import get_project
from ace.models.source import add_source

from .conftest import browser_params


def _project_id(path: Path) -> str:
    conn = open_project(path)
    try:
        return get_project(conn)["id"]
    finally:
        conn.close()


def _create_second_project(path: Path) -> str:
    conn = create_project(path, "Project B")
    try:
        project_id = get_project(conn)["id"]
        add_source(conn, "B001", "Project B first source.", "row")
        add_source(conn, "B002", "Project B second source.", "row")
        return project_id
    finally:
        conn.close()


def _open_project(page: Page, base_url: str, path: Path) -> None:
    response = page.context.request.post(
        f"{base_url}/api/project/open",
        form={"path": str(path)},
    )
    assert response.status == 200
    assert response.headers["hx-redirect"] == "/code"


def _expect_source(page: Page, counter: str, text: str) -> None:
    expect(page.locator("#nav-counter")).to_have_text(counter)
    expect(page.locator("#text-panel")).to_contain_text(text)


@pytest.mark.parametrize("browser_name", browser_params())
def test_source_position_is_scoped_to_project_id(
    ace_server, tmp_path: Path, browser_name: str
) -> None:
    project_a = tmp_path / "test.ace"
    project_b = tmp_path / "project-b.ace"
    project_a_id = _project_id(project_a)
    project_b_id = _create_second_project(project_b)

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()

            page.goto(f"{ace_server}/code")
            _expect_source(page, "1 / 2", "First sentence.")

            page.goto(f"{ace_server}/code?index=1")
            _expect_source(page, "2 / 2", "Third sentence.")
            assert page.evaluate("localStorage.getItem('ace-last-index')") is None

            # A legacy global value must neither select a source nor be overwritten.
            page.evaluate("localStorage.setItem('ace-last-index', '987')")
            _open_project(page, ace_server, project_b)
            page.goto(f"{ace_server}/code")
            _expect_source(page, "1 / 2", "Project B first source.")
            assert page.url == f"{ace_server}/code"

            # An explicit index still wins over Project B's stored index of zero.
            page.goto(f"{ace_server}/code?index=1")
            _expect_source(page, "2 / 2", "Project B second source.")
            page.goto(f"{ace_server}/code?index=0")
            _expect_source(page, "1 / 2", "Project B first source.")

            # Each project resumes its own source when subsequently opened bare.
            _open_project(page, ace_server, project_a)
            page.goto(f"{ace_server}/code")
            _expect_source(page, "2 / 2", "Third sentence.")
            assert page.url == f"{ace_server}/code?index=1"

            _open_project(page, ace_server, project_b)
            page.goto(f"{ace_server}/code")
            _expect_source(page, "1 / 2", "Project B first source.")
            assert page.url == f"{ace_server}/code"

            assert page.evaluate("localStorage.getItem('ace-last-index')") == "987"
            position_keys = page.evaluate(
                "() => Object.keys(localStorage)"
                ".filter(key => key.startsWith('ace-source-index:'))"
            )
            assert set(position_keys) == {
                f"ace-source-index:{project_a_id}",
                f"ace-source-index:{project_b_id}",
            }
            assert all(str(tmp_path) not in key and ".ace" not in key for key in position_keys)
        finally:
            browser.close()
