"""API routes — JSON/HTMX fragment responses."""

from __future__ import annotations


from fastapi import (
    APIRouter,
    Form,
    HTTPException,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    Response,
)


router = APIRouter(prefix="/api")

from ace.routes.api_support import (
    _annotation_only_response,
    _build_undo_response,
    _csv_download,
    _get_undo_manager,
    _oob_announce,
    _oob_status,
    _oob_status_undo,
    _project_db,
    _render_full_coding_oob,
    _require_coder,
    _resolve_source_id,
    _with_headers,
    logger,
)


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

        if replaced_ids:
            status_msg = "Merged code"
        else:
            status_msg = "Added code"
        status_html = _oob_status(status_msg, "ok").body.decode()

        return _annotation_only_response(
            request, conn, coder_id, current_index, extra=status_html,
        )


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
            _oob_status_undo("Removed code"),
        )


@router.post("/undo")
async def undo_route(
    request: Request,
    current_index: int = Form(default=0),
    codebook_mode: str = Form(default="coding"),
    current_code_id: str | None = Form(default=None),
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
            return _with_headers(_oob_status("Undo failed", "err"), no_swap)

        return _build_undo_response(
            request,
            conn,
            coder_id,
            current_index,
            result,
            codebook_mode=codebook_mode,
            current_code_id=current_code_id,
        )


@router.post("/redo")
async def redo_route(
    request: Request,
    current_index: int = Form(default=0),
    codebook_mode: str = Form(default="coding"),
    current_code_id: str | None = Form(default=None),
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
            return _with_headers(_oob_status("Redo failed", "err"), no_swap)

        return _build_undo_response(
            request,
            conn,
            coder_id,
            current_index,
            result,
            codebook_mode=codebook_mode,
            current_code_id=current_code_id,
        )


@router.post("/navigation")
async def navigation_route(
    request: Request,
    from_index: int = Form(...),
    to_index: int = Form(...),
):
    """Record app-initiated source navigation in the undo sequence."""
    from ace.models.assignment import get_assignments_for_coder

    coder_id = _require_coder(request)

    with _project_db(request) as conn:
        assignments = get_assignments_for_coder(conn, coder_id)
        if (
            from_index < 0
            or to_index < 0
            or from_index >= len(assignments)
            or to_index >= len(assignments)
        ):
            raise HTTPException(status_code=400, detail="source index out of range")

        if from_index != to_index:
            _get_undo_manager(request).record_navigation(
                assignments[from_index]["source_id"],
                assignments[to_index]["source_id"],
            )

    return Response(status_code=204)


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
        add_annotation, delete_annotation, get_annotations_for_source,
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
        status_msg = ""

        if existing_same_code:
            # Toggle off: remove this specific code
            delete_annotation(conn, existing_same_code["id"])
            undo.record_delete(source_id, existing_same_code["id"])
            status_msg = "Removed code"
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
                # Replace adjacent same-code rows with a merged annotation so
                # undo can restore the original row instead of deleting it.
                new_start = min(neighbour["start_offset"], start)
                new_end = max(neighbour["end_offset"], end)
                new_text = source_text[new_start:new_end]
                from ace.models.annotation import add_annotation_merging
                ann_id, replaced_ids = add_annotation_merging(
                    conn, source_id, coder_id, code_id,
                    new_start, new_end, new_text,
                )
                undo.record_merge_add(source_id, ann_id, replaced_ids)
                status_msg = "Merged code"
            else:
                try:
                    ann_id = add_annotation(
                        conn, source_id, coder_id, code_id,
                        start, end, unit["text"],
                    )
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
                undo.record_add(source_id, ann_id)
                status_msg = "Added code"

        status_html = _oob_status(status_msg, "ok").body.decode()
        return _annotation_only_response(request, conn, coder_id, current_index, extra=status_html)


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

        extra = _oob_status_undo("Removed code") if most_recent else ""
        return _annotation_only_response(request, conn, coder_id, current_index, extra)
