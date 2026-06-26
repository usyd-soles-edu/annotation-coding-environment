from __future__ import annotations

import pytest
from playwright.sync_api import expect, sync_playwright

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
            page.wait_for_url("**/new-project", timeout=5000)
            assert page.evaluate("document.activeElement.id") == "new-project-input"

            page.keyboard.press("Escape")
            page.wait_for_url(f"{ace_server}/", timeout=5000)

            page.keyboard.press("n")
            page.wait_for_url("**/new-project", timeout=5000)
            page.go_back()
            assert page.url == f"{ace_server}/"

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
            assert page.evaluate(
                "() => document.activeElement.classList.contains('ace-home-tool-link')"
            )
            assert page.evaluate("document.activeElement.textContent.trim()") == "User guide"
            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "new-project-link"

            page.keyboard.press("Enter")
            page.wait_for_url("**/new-project", timeout=5000)
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
def test_new_project_form_controls_keep_keyboard_focus(
    ace_server, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/new-project")
            assert page.locator("#new-project-form").is_visible()
            assert page.evaluate("document.activeElement.id") == "new-project-input"

            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "choose-project-folder-btn"
            page.keyboard.press("ArrowUp")
            assert page.evaluate("document.activeElement.id") == "new-project-input"
            page.keyboard.press("ArrowUp")
            assert page.evaluate("document.activeElement.id") == "choose-project-folder-btn"
            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "new-project-input"
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_new_project_page_creates_project_from_keyboard(
    ace_server, tmp_path, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.route(
                "**/api/native/pick-folder",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"path": "%s"}' % str(tmp_path).replace('\\', '\\\\'),
                ),
            )

            page.goto(f"{ace_server}/new-project")
            page.locator("#new-project-input").fill("Keyboard Created")
            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "choose-project-folder-btn"
            page.keyboard.press("Enter")
            expect(page.locator("#new-project-folder-label")).to_have_text(str(tmp_path))
            assert page.evaluate("document.activeElement.id") == "create-project-btn"
            page.keyboard.press("Enter")

            page.wait_for_url("**/import", timeout=5000)
            assert (tmp_path / "Keyboard Created.ace").exists()
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_new_project_rejects_unsafe_project_name_before_submit(
    ace_server, tmp_path, browser_name
):
    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.route(
                "**/api/native/pick-folder",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"path": "%s"}' % str(tmp_path).replace('\\', '\\\\'),
                ),
            )

            page.goto(f"{ace_server}/new-project")
            page.locator("#new-project-input").fill("bad:name")
            page.locator("#choose-project-folder-btn").click()
            expect(page.locator("#new-project-folder-label")).to_have_text(str(tmp_path))
            expect(page.locator("#create-project-btn")).to_be_disabled()
            expect(page.locator("#ace-task-message")).to_contain_text(
                "Use a project name without"
            )

            page.locator("#new-project-input").fill("Safe Name")
            expect(page.locator("#ace-task-message")).to_have_text("")
            expect(page.locator("#create-project-btn")).to_be_enabled()
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_new_project_choose_another_folder_clears_conflicting_path(
    ace_server, tmp_path, browser_name
):
    existing = tmp_path / "Conflict.ace"
    conn = create_project(str(existing), "Conflict")
    conn.close()

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.route(
                "**/api/native/pick-folder",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"path": "%s"}' % str(tmp_path).replace('\\', '\\\\'),
                ),
            )

            page.goto(f"{ace_server}/new-project")
            page.locator("#new-project-input").fill("Conflict")
            page.locator("#choose-project-folder-btn").click()
            expect(page.locator("#new-project-folder-label")).to_have_text(str(tmp_path))
            expect(page.locator("#create-project-btn")).to_be_enabled()
            page.locator("#create-project-btn").click()
            expect(page.locator("#project-overwrite-dialog")).to_be_visible()

            page.get_by_role("button", name="Choose another folder").click()

            expect(page.locator("#project-overwrite-dialog")).to_have_count(0)
            expect(page.locator("#new-project-folder-label")).to_have_text("No folder chosen")
            expect(page.locator("#new-project-path-preview")).to_have_text("")
            expect(page.locator("#create-project-btn")).to_be_disabled()
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
                  JSON.stringify([
                    { path: "/tmp/example.ace", openedAt: 2 },
                    { path: "/tmp/backup.ace", openedAt: 1 }
                  ])
                );
                """
            )
            page.reload()

            resume = page.locator("#resume-link")
            assert resume.is_visible()

            page.locator("#resume-clear-btn").click()

            assert resume.is_visible()
            expect(page.locator("#resume-project-link")).to_have_text("backup.ace")
            assert page.evaluate(
                """
                () => JSON.parse(localStorage.getItem("ace-recent-files"))
                  .map((item) => item.path)
                """
            ) == ["/tmp/backup.ace"]
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
                  JSON.stringify([
                    { path: "/tmp/example.ace", openedAt: 2 },
                    { path: "/tmp/backup.ace", openedAt: 1 }
                  ])
                );
                """
            )
            page.reload()

            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "resume-project-link"
            page.keyboard.press("ArrowDown")
            assert page.evaluate("document.activeElement.id") == "resume-clear-btn"
            page.keyboard.press("Enter")

            expect(page.locator("#resume-project-link")).to_have_text("backup.ace")
            assert page.evaluate(
                """
                () => JSON.parse(localStorage.getItem("ace-recent-files"))
                  .map((item) => item.path)
                """
            ) == ["/tmp/backup.ace"]
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_landing_failed_resume_removes_only_dead_recent(
    ace_server, tmp_path, browser_name
):
    project = tmp_path / "Still here.ace"
    conn = create_project(str(project), "Still here")
    conn.close()
    missing = tmp_path / "Missing.ace"

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.goto(f"{ace_server}/")
            page.evaluate(
                """
                ([missingPath, projectPath]) => localStorage.setItem(
                  "ace-recent-files",
                  JSON.stringify([
                    { path: missingPath, openedAt: 2 },
                    { path: projectPath, openedAt: 1 }
                  ])
                )
                """,
                [str(missing), str(project)],
            )
            page.reload()

            page.locator("#resume-project-link").click()

            expect(page.locator("#ace-home-message")).to_contain_text(
                "Could not open that project"
            )
            expect(page.locator("#resume-project-link")).to_have_text("Still here.ace")
            assert page.evaluate(
                """
                () => JSON.parse(localStorage.getItem("ace-recent-files"))
                  .map((item) => item.path)
                """
            ) == [str(project)]
        finally:
            browser.close()


