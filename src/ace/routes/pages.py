"""Page routes — HTML responses rendered via Jinja2."""

import html
import hashlib
import json
import logging
import sqlite3
from pathlib import Path

from markupsafe import Markup

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from ace import __version__
from ace.app import HtmxRedirect, get_db
from ace.models.annotation import (
    get_annotation_counts_by_code,
    get_annotation_counts_by_source,
    get_annotations_for_source,
    get_code_view_data,
)
from ace.models.assignment import ensure_assignments, get_assignments_for_coder
from ace.models.codebook import COLOUR_PALETTE, list_codes, list_codes_with_tree
from ace.models.project import get_project
from ace.models.source import (
    decode_section_heading_spans,
    get_source_content,
    list_sources,
)
from ace.models.source_note import get_note, source_ids_with_notes
from ace.routes.api_project_import import _clear_folder_import_manifests
from ace.services.coding_context_cache import CodingContextCache
from ace.services.shared_recent_project import remember_recent_project
from ace.services.shared_preferences import preferences_for_request
from ace.services.shared_source_position import position_key, remember_source_position

router = APIRouter()
_LOG = logging.getLogger(__name__)


def _sources_snapshot_version(sources_json: list[dict]) -> str:
    """Identify the project-wide source grid data sent to the browser."""
    payload = json.dumps(sources_json, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _annotation_excerpt(source_text: str, start: int, end: int, limit: int = 58) -> str:
    snippet = " ".join(source_text[start:end].split())
    if len(snippet) > limit:
        snippet = snippet[: limit - 3].rstrip() + "..."
    return snippet or "Selected text"


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "landing.html")


@router.get("/new-project", response_class=HTMLResponse)
async def new_project_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "new_project.html")


@router.get("/import", response_class=HTMLResponse)
async def import_page(request: Request):
    project_path: str | None = getattr(request.app.state, "project_path", None)
    if project_path is None or not Path(project_path).exists():
        raise HtmxRedirect("/")

    db_gen = get_db(request)
    conn = next(db_gen)
    try:
        project = get_project(conn)
        sources = list_sources(conn)
    finally:
        db_gen.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "import.html",
        {
            "project_name": project["name"],
            "source_count": len(sources),
        },
    )


