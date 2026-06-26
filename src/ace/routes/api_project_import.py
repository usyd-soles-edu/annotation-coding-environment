"""API routes — JSON/HTMX fragment responses."""

from __future__ import annotations

import asyncio
import html
import platform
import re
import sqlite3
from pathlib import Path
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Form,
    Query,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    Response,
)


router = APIRouter(prefix="/api")

_INVALID_PROJECT_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_PROJECT_NAME_ERROR = (
    'Use a project name without / \\ : * ? " < > | or control characters.'
)


def _validate_project_name(name: str) -> str | None:
    cleaned = name.strip().removesuffix(".ace").strip()
    if not cleaned or cleaned in {".", ".."}:
        return _PROJECT_NAME_ERROR
    if _INVALID_PROJECT_NAME_RE.search(cleaned):
        return _PROJECT_NAME_ERROR
    if any(part in {".", ".."} for part in Path(cleaned).parts):
        return _PROJECT_NAME_ERROR
    return None


def _friendly_import_error() -> str:
    return "Import failed. Check the selected file and try again."


from ace.routes.api_support import (
    _accept_to_filetypes,
    _accept_to_types,
    _codebook_import_payload,
    _codebook_mapping_select,
    _csv_download,
    _empty_skipped_html,
    _folder_import_preview_fragment,
    _import_done_actions,
    _import_result_fragment,
    _native_selection_path,
    _normalise_codebook_mapping_column,
    _oob_status,
    _parse_tabular_for_mapping,
    _project_db,
    _require_coder,
    _run_osascript,
    _skipped_html,
    _tk_pick_file,
    _tk_pick_files,
    _tk_pick_folder,
    _with_headers,
    logger,
)


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

    name_error = _validate_project_name(name)
    if name_error:
        return _oob_status(name_error)

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
    except Exception:
        logger.exception("Failed to create project at %s", file_path)
        return _oob_status(
            "Could not create that project. Check the name, location, and file permissions."
        )


@router.post("/project/open")
async def project_open(request: Request, path: str = Form(...)):
    """Open an existing .ace project file."""
    from ace.db.connection import open_project
    from ace.models.project import list_coders
    from ace.models.source import list_sources

    file_path = _native_selection_path(path)
    try:
        conn = open_project(str(file_path))
    except (ValueError, FileNotFoundError, sqlite3.DatabaseError):
        logger.exception("Failed to open project at %s", file_path)
        return _oob_status(
            "Could not open that project. Choose a valid .ace file."
        )

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


@router.post("/import/file")
async def import_file_path(request: Request, path: str = Form(...)):
    """Parse a CSV/Excel file chosen by the native picker."""
    file_path = _native_selection_path(path)
    if not file_path.exists() or file_path.suffix.lower() not in {".csv", ".xlsx"}:
        return _oob_status("Choose a CSV or Excel file.")
    return _parse_tabular_for_mapping(
        request, file_path, cleanup=False, filename=file_path.name
    )


@router.post("/import/commit")
async def import_commit(
    request: Request,
    id_column: str = Form(default=""),
    text_columns: str = Form(default=""),
):
    """Commit the uploaded file: import selected columns as sources."""
    from ace.app import get_db
    from ace.services.importer import import_csv, read_tabular

    tmp_path = getattr(request.app.state, "import_tmp_path", None)
    if tmp_path is None or not Path(tmp_path).exists():
        return _oob_status("No uploaded file found. Please upload again.")

    text_col_list = [c.strip() for c in text_columns.split(",") if c.strip()]
    id_column = id_column.strip()
    if not id_column:
        return _oob_status("Choose a source label column.")
    if not text_col_list:
        return _oob_status("Choose at least one text column.")

    try:
        _rows, columns = read_tabular(Path(tmp_path))
    except Exception:
        return _oob_status(_friendly_import_error())

    if id_column not in columns:
        return _oob_status(
            "Selected source label column was not found. Choose a column from the file."
        )
    for column in text_col_list:
        if column not in columns:
            return _oob_status(
                f'Selected text column "{column}" was not found. '
                "Choose text columns from the file."
            )

    db_gen = get_db(request)
    conn = next(db_gen)
    try:
        result = import_csv(conn, tmp_path, id_column, text_col_list)
        count, skipped, created_ids = result
    except Exception:
        return _oob_status(_friendly_import_error())
    finally:
        db_gen.close()

    # Remember the last import's source ids so the 'Remove last import'
    # button can delete them directly (imports are NOT on the undo stack).
    # Set unconditionally — a no-op import (all duplicates) clears the
    # record so the button never removes a previous batch by mistake.
    request.app.state.last_import_source_ids = created_ids

    # Clean up upload temp files. Native picker paths belong to the user.
    if getattr(request.app.state, "import_tmp_cleanup", True):
        Path(tmp_path).unlink(missing_ok=True)
    source_name = getattr(request.app.state, "import_source_name", None)
    request.app.state.import_tmp_path = None
    request.app.state.import_tmp_cleanup = True
    request.app.state.import_source_name = None

    count_label = f'{count} source{"s" if count != 1 else ""}'
    return HTMLResponse(
        _import_result_fragment(
            count_label,
            source_name,
            skipped=skipped,
            empty_skipped=result.empty_skipped,
        )
    )


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
        result = import_text_files(conn, folder)
        count, skipped, created_ids = result
    except Exception:
        return _oob_status(_friendly_import_error())
    finally:
        db_gen.close()

    # Remember the last import's source ids so the 'Remove last import'
    # button can delete them directly (imports are NOT on the undo stack).
    # Set unconditionally — a no-op import (all duplicates) clears the
    # record so the button never removes a previous batch by mistake.
    request.app.state.last_import_source_ids = created_ids

    folder_name = html.escape(folder.name)
    escaped_path = html.escape(quote(str(folder), safe=""))

    total, previews = get_random_previews(folder)
    preview_html = (
        _folder_import_preview_fragment(previews, total, escaped_path)
        if previews
        else ""
    )

    skipped_html = _skipped_html(skipped, "file")
    empty_skipped_html = _empty_skipped_html(result.empty_skipped, "source")

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
        f"{skipped_html}"
        f"{empty_skipped_html}"
        f"{preview_html}"
        f"{_import_done_actions(include_back=True)}"
        "</div>"
    )


