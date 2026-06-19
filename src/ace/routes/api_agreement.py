"""API routes — JSON/HTMX fragment responses."""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import (
    APIRouter,
    Form,
    Request,
)
from fastapi.responses import (
    HTMLResponse,
    Response,
)


router = APIRouter(prefix="/api")

from ace.routes.api_support import (
    _AGREEMENT_STALE,
    _agreement_error,
    _agreement_progress,
    _clear_agreement_cache,
    _parse_agreement_paths,
    _render_agreement_preview,
    _run_agreement,
    _run_agreement_preview,
)


@router.post("/agreement/preview")
async def agreement_preview(
    request: Request,
    paths: str | None = Form(default=None),
):
    _clear_agreement_cache(request.app.state)

    path_list, error = _parse_agreement_paths(paths)
    if error:
        return HTMLResponse(_agreement_error(error), status_code=200)

    preview = await asyncio.to_thread(_run_agreement_preview, path_list)
    html_out = _render_agreement_preview(preview, request.app.state.templates.env)
    return HTMLResponse(html_out, status_code=200)


@router.post("/agreement/compute")
async def agreement_compute(
    request: Request,
    paths: str | None = Form(default=None),
):
    """Load files, compute agreement (off-thread), return minimalist results HTML.

    The load + build + compute runs in a worker thread (``asyncio.to_thread``)
    so the event loop stays responsive. Progress is published to
    ``app.state.agreement_progress`` and read via ``GET /api/agreement/progress``.
    """
    generation = _clear_agreement_cache(request.app.state)

    path_list, error = _parse_agreement_paths(paths)
    if error:
        return HTMLResponse(_agreement_error(error), status_code=200)

    request.app.state.agreement_progress = _agreement_progress(0, "Loading files")

    html_out = await asyncio.to_thread(
        _run_agreement,
        path_list,
        request.app.state,
        request.app.state.templates.env,
        generation,
    )
    if html_out is _AGREEMENT_STALE:
        return Response(status_code=204)

    prog = getattr(request.app.state, "agreement_progress", {}) or {}
    if prog.get("error"):
        return HTMLResponse(_agreement_error(prog["error"]), status_code=200)
    if html_out is None:
        return HTMLResponse(
            _agreement_error("Agreement could not be computed."),
            status_code=200,
        )
    return HTMLResponse(html_out)


@router.get("/agreement/progress")
async def agreement_progress(request: Request):
    """Return the current agreement-compute progress as JSON.

    Shape: ``{percent: 0-100, stage: str, done: bool, error: str | null}``.
    """
    p = getattr(request.app.state, "agreement_progress", None) or _agreement_progress(0, "")
    return {
        "percent": p.get("percent", 0),
        "stage": p.get("stage", ""),
        "done": bool(p.get("done")),
        "error": p.get("error"),
    }


@router.post("/agreement/clear")
async def agreement_clear(request: Request):
    """Clear cached agreement results before a replacement file selection."""
    _clear_agreement_cache(request.app.state)
    return Response(status_code=204)


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