def _source_annotation_context(
    conn: sqlite3.Connection,
    coder_id: str,
    source_id: str | None,
    source_text: str,
    section_heading_spans: tuple[tuple[int, int], ...],
    *,
    render_sentences: bool,
    sentence_cache: CodingContextCache | None = None,
    project_path: str | None = None,
) -> dict:
    """Shape the current source's annotations without reading project-wide data."""
    codes_list = [dict(code) for code in list_codes(conn)]
    codes_by_id = {code["id"]: code for code in codes_list}
    annotations_list = (
        [dict(ann) for ann in get_annotations_for_source(conn, source_id, coder_id)]
        if source_id else []
    )

    sentence_html = ""
    if render_sentences:
        from ace.services.coding_render import render_sentence_text
        from ace.services.text_splitter import split_into_units

        sentence_units = (
            sentence_cache.get_sentence_units(
                project_path, source_id, source_text, section_heading_spans
            )
            if sentence_cache is not None and project_path and source_id
            else split_into_units(source_text, section_heading_spans)
        )
        sentence_html = render_sentence_text(sentence_units, annotations_list, codes_by_id)

    seen_codes: set[str] = set()
    margin_codes: list[dict] = []
    applied_code_rows: list[dict] = []
    annotations_by_code: dict[str, list[dict]] = {}
    code_counts: dict[str, int] = {}
    for ann in annotations_list:
        cid = ann["code_id"]
        annotations_by_code.setdefault(cid, []).append(ann)
        code_counts[cid] = code_counts.get(cid, 0) + 1
        if cid not in seen_codes:
            code = codes_by_id.get(cid)
            if code:
                seen_codes.add(cid)
                margin_codes.append({
                    "code_id": cid,
                    "code_name": code["name"],
                    "colour": code["colour"],
                })

    source_length = max(len(source_text), 1)
    for code in margin_codes:
        cid = code["code_id"]
        segments = []
        occurrences = []
        for idx, ann in enumerate(annotations_by_code.get(cid, []), start=1):
            start_pct = max(0.0, min(100.0, 100.0 * ann["start_offset"] / source_length))
            width_pct = max(0.2, min(100.0 - start_pct, 100.0 * (ann["end_offset"] - ann["start_offset"]) / source_length))
            segments.append({
                "annotation_id": ann["id"],
                "left": round(start_pct, 3),
                "width": round(width_pct, 3),
            })
            occurrences.append({
                "annotation_id": ann["id"],
                "ordinal": idx,
                "excerpt": _annotation_excerpt(
                    source_text,
                    ann["start_offset"],
                    ann["end_offset"],
                ),
            })
        applied_code_rows.append({
            "code_id": cid,
            "code_name": code["code_name"],
            "colour": code["colour"],
            "count": code_counts.get(cid, 0),
            "segments": segments,
            "occurrences": occurrences,
        })

    annotation_highlights_json = Markup(html.escape(json.dumps([
        {"id": ann["id"], "code_id": ann["code_id"],
         "start": ann["start_offset"], "end": ann["end_offset"]}
        for ann in annotations_list
        if ann["code_id"] in codes_by_id
    ])))
    return {
        "codes": codes_list,
        "codes_by_id": codes_by_id,
        "annotations": annotations_list,
        "code_counts": code_counts,
        "margin_codes": margin_codes,
        "applied_code_rows": applied_code_rows,
        "annotation_highlights_json": annotation_highlights_json,
        "sentence_html": sentence_html,
    }


def _global_coding_context(
    conn: sqlite3.Connection,
    coder_id: str,
    project_path: str | None = None,
) -> dict:
    """Build the project-wide coding data shared by every source."""
    project = get_project(conn)
    sources = list_sources(conn)
    total_sources = len(sources)
    project_file_stem = Path(project_path).stem if project_path else ""

    # Repair missing assignments in projects imported before reconciliation.
    assignments = [dict(row) for row in get_assignments_for_coder(conn, coder_id)]
    if len(assignments) != total_sources:
        ensure_assignments(conn, coder_id)
        assignments = [dict(row) for row in get_assignments_for_coder(conn, coder_id)]

    notes_present = source_ids_with_notes(conn, coder_id)
    annotation_counts = get_annotation_counts_by_source(conn, coder_id)
    code_counts_by_id = get_annotation_counts_by_code(conn, coder_id)
    tree_codes = list_codes_with_tree(conn)
    code_counts_json = Markup(html.escape(json.dumps(code_counts_by_id)))
    coder_row = conn.execute(
        "SELECT name FROM coder WHERE id = ?", (coder_id,),
    ).fetchone()
    coder_name = coder_row["name"] if coder_row else "Unknown"
    sources_json = [
        {
            "index": i,
            "source_id": a["source_id"],
            "display_id": a["display_id"],
            "count": annotation_counts.get(a["source_id"], 0),
            "flagged": bool(a["flagged"]),
            "note": a["source_id"] in notes_present,
        }
        for i, a in enumerate(assignments)
    ]
    return {
        "project_name": project["name"],
        "project_file_stem": project_file_stem,
        "source_index_storage_key": (
            f"ace-source-index:{position_key(project_path, project['id'], coder_id)}"
            if project_path else f"ace-source-index:{project['id']}"
        ),
        "total_sources": total_sources,
        "colour_palette": [hex_val for hex_val, _label in COLOUR_PALETTE],
        "annotation_counts": annotation_counts,
        "coder_name": coder_name,
        "source_ids_with_notes": notes_present,
        "assignments": assignments,
        "sources_json": sources_json,
        "sources_snapshot_version": _sources_snapshot_version(sources_json),
        "tree_codes": tree_codes,
        "code_counts_by_id": code_counts_by_id,
        "code_counts_json": code_counts_json,
        "show_coding_text_controls": True,
        "version": __version__,
    }