@router.post("/import/remove-last")
async def import_remove_last(request: Request):
    """Remove the most recent source import's sources directly.

    Imports are not on the undo stack (that risked silent data loss when Z
    bumped against later annotations/notes/flags). Instead the last import's
    source ids are stored on app state and this button deletes them — plus
    any annotations made on them since — then reloads the wizard. Not
    reversible.
    """
    ids = list(getattr(request.app.state, "last_import_source_ids", None) or [])
    if not ids:
        return _oob_status("No import to remove.", "err")
    try:
        with _project_db(request) as conn:
            placeholders = ",".join("?" * len(ids))
            # Count only live annotations for the user-facing message (what
            # they'd lose); the DELETE below also clears soft-deleted rows.
            n_ann = conn.execute(
                f"SELECT COUNT(*) FROM annotation WHERE source_id IN ({placeholders}) "
                "AND deleted_at IS NULL",
                ids,
            ).fetchone()[0]
            # No ON DELETE CASCADE in the schema, so clear each dependent
            # table explicitly (one batched DELETE each) before the sources.
            conn.execute(f"DELETE FROM annotation WHERE source_id IN ({placeholders})", ids)
            conn.execute(f"DELETE FROM source_note WHERE source_id IN ({placeholders})", ids)
            conn.execute(f"DELETE FROM assignment WHERE source_id IN ({placeholders})", ids)
            conn.execute(f"DELETE FROM source_content WHERE source_id IN ({placeholders})", ids)
            conn.execute(f"DELETE FROM source WHERE id IN ({placeholders})", ids)
            conn.commit()
        request.app.state.last_import_source_ids = None
        msg = "Removed the last import."
        if n_ann:
            msg += f" · {n_ann} annotation{'s' if n_ann != 1 else ''} also removed."
        return _with_headers(_oob_status(msg, "ok"), {"HX-Refresh": "true"})
    except Exception:
        logger.exception("remove-last import failed")
        return _oob_status("Could not remove the last import.", "err")


@router.get("/import/preview")
async def import_preview(request: Request, folder: str = Query(...)):
    """Return an HTML fragment previewing a random text file from the folder."""
    from ace.services.importer import count_already_present, get_random_previews

    folder_path = Path(folder)
    if not folder_path.is_dir():
        return HTMLResponse('<p style="color:var(--ace-text-muted)">Invalid folder.</p>')

    total, previews = get_random_previews(folder_path)
    escaped_folder = html.escape(quote(folder, safe=""))

    # Count how many files in the folder are already sources in the open
    # project so the preview can flag duplicates before import.
    already_present = 0
    project_path = getattr(request.app.state, "project_path", None)
    if project_path and Path(project_path).exists():
        with _project_db(request) as conn:
            already_present = count_already_present(conn, folder_path)

    return HTMLResponse(
        _folder_import_preview_fragment(
            previews, total, escaped_folder, already_present=already_present
        )
    )


@router.get("/export/annotations")
async def export_annotations(request: Request):
    """Export all annotations as CSV download."""
    from ace.services.exporter import export_annotations_csv

    return _csv_download(request, "annotations", export_annotations_csv)


