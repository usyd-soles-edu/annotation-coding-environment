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


def test_unmatched_warning_counts_source_identities(tmp_path):
    """Matched/unmatched counts are source identities, not file entries or text hashes."""
    a, b = tmp_path / "A.ace", tmp_path / "B.ace"
    _create_project(a, [("S1", TEXT), ("S2", "A different respondent answer entirely.")])
    _create_project(b, [("S1", TEXT)])
    _annotate(a, "Alice", [("S1", 0, 80), ("S2", 0, 20)])
    _annotate(b, "Bob", [("S1", 0, 80)])

    loader = _loader(a, b)
    result = loader.validate()

    assert result["valid"] is True
    assert result["matched_sources"] == 1
    assert any("1 of 2 sources" in w for w in result["warnings"])


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
    assert any("1 of 3 sources" in w for w in result["warnings"])


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

# ── Copied projects: identity must not degrade to text matching ──────────────────


def _reimport_source(path: Path, display_id: str, new_display_id: str, *, text: str | None = None) -> None:
    """Replace a source with a fresh UUID (simulates independent re-import into a copy)."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT s.id, sc.content_text FROM source s "
        "JOIN source_content sc ON sc.source_id = s.id WHERE s.display_id = ?",
        (display_id,),
    ).fetchone()
    conn.execute("DELETE FROM source_content WHERE source_id = ?", (row["id"],))
    conn.execute("DELETE FROM source WHERE id = ?", (row["id"],))
    add_source(conn, new_display_id, text or row["content_text"], "row")
    conn.commit()
    conn.close()


def _delete_source(path: Path, display_id: str) -> None:
    conn = sqlite3.connect(path)
    sid = conn.execute(
        "SELECT id FROM source WHERE display_id = ?", (display_id,)
    ).fetchone()[0]
    conn.execute("DELETE FROM source_content WHERE source_id = ?", (sid,))
    conn.execute("DELETE FROM source WHERE id = ?", (sid,))
    conn.commit()
    conn.close()


def _divergent_copies(tmp_path: Path, *, anchor: str) -> tuple[Path, Path]:
    """Copies of one project whose respondent was re-imported with a new UUID.

    A and B are copies of one project (same project id). B re-imports R2 as
    R3: identical text, different UUID. Only A's R2 and B's R3 are coded, so
    no respondent is actually coded by both coders.

    anchor:
      "same"       — both files keep R1 with one UUID and text
      "reimported" — B also re-imports R1 with a new UUID and different text
      "none"       — the project has no anchor respondent at all
    """
    sources: list[tuple[str, str]] = []
    if anchor != "none":
        sources.append(("R1", "An anchor respondent with its own text."))
    sources.append(("R2", TEXT))
    base = tmp_path / f"{anchor}-base.ace"
    _create_project(base, sources)
    a, b = tmp_path / f"{anchor}-A.ace", tmp_path / f"{anchor}-B.ace"
    shutil.copyfile(base, a)
    shutil.copyfile(base, b)
    if anchor == "reimported":
        _reimport_source(b, "R1", "R1b", text="A different anchor text entirely.")
    _reimport_source(b, "R2", "R3")
    _annotate(a, "Alice", [("R2", 0, 80)])
    _annotate(b, "Bob", [("R3", 0, 80)])
    return a, b


@pytest.mark.parametrize("anchor", ["same", "reimported", "none"])
def test_copied_divergent_uuids_never_bridge_as_one_respondent(tmp_path, anchor):
    """Re-imported sources in copies of one project are not one respondent.

    Before the fix the identical R2/R3 text matched via the content fallback,
    validated, and produced perfect agreement although no respondent was
    coded by both coders.
    """
    a, b = _divergent_copies(tmp_path, anchor=anchor)
    loader = _loader(a, b)
    result = loader.validate()

    assert result["valid"] is False, result
    with pytest.raises(ValueError):
        loader.build_dataset()


def test_independent_third_file_cannot_bridge_same_project_conflict(tmp_path):
    """An independent file's identical text must not bridge a same-project conflict.

    A and B are copies of one project disagreeing on the UUID for TEXT; C is an
    unrelated project holding the same text. Order of the files must not matter.
    """
    base = tmp_path / "bridge-base.ace"
    _create_project(base, [("R1", "An anchor respondent with its own text."), ("R2", TEXT)])
    a, b = tmp_path / "bridge-A.ace", tmp_path / "bridge-B.ace"
    shutil.copyfile(base, a)
    shutil.copyfile(base, b)
    _reimport_source(b, "R2", "R3")
    c = tmp_path / "bridge-C.ace"
    _create_project(c, [("S1", TEXT), ("S2", "An independent extra response.")])
    _annotate(a, "Alice", [("R2", 0, 80)])
    _annotate(b, "Bob", [("R3", 0, 80)])
    _annotate(c, "Carol", [("S1", 0, 80)])

    for paths in ([a, b, c], [c, a, b], [b, c, a]):
        loader = _loader(*paths)
        result = loader.validate()
        assert result["valid"] is False, (paths, result)


def test_multiple_copy_groups_match_only_within_agreeing_groups(tmp_path):
    """Each project-id group must agree internally; conflicting groups refuse.

    Group 1 (A, B) agrees on both UUIDs. Group 2 (C, D) agrees on T2 but
    disagrees on T1 (D re-imported it). T1 must be refused even though every
    file holds its text; T2 stays matched.
    """
    t1 = "First group-shared response text."
    t2 = "Second group-shared response text."
    base1 = tmp_path / "g1-base.ace"
    _create_project(base1, [("T1", t1), ("T2", t2)])
    a, b = tmp_path / "g1-A.ace", tmp_path / "g1-B.ace"
    shutil.copyfile(base1, a)
    shutil.copyfile(base1, b)
    base2 = tmp_path / "g2-base.ace"
    _create_project(base2, [("T1", t1), ("T2", t2)])
    c, d = tmp_path / "g2-C.ace", tmp_path / "g2-D.ace"
    shutil.copyfile(base2, c)
    shutil.copyfile(base2, d)
    _reimport_source(d, "T1", "T1x")
    spans = [("T1", 0, 6), ("T2", 0, 10)]
    for p, name, s in ((a, "Alice", spans), (b, "Bob", spans),
                       (c, "Carol", spans), (d, "Dave", [("T1x", 0, 6), ("T2", 0, 10)])):
        _annotate(p, name, s)  # both coded everywhere (D codes the re-imported T1x)

    loader = _loader(a, b, c, d)
    result = loader.validate()

    assert result["valid"] is True
    assert result["matched_sources"] == 1
    ds = loader.build_dataset()
    assert [s.content_text for s in ds.sources] == [t2]


def test_shared_uuid_copies_plus_independent_file_still_match(tmp_path):
    """Valid mixed provenance keeps matching: copies agreeing on the UUID plus C."""
    base = tmp_path / "mix-base.ace"
    _create_project(base, [("R1", TEXT)])
    a, b = tmp_path / "mix-A.ace", tmp_path / "mix-B.ace"
    shutil.copyfile(base, a)
    shutil.copyfile(base, b)
    c = tmp_path / "mix-C.ace"
    _create_project(c, [("S1", TEXT)])
    _annotate(a, "Alice", [("R1", 0, 80)])
    _annotate(b, "Bob", [("R1", 0, 80)])
    _annotate(c, "Carol", [("S1", 0, 80)])

    loader = _loader(a, b, c)
    result = loader.validate()

    assert result["valid"] is True
    assert result["matched_sources"] == 1
    assert compute_agreement(loader.build_dataset()).overall.percent_agreement == pytest.approx(1.0)


def test_total_source_identities_counts_distinct_uuids_not_file_entries(tmp_path):
    """Totals count identities: matched once, unmatched by distinct source UUID."""
    base = tmp_path / "count-base.ace"
    _create_project(base, [("R1", "First response text."), ("R2", "Second response text.")])
    a, b, c = (tmp_path / f"count-{n}.ace" for n in "ABC")
    shutil.copyfile(base, a)
    shutil.copyfile(base, b)
    shutil.copyfile(base, c)
    _delete_source(c, "R2")  # third copy holds only R1
    _annotate(a, "Alice", [("R1", 0, 5), ("R2", 0, 6)])
    _annotate(b, "Bob", [("R1", 0, 5), ("R2", 0, 6)])
    _annotate(c, "Carol", [("R1", 0, 5)])

    loader = _loader(a, b, c)
    result = loader.validate()
    assert result["valid"] is True
    assert result["matched_sources"] == 1
    matches, _ = loader._match_sources()
    # R1 matched + one unmatched identity (R2's UUID shared by A and B).
    assert loader._total_source_identities(matches) == 2
    assert any("1 of 2 sources" in w for w in result["warnings"])

    # Duplicate text between a matched and an unmatched source counts both.
    dup_base = tmp_path / "dup-base.ace"
    _create_project(dup_base, [("R1", TEXT), ("R2", TEXT)])
    d, e = tmp_path / "dup-D.ace", tmp_path / "dup-E.ace"
    shutil.copyfile(dup_base, d)
    shutil.copyfile(dup_base, e)
    _delete_source(e, "R2")
    _annotate(d, "Dana", [("R1", 0, 80)])
    _annotate(e, "Evan", [("R1", 0, 80)])

    loader2 = _loader(d, e)
    result2 = loader2.validate()
    assert result2["valid"] is True
    matches2, _ = loader2._match_sources()
    assert loader2._total_source_identities(matches2) == 2


def _clear_project_identity(path: Path, value: str | None) -> None:
    with sqlite3.connect(path) as conn:
        if value == "missing-row":
            conn.execute("DELETE FROM project")
        else:
            conn.execute("UPDATE project SET id = ?", (value,))


@pytest.mark.parametrize("project_id", [None, "", " \t", "missing-row"])
@pytest.mark.parametrize("independent_third", [False, True])
def test_unknown_provenance_never_allows_text_fallback(tmp_path, project_id, independent_third):
    a, b = _divergent_copies(tmp_path, anchor="same")
    _clear_project_identity(b, project_id)
    paths = [a, b]
    if independent_third:
        c = tmp_path / "independent.ace"
        _create_project(c, [("S1", TEXT)])
        _annotate(c, "Carol", [("S1", 0, 80)])
        paths.append(c)

    for ordered_paths in (paths, list(reversed(paths))):
        loader = _loader(*ordered_paths)
        assert loader.validate()["valid"] is False
        with pytest.raises(ValueError):
            loader.build_dataset()


@pytest.mark.parametrize("project_id", [None, "", " \t", "missing-row"])
def test_unknown_provenance_preserves_verified_shared_source_ids(tmp_path, project_id):
    a, b = _copied_pair(tmp_path)
    _annotate(a, "Alice", [("R1", 0, 80), ("R2", 0, 80)])
    _annotate(b, "Bob", [("R1", 0, 80), ("R2", 0, 80)])
    _clear_project_identity(b, project_id)

    loader = _loader(a, b)
    assert loader.validate()["matched_sources"] == 2
    dataset = loader.build_dataset()
    assert len({s.source_key for s in dataset.sources}) == 2
    metrics = compute_agreement(dataset)
    assert metrics.n_sources == 2
    assert metrics.overall.n_positions == 160
    assert metrics.overall.percent_agreement == pytest.approx(1.0)
