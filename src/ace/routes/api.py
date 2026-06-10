"""API routes — JSON/HTMX fragment responses."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import platform
import random
import re
import sqlite3
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)


def _require_coder(request: Request) -> str:
    """Return coder_id from app state; raise HTTP 400 if not set.

    Used by every route that mutates coder-owned state. The single
    remaining caller that wants Optional semantics (the `codes`
    listing route) reads `request.app.state.coder_id` directly.
    """
    cid = getattr(request.app.state, "coder_id", None)
    if cid is None:
        raise HTTPException(status_code=400)
    return cid


def _safe_filename(name: str) -> str:
    """Sanitise a string for use in HTTP Content-Disposition filename.

    HTTP header values are ASCII/latin-1 only, and the filename attribute
    is vulnerable to header injection via CR/LF and parsing ambiguity from
    quotes/semicolons/backslashes. Collapses everything except alphanum,
    dot, dash, underscore, and space into underscores.
    """
    return re.sub(r"[^A-Za-z0-9._\- ]", "_", name)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _accept_to_types(accept: str | None) -> str:
    """Convert an accept filter like ".ace,.csv" to osascript type list."""
    if not accept:
        return ""
    extensions = [ext.lstrip(".").strip() for ext in accept.split(",") if ext.strip()]
    if not extensions:
        return ""
    quoted = ", ".join(f'"{e}"' for e in extensions)
    return f" of type {{{quoted}}}"


def _accept_to_filetypes(accept: str | None) -> list[tuple[str, str]]:
    """Convert an accept filter like ".ace,.csv" to tkinter filetypes."""
    if not accept:
        return []
    extensions = [ext.strip() for ext in accept.split(",") if ext.strip()]
    types = []
    for ext in extensions:
        ext = ext if ext.startswith(".") else f".{ext}"
        types.append((f"{ext.lstrip('.')} files", f"*{ext}"))
    return types


def _run_osascript(script: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _tk_root():
    """Create a hidden topmost tkinter root for file dialogs."""
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    return root


def _tk_pick_file(filetypes: list[tuple[str, str]] | None = None) -> str:
    from tkinter import filedialog
    root = _tk_root()
    path = filedialog.askopenfilename(filetypes=filetypes or [])
    root.destroy()
    return path or ""


def _tk_pick_folder() -> str:
    from tkinter import filedialog
    root = _tk_root()
    path = filedialog.askdirectory()
    root.destroy()
    return path or ""


def _tk_pick_files(filetypes: list[tuple[str, str]] | None = None) -> list[str]:
    from tkinter import filedialog
    root = _tk_root()
    paths = filedialog.askopenfilenames(filetypes=filetypes or [])
    root.destroy()
    return list(paths)


# ---------------------------------------------------------------------------
# Native file picker endpoints
# ---------------------------------------------------------------------------

@router.post("/native/pick-file")
async def pick_file(accept: str | None = Form(default=None)):
    """Open a native file picker and return the selected path."""
    if platform.system() == "Darwin":
        type_filter = _accept_to_types(accept)
        script = f'POSIX path of (choose file{type_filter})'
        result = await asyncio.to_thread(_run_osascript, script)
        path = result.stdout.strip() if result.returncode == 0 else ""
    else:
        filetypes = _accept_to_filetypes(accept)
        path = await asyncio.to_thread(_tk_pick_file, filetypes)
    return JSONResponse({"path": path})


@router.post("/native/pick-folder")
async def pick_folder():
    """Open a native folder picker and return the selected path."""
    if platform.system() == "Darwin":
        script = 'POSIX path of (choose folder)'
        result = await asyncio.to_thread(_run_osascript, script)
        path = result.stdout.strip() if result.returncode == 0 else ""
    else:
        path = await asyncio.to_thread(_tk_pick_folder)
    return JSONResponse({"path": path})


@router.post("/native/pick-files")
async def pick_files(accept: str | None = Form(default=None)):
    """Open a native file picker (multiple selection) and return paths."""
    if platform.system() == "Darwin":
        type_filter = _accept_to_types(accept)
        script = (
            f'set theFiles to (choose file{type_filter}'
            f' with multiple selections allowed)\n'
            f'set output to ""\n'
            f'repeat with f in theFiles\n'
            f'  set output to output & POSIX path of f & linefeed\n'
            f'end repeat\n'
            f'return output'
        )
        result = await asyncio.to_thread(_run_osascript, script)
        paths = [p for p in result.stdout.strip().split("\n") if p] if result.returncode == 0 else []
    else:
        filetypes = _accept_to_filetypes(accept)
        paths = await asyncio.to_thread(_tk_pick_files, filetypes)
    return JSONResponse({"paths": paths})


# ---------------------------------------------------------------------------
# Import preview fragment helper
# ---------------------------------------------------------------------------

def _import_done_actions(*, include_back: bool = False) -> str:
    import_more = (
        '<button class="ace-wizard-link ace-wizard-link--inline" type="button" '
        'onclick="showStep(\'step-choose\')">Import more data</button>'
    )
    if include_back:
        return (
            '<div class="ace-import-result-actions">'
            '<button class="ace-btn" type="button" onclick="showStep(\'step-choose\')">Back</button>'
            '<a href="/code" class="ace-btn ace-btn--primary ace-import-start">Start coding</a>'
            f"{import_more}"
            "</div>"
        )
    return (
        '<div class="ace-import-result-actions">'
        '<a href="/code" class="ace-btn ace-btn--primary ace-import-start">Start coding</a>'
        "</div>"
        '<div class="ace-import-result-actions ace-import-result-actions--secondary">'
        f"{import_more}"
        "</div>"
    )


def _import_result_fragment(count_label: str, source_label: str | None = None) -> str:
    source_html = ""
    if source_label:
        source_html = (
            " from "
            f'<span class="ace-import-result-meta">{html.escape(source_label)}</span>'
        )
    return (
        '<div class="ace-import-result">'
        '<div class="ace-import-result-top">'
        '<span class="ace-wizard-crumb">Import complete</span>'
        "</div>"
        f'<div class="ace-import-result-count">{html.escape(count_label)}</div>'
        f"<p>Imported successfully{source_html}</p>"
        f"{_import_done_actions()}"
        "</div>"
    )


def _folder_preview_teaser(snippet: str, max_chars: int = 72) -> str:
    teaser = " ".join(snippet.split())
    if not teaser:
        return "(empty file)"
    if len(teaser) > max_chars:
        return teaser[:max_chars].rstrip() + "..."
    return teaser


def _folder_preview_button(preview: dict, selected: bool) -> str:
    filename = str(preview["filename"])
    snippet = str(preview["snippet"])
    size_label = str(preview["size_label"])
    selected_class = " is-selected" if selected else ""
    aria_current = ' aria-current="true"' if selected else ""
    return (
        f'<button class="ace-folder-import-file{selected_class}" type="button"'
        f' data-import-preview-file data-filename="{html.escape(filename, quote=True)}"'
        f' data-size-label="{html.escape(size_label, quote=True)}"'
        f' data-preview-json="{html.escape(json.dumps(snippet), quote=True)}"{aria_current}>'
        f"<b>{html.escape(filename)}</b>"
        f"<span>{html.escape(size_label)}</span>"
        f"<small>{html.escape(_folder_preview_teaser(snippet))}</small>"
        "</button>"
    )


def _folder_preview_panel(preview: dict) -> str:
    return (
        '<section class="ace-folder-import-preview" aria-live="polite">'
        '<div class="ace-folder-import-preview-head">'
        "<div>"
        "<span>Previewing</span>"
        f'<strong data-import-preview-title>{html.escape(str(preview["filename"]))}</strong>'
        "</div>"
        f'<span data-import-preview-size>{html.escape(str(preview["size_label"]))}</span>'
        "</div>"
        '<div class="ace-folder-import-preview-body" tabindex="0">'
        f'<pre data-import-preview-text>{html.escape(str(preview["snippet"]))}</pre>'
        "</div>"
        "</section>"
    )


def _folder_import_preview_fragment(
    previews: list[dict], total: int, escaped_folder: str
) -> str:
    """Return the #import-preview HTML fragment (outerHTML-swappable)."""
    if not previews:
        return (
            '<div id="import-preview" class="ace-folder-import-empty">'
            '<p>No text files found.</p>'
            "</div>"
        )

    first = previews[0]
    buttons = "".join(
        _folder_preview_button(preview, selected=(i == 0))
        for i, preview in enumerate(previews)
    )
    visible = len(previews)
    remaining = max(total - visible, 0)
    more_label = (
        f"{remaining} more file{'s' if remaining != 1 else ''} imported"
        if remaining
        else "All files shown"
    )
    return (
        '<div id="import-preview" class="ace-folder-import-browser">'
        '<aside class="ace-folder-import-list" aria-label="Imported files">'
        '<div class="ace-folder-import-list-head">'
        '<div class="ace-folder-import-list-title">'
        "<strong>Random sample</strong>"
        f"<span>Showing {visible} of {total}</span>"
        "</div>"
        f'<button class="ace-folder-import-refresh" type="button"'
        f' hx-get="/api/import/preview?folder={escaped_folder}"'
        f' hx-target="#import-preview" hx-swap="outerHTML"'
        f' title="Preview another file"'
        f' aria-label="Preview another file">&#x21BB;</button>'
        "</div>"
        f'<div class="ace-folder-import-files">{buttons}</div>'
        f'<div class="ace-folder-import-more">{html.escape(more_label)}</div>'
        "</aside>"
        f"{_folder_preview_panel(first)}"
        "</div>"
    )


def _oob_announce(message: str, assertive: bool = False) -> str:
    """Return an OOB-swap fragment that writes to an ARIA live region.

    Screen readers announce polite by default; pass assertive=True for errors
    that should interrupt the user's flow. Returns a string fragment that a
    caller can concatenate to their existing HTML response body.
    """
    escaped = html.escape(message)
    target_id = "ace-live-region-assertive" if assertive else "ace-live-region"
    role = 'role="alert" ' if assertive else ""
    aria = "assertive" if assertive else "polite"
    return (
        f'<div {role}aria-live="{aria}" class="ace-sr-only" '
        f'id="{target_id}" hx-swap-oob="innerHTML">{escaped}</div>'
    )


def _with_headers(response: HTMLResponse, headers: dict[str, str]) -> HTMLResponse:
    """Mutate-and-return: merge headers onto an existing HTMLResponse."""
    for k, v in headers.items():
        response.headers[k] = v
    return response


def _oob_status_undo(message: str) -> str:
    """OOB-swap status with an inline [Z] undo keycap — for soft-delete actions.

    Returns the raw HTML string (not HTMLResponse) so callers can concatenate
    it with other OOB fragments before wrapping. Only emits the statusbar
    fragment + ARIA announce — the text-panel pill on /code is populated
    client-side by bridge.js (its DOM lives inside #text-panel, so an OOB
    swap to it would be clobbered by the primary swap that re-renders the
    text panel). Keycap is a real button so mouse users have a click target;
    pressing Z on the keyboard fires the same /api/undo path via bridge.js.
    """
    escaped = html.escape(message)
    inner = (
        f'<span class="ace-statusbar-undo-msg">{escaped}</span>'
        '<span class="ace-statusbar-undo-sep">·</span>'
        '<button type="button" class="ace-statusbar-undo" '
        'data-ace-undo-affordance="1" aria-label="Undo (Z)">'
        '<span class="ace-statusbar-undo-keycap">Z</span>'
        '<span>undo</span>'
        '</button>'
    )
    status_fragment = (
        '<span class="ace-statusbar-event ace-statusbar-event--undo" '
        'id="ace-statusbar-event" hx-swap-oob="outerHTML">' + inner + '</span>'
    )
    announce = _oob_announce(message, assertive=False)
    return status_fragment + announce


