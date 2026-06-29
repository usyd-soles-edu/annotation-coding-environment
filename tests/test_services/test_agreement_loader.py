"""Tests for AgreementLoader."""

import sqlite3
from pathlib import Path

from ace.db.connection import create_project
from ace.db.schema import ACE_APPLICATION_ID
from ace.models.source import add_source
from ace.models.codebook import add_code
from ace.models.annotation import add_annotation
from ace.models.project import add_coder
from ace.services.agreement_loader import AgreementLoader


def _make_coder_file(path: Path, coder_name: str, text: str, code_name: str, spans: list[tuple[int, int]]) -> Path:
    """Helper: create an .ace file with one coder, one source, one code, N annotations."""
    conn = create_project(path, f"Project {coder_name}")
    source_id = add_source(conn, "S001", text, "row")
    code_id = add_code(conn, code_name, "#4CAF50")

    # Rename the default coder
    conn.execute("UPDATE coder SET name = ? WHERE name = 'default'", (coder_name,))
    conn.commit()
    coder_id = conn.execute("SELECT id FROM coder WHERE name = ?", (coder_name,)).fetchone()["id"]

    for start, end in spans:
        add_annotation(conn, source_id, coder_id, code_id, start, end, text[start:end])

    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.close()
    return path


def _make_coder_file_with_sources(
    path: Path,
    coder_name: str,
    sources: list[tuple[str, str]],
    code_name: str,
    annotations: list[tuple[int, int, int]],
    inactive_coder_names: list[str] | None = None,
) -> Path:
    """Helper: create an .ace file with several sources and one code."""
    conn = create_project(path, f"Project {coder_name}")
    source_ids = [add_source(conn, display_id, text, "row") for display_id, text in sources]
    code_id = add_code(conn, code_name, "#4CAF50")

    conn.execute("UPDATE coder SET name = ? WHERE name = 'default'", (coder_name,))
    conn.commit()
    coder_id = conn.execute("SELECT id FROM coder WHERE name = ?", (coder_name,)).fetchone()["id"]
    for inactive_name in inactive_coder_names or []:
        add_coder(conn, inactive_name)

    for source_index, start, end in annotations:
        text = sources[source_index][1]
        add_annotation(conn, source_ids[source_index], coder_id, code_id, start, end, text[start:end])

    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.close()
    return path


def test_load_single_valid_file(tmp_path):
    text = "I enjoyed the group work sessions."
    path = _make_coder_file(tmp_path / "alice.ace", "Alice", text, "Positive", [(2, 9)])

    loader = AgreementLoader()
    info = loader.add_file(path)

    assert info["coder_names"] == ["Alice"]
    assert info["source_count"] == 1
    assert info["annotation_count"] == 1
    assert info["warnings"] == []


def test_reject_invalid_file(tmp_path):
    bad_file = tmp_path / "bad.ace"
    conn = sqlite3.connect(str(bad_file))
    conn.execute("CREATE TABLE dummy (id TEXT)")
    conn.close()

    loader = AgreementLoader()
    info = loader.add_file(bad_file)
    assert info["error"] is not None
    assert "not a valid ace project" in info["error"].lower()


def test_warn_wal_file(tmp_path):
    text = "Test text here."
    path = _make_coder_file(tmp_path / "bob.ace", "Bob", text, "Code", [(0, 4)])
    # Create a fake WAL file
    wal_path = Path(str(path) + "-wal")
    wal_path.write_bytes(b"fake wal")

    loader = AgreementLoader()
    info = loader.add_file(path)
    assert any("uncommitted" in w.lower() for w in info["warnings"])


def test_validate_two_matching_files(tmp_path):
    text = "I enjoyed the group work sessions."
    _make_coder_file(tmp_path / "alice.ace", "Alice", text, "Positive", [(2, 9)])
    _make_coder_file(tmp_path / "bob.ace", "Bob", text, "Positive", [(2, 12)])

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")

    result = loader.validate()
    assert result["valid"] is True
    assert result["matched_sources"] == 1
    assert result["matched_codes"] == 1
    assert result["n_coders"] == 2


def test_validate_no_overlapping_sources(tmp_path):
    _make_coder_file(tmp_path / "alice.ace", "Alice", "Text A", "Code", [(0, 4)])
    _make_coder_file(tmp_path / "bob.ace", "Bob", "Text B", "Code", [(0, 4)])

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")

    result = loader.validate()
    assert result["valid"] is False
    assert "no source texts" in result["error"].lower()


