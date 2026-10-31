"""Issue #125: source identity must be explicit and survive duplicate texts.

Regression coverage for matching respondents across agreement files:
copied projects (shared stored source IDs) and independent imports
(unique content matching, ambiguous duplicate content rejected).
"""

import asyncio
import csv
import hashlib
import io
import shutil
import sqlite3
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from ace.db.connection import create_project
from ace.models.annotation import add_annotation
from ace.models.codebook import add_code
from ace.models.source import add_source
from ace.routes.api_agreement import agreement_export_raw
from ace.services.agreement_computer import compute_agreement
from ace.services.agreement_loader import AgreementLoader

# Two respondents with identical answers: the core #125 fixture.
TEXT = "This is a synthetic respondent answer, deliberately repeated for identity testing. " * 3


def _create_project(path: Path, sources: list[tuple[str, str]]) -> None:
    conn = create_project(path, "Source identity test")
    for display_id, text in sources:
        add_source(conn, display_id, text, "row")
    add_code(conn, "Theme", "#4CAF50")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.close()


def _annotate(path: Path, coder_name: str, spans: list[tuple[str, int, int]]) -> None:
    """Rename the default coder and add one annotation per (display_id, start, end)."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("UPDATE coder SET name = ? WHERE name = 'default'", (coder_name,))
    conn.commit()
    coder_id = conn.execute("SELECT id FROM coder WHERE name = ?", (coder_name,)).fetchone()[0]
    code_id = conn.execute("SELECT id FROM codebook_code WHERE name = 'Theme'").fetchone()[0]
    for display_id, start, end in spans:
        row = conn.execute(
            "SELECT s.id, sc.content_text FROM source s "
            "JOIN source_content sc ON sc.source_id = s.id WHERE s.display_id = ?",
            (display_id,),
        ).fetchone()
        add_annotation(conn, row["id"], coder_id, code_id, start, end, row["content_text"][start:end])
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.close()


def _mutate_source(path: Path, display_id: str, *, text: str | None = None, content_hash: str | None = None) -> None:
    """Rewrite stored source content directly — the stale-metadata failure mode.

    Nothing in the schema keeps content_text and content_hash in sync, so
    identity matching must be verified against the actual text.
    """
    conn = sqlite3.connect(path)
    source_id = conn.execute(
        "SELECT sc.source_id FROM source_content sc "
        "JOIN source s ON s.id = sc.source_id WHERE s.display_id = ?",
        (display_id,),
    ).fetchone()[0]
    if text is not None:
        conn.execute("UPDATE source_content SET content_text = ? WHERE source_id = ?", (text, source_id))
    if content_hash is not None:
        conn.execute("UPDATE source_content SET content_hash = ? WHERE source_id = ?", (content_hash, source_id))
    conn.commit()
    conn.close()


def _annotate_rows(path: Path, coder_name: str, spans: list[tuple[int, int, int]]) -> None:
    """Annotate by source row index (sources may share a display_id)."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("UPDATE coder SET name = ? WHERE name = 'default'", (coder_name,))
    conn.commit()
    coder_id = conn.execute("SELECT id FROM coder WHERE name = ?", (coder_name,)).fetchone()[0]
    code_id = conn.execute("SELECT id FROM codebook_code WHERE name = 'Theme'").fetchone()[0]
    rows = conn.execute(
        "SELECT s.id, sc.content_text FROM source s "
        "JOIN source_content sc ON sc.source_id = s.id ORDER BY s.id"
    ).fetchall()
    for row_idx, start, end in spans:
        row = rows[row_idx]
        add_annotation(conn, row["id"], coder_id, code_id, start, end, row["content_text"][start:end])
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.close()


