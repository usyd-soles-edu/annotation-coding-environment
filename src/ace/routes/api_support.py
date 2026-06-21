"""API routes — JSON/HTMX fragment responses."""

from __future__ import annotations

import html
import json
import logging
import random
import re
import sqlite3
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import (
    unquote,
    urlparse,
)

from fastapi import (
    HTTPException,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    Response,
)

from ace import __version__


logger = logging.getLogger(__name__)


_AGREEMENT_STALE = object()


def _require_coder(request: Request) -> str:
    """Return coder_id from app state; raise HTTP 400 if not set.

    Used by every route that mutates coder-owned state. The single
    remaining caller that wants Optional semantics (the `codes`
    listing route) reads `request.app.state.coder_id` directly.

    The detail is plain English so the client's htmx:beforeSwap
    listener can surface it in the status bar (HTMX drops 4xx bodies
    by default; we parse the JSON and show it).
    """
    cid = getattr(request.app.state, "coder_id", None)
    if cid is None:
        raise HTTPException(
            status_code=400,
            detail="No coder is selected — open a project from the home page.",
        )
    return cid


def _safe_filename(name: str) -> str:
    """Sanitise a string for use in HTTP Content-Disposition filename.

    HTTP header values are ASCII/latin-1 only, and the filename attribute
    is vulnerable to header injection via CR/LF and parsing ambiguity from
    quotes/semicolons/backslashes. Collapses everything except alphanum,
    dot, dash, underscore, and space into underscores.
    """
    return re.sub(r"[^A-Za-z0-9._\- ]", "_", name)


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


def _import_done_actions(*, include_back: bool = False) -> str:
    import_more = (
        '<button class="ace-wizard-link ace-wizard-link--inline" type="button" '
        'onclick="showStep(\'step-choose\')">Import more data</button>'
    )
    remove_last = (
        '<button class="ace-wizard-link ace-wizard-link--inline" type="button" '
        'hx-post="/api/import/remove-last" hx-swap="none" '
        'hx-confirm="Remove the most recent import? This can’t be undone — any coding on those sources is deleted." '
        'title="Remove the most recent import">Remove last import</button>'
    )
    if include_back:
        return (
            '<div class="ace-import-result-actions">'
            '<button class="ace-btn" type="button" onclick="showStep(\'step-choose\')">Back</button>'
            '<a href="/code" class="ace-btn ace-btn--primary ace-import-start">Start coding</a>'
            f"{import_more}"
            "</div>"
            f'<div class="ace-import-result-actions ace-import-result-actions--secondary">'
            f"{remove_last}"
            "</div>"
        )
    return (
        '<div class="ace-import-result-actions">'
        '<a href="/code" class="ace-btn ace-btn--primary ace-import-start">Start coding</a>'
        "</div>"
        '<div class="ace-import-result-actions ace-import-result-actions--secondary">'
        f"{import_more}"
        f"{remove_last}"
        "</div>"
    )


def _skipped_html(n: int, unit: str) -> str:
    """Render the 'skipped duplicates' notice (empty string when n == 0)."""
    if not n:
        return ""
    plural = "" if n == 1 else "s"
    return (f'<p class="ace-import-result-skipped">Skipped {n} {unit}{plural} '
            f"already present in this project.</p>")


