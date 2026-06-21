"""API routes — JSON/HTMX fragment responses."""

from __future__ import annotations

import json
import re
import sqlite3
import tempfile
from pathlib import Path

from fastapi import (
    APIRouter,
    Form,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
)
from starlette.background import BackgroundTask


router = APIRouter(prefix="/api")

from ace.routes.api_support import (
    _codebook_tree_payload,
    _fallback_code_after_delete,
    _get_undo_manager,
    _oob_announce,
    _oob_status,
    _oob_status_undo,
    _project_db,
    _request_codebook_mode,
    _render_codebook_mutation_response,
    _render_code_sidebar,
    _render_full_coding_oob,
    _require_coder,
    _scope_ordering,
    _with_headers,
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
    codebook_mode: str = Form(default="coding"),
    current_code_id: str | None = Form(default=None),
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
        return _render_codebook_mutation_response(
            request,
            conn,
            coder_id,
            coding_content=content,
            mode=codebook_mode,
            current_code_id=current_code_id or new_code_id,
        )


@router.post("/codes/folder")
async def create_folder_route(
    request: Request,
    name: str = Form(...),
    parent_id: str = Form(default=""),
    current_index: int = Form(default=0),
    codebook_mode: str = Form(default="coding"),
    current_code_id: str | None = Form(default=None),
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
        return _render_codebook_mutation_response(
            request,
            conn,
            coder_id,
            coding_content=content,
            mode=codebook_mode,
            current_code_id=current_code_id,
            status_html=_oob_announce(f"Created folder {name}"),
            headers={"HX-Reswap": "none"},
        )


@router.put("/codes/{code_id}/parent")
async def set_code_parent_route(
    request: Request,
    code_id: str,
    parent_id: str = Form(default=""),
    target_order_ids: str = Form(default=""),
    current_index: int = Form(default=0),
    codebook_mode: str = Form(default="coding"),
    current_code_id: str | None = Form(default=None),
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
        return _render_codebook_mutation_response(
            request,
            conn,
            coder_id,
            coding_content=content,
            mode=codebook_mode,
            current_code_id=current_code_id,
            affected_code_ids=[code_id],
            headers={"HX-Reswap": "none"},
        )


@router.post("/codes/{code_id}/indent-promote")
async def indent_promote_route(
    request: Request,
    code_id: str,
    above_code_id: str = Form(...),
    folder_name: str = Form(default="New folder"),
    current_index: int = Form(default=0),
    codebook_mode: str = Form(default="coding"),
    current_code_id: str | None = Form(default=None),
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
        status_html = _oob_announce(
            f"Created folder containing {names.get(above_code_id, '?')} and {names.get(code_id, '?')}"
        )
        return _render_codebook_mutation_response(
            request,
            conn,
            coder_id,
            coding_content=content,
            mode=codebook_mode,
            current_code_id=current_code_id,
            affected_code_ids=[above_code_id, code_id],
            status_html=status_html,
        )


@router.post("/codes/cut-paste")
async def cut_paste_route(
    request: Request,
    code_id: str = Form(...),
    target_id: str = Form(default=""),
    current_index: int = Form(default=0),
    codebook_mode: str = Form(default="coding"),
    current_code_id: str | None = Form(default=None),
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
        return _render_codebook_mutation_response(
            request,
            conn,
            coder_id,
            coding_content=content,
            mode=codebook_mode,
            current_code_id=current_code_id,
            affected_code_ids=[code_id],
            headers={"HX-Reswap": "none"},
        )


@router.post("/codes/reorder-in-scope")
async def reorder_in_scope_route(
    request: Request,
    code_ids: str = Form(...),
    parent_id: str = Form(default=""),
    current_index: int = Form(default=0),
    codebook_mode: str = Form(default="coding"),
    current_code_id: str | None = Form(default=None),
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
        return _render_codebook_mutation_response(
            request,
            conn,
            coder_id,
            coding_content=content,
            mode=codebook_mode,
            current_code_id=current_code_id,
            headers={"HX-Reswap": "none"},
        )


@router.post("/codes/reorder")
async def reorder_codes_route(
    request: Request,
    code_ids: str = Form(...),
    current_index: int = Form(default=0),
    codebook_mode: str = Form(default="coding"),
    current_code_id: str | None = Form(default=None),
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
        return _render_codebook_mutation_response(
            request,
            conn,
            coder_id,
            coding_content=content,
            mode=codebook_mode,
            current_code_id=current_code_id,
            affected_code_ids=ids_list,
            headers={"HX-Reswap": "none"},
        )


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
        background=BackgroundTask(Path(tmp.name).unlink, missing_ok=True),
    )


@router.post("/codes/import")
async def import_codebook(
    request: Request,
    codes_json: str = Form(...),
    current_index: int = Form(default=0),
    codebook_mode: str = Form(default="coding"),
    current_code_id: str | None = Form(default=None),
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
        response = _render_codebook_mutation_response(
            request,
            conn,
            coder_id,
            coding_content=content,
            mode=codebook_mode,
            current_code_id=current_code_id,
            affected_code_ids=imported_ids,
            audit_reload=bool(imported_ids and current_code_id),
        )

    # Clean up temp file
    tmp_path = getattr(request.app.state, "codebook_import_tmp", None)
    if tmp_path:
        Path(tmp_path).unlink(missing_ok=True)
        request.app.state.codebook_import_tmp = None

    return response


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
    codebook_mode: str = Form(default="coding"),
    current_code_id: str | None = Form(default=None),
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
        return _render_codebook_mutation_response(
            request,
            conn,
            coder_id,
            coding_content=content,
            mode=codebook_mode,
            current_code_id=current_code_id or code_id,
        )


@router.delete("/codes/{code_id}")
async def delete_code_route(
    request: Request,
    code_id: str,
    current_index: int = Query(default=0),
    codebook_mode: str = Query(default="coding"),
    current_code_id: str | None = Query(default=None),
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
        resolved_mode = _request_codebook_mode(request, explicit=codebook_mode)
        fallback_code_id = None
        if (
            resolved_mode == "audit"
            and prev["kind"] == "code"
            and current_code_id == code_id
        ):
            fallback_code_id = _fallback_code_after_delete(conn, code_id)

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
        return _render_codebook_mutation_response(
            request,
            conn,
            coder_id,
            coding_content=content,
            mode=codebook_mode,
            current_code_id=current_code_id,
            affected_code_ids=[code_id],
            fallback_code_id=fallback_code_id,
            status_html=_oob_status_undo(message),
        )