def _oob_status(message: str, kind: str = "err") -> HTMLResponse:
    """Return OOB-swap fragments that set the event channel on all pages.

    Emits three fragments:
      1. Statusbar event span (visible on /, /import, /agreement — hidden by
         CSS on /code but still DOM-present).
      2. Text-panel event pill (only exists on /code — HTMX silently drops
         the fragment on other pages).
      3. Assertive ARIA live region (because the statusbar and pill are
         aria-hidden / role=status, so screen-reader users would otherwise
         miss errors).

    kind is "err" for sticky errors, "ok" for 2-second ephemeral success
    (client-side timer in _setStatus clears ok pills).
    """
    escaped = html.escape(message)
    status_fragment = (
        f'<span class="ace-statusbar-event ace-statusbar-event--{kind}" '
        f'id="ace-statusbar-event" hx-swap-oob="outerHTML">{escaped}</span>'
    )
    # Same message, second target — only present on /code.
    pill_fragment = (
        f'<span class="ace-text-event-pill ace-text-event-pill--{kind}" '
        f'id="ace-text-event-pill" role="status" aria-live="polite" '
        f'hx-swap-oob="outerHTML">{escaped}</span>'
    )
    # Assertive region for errors (sticky), polite for ok (ephemeral).
    announce = _oob_announce(message, assertive=(kind == "err"))
    return HTMLResponse(status_fragment + pill_fragment + announce)


# ---------------------------------------------------------------------------
# Project create / open
# ---------------------------------------------------------------------------

@router.post("/project/create")
async def project_create(
    request: Request,
    name: str = Form(...),
    path: str = Form(...),
    overwrite: bool = Form(default=False),
    coder_name: str = Form(default="default"),
):
    """Create a new .ace project file."""
    from ace.db.connection import create_project
    from ace.models.project import list_coders

    file_path = _native_selection_path(path)

    # Ensure the path ends with .ace
    if file_path.suffix != ".ace":
        file_path = file_path.with_suffix(".ace")

    try:
        if file_path.exists() and not overwrite:
            file_name = html.escape(file_path.name)
            return HTMLResponse(
                '<dialog id="project-overwrite-dialog" '
                'class="ace-dialog ace-project-overwrite-dialog" '
                'aria-modal="true" aria-labelledby="project-overwrite-title" '
                'aria-describedby="project-overwrite-description">'
                '<h3 id="project-overwrite-title">A project already exists here</h3>'
                f'<p id="project-overwrite-description"><strong>{file_name}</strong> '
                "is already in this folder. Choose another location, or replace "
                "the existing project file.</p>"
                '<div class="ace-project-overwrite-note">'
                "Replacing this file will delete the existing ACE project at this path."
                "</div>"
                '<div class="ace-home-form-actions">'
                '<button type="button" class="ace-btn" onclick="window._aceChooseAnotherFolder()">Choose another folder</button>'
                '<button type="button" class="ace-btn ace-btn--danger" '
                'name="overwrite" value="true" onclick="window._aceConfirmOverwrite()">Overwrite project</button>'
                "</div>"
                "</dialog>"
            )

        if file_path.exists() and overwrite:
            file_path.unlink()

        conn = create_project(str(file_path), name, coder_name=coder_name)
        coders = list_coders(conn)
        coder_id = coders[0]["id"] if coders else None
        conn.close()

        request.app.state.project_path = str(file_path)
        if coder_id:
            request.app.state.coder_id = coder_id
        request.app.state.active_projects.add(str(file_path))

        return Response(
            status_code=200,
            headers={"HX-Redirect": "/import"},
        )
    except Exception as e:
        return _oob_status(f"Failed to create project: {e}")


@router.post("/project/open")
async def project_open(request: Request, path: str = Form(...)):
    """Open an existing .ace project file."""
    from ace.db.connection import open_project
    from ace.models.project import list_coders
    from ace.models.source import list_sources

    file_path = _native_selection_path(path)
    try:
        conn = open_project(str(file_path))
    except (ValueError, FileNotFoundError, sqlite3.DatabaseError) as e:
        return _oob_status(str(e))

    try:
        coders = list_coders(conn)
        coder_id = coders[0]["id"] if coders else None
        sources = list_sources(conn)
    finally:
        conn.close()

    request.app.state.project_path = str(file_path)
    if coder_id:
        request.app.state.coder_id = coder_id
    request.app.state.active_projects.add(str(file_path))

    redirect = "/code" if sources else "/import"
    return Response(
        status_code=200,
        headers={"HX-Redirect": redirect},
    )


# ---------------------------------------------------------------------------
# Import routes
# ---------------------------------------------------------------------------

def _native_selection_path(value: str) -> Path:
    """Accept native picker paths returned as POSIX paths or file:// URIs."""
    parsed = urlparse(value)
    if parsed.scheme == "file":
        path = unquote(parsed.path)
        if re.match(r"^/[A-Za-z]:/", path):
            path = path[1:]
        return Path(path)
    return Path(value)


@router.post("/import/file")
async def import_file_path(request: Request, path: str = Form(...)):
    """Parse a CSV/Excel file chosen by the native picker."""
    file_path = _native_selection_path(path)
    if not file_path.exists() or file_path.suffix.lower() not in {".csv", ".xlsx"}:
        return _oob_status("Choose a CSV or Excel file.")
    return _parse_tabular_for_mapping(
        request, file_path, cleanup=False, filename=file_path.name
    )


def _parse_tabular_for_mapping(
    request: Request, path: Path, *, cleanup: bool, filename: str
) -> HTMLResponse:
    from ace.services.importer import read_tabular

    try:
        rows, columns = read_tabular(path)
    except Exception as e:
        if cleanup:
            path.unlink(missing_ok=True)
        return _oob_status(f"Could not parse file: {e}")

    request.app.state.import_tmp_path = str(path)
    request.app.state.import_tmp_cleanup = cleanup
    request.app.state.import_source_name = filename
    return HTMLResponse(_build_import_mapping_fragment(filename, rows, columns))


def _infer_import_column_type(rows: list[dict], col_name: str) -> str:
    for row in rows[:8]:
        value = row.get(col_name)
        if value is None or value == "":
            continue
        if isinstance(value, (int, float)):
            return "number"
        try:
            float(str(value))
            return "number"
        except (TypeError, ValueError):
            return "text"
    return "text"


def _sample_values(rows: list[dict], col_name: str) -> str:
    vals = []
    for row in rows[:3]:
        value = row.get(col_name)
        sample = "NA" if value is None else str(value)
        if len(sample) > 30:
            sample = sample[:28] + "\u2026"
        vals.append(sample)
    return ", ".join(vals)


def _default_import_columns(rows: list[dict], columns: list[str]) -> tuple[str, list[str]]:
    if not columns:
        return "", []
    id_col = columns[0]
    text_cols = [
        col for col in columns[1:]
        if _infer_import_column_type(rows, col) == "text"
    ][:2]
    if not text_cols and len(columns) > 1:
        text_cols = [columns[1]]
    return id_col, text_cols


def _row_value(row: dict, col: str) -> str:
    value = row.get(col)
    return "" if value is None else str(value)


def _sample_import_preview_rows(rows: list[dict], limit: int = 20) -> list[dict]:
    if len(rows) <= limit:
        return rows
    return [rows[0], *random.sample(rows[1:], limit - 1)]


def _build_import_mapping_fragment(
    filename: str, rows: list[dict], columns: list[str]
) -> str:
    safe_filename = html.escape(filename)
    n_rows = len(rows)
    n_cols = len(columns)
    id_col, text_cols = _default_import_columns(rows, columns)
    first_row = rows[0] if rows else {}
    source_label = _row_value(first_row, id_col) if id_col else ""
    if not source_label:
        source_label = "Row 1" if rows else "No rows"

    preview_rows = _sample_import_preview_rows(rows)
    preview_payload = [
        {
            "label": _row_value(row, id_col) if id_col else f"Row {i + 1}",
            "values": {col: _row_value(row, col) for col in columns},
        }
        for i, row in enumerate(preview_rows)
    ]
    preview_data = html.escape(json.dumps(preview_payload), quote=True)
    selected_text_value = ",".join(text_cols)

    id_options = []
    for col in columns:
        esc_col = html.escape(str(col))
        selected = " selected" if col == id_col else ""
        id_options.append(f'<option value="{esc_col}"{selected}>{esc_col}</option>')

    examples = []
    seen = set()
    for row in rows:
        label = _row_value(row, id_col) if id_col else ""
        if not label or label in seen:
            continue
        seen.add(label)
        examples.append(f"<code>{html.escape(label)}</code>")
        if len(examples) == 3:
            break
    examples_html = "".join(examples) or "<code>No labels yet</code>"

    column_rows = []
    selected_text_set = set(text_cols)
    for col in columns:
        esc_col = html.escape(str(col))
        col_type = _infer_import_column_type(rows, col)
        sample = html.escape(_sample_values(rows, col))
        checked = " checked" if col in selected_text_set else ""
        selected_class = " is-selected" if checked else ""
        column_rows.append(
            f'<label class="ace-import-column-row{selected_class}">'
            f'<input type="checkbox" data-import-text-col value="{esc_col}"{checked}>'
            f"<code>{esc_col}</code>"
            f'<span class="ace-import-column-type">{html.escape(col_type)}</span>'
            f'<span class="ace-import-column-sample">{sample}</span>'
            "</label>"
        )
    column_rows_html = "".join(column_rows)

    preview_fields = []
    for col in text_cols:
        preview_fields.append(
            '<article class="ace-import-sample-field">'
            f"<header><b>{html.escape(str(col))}</b></header>"
            f"<p>{html.escape(_row_value(first_row, col))}</p>"
            "</article>"
        )
    preview_fields_html = "".join(preview_fields) or (
        '<article class="ace-import-sample-field">'
        "<p>Select at least one text column to preview source text.</p>"
        "</article>"
    )

    import_label = f"Import {n_rows:,} source{'s' if n_rows != 1 else ''}"

    return f"""
    <h1 class="ace-wizard-title" tabindex="-1">Choose source labels and coding text</h1>
    <form id="import-form" class="ace-import-mapping" hx-post="/api/import/commit" hx-target="#step-done" hx-swap="innerHTML"
          hx-on::after-request="window.handleImportCommit(event)">
      <div id="import-preview-data" data-preview-rows="{preview_data}" hidden></div>
      <div class="ace-import-mapping-grid">
        <section class="ace-import-card ace-import-card--source">
          <div class="ace-import-card-head">
            <strong>1. Source label</strong>
            <span>Names each source.</span>
          </div>
          <div class="ace-import-card-body">
            <label class="ace-import-field">
              <span>Column</span>
              <select id="import-id-choice" name="id_column_choice">
                {''.join(id_options)}
              </select>
            </label>
            <div class="ace-import-examples">
              <span>Example labels</span>
              {examples_html}
            </div>
          </div>
        </section>
        <section class="ace-import-card ace-import-card--text">
          <div class="ace-import-card-head">
            <strong>2. Text to code</strong>
            <span>Choose text columns.</span>
          </div>
          <div class="ace-import-toolbar">
            <input class="ace-import-search" value="" placeholder="Filter columns" aria-label="Filter columns">
            <span class="ace-import-summary">{n_cols:,} columns</span>
          </div>
          <div class="ace-import-column-list" tabindex="0" aria-label="Candidate text columns">
            {column_rows_html}
          </div>
          <div class="ace-import-card-foot">
            <span>Selected</span>
            <strong data-import-selected-count>{len(text_cols)}</strong>
          </div>
        </section>
        <section class="ace-import-preview-card">
          <div class="ace-import-preview-head">
            <div>
              <strong>Preview source</strong>
              <span data-import-preview-meta>row 1 · {len(text_cols)} column{'s' if len(text_cols) != 1 else ''}</span>
            </div>
            <button class="ace-folder-import-refresh" type="button" data-import-preview-refresh
                    aria-label="Show another random source">&#x21BB;</button>
          </div>
          <div class="ace-import-source-meta">
            <span>Source label</span>
            <code data-import-preview-label>{html.escape(source_label)}</code>
          </div>
          <div class="ace-import-preview-scroll" tabindex="0" aria-label="Preview selected source">
            {preview_fields_html}
          </div>
        </section>
      </div>
      <input type="hidden" name="id_column" id="import-id-col" value="{html.escape(str(id_col), quote=True)}">
      <input type="hidden" name="text_columns" id="import-text-cols" value="{html.escape(selected_text_value, quote=True)}">
      <div class="ace-import-actions">
        <button class="ace-btn" type="button" onclick="showStep('step-choose')">Back</button>
        <button type="submit" class="ace-btn ace-btn--primary" id="import-submit"{' disabled' if not (id_col and text_cols) else ''}>{import_label}</button>
      </div>
      <p class="ace-import-file-meta">{safe_filename} · {n_rows:,} rows x {n_cols:,} columns</p>
    </form>
    """