@router.post("/codes/import/preview-path")
async def import_codebook_preview_path(
    request: Request,
    path: str = Form(...),
    current_index: int = Form(default=0),
    codebook_mode: str = Form(default="coding"),
    current_code_id: str | None = Form(default=None),
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
    except Exception:
        return _oob_status("Could not parse that codebook CSV. Check the columns and try again.")

    filename = html.escape(file_path.name)
    safe_path = html.escape(str(file_path))
    codes_json_escaped = html.escape(payload["codes_json"])
    safe_mode = html.escape(codebook_mode)
    safe_current_code_id = html.escape(current_code_id or "")

    dialog_html = (
        '<dialog class="ace-dialog ace-import-dialog ace-codebook-import-dialog ace-codebook-import-ledger" '
        f'data-csv-path="{safe_path}" data-current-index="{current_index}" '
        'aria-labelledby="codebook-import-title" aria-describedby="codebook-import-help">'
        '<header class="ace-codebook-import-head">'
        '<div>'
        '<h2 id="codebook-import-title" class="ace-import-dialog-title" tabindex="-1">Import codebook</h2>'
        f'<span class="ace-import-dialog-sub" data-codebook-import-summary>{filename} · {html.escape(payload["summary"])}</span>'
        '</div>'
        '<div class="ace-codebook-import-tabs" role="tablist" aria-label="Import steps">'
        '<button type="button" id="codebook-import-tab-match" role="tab" '
        'data-codebook-import-view="match" aria-selected="true" tabindex="0" '
        'aria-controls="codebook-import-panel-match">Match</button>'
        '<button type="button" id="codebook-import-tab-review" role="tab" '
        'data-codebook-import-view="review" aria-selected="false" tabindex="-1" '
        'aria-controls="codebook-import-panel-review">Review</button>'
        '<button type="button" id="codebook-import-tab-skipped" role="tab" '
        'data-codebook-import-view="skipped" aria-selected="false" tabindex="-1" '
        'aria-controls="codebook-import-panel-skipped">Skipped</button>'
        '</div>'
        '</header>'
        '<div class="ace-codebook-import-body">'
        '<aside class="ace-codebook-import-map" id="codebook-import-help">'
        '<p class="ace-codebook-import-kicker">Match columns</p>'
        '<p>Select columns from your file to match ACE fields.</p>'
        f'{_codebook_mapping_select(field_id="codebook-map-name", label="Code name", columns=columns, selected=detected.get("name"))}'
        f'{_codebook_mapping_select(field_id="codebook-map-group", label="Folder/group", columns=columns, selected=detected.get("group"), optional=True)}'
        f'{_codebook_mapping_select(field_id="codebook-map-definition", label="Definition", columns=columns, selected=detected.get("definition"), optional=True)}'
        '</aside>'
        '<section id="codebook-import-panel-match" class="ace-codebook-import-panel is-active" '
        'data-codebook-import-panel="match" role="tabpanel" '
        'aria-labelledby="codebook-import-tab-match">'
        '<div class="ace-codebook-import-panel-head"><h3>File preview</h3>'
        f'<span data-codebook-import-counts role="status" aria-live="polite" aria-atomic="true">{html.escape(payload["summary"])}</span></div>'
        f'<div id="codebook-import-preview" class="ace-codebook-import-preview-list">{payload["preview_html"]}</div>'
        '</section>'
        '<section id="codebook-import-panel-review" class="ace-codebook-import-panel" '
        'data-codebook-import-panel="review" role="tabpanel" hidden '
        'aria-labelledby="codebook-import-tab-review">'
        '<div class="ace-codebook-import-panel-head"><h3>Review changes</h3><span>New and existing codes</span></div>'
        f'<div id="codebook-import-review" class="ace-codebook-import-preview-list">{payload["review_html"]}</div>'
        '</section>'
        '<section id="codebook-import-panel-skipped" class="ace-codebook-import-panel" '
        'data-codebook-import-panel="skipped" role="tabpanel" hidden '
        'aria-labelledby="codebook-import-tab-skipped">'
        '<div class="ace-codebook-import-panel-head"><h3>Skipped rows</h3><span>Invalid rows only</span></div>'
        f'<div id="codebook-import-skipped" class="ace-codebook-import-preview-list">{payload["skipped_html"]}</div>'
        '</section>'
        '</div>'
        '<footer class="ace-import-actions">'
        '<span class="ace-codebook-import-action-note">Import can be undone.</span>'
        '<button type="button" class="ace-btn" onclick="this.closest(\'dialog\').close()">Cancel</button>'
        f'<button type="button" class="ace-btn ace-btn--primary" '
        f'id="codebook-import-commit" onclick="aceImportFromPreview(this)" '
        f'data-codes="{codes_json_escaped}" data-current-index="{current_index}"'
        f' data-codebook-mode="{safe_mode}" data-current-code-id="{safe_current_code_id}"'
        f'{" disabled" if payload["disabled"] else ""}>'
        f'{html.escape(payload["import_label"])}</button>'
        '</footer></dialog>'
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
    except Exception:
        return JSONResponse(
            {
                "preview_html": (
                    '<div class="ace-codebook-import-empty">'
                    'Could not preview CSV. Check the columns and try again.</div>'
                ),
                "review_html": (
                    '<div class="ace-codebook-import-empty">'
                    'Could not preview CSV. Check the columns and try again.</div>'
                ),
                "skipped_html": (
                    '<div class="ace-codebook-import-empty">'
                    'Could not preview CSV. Check the columns and try again.</div>'
                ),
                "codes_json": "[]",
                "new_count": 0,
                "exists_count": 0,
                "skipped_count": 0,
                "row_count": 0,
                "summary": "Preview failed",
                "import_label": "Import 0 codes",
                "disabled": True,
            }
        )
    return JSONResponse(payload)