def _copied_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Two coder files copied from one project: shared stored source IDs, duplicate texts."""
    base = tmp_path / "base.ace"
    _create_project(base, [("R1", TEXT), ("R2", TEXT)])
    a, b = tmp_path / "A.ace", tmp_path / "B.ace"
    shutil.copyfile(base, a)
    shutil.copyfile(base, b)
    return a, b


def _loader(*paths: Path) -> AgreementLoader:
    loader = AgreementLoader()
    for p in paths:
        assert loader.add_file(p)["error"] is None
    return loader


def test_copied_duplicate_text_cross_coded_only_is_rejected(tmp_path):
    """A codes only R1, B codes only R2: no respondent coded by both, so no agreement."""
    a, b = _copied_pair(tmp_path)
    _annotate(a, "Alice", [("R1", 0, 80)])
    _annotate(b, "Bob", [("R2", 0, 80)])

    loader = _loader(a, b)
    result = loader.validate()

    assert result["valid"] is False
    assert "coded by every coder" in result["error"]
    with pytest.raises(ValueError):
        loader.build_dataset()


def test_copied_duplicate_text_both_coded_keeps_both_sources(tmp_path):
    """Legitimate duplicate responses: two matched sources, 80 coded positions each."""
    a, b = _copied_pair(tmp_path)
    _annotate(a, "Alice", [("R1", 0, 80), ("R2", 0, 80)])
    _annotate(b, "Bob", [("R1", 0, 80), ("R2", 0, 80)])

    loader = _loader(a, b)
    result = loader.validate()

    assert result["valid"] is True
    assert result["matched_sources"] == 2
    ds = loader.build_dataset()
    assert len(ds.sources) == 2
    assert len({s.source_key for s in ds.sources}) == 2
    metrics = compute_agreement(ds)
    assert metrics.n_sources == 2
    assert metrics.overall.n_positions == 160
    assert metrics.overall.percent_agreement == pytest.approx(1.0)


def test_copied_duplicate_text_swapped_spans_score_zero(tmp_path):
    """Both respondents eligible but coders swap spans: full disagreement, not 100%."""
    a, b = _copied_pair(tmp_path)
    _annotate(a, "Alice", [("R1", 0, 80), ("R2", 80, 160)])
    _annotate(b, "Bob", [("R1", 80, 160), ("R2", 0, 80)])

    loader = _loader(a, b)
    assert loader.validate()["valid"] is True

    metrics = compute_agreement(loader.build_dataset())
    assert metrics.overall.n_positions == 320
    assert metrics.overall.percent_agreement == pytest.approx(0.0)
    assert metrics.overall.gwets_ac1 == pytest.approx(-1.0)
    pair = next(iter(metrics.pairwise.values()))
    assert pair.n_positions == 320
    assert pair.percent_agreement == pytest.approx(0.0)
    assert pair.gwets_ac1 == pytest.approx(-1.0)


def test_independent_duplicate_content_is_rejected(tmp_path):
    """Independently imported files with duplicate texts cannot be matched reliably."""
    a, b = tmp_path / "A.ace", tmp_path / "B.ace"
    _create_project(a, [("R1", TEXT), ("R2", TEXT)])
    _create_project(b, [("R1", TEXT), ("R2", TEXT)])
    _annotate(a, "Alice", [("R1", 0, 80), ("R2", 0, 80)])
    _annotate(b, "Bob", [("R1", 0, 80), ("R2", 0, 80)])

    loader = _loader(a, b)
    result = loader.validate()

    assert result["valid"] is False
    assert "cannot be matched" in result["error"]
    # Guidance must not suggest mutating the respondents' text.
    assert "copies of the same original project" in result["error"]
    assert "unique" not in result["error"]
    with pytest.raises(ValueError):
        loader.build_dataset()


def test_independent_unique_content_still_matches(tmp_path):
    """The established fallback: unique identical text matches across independent files."""
    a, b = tmp_path / "A.ace", tmp_path / "B.ace"
    _create_project(a, [("S1", TEXT)])
    _create_project(b, [("S1", TEXT)])
    _annotate(a, "Alice", [("S1", 0, 80)])
    _annotate(b, "Bob", [("S1", 0, 80)])

    loader = _loader(a, b)
    assert loader.validate()["valid"] is True

    ds = loader.build_dataset()
    assert len(ds.sources) == 1
    assert compute_agreement(ds).overall.percent_agreement == pytest.approx(1.0)


def test_shared_source_id_with_changed_content_is_rejected(tmp_path):
    """Same stored source ID with different text must not silently match."""
    a, b = _copied_pair(tmp_path)
    conn = sqlite3.connect(b)
    source_id = conn.execute(
        "SELECT sc.source_id FROM source_content sc "
        "JOIN source s ON s.id = sc.source_id WHERE s.display_id = 'R2'"
    ).fetchone()[0]
    new_text = TEXT + " Edited after copying."
    conn.execute(
        "UPDATE source_content SET content_text = ?, content_hash = ? WHERE source_id = ?",
        (new_text, hashlib.sha256(new_text.encode()).hexdigest(), source_id),
    )
    conn.commit()
    conn.close()
    _annotate(a, "Alice", [("R1", 0, 80), ("R2", 0, 80)])
    _annotate(b, "Bob", [("R1", 0, 80), ("R2", 0, 80)])

    loader = _loader(a, b)
    result = loader.validate()

    assert result["valid"] is False
    assert "different text" in result["error"]
    with pytest.raises(ValueError):
        loader.build_dataset()


def test_raw_export_attributes_each_coder_to_their_own_source(tmp_path):
    """Raw CSV rows must carry the display id of the source actually annotated."""
    a, b = _copied_pair(tmp_path)
    _annotate(a, "Alice", [("R1", 0, 80), ("R2", 0, 80)])
    _annotate(b, "Bob", [("R1", 0, 80), ("R2", 0, 80)])

    loader = _loader(a, b)
    ds = loader.build_dataset()
    result = compute_agreement(ds)

    request = Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace(
        agreement_loader=loader, agreement_dataset=ds, agreement_result=result))})
    response = asyncio.run(agreement_export_raw(request))
    assert response.status_code == 200

    rows = list(csv.DictReader(io.StringIO(response.body.decode())))
    coder_id = {c.label: c.id for c in ds.coders}
    assert Counter((r["source_id"], r["coder_id"]) for r in rows) == Counter({
        ("R1", coder_id["Alice"]): 1,
        ("R1", coder_id["Bob"]): 1,
        ("R2", coder_id["Alice"]): 1,
        ("R2", coder_id["Bob"]): 1,
    })


def test_unmatched_warning_counts_source_units(tmp_path):
    """Matched/unmatched counts are source entries, not distinct text hashes."""
    a, b = tmp_path / "A.ace", tmp_path / "B.ace"
    _create_project(a, [("S1", TEXT), ("S2", "A different respondent answer entirely.")])
    _create_project(b, [("S1", TEXT)])
    _annotate(a, "Alice", [("S1", 0, 80), ("S2", 0, 20)])
    _annotate(b, "Bob", [("S1", 0, 80)])

    loader = _loader(a, b)
    result = loader.validate()

    assert result["valid"] is True
    assert result["matched_sources"] == 1
    assert any("2 of 3 sources" in w for w in result["warnings"])


# ── Stale stored metadata: identity must be verified against actual text ──────────


def test_shared_source_id_stale_hash_with_different_text_is_rejected(tmp_path):
    """Same UUID, stored hash unchanged, but the actual text differs: must fail.

    A synthetic .ace file can keep a stale content_hash while its content_text
    was edited; the shared-ID check must compare the text itself, or two
    different responses validate as one and score false perfect agreement.
    """
    a, b = _copied_pair(tmp_path)
    _mutate_source(b, "R2", text=TEXT + " Quietly edited after copying.")
    _annotate(a, "Alice", [("R1", 0, 80), ("R2", 0, 80)])
    _annotate(b, "Bob", [("R1", 0, 80), ("R2", 0, 80)])

    loader = _loader(a, b)
    result = loader.validate()

    assert result["valid"] is False
    assert "different text" in result["error"]
    with pytest.raises(ValueError):
        loader.build_dataset()


def test_shared_source_id_identical_text_differing_stale_hashes_validates(tmp_path):
    """Same UUID, identical actual text, differing stored hashes: still valid."""
    a, b = _copied_pair(tmp_path)
    _mutate_source(b, "R2", content_hash="0" * 64)  # stale metadata, text intact
    _annotate(a, "Alice", [("R1", 0, 80), ("R2", 0, 80)])
    _annotate(b, "Bob", [("R1", 0, 80), ("R2", 0, 80)])

    loader = _loader(a, b)
    result = loader.validate()

    assert result["valid"] is True
    assert result["matched_sources"] == 2


def test_independent_stale_hash_cannot_fake_content_match(tmp_path):
    """Fallback grouping must use actual text, not stored hashes.

    B's S2 stores A's S2 hash while carrying different text. If the fallback
    trusted the hash, the tampered source would count as matched and agreement
    would silently compare two different responses.
    """
    a, b = tmp_path / "A.ace", tmp_path / "B.ace"
    s2_text = "A different respondent answer entirely."
    _create_project(a, [("S1", TEXT), ("S2", s2_text)])
    _create_project(b, [("S1", TEXT), ("S2", "Tampered text that only claims to be S2.")])
    _mutate_source(b, "S2", content_hash=hashlib.sha256(s2_text.encode()).hexdigest())
    _annotate(a, "Alice", [("S1", 0, 80), ("S2", 0, 20)])
    _annotate(b, "Bob", [("S1", 0, 80), ("S2", 0, 20)])

    loader = _loader(a, b)
    result = loader.validate()

    assert result["valid"] is True
    assert result["matched_sources"] == 1
    assert any("2 of 4 sources" in w for w in result["warnings"])


def test_independent_identical_text_differing_stale_hashes_still_matches(tmp_path):
    """Identical actual text with differing stored hashes still matches."""
    a, b = tmp_path / "A.ace", tmp_path / "B.ace"
    _create_project(a, [("S1", TEXT)])
    _create_project(b, [("S1", TEXT)])
    _mutate_source(b, "S1", content_hash="deadbeef")
    _annotate(a, "Alice", [("S1", 0, 80)])
    _annotate(b, "Bob", [("S1", 0, 80)])

    loader = _loader(a, b)
    result = loader.validate()

    assert result["valid"] is True
    assert result["matched_sources"] == 1


# ── Raw export identity ───────────────────────────────────────────────────────────


def test_raw_export_distinguishes_duplicate_display_labels(tmp_path):
    """Two sources sharing one display_id stay distinguishable via source_key."""
    base = tmp_path / "base.ace"
    _create_project(base, [("R1", TEXT), ("R1", TEXT)])
    a, b = tmp_path / "A.ace", tmp_path / "B.ace"
    shutil.copyfile(base, a)
    shutil.copyfile(base, b)
    _annotate_rows(a, "Alice", [(0, 0, 80), (1, 0, 80)])
    _annotate_rows(b, "Bob", [(0, 0, 80), (1, 0, 80)])

    loader = _loader(a, b)
    ds = loader.build_dataset()
    result = compute_agreement(ds)

    request = Request({"type": "http", "app": SimpleNamespace(state=SimpleNamespace(
        agreement_loader=loader, agreement_dataset=ds, agreement_result=result))})
    response = asyncio.run(agreement_export_raw(request))
    assert response.status_code == 200

    rows = list(csv.DictReader(io.StringIO(response.body.decode())))
    keys = {r["source_key"] for r in rows}
    assert keys == {s.source_key for s in ds.sources}
    assert len(keys) == 2  # two identities despite one shared label
    assert {r["source_id"] for r in rows} == {"R1"}  # label alone is ambiguous
    assert all(r["n_sources"] == "2" for r in rows)
    assert len(rows) == 4
    coder_id = {c.label: c.id for c in ds.coders}
    assert Counter((r["source_key"], r["coder_id"]) for r in rows) == Counter({
        (k, cid): 1 for k in keys for cid in coder_id.values()
    })
    assert set(result.per_source) == keys
    assert result.overall.n_positions == 160


# ── Determinism of eligibility computation ────────────────────────────────────────


def test_build_dataset_computes_eligibility_once(tmp_path, monkeypatch):
    """_eligible_match_keys runs once per build_dataset pass, not once per match."""
    a, b = _copied_pair(tmp_path)
    _annotate(a, "Alice", [("R1", 0, 80), ("R2", 0, 80)])
    _annotate(b, "Bob", [("R1", 0, 80), ("R2", 0, 80)])
    loader = _loader(a, b)

    calls = {"n": 0}
    original = AgreementLoader._eligible_match_keys

    def counting(self, matches):
        calls["n"] += 1
        return original(self, matches)

    monkeypatch.setattr(AgreementLoader, "_eligible_match_keys", counting)
    loader.build_dataset()

    # Once via validate(), once directly — never once per matched source.
    assert calls["n"] == 2