@router.post("/import/commit")
async def import_commit(
    request: Request,
    id_column: str = Form(default=""),
    text_columns: str = Form(default=""),
):
    """Commit the uploaded file: import selected columns as sources."""
    from ace.app import get_db
    from ace.services.importer import import_csv

    tmp_path = getattr(request.app.state, "import_tmp_path", None)
    if tmp_path is None or not Path(tmp_path).exists():
        return _oob_status("No uploaded file found. Please upload again.")

    db_gen = get_db(request)
    conn = next(db_gen)
    try:
        text_col_list = [c.strip() for c in text_columns.split(",") if c.strip()]
        if not id_column.strip():
            return _oob_status("Choose a source label column.")
        if not text_col_list:
            return _oob_status("Choose at least one text column.")
        count = import_csv(conn, tmp_path, id_column, text_col_list)
    except Exception as e:
        db_gen.close()
        return _oob_status(f"Import failed: {e}")
    finally:
        db_gen.close()

    # Clean up upload temp files. Native picker paths belong to the user.
    if getattr(request.app.state, "import_tmp_cleanup", True):
        Path(tmp_path).unlink(missing_ok=True)
    source_name = getattr(request.app.state, "import_source_name", None)
    request.app.state.import_tmp_path = None
    request.app.state.import_tmp_cleanup = True
    request.app.state.import_source_name = None

    count_label = f'{count} source{"s" if count != 1 else ""}'
    return HTMLResponse(_import_result_fragment(count_label, source_name))


@router.post("/import/folder")
async def import_folder(
    request: Request,
    path: str = Form(...),
):
    """Import .txt and .md files from a folder."""
    from ace.app import get_db
    from ace.services.importer import import_text_files, get_random_previews

    folder = _native_selection_path(path)
    if not folder.is_dir():
        return _oob_status("Invalid folder path.")

    db_gen = get_db(request)
    conn = next(db_gen)
    try:
        count = import_text_files(conn, folder)
    except Exception as e:
        db_gen.close()
        return _oob_status(f"Import failed: {e}")
    finally:
        db_gen.close()

    folder_name = html.escape(folder.name)
    escaped_path = html.escape(quote(str(folder), safe=""))

    total, previews = get_random_previews(folder)
    preview_html = (
        _folder_import_preview_fragment(previews, total, escaped_path)
        if previews
        else ""
    )

    return HTMLResponse(
        '<div class="ace-import-result ace-import-result--folder">'
        '<div class="ace-import-result-top">'
        '<span class="ace-wizard-crumb">Folder import</span>'
        f'<span class="ace-wizard-pill">{folder_name}/ · {count} file{"s" if count != 1 else ""}</span>'
        "</div>"
        '<h1 class="ace-wizard-title" tabindex="-1">Check imported text files</h1>'
        '<p class="ace-wizard-hint">'
        "ACE imported each text or Markdown file as a separate source. "
        "Scan a random sample before coding."
        "</p>"
        f"{preview_html}"
        f"{_import_done_actions(include_back=True)}"
        "</div>"
    )


@router.get("/code/{code_id}/view-data")
async def code_view_data_json(request: Request, code_id: str):
    """JSON payload that drives the /code/{id}/view audit view.

    Same dict that the page route embeds into <script id="ace-codeview-data">.
    Used by the client to switch between codes without a full page reload.
    """
    from ace.app import HtmxRedirect
    from ace.models.annotation import get_code_view_data

    project_path = getattr(request.app.state, "project_path", None)
    if project_path is None or not Path(project_path).exists():
        raise HtmxRedirect("/")
    coder_id = _require_coder(request)
    with _project_db(request) as conn:
        data = get_code_view_data(conn, code_id, coder_id)
    if data is None:
        raise HTTPException(status_code=404)
    return JSONResponse(data)


@router.get("/import/preview")
async def import_preview(folder: str = Query(...)):
    """Return an HTML fragment previewing a random text file from the folder."""
    from ace.services.importer import get_random_previews

    folder_path = Path(folder)
    if not folder_path.is_dir():
        return HTMLResponse('<p style="color:var(--ace-text-muted)">Invalid folder.</p>')

    total, previews = get_random_previews(folder_path)
    escaped_folder = html.escape(quote(folder, safe=""))
    return HTMLResponse(_folder_import_preview_fragment(previews, total, escaped_folder))


# ---------------------------------------------------------------------------
# CSV-download helper + annotation/notes exports
# ---------------------------------------------------------------------------