def _import_result_fragment(
    count_label: str,
    source_label: str | None = None,
    *,
    skipped: int = 0,
) -> str:
    source_html = ""
    if source_label:
        source_html = (
            " from "
            f'<span class="ace-import-result-meta">{html.escape(source_label)}</span>'
        )
    skipped_html = _skipped_html(skipped, "source")
    return (
        '<div class="ace-import-result">'
        '<div class="ace-import-result-top">'
        '<span class="ace-wizard-crumb">Import complete</span>'
        "</div>"
        f'<div class="ace-import-result-count">{html.escape(count_label)}</div>'
        f"<p>Imported successfully{source_html}</p>"
        f"{skipped_html}"
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
    previews: list[dict],
    total: int,
    escaped_folder: str,
    *,
    already_present: int = 0,
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
    dup_html = ""
    if already_present > 0:
        unit = "file" if already_present == 1 else "files"
        dup_html = (
            f'<p class="ace-folder-import-duplicates">'
            f"{already_present} {unit} already in this project."
            f"</p>"
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
        f"{dup_html}"
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


def _native_selection_path(value: str) -> Path:
    """Accept native picker paths returned as POSIX paths or file:// URIs."""
    parsed = urlparse(value)
    if parsed.scheme == "file":
        path = unquote(parsed.path)
        if re.match(r"^/[A-Za-z]:/", path):
            path = path[1:]
        return Path(path)
    return Path(value)


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


def _request_codebook_mode(request: Request, explicit: str | None = None) -> str:
    mode = explicit or request.query_params.get("codebook_mode")
    if mode is None:
        try:
            mode = request._form.get("codebook_mode")
        except Exception:
            mode = None
    return mode if mode in {"coding", "audit", "readonly"} else "coding"


def _request_current_code_id(request: Request, explicit: str | None = None) -> str | None:
    current_code_id = explicit or request.query_params.get("current_code_id")
    if current_code_id is None:
        try:
            current_code_id = request._form.get("current_code_id")
        except Exception:
            current_code_id = None
    return current_code_id or None


def _codebook_mutation_operation(request: Request) -> str:
    path = request.url.path.rstrip("/")
    code_id = request.path_params.get("code_id")
    method = request.method.upper()
    if method == "PUT" and code_id:
        return "update"
    if method == "DELETE" and code_id:
        return "delete"
    if method == "POST" and path.endswith("/codes/folder"):
        return "create-folder"
    if method == "POST" and path.endswith("/codes"):
        return "create"
    return method.lower()


def _audit_codebook_mutation_detail(
    request: Request,
    *,
    affected_code_ids: list[str] | None = None,
    current_code_id: str | None = None,
    fallback_code_id: str | None = None,
) -> dict[str, object]:
    operation = _codebook_mutation_operation(request)
    if affected_code_ids is None:
        affected_code_ids = []
        code_id = request.path_params.get("code_id")
        if code_id:
            affected_code_ids.append(str(code_id))
    should_reload_current = (
        current_code_id is not None
        and current_code_id in affected_code_ids
        and operation != "delete"
    )
    return {
        "mode": "audit",
        "operation": operation,
        "affectedCodeIds": affected_code_ids,
        "currentCodeId": current_code_id,
        "auditReload": should_reload_current,
        "fallbackCodeId": fallback_code_id,
    }


def _fallback_code_after_delete(conn, deleted_code_id: str) -> str | None:
    from ace.models.codebook import list_codes_with_tree

    ordered_code_ids = [
        str(node["id"])
        for node in list_codes_with_tree(conn)
        if node.get("kind") == "code"
    ]
    if not ordered_code_ids:
        return None
    if deleted_code_id not in ordered_code_ids:
        return ordered_code_ids[0]

    idx = ordered_code_ids.index(deleted_code_id)
    if idx + 1 < len(ordered_code_ids):
        return ordered_code_ids[idx + 1]
    if idx > 0:
        return ordered_code_ids[idx - 1]
    return None


def _merge_hx_trigger(
    headers: dict[str, str] | None,
    event_name: str,
    detail: dict[str, object],
    header_name: str = "HX-Trigger",
) -> dict[str, str]:
    merged = dict(headers or {})
    payload: dict[str, object]
    current = merged.get(header_name)
    if current:
        try:
            payload = json.loads(current)
        except json.JSONDecodeError:
            payload = {}
    else:
        payload = {}
    payload[event_name] = detail
    merged[header_name] = json.dumps(payload)
    return merged


def _render_audit_code_sidebar(
    request: Request,
    conn,
    coder_id: str,
    current_code_id: str | None = None,
) -> str:
    from ace.models.annotation import get_annotation_counts_by_code
    from ace.models.codebook import list_codes_with_tree
    from jinja2_fragments import render_block

    templates = request.app.state.templates
    project_path = request.app.state.project_path
    ctx = {
        "request": request,
        "version": __version__,
        "project_file_stem": Path(project_path).stem if project_path else "",
        "tree_codes": list_codes_with_tree(conn),
        "code_counts_by_id": get_annotation_counts_by_code(conn, coder_id),
        "codebook_mode": "audit",
        "current_code_id": current_code_id,
    }
    return render_block(templates.env, "code_view.html", "code_sidebar", ctx)


def _render_codebook_mutation_response(
    request: Request,
    conn,
    coder_id: str,
    *,
    coding_content: str,
    mode: str = "coding",
    current_code_id: str | None = None,
    affected_code_ids: list[str] | None = None,
    fallback_code_id: str | None = None,
    status_html: str = "",
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    resolved_mode = _request_codebook_mode(request, explicit=mode)
    if resolved_mode == "audit":
        content = _inject_oob(
            _render_audit_code_sidebar(
                request,
                conn,
                coder_id,
                current_code_id=current_code_id,
            ),
            "code-sidebar",
        )
        audit_headers = _merge_hx_trigger(
            headers,
            "ace:codebook-mutated",
            _audit_codebook_mutation_detail(
                request,
                affected_code_ids=affected_code_ids,
                current_code_id=current_code_id,
                fallback_code_id=fallback_code_id,
            ),
            header_name="HX-Trigger-After-Settle",
        )
        content += status_html
        audit_headers["HX-Reswap"] = "none"
        return HTMLResponse(content, headers=audit_headers)

    return HTMLResponse(coding_content + status_html, headers=headers)


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
    mode = _request_codebook_mode(request)
    current_code_id = _request_current_code_id(request)

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

    if mode == "audit" and result.get("codebook_changed", True):
        status_html = _oob_status(description, "ok").body.decode()
        return _render_codebook_mutation_response(
            request,
            conn,
            coder_id,
            coding_content="",
            mode=mode,
            current_code_id=current_code_id,
            status_html=status_html,
            headers=headers,
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


def _agreement_progress(percent: int, stage: str, *, done: bool = False, error: str | None = None) -> dict:
    """Build the agreement-compute progress dict stored on app.state."""
    return {"percent": percent, "stage": stage, "done": done, "error": error}


def _agreement_generation(state) -> int:
    return int(getattr(state, "agreement_generation", 0) or 0)


def _clear_agreement_cache(state) -> int:
    """Drop cached agreement data so exports cannot serve stale results."""
    state.agreement_generation = _agreement_generation(state) + 1
    state.agreement_loader = None
    state.agreement_dataset = None
    state.agreement_result = None
    state.agreement_progress = _agreement_progress(0, "")
    return state.agreement_generation


def _agreement_is_current(state, generation: int) -> bool:
    return _agreement_generation(state) == generation


def _parse_agreement_paths(paths: str | None) -> tuple[list[str] | None, str | None]:
    try:
        path_list = json.loads(paths)
    except (json.JSONDecodeError, TypeError):
        return None, "Invalid file paths."

    if not isinstance(path_list, list) or not all(isinstance(p, str) and p for p in path_list):
        return None, "Invalid file paths."

    if len(path_list) < 2:
        return None, "Select at least 2 .ace files."

    return path_list, None


def _run_agreement_preview(path_list: list[str]) -> dict:
    from ace.services.agreement_loader import AgreementLoader

    loader = AgreementLoader()
    files = []

    for p in path_list:
        path = Path(p)
        try:
            info = loader.add_file(path)
        except Exception as exc:
            logger.warning("agreement preview could not load %s: %s", path, exc)
            files.append({
                "path": str(path),
                "filename": path.name,
                "coder_names": [],
                "source_count": 0,
                "annotation_count": 0,
                "code_count": 0,
                "warnings": [],
                "error": f"Cannot open '{path.name}': {exc}",
            })
            continue

        if info.get("error"):
            files.append({
                "path": str(path),
                "filename": path.name,
                "coder_names": [],
                "source_count": 0,
                "annotation_count": 0,
                "code_count": 0,
                "warnings": [],
                "error": info["error"],
            })
            continue

        info["code_count"] = len(loader._file_data[-1]["codes"])
        files.append(info)

    file_errors = any(f.get("error") for f in files)
    validation = {
        "valid": False,
        "error": "Select at least 2 valid .ace files.",
        "warnings": [],
    }
    if len(loader._file_data) >= 2:
        try:
            validation = loader.validate()
        except Exception:
            logger.exception("agreement preview validation failed")
            validation = {
                "valid": False,
                "error": "Cannot preview agreement. Check that the files have shared sources and codes.",
                "warnings": [],
            }

    if file_errors:
        validation = {
            **validation,
            "valid": False,
            "error": "Remove files with errors before computing agreement.",
        }

    return {
        "files": files,
        "valid": bool(validation.get("valid")),
        "error": validation.get("error"),
        "warnings": validation.get("warnings", []),
        "matched_sources": validation.get("matched_sources"),
        "matched_codes": validation.get("matched_codes"),
        "n_coders": validation.get("n_coders"),
    }


def _render_agreement_preview(preview: dict, jinja_env) -> str:
    tmpl = jinja_env.get_template("agreement_review.html")
    return tmpl.render(
        files=preview["files"],
        paths=[f["path"] for f in preview["files"]],
        valid=preview["valid"],
        error=preview["error"],
        warnings=preview["warnings"],
        matched_sources=preview["matched_sources"],
        matched_codes=preview["matched_codes"],
        n_coders=preview["n_coders"],
    )


def _run_agreement(path_list, state, jinja_env, generation: int):
    """Worker-thread entry point: load files, build dataset, compute, render.

    Writes progress to ``state.agreement_progress``. Returns the rendered
    results HTML, or ``None`` on a handled error (progress.error set).

    The whole worker body is wrapped in a catch-all ``try/except`` so that
    any escape from the load/build/compute/render pipeline is converted into
    the standard failure state — the progress bar never spins forever on a
    500. Note: ``percent`` is unreliable when ``error`` is set (reviewer I3);
    readers should branch on ``error`` first.
    """
    from ace.services.agreement_loader import AgreementLoader
    from ace.services.agreement_computer import compute_agreement

    def _fail(message):
        if not _agreement_is_current(state, generation):
            return _AGREEMENT_STALE
        state.agreement_progress = _agreement_progress(0, "", error=message)
        return None

    try:
        loader = AgreementLoader()
        for p in path_list:
            result = loader.add_file(p)
            if result.get("error"):
                return _fail(f"Error loading {Path(p).name}: {result['error']}")

        if not _agreement_is_current(state, generation):
            return _AGREEMENT_STALE

        state.agreement_loader = loader
        state.agreement_progress = _agreement_progress(5, "Building dataset")

        try:
            dataset = loader.build_dataset()
        except Exception:
            return _fail(
                "Cannot compute agreement. Check that the files have shared sources and codes."
            )

        if not dataset.sources:
            return _fail("No shared sources found across the selected files.")

        total = max(1, len(dataset.sources))

        def cb(done, stage):
            # Scale the per-source callback (0..total) into 10..99 so the bar
            # doesn't leap to 100% before the (cheap) rendering step.
            pct = 10 + int(done * 89 / total)
            if _agreement_is_current(state, generation):
                state.agreement_progress = _agreement_progress(min(99, pct), stage)

        result = compute_agreement(dataset, progress_callback=cb)

        if not _agreement_is_current(state, generation):
            return _AGREEMENT_STALE

        state.agreement_dataset = dataset
        state.agreement_result = result
        state.agreement_progress = _agreement_progress(100, "Rendering results", done=True)

        return _render_agreement_results(result, dataset, loader, jinja_env)
    except Exception:
        logger.exception("agreement compute failed")
        return _fail("Agreement could not be computed.")