def test_validate_counts_only_sources_coded_in_every_file(tmp_path):
    fully_coded = "This source is present and coded by every coder."
    uncoded_by_carol = "This source is present but not coded by Carol."
    alice_bob_only = "This source is present only for Alice and Bob."
    bob_carol_only = "This source is present only for Bob and Carol."

    _make_coder_file_with_sources(
        tmp_path / "alice.ace",
        "Alice",
        [("A1", fully_coded), ("A2", uncoded_by_carol), ("A3", alice_bob_only)],
        "Code",
        [(0, 0, 6), (1, 0, 6), (2, 0, 6)],
    )
    _make_coder_file_with_sources(
        tmp_path / "bob.ace",
        "Bob",
        [("B1", fully_coded), ("B2", uncoded_by_carol), ("B3", alice_bob_only), ("B4", bob_carol_only)],
        "Code",
        [(0, 0, 6), (1, 0, 6), (2, 0, 6), (3, 0, 6)],
    )
    _make_coder_file_with_sources(
        tmp_path / "carol.ace",
        "Carol",
        [("C1", fully_coded), ("C2", uncoded_by_carol), ("C3", bob_carol_only)],
        "Code",
        [(0, 0, 6), (2, 0, 6)],
    )

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")
    loader.add_file(tmp_path / "carol.ace")

    result = loader.validate()
    ds = loader.build_dataset()

    assert result["valid"] is True
    assert result["matched_sources"] == 1
    assert [s.content_text for s in ds.sources] == [fully_coded]
    assert len(ds.annotations) == 3
    assert any("coded by every coder" in w for w in result["warnings"])


def test_validate_ignores_inactive_coder_rows(tmp_path):
    shared = "This source is coded by the active coders."

    _make_coder_file_with_sources(
        tmp_path / "alice.ace",
        "Alice",
        [("A1", shared)],
        "Code",
        [(0, 0, 6)],
        inactive_coder_names=["Unused coder"],
    )
    _make_coder_file_with_sources(
        tmp_path / "bob.ace",
        "Bob",
        [("B1", shared)],
        "Code",
        [(0, 0, 6)],
    )

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")

    result = loader.validate()
    ds = loader.build_dataset()

    assert result["valid"] is True
    assert result["matched_sources"] == 1
    assert result["n_coders"] == 2
    assert [c.label for c in ds.coders] == ["Alice", "Bob"]


def test_validate_rejects_when_shared_sources_are_not_coded_by_every_file(tmp_path):
    shared_uncoded_by_carol = "This shared source is not coded by Carol."
    carol_unique = "Carol coded a different source."

    _make_coder_file_with_sources(
        tmp_path / "alice.ace",
        "Alice",
        [("A1", shared_uncoded_by_carol)],
        "Code",
        [(0, 0, 6)],
    )
    _make_coder_file_with_sources(
        tmp_path / "bob.ace",
        "Bob",
        [("B1", shared_uncoded_by_carol)],
        "Code",
        [(0, 0, 6)],
    )
    _make_coder_file_with_sources(
        tmp_path / "carol.ace",
        "Carol",
        [("C1", shared_uncoded_by_carol), ("C2", carol_unique)],
        "Code",
        [(1, 0, 6)],
    )

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")
    loader.add_file(tmp_path / "carol.ace")

    result = loader.validate()

    assert result["valid"] is False
    assert "coded by every coder" in result["error"]


def test_validate_no_shared_codes(tmp_path):
    text = "Same text for both."
    _make_coder_file(tmp_path / "alice.ace", "Alice", text, "CodeA", [(0, 4)])
    _make_coder_file(tmp_path / "bob.ace", "Bob", text, "CodeB", [(0, 4)])

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")

    result = loader.validate()
    assert result["valid"] is False
    assert "no codes" in result["error"].lower()


def test_build_dataset(tmp_path):
    text = "I enjoyed the group work sessions."
    _make_coder_file(tmp_path / "alice.ace", "Alice", text, "Positive", [(2, 9)])
    _make_coder_file(tmp_path / "bob.ace", "Bob", text, "Positive", [(2, 12)])

    loader = AgreementLoader()
    loader.add_file(tmp_path / "alice.ace")
    loader.add_file(tmp_path / "bob.ace")

    ds = loader.build_dataset()
    assert len(ds.sources) == 1
    assert len(ds.coders) == 2
    assert len(ds.codes) == 1
    assert ds.codes[0].name == "Positive"
    assert len(ds.annotations) == 2
    assert ds.sources[0].content_text == text