def _csv_download(
    request: Request,
    suffix: str,
    write_csv,
) -> Response:
    """Run `write_csv(conn, tmp_path)` against the project db, read the
    resulting CSV back and return it as an attachment download named
    `<project>_<suffix>_<timestamp>.csv`.

    Shared by the annotations and notes export routes — both follow the
    same open-db / write-to-tempfile / read-back / delete flow.
    """
    from datetime import datetime

    from ace.models.project import get_project

    with _project_db(request) as conn:
        project = get_project(conn)
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", delete=False, encoding="utf-8"
        )
        tmp.close()
        tmp_path = Path(tmp.name)
        try:
            write_csv(conn, tmp.name)
            content = tmp_path.read_text(encoding="utf-8")
        finally:
            tmp_path.unlink(missing_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    filename = _safe_filename(f"{project['name']}_{suffix}_{timestamp}.csv")
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export/annotations")
async def export_annotations(request: Request):
    """Export all annotations as CSV download."""
    from ace.services.exporter import export_annotations_csv

    return _csv_download(request, "annotations", export_annotations_csv)


# ---------------------------------------------------------------------------
# Coding annotation helpers
# ---------------------------------------------------------------------------


def _get_undo_manager(request: Request):
    """Get or create the UndoManager for the current project."""
    from ace.services.undo import UndoManager

    project_path = request.app.state.project_path
    managers = request.app.state.undo_managers
    if project_path not in managers:
        managers[project_path] = UndoManager()
    return managers[project_path]


@contextmanager
def _project_db(request: Request) -> Iterator[sqlite3.Connection]:
    """Context-manager form: yields a direct SQLite connection to the
    current project and closes it on exit.

    Replaces the old `_open_project_db` + `try/finally: conn.close()`
    scaffold that appeared at ~20 call sites.
    """
    conn = sqlite3.connect(request.app.state.project_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
    finally:
        conn.close()


def _hex_to_rgb(hex_col: str) -> tuple[int, int, int]:
    return int(hex_col[1:3], 16), int(hex_col[3:5], 16), int(hex_col[5:7], 16)


def _inject_oob(html: str, element_id: str) -> str:
    return html.replace(f'id="{element_id}"', f'id="{element_id}" hx-swap-oob="outerHTML"', 1)


def _render_colour_style_oob(codes: list[dict]) -> str:
    """Generate <style> block with per-code CSS classes and SVG rect fill rules.

    Emits three rules per code:
    - .ace-code-{cid}: background-color for sidebar dots and bottom chip colours
    - rect.ace-hl-{cid}: fill for annotation highlight rects in the SVG overlay
    - rect.ace-flash-{cid}: fill for temporary chip-click flash rects
    """
    parts = []
    for code in codes:
        # Folders carry colour='' (NOT NULL column); skip them — only kind='code'
        # rows ever paint annotation rects or sidebar dots.
        if code.get("kind") == "folder" or not code.get("colour"):
            continue
        r, g, b = _hex_to_rgb(code["colour"])
        cid = code["id"]
        parts.append(
            f".ace-code-{cid} {{"
            f" background-color: rgba({r},{g},{b},var(--ace-annotation-alpha)); }}"
        )
        parts.append(
            f"rect.ace-hl-{cid} {{"
            f" fill: rgba({r},{g},{b},0.30); }}"
        )
        parts.append(
            f"rect.ace-flash-{cid} {{"
            f" fill: rgba({r},{g},{b},0.70); }}"
        )
    return f'<style id="code-colours" hx-swap-oob="outerHTML">{chr(10).join(parts)}</style>'


def _render_ann_data_oob(ctx: dict) -> str:
    """Generate OOB div with annotation data for the SVG highlight overlay."""
    ann_json = ctx.get("annotation_highlights_json", "[]")
    return f'<div id="ace-ann-data" class="ace-hidden" data-annotations="{ann_json}" hx-swap-oob="outerHTML"></div>'


def _render_sources_data_oob(ctx: dict) -> str:
    """Emit an OOB-swap <script> blob with the sources_json payload so the
    client's sparkline + tile grid can re-render after an annotation change.
    """
    # Inside <script type="application/json"> HTML character refs are NOT decoded,
    # so html.escape would break JSON.parse at runtime. Use JSON \uXXXX escapes
    # for < > & — still valid JSON, can't terminate the tag early.
    payload = (
        json.dumps(ctx.get("sources_json", []))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return (
        '<script id="ace-sources-data" type="application/json" '
        f'hx-swap-oob="outerHTML">{payload}</script>'
    )


def _render_full_coding_oob(
    request: Request,
    conn,
    coder_id: str,
    target_index: int,
    include_sidebar: bool = True,
) -> str:
    """Render all coding swap zones with text-panel as the primary target.

    `include_sidebar=False` is for navigate/flag/undo paths where the
    sidebar's structure is unchanged — bridge.js's _syncCodeCounts patches
    the per-row count chips from the swapped-in #ace-ann-data so the aside
    doesn't need to be torn down and rebuilt on every action.
    """
    from ace.routes.pages import _coding_context
    from jinja2_fragments import render_block

    templates = request.app.state.templates
    project_path = request.app.state.project_path
    ctx = _coding_context(conn, coder_id, target_index, project_path=project_path)
    ctx["request"] = request

    parts = [render_block(templates.env, "coding.html", "text_panel", ctx)]
    inspector_html = render_block(templates.env, "coding.html", "right_inspector", ctx)
    parts.append(_inject_oob(inspector_html, "ace-right-inspector"))
    if include_sidebar:
        block_html = render_block(templates.env, "coding.html", "code_sidebar", ctx)
        parts.append(_inject_oob(block_html, "code-sidebar"))
    parts.append(_render_colour_style_oob(ctx["codes"]))
    parts.append(_render_ann_data_oob(ctx))
    parts.append(_render_sources_data_oob(ctx))
    return "".join(parts)


def _annotation_only_response(
    request: Request,
    conn,
    coder_id: str,
    target_index: int,
    extra: str = "",
) -> HTMLResponse:
    """OOB-only response for routes that don't change source text or codes.

    Returns applied-codes panel + data blobs only; bridge.js refreshes SVG
    highlights inside the existing #ace-hl-overlay and patches count chips
    from the swapped-in ann-data. HX-Reswap: none tells HTMX to leave #text-panel
    alone (otherwise the empty primary body would wipe it).
    """
    from ace.routes.pages import _coding_context
    from jinja2_fragments import render_block

    templates = request.app.state.templates
    project_path = request.app.state.project_path
    ctx = _coding_context(conn, coder_id, target_index, project_path=project_path)
    ctx["request"] = request

    applied_html = render_block(templates.env, "coding.html", "applied_codes_panel", ctx)
    parts = [
        _inject_oob(applied_html, "ace-applied-codes-panel"),
        _render_colour_style_oob(ctx["codes"]),
        _render_ann_data_oob(ctx),
        _render_sources_data_oob(ctx),
    ]
    return HTMLResponse("".join(parts) + extra, headers={"HX-Reswap": "none"})


def _resolve_source_id(conn, coder_id: str, current_index: int) -> str | None:
    """Get the source_id for the given assignment index."""
    from ace.models.assignment import get_assignments_for_coder

    assignments = get_assignments_for_coder(conn, coder_id)
    if not assignments or current_index >= len(assignments):
        return None
    return assignments[current_index]["source_id"]


# ---------------------------------------------------------------------------
# Coding annotation routes
# ---------------------------------------------------------------------------


@router.post("/code/apply")
async def annotate(
    request: Request,
    code_id: str = Form(...),
    current_index: int = Form(default=0),
    start_offset: int = Form(default=-1),
    end_offset: int = Form(default=-1),
    selected_text: str = Form(default=""),
):
    """Create an annotation and return updated text panel + annotation list."""
    from ace.models.annotation import add_annotation_merging

    coder_id = _require_coder(request)

    # If no selection provided, ignore
    if start_offset < 0 or end_offset < 0 or not selected_text:
        return HTMLResponse("", status_code=400)

    with _project_db(request) as conn:
        source_id = _resolve_source_id(conn, coder_id, current_index)
        if source_id is None:
            return HTMLResponse("", status_code=400)

        try:
            ann_id, replaced_ids = add_annotation_merging(
                conn, source_id, coder_id, code_id,
                start_offset, end_offset, selected_text,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Record for undo — compound if any existing annotations were merged
        undo = _get_undo_manager(request)
        if replaced_ids:
            undo.record_merge_add(source_id, ann_id, replaced_ids)
        else:
            undo.record_add(source_id, ann_id)

        return _annotation_only_response(request, conn, coder_id, current_index)


@router.post("/code/delete-annotation")
async def delete_annotation_route(
    request: Request,
    annotation_id: str = Form(...),
    current_index: int = Form(default=0),
):
    """Soft-delete an annotation and return updated HTML."""
    from ace.models.annotation import delete_annotation

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        # Look up source_id from the annotation before deleting
        ann_row = conn.execute(
            "SELECT source_id FROM annotation WHERE id = ?",
            (annotation_id,),
        ).fetchone()
        if ann_row is None:
            return HTMLResponse("", status_code=404)

        source_id = ann_row["source_id"]
        delete_annotation(conn, annotation_id)

        # Record for undo
        undo = _get_undo_manager(request)
        undo.record_delete(source_id, annotation_id)

        return _annotation_only_response(
            request,
            conn,
            coder_id,
            current_index,
            _oob_status_undo("Applied code removed"),
        )


def _build_undo_response(
    request: Request, conn, coder_id: str, current_index: int, result: dict
) -> HTMLResponse:
    """Assemble the HTMX swap, status bar, optional navigate trigger, and flash hint.

    Used by both `/api/undo` and `/api/redo` after the manager has run the
    inverse mutation. `result` is the dict returned from
    `UndoManager.undo(conn)` / `redo(conn)`:
        {
            "description": str,
            "source_id": str | None,
            "flash_annotation_id": str | None,
            "codebook_changed": bool,
        }
    """
    from ace.models.assignment import get_assignments_for_coder

    description = result["description"]
    source_id = result["source_id"]
    flash_id = result["flash_annotation_id"]

    # Determine target_index: stay where the user is unless the op was
    # bound to a different source than the one currently visible.
    target_index = current_index
    headers: dict = {}

    if source_id is not None:
        assignments = get_assignments_for_coder(conn, coder_id)
        idx = next(
            (i for i, a in enumerate(assignments) if a["source_id"] == source_id),
            None,
        )
        if idx is None:
            description += " (source no longer assigned)"
        elif idx != current_index:
            target_index = idx
            headers["HX-Trigger"] = json.dumps(
                {"ace-navigate": {"index": target_index, "total": len(assignments)}}
            )

    content = _render_full_coding_oob(
        request,
        conn,
        coder_id,
        target_index,
        include_sidebar=result.get("codebook_changed", True),
    )
    # _oob_status returns an HTMLResponse — extract its body to concat as a string.
    # It already emits an _oob_announce internally, so no separate announce call here.
    status_html = _oob_status(description, "ok").body.decode()
    content += status_html

    if flash_id is not None:
        # One-shot inline script that defers to bridge.js after settle. The
        # OOB swap replaces any previous flash hint on the page so multiple
        # consecutive undo/redo ops cleanly chain.
        content += (
            f'<script id="ace-undo-flash" hx-swap-oob="outerHTML">'
            f'window.addEventListener("htmx:afterSettle",function(e){{'
            f'if(window._flashAnnotation)window._flashAnnotation({json.dumps(flash_id)});'
            f'}},{{once:true}});</script>'
        )

    return HTMLResponse(content, headers=headers)


@router.post("/undo")
async def undo_route(
    request: Request,
    current_index: int = Form(default=0),
):
    """Pop the top entry from the global undo stack and replay its inverse."""
    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        mgr = _get_undo_manager(request)

        # OOB-only responses (no #text-panel content) — tell HTMX to skip the
        # primary swap; otherwise it would replace the text panel with empty.
        no_swap = {"HX-Reswap": "none"}

        if not mgr.can_undo():
            return _with_headers(_oob_status("Nothing to undo", "ok"), no_swap)

        try:
            result = mgr.undo(conn)
        except Exception:
            logger.exception("Undo failed")
            return _with_headers(_oob_status("Undo failed — please report this", "err"), no_swap)

        return _build_undo_response(request, conn, coder_id, current_index, result)


@router.post("/redo")
async def redo_route(
    request: Request,
    current_index: int = Form(default=0),
):
    """Pop the top entry from the global redo stack and replay it forward."""
    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        mgr = _get_undo_manager(request)

        no_swap = {"HX-Reswap": "none"}

        if not mgr.can_redo():
            return _with_headers(_oob_status("Nothing to redo", "ok"), no_swap)

        try:
            result = mgr.redo(conn)
        except Exception:
            logger.exception("Redo failed")
            return _with_headers(_oob_status("Redo failed — please report this", "err"), no_swap)

        return _build_undo_response(request, conn, coder_id, current_index, result)


# ---------------------------------------------------------------------------
# Source navigation + flag routes
# ---------------------------------------------------------------------------


@router.post("/code/flag")
async def flag_route(
    request: Request,
    source_index: int = Form(default=0),
):
    """Toggle the flagged status of the current source."""
    from ace.models.assignment import get_assignments_for_coder, set_flagged

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        assignments = get_assignments_for_coder(conn, coder_id)
        if not assignments or source_index >= len(assignments):
            return HTMLResponse("", status_code=400)

        assignment = assignments[source_index]
        source_id = assignment["source_id"]
        prev_flagged = bool(assignment["flagged"])
        new_flagged = not prev_flagged
        set_flagged(conn, source_id, coder_id, new_flagged)
        _get_undo_manager(request).record_flag_toggle(source_id, coder_id, prev_flagged)

        msg = "Source flagged" if new_flagged else "Source unflagged"
        content = _render_full_coding_oob(
            request, conn, coder_id, source_index, include_sidebar=False,
        ) + _oob_announce(msg)
        return HTMLResponse(content)


# ---------------------------------------------------------------------------
# Source note routes
# ---------------------------------------------------------------------------


@router.get("/source-note/{source_id}")
async def get_source_note(request: Request, source_id: str):
    """Return the current coder's note text for this source (empty if none)."""
    from ace.models.source_note import get_note

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        row = conn.execute("SELECT id FROM source WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            return JSONResponse({"error": "source not found"}, status_code=404)
        text = get_note(conn, source_id, coder_id) or ""
        return JSONResponse({"note_text": text})


@router.put("/source-note/{source_id}")
async def put_source_note(
    request: Request,
    source_id: str,
    note_text: str = Form(default=""),
):
    """Upsert (or delete via empty text) the current coder's note for a source.

    Returns a minimal JSON response (no HTMX swap) so the save doesn't
    interfere with the SVG highlight overlay. The JS caller updates the
    pill state client-side.
    """
    from ace.models.assignment import get_assignments_for_coder
    from ace.models.source_note import upsert_note

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        assignments = get_assignments_for_coder(conn, coder_id)
        found = any(a["source_id"] == source_id for a in assignments)
        if not found:
            return JSONResponse({"ok": False}, status_code=404)

        upsert_note(conn, source_id, coder_id, note_text)

        return JSONResponse({"ok": True, "has_note": bool(note_text.strip()), "promoted": False})


@router.get("/export/notes")
async def export_notes_route(request: Request):
    """Export all source notes for the current coder as a CSV download."""
    from ace.services.notes_exporter import export_notes_csv

    coder_id = _require_coder(request)
    return _csv_download(
        request,
        "notes",
        lambda conn, path: export_notes_csv(conn, coder_id, path),
    )


@router.post("/code/apply-sentence")
async def annotate_sentence(
    request: Request,
    code_id: str = Form(...),
    sentence_index: int = Form(...),
    current_index: int = Form(default=0),
):
    """Apply a code to a sentence with auto-merge.

    If the same code already exists on this sentence, toggle it off.
    If an adjacent sentence already has the same code, expand that
    annotation to include this sentence (merge) instead of creating a new row.
    Otherwise, add a new annotation alongside any existing codes.
    """
    from ace.models.annotation import (
        add_annotation, delete_annotation, expand_annotation, get_annotations_for_source,
    )
    from ace.models.source import get_source_content
    from ace.services.text_splitter import split_into_units

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        source_id = _resolve_source_id(conn, coder_id, current_index)
        if source_id is None:
            return HTMLResponse("", status_code=400)

        content_row = get_source_content(conn, source_id)
        if not content_row:
            return HTMLResponse("", status_code=400)

        source_text = content_row["content_text"]
        units = split_into_units(source_text)
        if sentence_index < 0 or sentence_index >= len(units):
            return HTMLResponse("", status_code=400)

        unit = units[sentence_index]
        start = unit["start_offset"]
        end = unit["end_offset"]

        # Check if this exact code already exists on this sentence (toggle)
        existing = get_annotations_for_source(conn, source_id, coder_id)
        existing_same_code = None
        for ann in existing:
            if ann["start_offset"] < end and ann["end_offset"] > start:
                if ann["code_id"] == code_id:
                    existing_same_code = ann
                    break

        undo = _get_undo_manager(request)

        if existing_same_code:
            # Toggle off: remove this specific code
            delete_annotation(conn, existing_same_code["id"])
            undo.record_delete(source_id, existing_same_code["id"])
        else:
            # Auto-merge: check if adjacent sentence already has the same code
            neighbour = None
            for ann in existing:
                if ann["code_id"] != code_id:
                    continue
                # Adjacent = annotation ends where this sentence starts (within 5 chars gap)
                # or annotation starts where this sentence ends
                gap_before = start - ann["end_offset"]
                gap_after = ann["start_offset"] - end
                if 0 <= gap_before <= 5 or 0 <= gap_after <= 5:
                    neighbour = ann
                    break

            if neighbour:
                # Expand the existing annotation to include this sentence
                new_start = min(neighbour["start_offset"], start)
                new_end = max(neighbour["end_offset"], end)
                new_text = source_text[new_start:new_end]
                expand_annotation(conn, neighbour["id"], new_start, new_end, new_text)
                undo.record_add(source_id, neighbour["id"])
            else:
                try:
                    ann_id = add_annotation(
                        conn, source_id, coder_id, code_id,
                        start, end, unit["text"],
                    )
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                undo.record_add(source_id, ann_id)

        return _annotation_only_response(request, conn, coder_id, current_index)


@router.post("/code/delete-sentence")
async def delete_sentence_annotations(
    request: Request,
    sentence_index: int = Form(...),
    current_index: int = Form(default=0),
):
    """Delete the most recently applied annotation on a focused sentence (X key).

    Press X multiple times to remove codes one by one (last-applied first).
    """
    from ace.models.annotation import delete_annotation
    from ace.models.source import get_source_content
    from ace.services.text_splitter import split_into_units

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        source_id = _resolve_source_id(conn, coder_id, current_index)
        if source_id is None:
            return HTMLResponse("", status_code=400)

        content_row = get_source_content(conn, source_id)
        if not content_row:
            return HTMLResponse("", status_code=400)

        units = split_into_units(content_row["content_text"])
        if sentence_index < 0 or sentence_index >= len(units):
            return HTMLResponse("", status_code=400)

        unit = units[sentence_index]
        start = unit["start_offset"]
        end = unit["end_offset"]

        # Find most recently created annotation overlapping this sentence
        most_recent = conn.execute(
            "SELECT id FROM annotation "
            "WHERE source_id = ? AND coder_id = ? AND deleted_at IS NULL "
            "AND start_offset < ? AND end_offset > ? "
            "ORDER BY created_at DESC LIMIT 1",
            (source_id, coder_id, end, start),
        ).fetchone()

        undo = _get_undo_manager(request)
        if most_recent:
            delete_annotation(conn, most_recent["id"])
            undo.record_delete(source_id, most_recent["id"])

        extra = _oob_announce("Annotation removed") if most_recent else ""
        return _annotation_only_response(request, conn, coder_id, current_index, extra)


# ---------------------------------------------------------------------------
# Codebook CRUD helpers
# ---------------------------------------------------------------------------


def _render_code_sidebar(request: Request, conn, coder_id: str, current_index: int) -> str:
    """Render just the code sidebar block."""
    from ace.routes.pages import _coding_context
    from jinja2_fragments import render_block

    templates = request.app.state.templates
    project_path = request.app.state.project_path
    ctx = _coding_context(conn, coder_id, current_index, project_path=project_path)
    ctx["request"] = request
    return render_block(templates.env, "coding.html", "code_sidebar", ctx)


def _codebook_tree_payload(
    tree_codes: list[dict],
    code_counts_by_id: dict[str, int],
) -> dict:
    """Return Headless Tree-friendly codebook data.

    The current sidebar renderer consumes nested Jinja rows. The Headless Tree
    adapter wants a stable item map: `root.children` gives top-level order and
    each item carries its direct child ids. Keep this translation server-side
    so the future tree island does not need to scrape sidebar DOM.
    """
    root_nodes = tree_codes[0].get("root_nodes", []) if tree_codes else []
    items = {
        "root": {
            "id": "root",
            "name": "Root",
            "kind": "folder",
            "parent_id": None,
            "level": 0,
            "children": [],
            "child_count": len(root_nodes),
            "count": 0,
        }
    }
    visited: set[str] = set()

    def visit(node: dict, parent_id: str) -> None:
        node_id = str(node["id"])
        if node_id in visited:
            return
        visited.add(node_id)

        children = node.get("children") or []
        child_ids = [str(child["id"]) for child in children]
        kind = str(node.get("kind", "code"))
        item = {
            "id": node_id,
            "name": str(node.get("name", "")),
            "kind": kind,
            "parent_id": None if parent_id == "root" else parent_id,
            "level": int(node.get("level", 1)),
            "sort_order": int(node.get("sort_order", 0)),
            "children": [],
            "child_count": len(child_ids) if kind == "folder" else 0,
            "count": int(code_counts_by_id.get(node_id, 0)) if kind == "code" else 0,
        }
        if kind == "code":
            item["colour"] = str(node.get("colour", ""))
            item["chord"] = node.get("chord")
            item["definition"] = node.get("definition") or ""
        items[node_id] = item
        items[parent_id]["children"].append(node_id)

        for child in children:
            visit(child, node_id)

    for root_node in root_nodes:
        visit(root_node, "root")

    return {
        "root_id": "root",
        "items": items,
    }


# ---------------------------------------------------------------------------
# Codebook CRUD routes
# ---------------------------------------------------------------------------


@router.get("/codes/tree")
async def codebook_tree_route(request: Request):
    """Return the current codebook tree as JSON for the Headless Tree island."""
    from ace.models.annotation import get_annotation_counts_by_code
    from ace.models.codebook import list_codes_with_tree

    project_path = getattr(request.app.state, "project_path", None)
    if not project_path:
        raise HTTPException(status_code=400, detail="project not open")

    coder_id = _require_coder(request)
    with _project_db(request) as conn:
        tree_codes = list_codes_with_tree(conn)
        code_counts_by_id = get_annotation_counts_by_code(conn, coder_id)
    return JSONResponse(_codebook_tree_payload(tree_codes, code_counts_by_id))


@router.post("/codes")
async def create_code(
    request: Request,
    name: str = Form(...),
    current_index: int = Form(default=0),
    parent_id: str | None = Form(default=None),
):
    """Create a new code and return updated sidebar."""
    from ace.models.codebook import (
        InvariantError,
        add_code,
        next_colour,
    )

    coder_id = _require_coder(request)

    name = name.strip()
    if not name:
        return _oob_status("Code name cannot be empty.")

    with _project_db(request) as conn:
        # Count active *codes* only — folders share the table but are not
        # part of the palette sequence, so including them would shift the
        # colour assigned to a fresh code based on how many folders exist.
        existing_count = conn.execute(
            "SELECT COUNT(*) FROM codebook_code "
            "WHERE deleted_at IS NULL AND kind = 'code'"
        ).fetchone()[0]
        colour = next_colour(existing_count)
        pid = parent_id.strip() if parent_id else None
        try:
            new_code_id = add_code(conn, name, colour, parent_id=pid or None)
        except InvariantError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except sqlite3.IntegrityError:
            return _oob_status(f"A code named '{name}' already exists.")
        _get_undo_manager(request).record_code_add(new_code_id)
        content = _render_code_sidebar(request, conn, coder_id, current_index)
        return HTMLResponse(content)


@router.post("/codes/folder")
async def create_folder_route(
    request: Request,
    name: str = Form(...),
    parent_id: str = Form(default=""),
    current_index: int = Form(default=0),
):
    """Create a new folder and return updated sidebar + text panel."""
    from ace.models.codebook import InvariantError, add_folder

    coder_id = _require_coder(request)

    name = name.strip()
    if not name:
        return _oob_status("Folder name cannot be empty.")

    with _project_db(request) as conn:
        pid = parent_id.strip() if parent_id else None
        try:
            folder_id = add_folder(conn, name, parent_id=pid or None)
        except InvariantError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except sqlite3.IntegrityError:
            return _oob_status(f"A folder named '{name}' already exists.")
        _get_undo_manager(request).record_create_folder(folder_id)
        content = _render_full_coding_oob(request, conn, coder_id, current_index)
        content += _oob_announce(f"Created folder {name}")
        return HTMLResponse(content, headers={"HX-Reswap": "none"})


def _scope_ordering(conn, scope_parent_id: str | None) -> list[tuple[str, int]]:
    """Snapshot (id, sort_order) for every active row in the given scope.

    `scope_parent_id` is None for root scope, else a folder id. Used by the
    parent-move and cut-paste routes to capture pre-move state for undo.
    """
    rows = conn.execute(
        "SELECT id, sort_order FROM codebook_code "
        "WHERE deleted_at IS NULL "
        "AND ((? IS NULL AND parent_id IS NULL) OR parent_id = ?)",
        (scope_parent_id, scope_parent_id),
    ).fetchall()
    return [(r["id"], r["sort_order"]) for r in rows]


@router.put("/codes/{code_id}/parent")
async def set_code_parent_route(
    request: Request,
    code_id: str,
    parent_id: str = Form(default=""),
    target_order_ids: str = Form(default=""),
    current_index: int = Form(default=0),
):
    """Move `code_id` into the scope of `parent_id` (folder id or empty for root)."""
    from ace.models.codebook import InvariantError, _move_code_to_parent_no_commit

    coder_id = _require_coder(request)
    new_parent: str | None = parent_id.strip() if parent_id else None
    new_parent = new_parent or None
    if target_order_ids:
        try:
            target_order = json.loads(target_order_ids)
        except (json.JSONDecodeError, TypeError):
            return _oob_status("Invalid target_order_ids format.")
        if not isinstance(target_order, list) or not all(
            isinstance(x, str) for x in target_order
        ):
            return _oob_status("Invalid target_order_ids format.")
    else:
        target_order = []

    with _project_db(request) as conn:
        prev = conn.execute(
            "SELECT parent_id FROM codebook_code WHERE id = ?", (code_id,)
        ).fetchone()
        if prev is None:
            raise HTTPException(status_code=404, detail=f"code {code_id} not found")
        prev_parent = prev["parent_id"]

        # Snapshot orderings BEFORE the move so undo can restore sibling
        # sort_orders that move_code_to_parent renumbered.
        prev_source_ordering = _scope_ordering(conn, prev_parent)
        prev_dest_ordering = _scope_ordering(conn, new_parent)

        try:
            _move_code_to_parent_no_commit(conn, code_id, new_parent)
            for i, item_id in enumerate(target_order):
                conn.execute(
                    "UPDATE codebook_code SET sort_order = ? "
                    "WHERE id = ? AND deleted_at IS NULL "
                    "AND ((? IS NULL AND parent_id IS NULL) OR parent_id = ?)",
                    (i, item_id, new_parent, new_parent),
                )
            conn.commit()
        except InvariantError as e:
            conn.rollback()
            raise HTTPException(status_code=400, detail=str(e))
        except Exception:
            conn.rollback()
            raise

        new_source_ordering = _scope_ordering(conn, prev_parent)
        new_dest_ordering = _scope_ordering(conn, new_parent)

        _get_undo_manager(request).record_move_parent(
            code_id=code_id,
            prev_parent_id=prev_parent,
            new_parent_id=new_parent,
            prev_source_ordering=prev_source_ordering,
            prev_dest_ordering=prev_dest_ordering,
            new_source_ordering=new_source_ordering,
            new_dest_ordering=new_dest_ordering,
        )
        content = _render_full_coding_oob(request, conn, coder_id, current_index)
        return HTMLResponse(content, headers={"HX-Reswap": "none"})


@router.post("/codes/{code_id}/indent-promote")
async def indent_promote_route(
    request: Request,
    code_id: str,
    above_code_id: str = Form(...),
    folder_name: str = Form(default="New folder"),
    current_index: int = Form(default=0),
):
    """Composite: create a folder, move (above_code_id, code_id) into it.

    Used by ⌥⇧→ — wraps two adjacent sibling codes into a brand-new folder
    in their current folder scope.
    The three writes (folder + 2 moves) run inside a single BEGIN IMMEDIATE
    transaction so a partial failure doesn't leave a half-built folder
    behind. On rollback, the gesture is a true no-op.
    """
    from ace.models.codebook import (
        InvariantError,
        _add_folder_no_commit,
        _move_code_to_parent_no_commit,
    )

    coder_id = _require_coder(request)
    with _project_db(request) as conn:
        # Validate both rows exist, are codes, and share one parent scope.
        rows = conn.execute(
            "SELECT id, kind, parent_id, sort_order FROM codebook_code "
            "WHERE id IN (?, ?) AND deleted_at IS NULL",
            (above_code_id, code_id),
        ).fetchall()
        by_id = {r["id"]: r for r in rows}
        if above_code_id not in by_id or code_id not in by_id:
            raise HTTPException(status_code=400, detail="code not found")
        if by_id[above_code_id]["kind"] != "code" or by_id[code_id]["kind"] != "code":
            raise HTTPException(status_code=400, detail="indent-promote requires two codes")
        shared_parent = by_id[code_id]["parent_id"]
        if by_id[above_code_id]["parent_id"] != shared_parent:
            raise HTTPException(status_code=400, detail="indent-promote requires sibling codes")
        prev_orders = {
            above_code_id: by_id[above_code_id]["sort_order"],
            code_id: by_id[code_id]["sort_order"],
        }

        # Atomic transaction — folder creation + two parent moves all-or-nothing.
        try:
            conn.execute("BEGIN IMMEDIATE")
            folder_id = _add_folder_no_commit(conn, folder_name, parent_id=shared_parent)
            _move_code_to_parent_no_commit(conn, above_code_id, folder_id)
            _move_code_to_parent_no_commit(conn, code_id, folder_id)
            conn.commit()
        except sqlite3.IntegrityError:
            conn.rollback()
            # OOB-only response (no #text-panel content) — tell HTMX to skip the
            # primary swap; otherwise it would replace the text panel with empty.
            return _with_headers(
                _oob_status(f"A folder named '{folder_name}' already exists."),
                {"HX-Reswap": "none"},
            )
        except InvariantError as e:
            conn.rollback()
            raise HTTPException(status_code=400, detail=str(e))

        _get_undo_manager(request).record_indent_promote_to_folder(
            folder_id=folder_id,
            code_ids=[above_code_id, code_id],
            prev_sort_orders=[prev_orders[above_code_id], prev_orders[code_id]],
            prev_parent_id=shared_parent,
        )
        # Look up the names for the announcement.
        name_rows = conn.execute(
            "SELECT id, name FROM codebook_code WHERE id IN (?, ?)",
            (above_code_id, code_id),
        ).fetchall()
        names = {r["id"]: r["name"] for r in name_rows}
        content = _render_full_coding_oob(request, conn, coder_id, current_index)
        content += _oob_announce(
            f"Created folder containing {names.get(above_code_id, '?')} and {names.get(code_id, '?')}"
        )
        return HTMLResponse(content)


@router.post("/codes/cut-paste")
async def cut_paste_route(
    request: Request,
    code_id: str = Form(...),
    target_id: str = Form(default=""),
    current_index: int = Form(default=0),
):
    """Move `code_id` into the scope determined by `target_id`.

    `target_id` is either a folder id (move into that folder) or a code id
    (move into the same scope as that code).
    """
    from ace.models.codebook import InvariantError, move_code_to_parent

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        # Empty target_id means "paste to root scope" — the context menu
        # uses this to surface the top-level paste target. Fall through to
        # the row lookup only when an actual id is supplied.
        if target_id == "":
            new_parent: str | None = None
        else:
            target = conn.execute(
                "SELECT id, kind, parent_id FROM codebook_code "
                "WHERE id = ? AND deleted_at IS NULL",
                (target_id,),
            ).fetchone()
            if target is None:
                raise HTTPException(status_code=404, detail="target_id not found")
            if target["kind"] == "folder":
                new_parent = target["id"]
            else:
                new_parent = target["parent_id"]

        prev = conn.execute(
            "SELECT parent_id FROM codebook_code WHERE id = ?", (code_id,)
        ).fetchone()
        if prev is None:
            raise HTTPException(status_code=404, detail="code_id not found")
        prev_parent = prev["parent_id"]

        # Snapshot orderings BEFORE the move so undo can restore sibling
        # sort_orders that move_code_to_parent renumbered.
        prev_source_ordering = _scope_ordering(conn, prev_parent)
        prev_dest_ordering = _scope_ordering(conn, new_parent)

        try:
            move_code_to_parent(conn, code_id, new_parent)
        except InvariantError as e:
            raise HTTPException(status_code=400, detail=str(e))

        _get_undo_manager(request).record_move_parent(
            code_id=code_id,
            prev_parent_id=prev_parent,
            new_parent_id=new_parent,
            prev_source_ordering=prev_source_ordering,
            prev_dest_ordering=prev_dest_ordering,
        )
        content = _render_full_coding_oob(request, conn, coder_id, current_index)
        return HTMLResponse(content, headers={"HX-Reswap": "none"})


@router.post("/codes/reorder-in-scope")
async def reorder_in_scope_route(
    request: Request,
    code_ids: str = Form(...),
    parent_id: str = Form(default=""),
    current_index: int = Form(default=0),
):
    """Reorder codebook items within a single scope. Returns text-panel + sidebar OOB.

    Same response shape as the parent / cut-paste / indent-promote routes
    so the count chips stay consistent. Records an undo entry for the
    affected scope so Z reverts the drag — matches the legacy
    ``/codes/reorder`` route's behaviour.

    The UPDATE is scoped to ``parent_id`` defensively: only rows already in
    that scope have their ``sort_order`` rewritten, so a stale client that
    sends ids from another scope can't accidentally move them.
    """
    coder_id = _require_coder(request)
    try:
        new_order = json.loads(code_ids)
    except (json.JSONDecodeError, TypeError):
        return _oob_status("Invalid code_ids format.")
    # Shape check: must be a list of strings. A stale or malicious client
    # sending objects/numbers shouldn't reach the SQL layer.
    if not isinstance(new_order, list) or not all(isinstance(x, str) for x in new_order):
        return _oob_status("Invalid code_ids format.")

    scope = parent_id.strip() if parent_id else ""
    scope_value: str | None = scope or None

    with _project_db(request) as conn:
        # Snapshot the scope's current (id, sort_order) BEFORE the UPDATE so
        # undo can restore the prior order.
        prev = [
            (r["id"], r["sort_order"])
            for r in conn.execute(
                "SELECT id, sort_order FROM codebook_code "
                "WHERE deleted_at IS NULL "
                "AND ((? IS NULL AND parent_id IS NULL) OR parent_id = ?) "
                "ORDER BY id",
                (scope_value, scope_value),
            ).fetchall()
        ]
        for i, cid in enumerate(new_order):
            conn.execute(
                "UPDATE codebook_code SET sort_order = ? "
                "WHERE id = ? AND deleted_at IS NULL "
                "AND ((? IS NULL AND parent_id IS NULL) OR parent_id = ?)",
                (i, cid, scope_value, scope_value),
            )
        conn.commit()
        new = [
            (r["id"], r["sort_order"])
            for r in conn.execute(
                "SELECT id, sort_order FROM codebook_code "
                "WHERE deleted_at IS NULL "
                "AND ((? IS NULL AND parent_id IS NULL) OR parent_id = ?) "
                "ORDER BY id",
                (scope_value, scope_value),
            ).fetchall()
        ]
        # Skip recording on no-ops so one drag doesn't burn two undo presses.
        if prev != new:
            _get_undo_manager(request).record_code_reorder(prev, new)
        content = _render_full_coding_oob(request, conn, coder_id, current_index)
        return HTMLResponse(content, headers={"HX-Reswap": "none"})


@router.post("/codes/reorder")
async def reorder_codes_route(
    request: Request,
    code_ids: str = Form(...),
    current_index: int = Form(default=0),
):
    """Reorder codes and return updated sidebar."""
    from ace.models.codebook import reorder_codes

    coder_id = _require_coder(request)

    try:
        ids_list = json.loads(code_ids)
    except (json.JSONDecodeError, TypeError):
        return _oob_status("Invalid code_ids format.")

    with _project_db(request) as conn:
        # ORDER BY id keeps prev/new aligned across the two reads so the undo
        # payload zips the right (id, sort_order) pairs — SQLite makes no
        # default ordering guarantee.
        prev = [
            (r["id"], r["sort_order"])
            for r in conn.execute(
                "SELECT id, sort_order FROM codebook_code WHERE deleted_at IS NULL ORDER BY id"
            ).fetchall()
        ]
        reorder_codes(conn, ids_list)
        new = [
            (r["id"], r["sort_order"])
            for r in conn.execute(
                "SELECT id, sort_order FROM codebook_code WHERE deleted_at IS NULL ORDER BY id"
            ).fetchall()
        ]
        # Skip recording when nothing actually changed. The client uses this
        # endpoint to re-render the sidebar after side-channel mutations
        # (group rename, etc.) and would otherwise pollute the undo stack
        # with no-op entries — making one user drag take two undo presses.
        if prev != new:
            _get_undo_manager(request).record_code_reorder(prev, new)
        content = _render_code_sidebar(request, conn, coder_id, current_index)
        return HTMLResponse(content, headers={"HX-Reswap": "none"})


# ---------------------------------------------------------------------------
# Codebook import / export  (registered before {code_id} to avoid path clash)
# ---------------------------------------------------------------------------


@router.get("/codes/export")
async def export_codebook(request: Request):
    """Export the codebook as a CSV file download."""
    from ace.models.codebook import export_codebook_to_csv

    with _project_db(request) as conn:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        tmp.close()
        export_codebook_to_csv(conn, tmp.name)

    return FileResponse(
        tmp.name,
        media_type="text/csv",
        filename="codebook.csv",
    )


def _normalise_codebook_mapping_column(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def _codebook_mapping_select(
    *,
    field_id: str,
    label: str,
    columns: list[str],
    selected: str | None,
    optional: bool = False,
) -> str:
    options = []
    if optional:
        options.append(
            '<option value=""'
            f'{" selected" if selected is None else ""}>None</option>'
        )
    for column in columns:
        safe = html.escape(column)
        options.append(
            f'<option value="{safe}"'
            f'{" selected" if column == selected else ""}>{safe}</option>'
        )
    return (
        '<label class="ace-codebook-import-field">'
        f'<span>{html.escape(label)}</span>'
        f'<select id="{field_id}" class="ace-codebook-import-select" '
        f'data-codebook-import-map>{"".join(options)}</select>'
        '</label>'
    )


def _render_codebook_import_preview(previewed: list[dict]) -> str:
    if not previewed:
        return (
            '<div class="ace-codebook-import-empty">'
            'No importable codes found with these columns.</div>'
        )

    groups: dict[str, list[dict]] = {}
    for code in previewed:
        groups.setdefault(code.get("group_name") or "", []).append(code)

    parts = []
    for group_name, codes in groups.items():
        if group_name:
            parts.append(
                '<div class="ace-codebook-import-folder">'
                f'{html.escape(group_name)}</div>'
            )
        for code in codes:
            status = "exists" if code["exists"] else "new"
            definition = (code.get("definition") or "").strip()
            definition_html = (
                f'<span class="ace-codebook-import-definition">'
                f'{html.escape(definition)}</span>'
                if definition else ""
            )
            parts.append(
                f'<div class="ace-codebook-import-row ace-codebook-import-row--{status}">'
                f'<span class="ace-codebook-import-stripe" '
                f'style="background:{html.escape(code["colour"])}"></span>'
                f'<span class="ace-codebook-import-name">{html.escape(code["name"])}</span>'
                f'{definition_html}'
                f'<span class="ace-codebook-import-badge">{status}</span>'
                '</div>'
            )
    return "".join(parts)


def _codebook_import_payload(
    conn: sqlite3.Connection,
    path: Path,
    name_column: str | None,
    group_column: str | None,
    definition_column: str | None,
) -> dict:
    from ace.models.codebook import preview_codebook_csv

    if not name_column:
        return {
            "preview_html": (
                '<div class="ace-codebook-import-empty">'
                'Choose the column that contains code names.</div>'
            ),
            "codes_json": "[]",
            "new_count": 0,
            "exists_count": 0,
            "summary": "No code column selected",
            "import_label": "Import",
            "disabled": True,
        }

    previewed = preview_codebook_csv(
        conn,
        path,
        name_column=name_column,
        group_column=group_column,
        definition_column=definition_column,
    )
    new_codes = [c for c in previewed if not c["exists"]]
    existing_codes = [c for c in previewed if c["exists"]]
    codes_for_import = [
        {
            "name": c["name"],
            "colour": c["colour"],
            "group_name": c.get("group_name"),
            "definition": c.get("definition"),
        }
        for c in new_codes
    ]
    new_count = len(new_codes)
    exists_count = len(existing_codes)
    summary = f"{new_count} new"
    if exists_count:
        summary += f" · {exists_count} already exist"
    import_label = f'Import {new_count} code{"s" if new_count != 1 else ""}'
    return {
        "preview_html": _render_codebook_import_preview(previewed),
        "codes_json": json.dumps(codes_for_import),
        "new_count": new_count,
        "exists_count": exists_count,
        "summary": summary,
        "import_label": import_label,
        "disabled": new_count == 0,
    }


@router.post("/codes/import/preview-path")
async def import_codebook_preview_path(
    request: Request,
    path: str = Form(...),
    current_index: int = Form(default=0),
):
    """Preview a codebook CSV from a local file path (native file picker flow)."""
    from ace.models.codebook import inspect_codebook_csv

    coder_id = _require_coder(request)

    file_path = Path(path)
    if file_path.suffix.lower() != ".csv":
        return _oob_status("Please select a valid CSV file.")

    try:
        with _project_db(request) as conn:
            inspection = inspect_codebook_csv(file_path)
            columns = inspection["columns"]
            detected = inspection["detected"]
            payload = _codebook_import_payload(
                conn,
                file_path,
                detected.get("name"),
                detected.get("group"),
                detected.get("definition"),
            )
    except Exception as e:
        return _oob_status(f"Could not parse CSV: {e}")

    filename = html.escape(file_path.name)
    safe_path = html.escape(str(file_path))
    codes_json_escaped = html.escape(payload["codes_json"])

    dialog_html = (
        '<dialog class="ace-dialog ace-import-dialog ace-codebook-import-dialog" '
        f'data-csv-path="{safe_path}" data-current-index="{current_index}">'
        '<div class="ace-import-dialog-title">Import Codebook</div>'
        f'<div class="ace-import-dialog-sub">{filename} · {html.escape(payload["summary"])}</div>'
        '<div class="ace-codebook-import-layout">'
        '<section class="ace-codebook-import-map">'
        '<p>ACE guessed these columns. Change only what looks wrong.</p>'
        f'{_codebook_mapping_select(field_id="codebook-map-name", label="Code", columns=columns, selected=detected.get("name"))}'
        f'{_codebook_mapping_select(field_id="codebook-map-group", label="Folder", columns=columns, selected=detected.get("group"), optional=True)}'
        f'{_codebook_mapping_select(field_id="codebook-map-definition", label="Definition", columns=columns, selected=detected.get("definition"), optional=True)}'
        '</section>'
        '<section class="ace-codebook-import-sidebar-preview" aria-live="polite">'
        '<div class="ace-codebook-import-sidebar-head">Sidebar preview</div>'
        f'<div id="codebook-import-preview" class="ace-codebook-import-preview-list">{payload["preview_html"]}</div>'
        '</section>'
        '</div>'
        '<div class="ace-import-actions">'
        '<button type="button" class="ace-btn" onclick="this.closest(\'dialog\').close()">Cancel</button>'
        f'<button type="button" class="ace-btn ace-btn--primary" '
        f'id="codebook-import-commit" onclick="aceImportFromPreview(this)" '
        f'data-codes="{codes_json_escaped}" data-current-index="{current_index}"'
        f'{" disabled" if payload["disabled"] else ""}>'
        f'{html.escape(payload["import_label"])}</button>'
        '</div></dialog>'
    )

    return HTMLResponse(dialog_html)


@router.post("/codes/import/preview-map")
async def import_codebook_preview_map(
    request: Request,
    path: str = Form(...),
    name_column: str = Form(default=""),
    group_column: str = Form(default=""),
    definition_column: str = Form(default=""),
):
    """Refresh codebook import preview after the user changes column mapping."""
    _require_coder(request)

    file_path = Path(path)
    try:
        with _project_db(request) as conn:
            payload = _codebook_import_payload(
                conn,
                file_path,
                _normalise_codebook_mapping_column(name_column),
                group_column,
                definition_column,
            )
    except Exception as e:
        return JSONResponse(
            {
                "preview_html": (
                    '<div class="ace-codebook-import-empty">'
                    f'Could not preview CSV: {html.escape(str(e))}</div>'
                ),
                "codes_json": "[]",
                "new_count": 0,
                "exists_count": 0,
                "summary": "Preview failed",
                "import_label": "Import",
                "disabled": True,
            }
        )
    return JSONResponse(payload)


@router.post("/codes/import")
async def import_codebook(
    request: Request,
    codes_json: str = Form(...),
    current_index: int = Form(default=0),
):
    """Import selected codes from a previously previewed CSV."""
    from ace.models.codebook import import_selected_codes

    coder_id = _require_coder(request)

    try:
        codes_list = json.loads(codes_json)
    except (json.JSONDecodeError, TypeError):
        return _oob_status("Invalid codes_json format.")

    with _project_db(request) as conn:
        imported_ids = import_selected_codes(conn, codes_list)
        if imported_ids:
            _get_undo_manager(request).record_codebook_import(imported_ids)
        content = _render_code_sidebar(request, conn, coder_id, current_index)

    # Clean up temp file
    tmp_path = getattr(request.app.state, "codebook_import_tmp", None)
    if tmp_path:
        Path(tmp_path).unlink(missing_ok=True)
        request.app.state.codebook_import_tmp = None

    return HTMLResponse(content)


# ---------------------------------------------------------------------------
# Codebook {code_id} routes
# ---------------------------------------------------------------------------


@router.post("/codes/{code_id}/convert-to-folder")
async def convert_code_to_folder_route(
    request: Request,
    code_id: str,
    current_index: int = Form(default=0),
):
    """Convert a code to a folder, preserving annotations in a child code."""
    from ace.models.codebook import InvariantError, convert_code_to_folder

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        try:
            result = convert_code_to_folder(conn, code_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="code not found")
        except InvariantError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except sqlite3.IntegrityError:
            return _with_headers(
                _oob_status("A folder with that name already exists."),
                {"HX-Reswap": "none"},
            )

        _get_undo_manager(request).record_code_convert_to_folder(
            code_id=code_id,
            prev_colour=result["prev_colour"],
            prev_chord=result["prev_chord"],
            child_code_id=result["child_code_id"],
            annotation_ids=result["annotation_ids"],
        )
        content = _render_full_coding_oob(request, conn, coder_id, current_index)
        n = len(result["annotation_ids"])
        if n:
            unit = "annotation" if n == 1 else "annotations"
            message = f'Converted "{result["name"]}" to folder · preserved {n} {unit}'
        else:
            message = f'Converted "{result["name"]}" to folder'
        content += _oob_status_undo(message)
        return HTMLResponse(content)


@router.put("/codes/{code_id}")
async def update_code_route(
    request: Request,
    code_id: str,
    name: str | None = Form(default=None),
    colour: str | None = Form(default=None),
    current_index: int = Form(default=0),
):
    """Update a code (rename, recolour) and return sidebar + text panel.

    Folder rename uses this same endpoint — folders share the `name` column
    and `kind='folder'` is preserved by `update_code`.
    """
    from ace.models.codebook import update_code

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        kwargs: dict = {}
        if name is not None:
            name = name.strip()
            if not name:
                return _oob_status("Code name cannot be empty.")
            kwargs["name"] = name
        if colour is not None:
            if not re.fullmatch(r'#[0-9a-fA-F]{6}', colour):
                return _oob_status("Invalid colour format.")
            kwargs["colour"] = colour

        # Read the prior state so we can record the right inverse op(s).
        prev = conn.execute(
            "SELECT name, colour FROM codebook_code WHERE id = ?",
            (code_id,),
        ).fetchone()
        if prev is None:
            raise HTTPException(status_code=404, detail=f"code {code_id} not found")

        try:
            update_code(conn, code_id, **kwargs)
        except sqlite3.IntegrityError:
            return _oob_status("An item with that name already exists.")

        mgr = _get_undo_manager(request)
        if "name" in kwargs and kwargs["name"] != prev["name"]:
            mgr.record_code_rename(code_id, prev["name"], kwargs["name"])
        if "colour" in kwargs and kwargs["colour"] != prev["colour"]:
            mgr.record_code_recolour(code_id, prev["colour"], kwargs["colour"])

        content = _render_full_coding_oob(request, conn, coder_id, current_index)
        return HTMLResponse(content)


@router.delete("/codes/{code_id}")
async def delete_code_route(
    request: Request,
    code_id: str,
    current_index: int = Query(default=0),
):
    """Delete a code or folder (cascades annotations / lifts children) and
    return sidebar + text panel."""
    from ace.models.codebook import delete_code

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        # Capture the prior row (name + parent + sort_order + kind) before
        # deletion — the row's deleted_at is set afterwards but we still need
        # the pre-delete shape for the undo entry.
        prev = conn.execute(
            "SELECT name, kind, parent_id, sort_order "
            "FROM codebook_code WHERE id = ?",
            (code_id,),
        ).fetchone()
        if prev is None:
            raise HTTPException(status_code=404, detail="code not found")
        code_name = prev["name"]

        affected_anns, affected_children = delete_code(conn, code_id)
        mgr = _get_undo_manager(request)
        if prev["kind"] == "folder":
            mgr.record_delete_folder_cascade(
                folder_id=code_id,
                child_ids=affected_children,
                annotation_ids=affected_anns,
            )
        else:
            mgr.record_code_delete(
                code_id=code_id,
                affected_annotation_ids=affected_anns,
                prev_parent_id=prev["parent_id"],
                prev_sort_order=prev["sort_order"],
                children_lifted_ids=affected_children,
            )
        content = _render_full_coding_oob(request, conn, coder_id, current_index)

        # Soft-delete affordance: status bar carries an inline [Z] undo keycap.
        n = len(affected_anns)
        if n > 0:
            unit = "annotation" if n == 1 else "annotations"
            message = f'Deleted "{code_name}" · {n} {unit} removed'
        else:
            message = f'Deleted "{code_name}"'
        content += _oob_status_undo(message)

        return HTMLResponse(content)


# ---------------------------------------------------------------------------
# Agreement routes
# ---------------------------------------------------------------------------


def _agreement_error(message: str) -> str:
    return (
        '<h1 class="ace-agreement-title">Inter-Coder Agreement</h1>'
        '<div class="ace-agreement-error">'
        f'<p>{html.escape(message)}</p>'
        '<button class="ace-agreement-choose-btn" onclick="acePickAndCompute()">Choose different files</button>'
        '</div>'
    )


def _agreement_fmt(val: float | None, decimals: int = 2, is_pct: bool = False) -> str:
    if val is None:
        return "\u2013"
    if is_pct:
        return f"{val * 100:.1f}"
    return f"{val:.{decimals}f}"


def _render_agreement_results(result, dataset, loader, jinja_env) -> str:
    from ace.services.agreement_verdict import classify_code, classify_overall

    n_coders = result.n_coders

    # Compute totals for context bar
    all_source_hashes = set()
    for fd in loader._file_data:
        all_source_hashes |= {s["content_hash"] for s in fd["sources"].values()}
    all_code_names = set()
    for fd in loader._file_data:
        all_code_names |= {info["name"] for info in fd["codes"].values()}

    # Build per-code verdicts
    code_verdicts = {
        name: classify_code(m) for name, m in result.per_code.items()
    }

    # Sort codes in codebook order (by sort_order from MatchedCode)
    code_order = {c.name: c for c in dataset.codes}
    per_code_sorted = sorted(
        result.per_code.items(),
        key=lambda item: code_order[item[0]].sort_order if item[0] in code_order else 0,
    )

    # Build group structure for template (with 1-based index)
    code_groups = []
    current_group = None
    code_idx = 1
    for name, metrics in per_code_sorted:
        mc = code_order.get(name)
        group = mc.group_name if mc else None
        if group != current_group:
            code_groups.append({"type": "group", "name": group})
            current_group = group
        code_groups.append({
            "type": "code",
            "name": name,
            "metrics": metrics,
            "verdict": code_verdicts[name],
            "index": code_idx,
        })
        code_idx += 1

    # Build code index for verdict text (1-based)
    code_index = {
        item["name"]: item["index"]
        for item in code_groups
        if item["type"] == "code"
    }

    # Overall verdict (needs code_index for large codebooks)
    verdict = classify_overall(result, code_verdicts, code_index)

    # Pairwise (3+ coders)
    pairwise_sorted = []
    if n_coders >= 3 and result.pairwise:
        coder_labels = {c.id: c.label for c in dataset.coders}
        for (cid_a, cid_b), pm in sorted(
            result.pairwise.items(),
            key=lambda x: x[1].gwets_ac1 if x[1].gwets_ac1 is not None else -1,
        ):
            label = (
                f"{coder_labels.get(cid_a, cid_a)} \u2194 "
                f"{coder_labels.get(cid_b, cid_b)}"
            )
            pairwise_sorted.append((label, pm, classify_code(pm, pairwise=True)))

    # Table numbering
    table_per_code = 1
    table_pairwise = 2 if pairwise_sorted else None
    table_full = 3 if pairwise_sorted else 2

    # Overall verdict for overall row
    overall_verdict = classify_code(result.overall)

    tmpl = jinja_env.get_template("agreement_results.html")
    return tmpl.render(
        n_coders=n_coders,
        n_sources=result.n_sources,
        n_codes=result.n_codes,
        total_sources=len(all_source_hashes),
        total_codes=len(all_code_names),
        warnings=dataset.warnings,
        verdict=verdict,
        code_groups=code_groups,
        code_verdicts=code_verdicts,
        per_code_sorted=per_code_sorted,
        overall=result.overall,
        overall_verdict=overall_verdict,
        pairwise_sorted=pairwise_sorted,
        kappa_header="Cohen \u03ba" if n_coders == 2 else "Fleiss \u03ba",
        fmt=_agreement_fmt,
        table_per_code=table_per_code,
        table_pairwise=table_pairwise,
        table_full=table_full,
    )


@router.post("/agreement/compute")
async def agreement_compute(
    request: Request,
    paths: str = Form(...),
):
    """Load files, compute agreement, return minimalist results HTML."""
    from ace.services.agreement_loader import AgreementLoader
    from ace.services.agreement_computer import compute_agreement

    try:
        path_list = json.loads(paths)
    except (json.JSONDecodeError, TypeError):
        return HTMLResponse(_agreement_error("Invalid file paths."), status_code=400)

    if not isinstance(path_list, list) or not all(isinstance(p, str) and p for p in path_list):
        return HTMLResponse(_agreement_error("Invalid file paths."), status_code=400)

    if len(path_list) < 2:
        return HTMLResponse(_agreement_error("Select at least 2 .ace files."), status_code=400)

    loader = AgreementLoader()
    for p in path_list:
        result = loader.add_file(p)
        if result.get("error"):
            return HTMLResponse(
                _agreement_error(f"Error loading {Path(p).name}: {result['error']}"),
                status_code=400,
            )

    # Store loader for export endpoints
    request.app.state.agreement_loader = loader

    try:
        dataset = loader.build_dataset()
    except Exception:
        return HTMLResponse(_agreement_error("Cannot compute agreement. Check that the files have shared sources and codes."), status_code=400)

    if not dataset.sources:
        return HTMLResponse(
            _agreement_error("No shared sources found across the selected files."),
            status_code=400,
        )

    result = compute_agreement(dataset)

    request.app.state.agreement_dataset = dataset
    request.app.state.agreement_result = result

    html_out = _render_agreement_results(result, dataset, loader, request.app.state.templates.env)
    return HTMLResponse(html_out)


@router.get("/agreement/export/results")
async def agreement_export_results(request: Request):
    """Export per-code metrics as CSV download."""
    import csv
    import io
    from datetime import date

    loader = getattr(request.app.state, "agreement_loader", None)
    dataset = getattr(request.app.state, "agreement_dataset", None)
    result = getattr(request.app.state, "agreement_result", None)
    if loader is None or loader.file_count < 2 or dataset is None or result is None:
        return HTMLResponse("No agreement data available. Compute first.", status_code=400)

    output = io.StringIO()

    # Metadata comment header
    file_names = ", ".join(f["filename"] for f in loader._files)
    coder_labels = ", ".join(c.label for c in dataset.coders)
    output.write(f"# ACE agreement summary — {date.today().isoformat()}\n")
    output.write(f"# Files: {file_names}\n")
    output.write(f"# Coders: {coder_labels}\n")
    output.write(f"# Sources: {result.n_sources}, Codes: {result.n_codes}\n")

    writer = csv.writer(output)
    writer.writerow([
        "code", "percent_agreement",
        "krippendorffs_alpha", "cohens_kappa", "fleiss_kappa",
        "congers_kappa", "gwets_ac1", "brennan_prediger",
        "n_sources", "n_positions",
    ])

    def _fmt(v):
        return f"{v:.4f}" if v is not None else ""

    for code_name in sorted(result.per_code):
        m = result.per_code[code_name]
        writer.writerow([
            code_name,
            _fmt(m.percent_agreement),
            _fmt(m.krippendorffs_alpha),
            _fmt(m.cohens_kappa),
            _fmt(m.fleiss_kappa),
            _fmt(m.congers_kappa),
            _fmt(m.gwets_ac1),
            _fmt(m.brennan_prediger),
            m.n_sources,
            m.n_positions,
        ])

    # Overall row
    o = result.overall
    writer.writerow([
        "Overall",
        _fmt(o.percent_agreement),
        _fmt(o.krippendorffs_alpha),
        _fmt(o.cohens_kappa),
        _fmt(o.fleiss_kappa),
        _fmt(o.congers_kappa),
        _fmt(o.gwets_ac1),
        _fmt(o.brennan_prediger),
        result.n_sources,
        o.n_positions,
    ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="agreement_summary.csv"'},
    )


@router.get("/agreement/export/raw")
async def agreement_export_raw(request: Request):
    """Export raw annotation data as long-form CSV for reproducibility in R/Python."""
    import csv
    import io
    from datetime import date

    loader = getattr(request.app.state, "agreement_loader", None)
    dataset = getattr(request.app.state, "agreement_dataset", None)
    if loader is None or loader.file_count < 2 or dataset is None:
        return HTMLResponse("No agreement data available. Compute first.", status_code=400)

    output = io.StringIO()
    coder_labels = ", ".join(c.label for c in dataset.coders)
    output.write(f"# ACE raw agreement data — {date.today().isoformat()}\n")
    output.write(f"# Coders: {coder_labels}\n")
    output.write(f"# Sources: {len(dataset.sources)}, Codes: {len(dataset.codes)}\n")

    writer = csv.writer(output)
    writer.writerow(["source_id", "start_offset", "end_offset", "coder_id", "code_name"])

    source_lookup = {s.content_hash: s.display_id for s in dataset.sources}

    for ann in sorted(dataset.annotations, key=lambda a: (a.source_hash, a.start_offset, a.coder_id)):
        source_id = source_lookup.get(ann.source_hash, ann.source_hash)
        writer.writerow([source_id, ann.start_offset, ann.end_offset, ann.coder_id, ann.code_name])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="agreement_raw_data.csv"'},
    )


@router.get("/agreement/export/references")
async def agreement_export_references():
    """Download the BibTeX references file for agreement metrics."""
    bib_path = Path(__file__).resolve().parent.parent / "static" / "agreement_references.bib"
    content = bib_path.read_text(encoding="utf-8")
    return Response(
        content=content,
        media_type="application/x-bibtex",
        headers={"Content-Disposition": 'attachment; filename="references.bib"'},
    )


@router.get("/agreement/export/methodology")
async def agreement_export_methodology():
    """Download the methodology markdown file describing agreement computations."""
    md_path = Path(__file__).resolve().parent.parent / "static" / "agreement_methodology.md"
    content = md_path.read_text(encoding="utf-8")
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="methodology.md"'},
    )