def _coding_context(
    conn: sqlite3.Connection,
    coder_id: str,
    current_index: int,
    project_path: str | None = None,
    *,
    render_sentences: bool = True,
    global_context: dict | None = None,
    sentence_cache: CodingContextCache | None = None,
) -> dict:
    """Assemble a source's coding view from fresh or cached project data."""
    project_ctx = global_context or _global_coding_context(
        conn, coder_id, project_path
    )
    assignments = project_ctx["assignments"]
    total_sources = project_ctx["total_sources"]
    current_index = max(0, min(current_index, total_sources - 1))

    current_source = None
    source_text = ""
    section_heading_spans: tuple[tuple[int, int], ...] = ()
    is_flagged = False
    if assignments and current_index < len(assignments):
        assignment = assignments[current_index]
        source_id = assignment["source_id"]
        current_source = {"display_id": assignment["display_id"], "id": source_id}
        is_flagged = bool(assignment["flagged"])
        content_row = get_source_content(conn, source_id)
        if content_row:
            source_text = content_row["content_text"]
            section_heading_spans = decode_section_heading_spans(
                source_text, content_row["section_headings_json"]
            )
    elif total_sources:
        # Defensive fallback for a project whose assignments could not yet be
        # reconciled; the normal path above reads only the selected source.
        source = list_sources(conn)[current_index]
        current_source = {"display_id": source["display_id"], "id": source["id"]}
        content_row = get_source_content(conn, source["id"])
        if content_row:
            source_text = content_row["content_text"]
            section_heading_spans = decode_section_heading_spans(
                source_text, content_row["section_headings_json"]
            )

    current_note_text = (
        get_note(conn, current_source["id"], coder_id) or ""
        if current_source else ""
    )
    source_ctx = _source_annotation_context(
        conn,
        coder_id,
        current_source["id"] if current_source else None,
        source_text,
        section_heading_spans,
        render_sentences=render_sentences,
        sentence_cache=sentence_cache,
        project_path=project_path,
    )
    return {
        **project_ctx,
        "current_index": current_index,
        "current_source": current_source,
        "is_flagged": is_flagged,
        "source_text": source_text,
        **source_ctx,
        "current_note_text": current_note_text,
        "has_note": bool(current_note_text),
    }


@router.get("/agreement", response_class=HTMLResponse)
async def agreement_page(request: Request):
    templates = request.app.state.templates
    return templates.TemplateResponse(request, "agreement.html")


