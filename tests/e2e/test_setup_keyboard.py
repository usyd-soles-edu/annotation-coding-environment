from __future__ import annotations

import pytest
from playwright.sync_api import sync_playwright

from ace.db.connection import create_project
from .conftest import browser_params


def _press_forward_tab(page, browser_name):
    key = "Alt+Tab" if browser_name == "webkit" else "Tab"
    page.keyboard.press(key)


@pytest.mark.parametrize("browser_name", browser_params())
def test_landing_tab_order_skips_hidden_project_form(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/")
            _press_forward_tab(page, browser_name)
            assert page.evaluate("document.activeElement.id") == "new-project-link"
            _press_forward_tab(page, browser_name)
            assert page.evaluate("document.activeElement.id") == "open-existing-btn"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_landing_keyboard_shortcuts_open_primary_actions(
    ace_server, tmp_path, browser_name
):
    project = tmp_path / "Keyboard Existing.ace"
    conn = create_project(str(project), "Keyboard Existing")
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

            page.goto(f"{ace_server}/")
            page.keyboard.press("n")
            assert page.locator("#new-project-form").is_visible()
            assert page.evaluate("document.activeElement.id") == "new-project-input"
            assert page.locator("#open-existing-btn").is_hidden()
            assert page.locator(".ace-home-tool-link").is_hidden()

            page.locator("#new-project-input").blur()
            page.keyboard.press("o")
            assert page.locator("#new-project-form").is_visible()
            assert page.url == f"{ace_server}/"

            page.get_by_role("button", name="Back").click()
            assert not page.locator("#new-project-form").is_visible()
            assert page.locator("#open-existing-btn").is_visible()

            page.keyboard.press("n")
            assert page.locator("#new-project-form").is_visible()
            page.keyboard.press("Escape")
            assert not page.locator("#new-project-form").is_visible()
            page.keyboard.press("o")
            page.wait_for_url("**/import", timeout=5000)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_landing_keyboard_shortcuts_open_resume_and_agreement(
    ace_server, tmp_path, browser_name
):
    project = tmp_path / "Recent Shortcut.ace"
    conn = create_project(str(project), "Recent Shortcut")
    conn.close()

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/")
            page.evaluate(
                """
                (path) => localStorage.setItem(
                  "ace-recent-files",
                  JSON.stringify([{ path, openedAt: 1 }])
                )
                """,
                str(project),
            )
            page.reload()

            page.keyboard.press("r")
            page.wait_for_url("**/import", timeout=5000)

            page.goto(f"{ace_server}/")
            page.keyboard.press("a")
            page.wait_for_url("**/agreement", timeout=5000)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_landing_arrow_keys_cycle_visible_actions_without_recent(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/")

            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "new-project-link"
            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "open-existing-btn"
            page.keyboard.press("ArrowDown")
            assert page.evaluate(
                "() => document.activeElement.classList.contains('ace-home-tool-link')"
            )
            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "new-project-link"

            page.keyboard.press("Enter")
            assert page.locator("#new-project-form").is_visible()
            assert page.evaluate("document.activeElement.id") == "new-project-input"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_landing_arrow_keys_include_recent_project(
    ace_server, tmp_path, browser_name
):
    project = tmp_path / "Recent Keyboard.ace"
    conn = create_project(str(project), "Recent Keyboard")
    conn.close()

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/")
            page.evaluate(
                """
                (path) => localStorage.setItem(
                  "ace-recent-files",
                  JSON.stringify([{ path, openedAt: 1 }])
                )
                """,
                str(project),
            )
            page.reload()

            page.keyboard.press("ArrowDown")
            assert page.evaluate(
                "() => document.activeElement.id === 'resume-project-link'"
            )
            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "resume-clear-btn"
            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "new-project-link"
            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "open-existing-btn"
            page.keyboard.press("ArrowDown")
            assert page.evaluate(
                "() => document.activeElement.classList.contains('ace-home-tool-link')"
            )

            page.keyboard.press("ArrowUp")
            assert page.evaluate("document.activeElement.id") == "open-existing-btn"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_landing_arrow_keys_and_enter_activate_open_project_and_agreement(
    ace_server, tmp_path, browser_name
):
    project = tmp_path / "Arrow Open.ace"
    conn = create_project(str(project), "Arrow Open")
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

            page.goto(f"{ace_server}/")
            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "new-project-link"
            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "open-existing-btn"
            page.keyboard.press("Enter")
            page.wait_for_url("**/import", timeout=5000)

            page.goto(f"{ace_server}/")
            page.evaluate('localStorage.removeItem("ace-recent-files")')
            page.reload()
            page.keyboard.press("ArrowDown")
            page.keyboard.press("ArrowDown")
            page.keyboard.press("ArrowDown")
            assert page.evaluate(
                "() => document.activeElement.classList.contains('ace-home-tool-link')"
            )
            page.keyboard.press("Enter")
            page.wait_for_url("**/agreement", timeout=5000)
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_landing_shortcuts_do_not_hijack_open_project_form_controls(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/")
            page.keyboard.press("n")
            assert page.locator("#new-project-form").is_visible()

            page.locator("#choose-project-folder-btn").focus()
            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "choose-project-folder-btn"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_landing_dismisses_last_recent_project(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/")
            page.evaluate(
                """
                localStorage.setItem(
                  "ace-recent-files",
                  JSON.stringify([{ path: "/tmp/example.ace", openedAt: 1 }])
                );
                """
            )
            page.reload()

            resume = page.locator("#resume-link")
            assert resume.is_visible()

            page.locator("#resume-clear-btn").click()

            assert not resume.is_visible()
            assert page.evaluate('localStorage.getItem("ace-recent-files")') is None
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_landing_arrow_keys_can_focus_and_enter_clear_recent(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/")
            page.evaluate(
                """
                localStorage.setItem(
                  "ace-recent-files",
                  JSON.stringify([{ path: "/tmp/example.ace", openedAt: 1 }])
                );
                """
            )
            page.reload()

            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "resume-project-link"
            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "resume-clear-btn"
            page.keyboard.press("Enter")

            assert not page.locator("#resume-link").is_visible()
            assert page.evaluate('localStorage.getItem("ace-recent-files")') is None
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_import_choice_screen_uses_direct_route_rows(ace_server, browser_name):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/import")

            import_more = page.get_by_role("button", name="Import more data")
            if import_more.is_visible():
                import_more.click()

            assert page.locator(".ace-route-list").is_visible()
            assert page.locator(".ace-route-row").count() == 2
            assert page.locator("#step-folder").count() == 0
            assert page.get_by_role("button", name="Import a spreadsheet").is_visible()
            assert page.get_by_role("button", name="Import a folder").is_visible()
        finally:
            browser.close()