@pytest.mark.parametrize("browser_name", browser_params())
def test_landing_manual_open_failure_keeps_recents(
    ace_server, tmp_path, browser_name
):
    project = tmp_path / "Recent.ace"
    conn = create_project(str(project), "Recent")
    conn.close()
    missing = tmp_path / "Picked Missing.ace"

    with sync_playwright() as p:
        browser = getattr(p, browser_name).launch()
        try:
            page = browser.new_page()
            page.route(
                "**/api/native/pick-file",
                lambda route: route.fulfill(
                    status=200,
                    content_type="application/json",
                    body='{"path": "%s"}' % str(missing).replace('\\', '\\\\'),
                ),
            )
            page.goto(f"{ace_server}/")
            page.evaluate(
                """
                (projectPath) => localStorage.setItem(
                  "ace-recent-files",
                  JSON.stringify([{ path: projectPath, openedAt: 1 }])
                )
                """,
                str(project),
            )
            page.reload()

            page.locator("#open-existing-btn").click()

            expect(page.locator("#ace-home-message")).to_contain_text(
                "Could not open that project"
            )
            expect(page.locator("#resume-project-link")).to_have_text("Recent.ace")
            assert page.evaluate(
                """
                () => JSON.parse(localStorage.getItem("ace-recent-files"))
                  .map((item) => item.path)
                """
            ) == [str(project)]
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