@router.get("/code", response_class=HTMLResponse)
async def coding_page(
    request: Request,
    index: int | None = Query(default=None),
    open_path: str | None = Query(default=None, alias="open"),
    note: int = Query(default=0),
    legacy_resume: bool = Query(default=False),
):
    # Launcher/browser file association: open a project before rendering the coding page
    if open_path:
        from ace.db.connection import open_project
        from ace.models.project import list_coders

        try:
            conn = open_project(open_path)
        except (ValueError, FileNotFoundError, sqlite3.DatabaseError):
            raise HtmxRedirect("/")
        try:
            coders = list_coders(conn)
        finally:
            conn.close()
        # A preview made for the previous project must not survive the switch:
        # confirmation imports into the current database, so drop the store
        # before the newly opened project is published.
        _clear_folder_import_manifests(request)
        request.app.state.coding_context_cache.close()
        request.app.state.project_path = str(open_path)
        if coders:
            request.app.state.coder_id = coders[0]["id"]
        request.app.state.active_projects.add(str(open_path))
        remember_recent_project(request, str(open_path))

    project_path: str | None = getattr(request.app.state, "project_path", None)
    if project_path is None or not Path(project_path).exists():
        raise HtmxRedirect("/")

    coder_id: str | None = getattr(request.app.state, "coder_id", None)
    if coder_id is None:
        raise HtmxRedirect("/")

    db_gen = get_db(request)
    conn = next(db_gen)
    try:
        sources = list_sources(conn)
        if not sources:
            raise HtmxRedirect("/import")

        global_context = _global_coding_context(conn, coder_id, project_path)
        key = position_key(project_path, get_project(conn)["id"], coder_id)
        store = getattr(request.app.state, "shared_source_position_store", None)
        shared_enabled = store is not None and request.session.get(
            "ace_launcher_authenticated"
        ) is True
        saved_position = None
        if shared_enabled:
            try:
                saved_position = store.read(key)
            except (OSError, sqlite3.Error):
                _LOG.warning("Could not read shared source position")
                shared_enabled = False
        saved_index = next(
            (i for i, row in enumerate(global_context["assignments"])
             if saved_position and row["source_id"] == saved_position["source_id"]),
            None,
        )
        requested_index = (
            saved_index if legacy_resume and saved_index is not None
            else 0 if legacy_resume and saved_position is not None
            else index if index is not None
            else saved_index if saved_index is not None
            else 0
        )
        context = _coding_context(
            conn, coder_id, requested_index, project_path=project_path,
            global_context=global_context,
            sentence_cache=request.app.state.coding_context_cache,
        )
        context["source_position_key"] = key
        context["source_position_enabled"] = shared_enabled
        context["source_position_has_record"] = saved_position is not None
        context["source_position_from_store"] = (
            (index is None or legacy_resume) and saved_position is not None
        )
        context["source_position_legacy_resume"] = legacy_resume
        if shared_enabled and context["current_source"] is not None:
            if (index is not None and not legacy_resume) or (
                saved_position is not None and saved_index is None
            ):
                remember_source_position(
                    request, conn, coder_id, context["current_source"]["id"]
                )
        context["open_note_drawer"] = bool(note)
        context["codebook_mode"] = "coding"
        context["shared_preferences"] = preferences_for_request(request)
    finally:
        db_gen.close()

    templates = request.app.state.templates
    return templates.TemplateResponse(request, "coding.html", context)


@router.get("/code/{code_id}/view", response_class=HTMLResponse)
async def code_view_page(request: Request, code_id: str):
    project_path: str | None = getattr(request.app.state, "project_path", None)
    if project_path is None or not Path(project_path).exists():
        raise HtmxRedirect("/")

    coder_id: str | None = getattr(request.app.state, "coder_id", None)
    if coder_id is None:
        raise HtmxRedirect("/")

    db_gen = get_db(request)
    conn = next(db_gen)
    try:
        data = get_code_view_data(conn, code_id, coder_id)
        if data is None:
            deleted_code = conn.execute(
                "SELECT 1 FROM codebook_code "
                "WHERE id = ? AND kind = 'code' AND deleted_at IS NOT NULL",
                (code_id,),
            ).fetchone()
            if deleted_code:
                return request.app.state.templates.TemplateResponse(
                    request, "code_view_deleted.html", status_code=410
                )
            raise HtmxRedirect("/code")
        tree_codes = list_codes_with_tree(conn)
        code_counts_by_id = get_annotation_counts_by_code(conn, coder_id)
    finally:
        db_gen.close()

    project_file_stem = Path(project_path).stem

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "code_view.html",
        {
            "code_view_data": data,
            "tree_codes": tree_codes,
            "code_counts_by_id": code_counts_by_id,
            "project_file_stem": project_file_stem,
            "version": __version__,
            "codebook_mode": "audit",
            "colour_palette": [hex_val for hex_val, _label in COLOUR_PALETTE],
            "shared_preferences": preferences_for_request(request),
        },
    )
