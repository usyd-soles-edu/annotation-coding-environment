"""Keyboard regression for the codebook context menu in all browser engines."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

import pytest

from ace.db.connection import create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code, add_folder
from ace.models.project import list_coders
from ace.models.source import add_source


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.slow
@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_codebook_menu_keyboard_access_and_focus(tmp_path, engine):
    sync_api = pytest.importorskip("playwright.sync_api")
    project = tmp_path / "menu.ace"
    conn = create_project(str(project), "Menu")
    source_id = add_source(conn, "Sample", "One sentence.", "row")
    coder_id = list_coders(conn)[0]["id"]
    alpha_id = add_code(conn, "Alpha", "#AA0000")
    add_code(conn, "Beta", "#00AA00")
    add_folder(conn, "Group")
    add_annotation(conn, source_id, coder_id, alpha_id, 0, 3, "One")
    conn.close()

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    for key in ("ACE_LAUNCHER_TOKEN", "ACE_RUNTIME_FILE", "ACE_IDLE_TIMEOUT_SECONDS"):
        env.pop(key, None)
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "ace.app:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 8
        while True:
            try:
                with urlopen(base + "/", timeout=0.5):
                    break
            except OSError:
                if server.poll() is not None or time.monotonic() >= deadline:
                    pytest.fail("ACE test server did not start")
                time.sleep(0.05)

        with sync_api.sync_playwright() as playwright:
            try:
                browser = getattr(playwright, engine).launch()
            except sync_api.Error as exc:
                if "Executable doesn't exist" in str(exc):
                    pytest.skip(f"Playwright {engine} is not installed")
                raise
            try:
                page = browser.new_page()
                page.goto(base + "/")
                assert page.request.post(base + "/api/project/open", form={"path": str(project)}).ok
                page.goto(base + "/code")
                row = page.locator(f'.ace-ht-row[data-code-id="{alpha_id}"]')
                row.wait_for()
                assert row.get_attribute("aria-haspopup") == "menu"
                shortcuts = row.get_attribute("aria-keyshortcuts")
                assert "Shift+F10" in shortcuts and "ContextMenu" in shortcuts

                row.focus()
                row.press("Shift+F10")
                menu = page.get_by_role("menu", name="Codebook actions")
                menu.wait_for()
                first = menu.get_by_role("menuitem", name="Move to folder")
                assert first.evaluate("el => el === document.activeElement")
                page.keyboard.press("End")
                assert menu.get_by_role("menuitem", name="Delete ⌫").evaluate(
                    "el => el === document.activeElement"
                )
                page.keyboard.press("Home")
                page.keyboard.press("Enter")
                back = menu.get_by_role("menuitem", name="← Back")
                back.wait_for()
                assert back.evaluate("el => el === document.activeElement")
                page.keyboard.press("ArrowDown")
                assert menu.get_by_role("menuitem", name="Group").evaluate(
                    "el => el === document.activeElement"
                )
                page.keyboard.press("Home")
                page.keyboard.press("Enter")
                first.wait_for()
                page.keyboard.press("Escape")
                assert menu.count() == 0
                page.wait_for_function(
                    "id => document.activeElement?.getAttribute('data-code-id') === id",
                    arg=alpha_id,
                )

                row.press("ContextMenu")
                menu.wait_for()
                page.keyboard.press("Escape")
                row.press("Shift+F10")
                menu.get_by_role("menuitem", name="Cut ⌘X").focus()
                page.keyboard.press("Enter")
                assert row.evaluate("el => el.classList.contains('ace-code-row--ghost')")
                assert row.evaluate("el => el === document.activeElement")
                row.press("Escape")
                row.click(button="right")
                menu.wait_for()
                page.keyboard.press("Escape")
                row.press("Shift+F10")
                menu.wait_for()
                page.keyboard.press("Tab")
                menu.wait_for(state="detached")
                row.focus()
                row.press("Shift+F10")
                menu.get_by_role("menuitem", name="Change colour…").focus()
                page.keyboard.press("Enter")
                palette = page.get_by_role("group", name="Change code colour")
                palette.wait_for()
                first_colour = palette.get_by_role("button").first
                assert first_colour.evaluate("el => el === document.activeElement")
                assert first_colour.get_attribute("aria-label").startswith("Set code colour to #")
                page.keyboard.press("Escape")
                assert palette.count() == 0
                assert row.evaluate("el => el === document.activeElement")
                folder = page.locator('.ace-ht-row[data-kind="folder"]')
                folder.focus()
                assert folder.get_attribute("aria-haspopup") == "menu"
                folder.press("Shift+F10")
                menu.get_by_role("menuitem", name="Rename folder F2").wait_for()
                page.keyboard.press("Escape")
                row.focus()
                row.press("Shift+F10")
                menu.get_by_role("menuitem", name="Change colour…").focus()
                page.keyboard.press("Enter")
                page.get_by_role("group", name="Change code colour").get_by_role(
                    "button", name="Set code colour to #0B4F8A"
                ).press("Enter")
                page.wait_for_function(
                    "id => document.querySelector(`.ace-ht-row[data-code-id='${id}']`)"
                    "?.style.getPropertyValue('--row-colour').trim().toUpperCase() === '#0B4F8A'",
                    arg=alpha_id,
                )
                page.wait_for_function(
                    "id => document.activeElement?.getAttribute('data-code-id') === id",
                    arg=alpha_id,
                )

                page.goto(f"{base}/code/{alpha_id}/view")
                audit_row = page.locator(f'.ace-ht-row[data-code-id="{alpha_id}"]')
                audit_row.wait_for()
                page.locator(".cv-track-row").first.wait_for()
                assert page.locator('.cv-track-row[tabindex="0"]').count() == 0
                assert "Shift+F10" in audit_row.get_attribute("aria-keyshortcuts")
                audit_row.focus()
                audit_row.press("Shift+F10")
                audit_menu = page.get_by_role("menu", name="Codebook actions")
                audit_menu.get_by_role(
                    "menuitem", name="View coded text V"
                ).wait_for()
                page.keyboard.press("ArrowDown")
                assert audit_menu.get_by_role("menuitem", name="Convert to folder").evaluate(
                    "el => el === document.activeElement"
                )
                assert page.locator('.cv-track-row[tabindex="0"]').count() == 0
                page.keyboard.press("Escape")
                assert page.url == f"{base}/code/{alpha_id}/view"
                audit_row.press("Shift+F10")
                page.get_by_role("menuitem", name="Change colour…").focus()
                page.keyboard.press("Enter")
                audit_palette = page.get_by_role("group", name="Change code colour")
                audit_palette.get_by_role("button").first.wait_for()
                page.keyboard.press("Escape")
                assert audit_row.evaluate("el => el === document.activeElement")
                assert page.url == f"{base}/code/{alpha_id}/view"
            finally:
                browser.close()
    finally:
        server.terminate()
        server.wait(timeout=5)
