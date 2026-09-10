import hashlib
import json
import os
import re
import sqlite3
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import openpyxl
import pytest

import ace.services.importer as importer
from ace.db.connection import create_project
from ace.db.connection import open_project
from ace.models.source import (
    decode_section_heading_spans,
    get_source_content,
    list_sources,
)
from ace.services.importer import (
    build_folder_import_preview,
    import_csv,
    import_text_files,
    get_random_previews,
    preview_folder_import,
    read_tabular,
)
from ace.models.source import add_source


def test_get_random_previews_returns_up_to_five_files(tmp_path):
    """Random folder previews return a bounded file sample plus total count."""
    folder = tmp_path / "preview-sample"
    folder.mkdir()
    for i in range(7):
        (folder / f"doc-{i}.txt").write_text(f"Content {i}")

    total, previews = get_random_previews(folder)

    assert total == 7
    assert len(previews) == 5
    assert {preview["filename"] for preview in previews} <= {
        f"doc-{i}.txt" for i in range(7)
    }
    assert all(preview["snippet"].startswith("Content ") for preview in previews)
    assert all(preview["size_label"] == "9 B" for preview in previews)


def test_get_random_previews_empty_folder(tmp_path):
    """Empty folders return a zero total and no previews."""
    folder = tmp_path / "empty-preview-sample"
    folder.mkdir()

    total, previews = get_random_previews(folder)

    assert total == 0
    assert previews == []


def test_import_csv_creates_sources(tmp_db, sample_csv):
    conn = create_project(tmp_db, "test")
    count, _skipped, _ids = import_csv(conn, sample_csv, id_column="participant_id", text_columns=["reflection"])
    assert count == 3
    sources = list_sources(conn)
    assert len(sources) == 3
    assert sources[0]["display_id"] == "P001"
    assert sources[0]["source_type"] == "row"
    assert get_source_content(conn, sources[0]["id"])["section_headings_json"] is None
    conn.close()


def test_import_csv_stores_metadata(tmp_db, sample_csv):
    conn = create_project(tmp_db, "test")
    import_csv(conn, sample_csv, id_column="participant_id", text_columns=["reflection"])
    sources = list_sources(conn)
    meta = json.loads(sources[0]["metadata_json"])
    assert meta["age"] == 22
    conn.close()


def test_import_csv_content_hash(tmp_db, sample_csv):
    conn = create_project(tmp_db, "test")
    import_csv(conn, sample_csv, id_column="participant_id", text_columns=["reflection"])
    sources = list_sources(conn)
    content_row = get_source_content(conn, sources[0]["id"])
    content_hash = content_row["content_hash"]
    assert len(content_hash) == 64
    assert all(c in "0123456789abcdef" for c in content_hash)
    conn.close()


def test_import_csv_multi_column(tmp_path, tmp_db):
    csv_path = tmp_path / "multi.csv"
    csv_path.write_text(
        "id,question1,question2,group\n"
        "S1,Answer A,Answer X,control\n"
        "S2,Answer B,Answer Y,treatment\n"
    )
    conn = create_project(tmp_db, "test")
    count, _skipped, _ids = import_csv(conn, csv_path, id_column="id", text_columns=["question1", "question2"])
    assert count == 2
    sources = list_sources(conn)
    assert len(sources) == 2
    assert [s["display_id"] for s in sources] == ["S1", "S2"]
    content_row = get_source_content(conn, sources[0]["id"])
    expected_content = "question1\nAnswer A\n\nquestion2\nAnswer X"
    assert content_row["content_text"] == expected_content
    assert content_row["content_hash"] == hashlib.sha256(
        expected_content.encode()
    ).hexdigest()
    spans = decode_section_heading_spans(
        expected_content, content_row["section_headings_json"]
    )
    assert spans == ((0, 9), (20, 29))
    assert [expected_content[start:end] for start, end in spans] == [
        "question1",
        "question2",
    ]
    assert sources[0]["source_column"] is None
    conn.close()


def test_import_text_files(tmp_path, tmp_db):
    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "file1.txt").write_text("Hello world")
    (folder / "file2.txt").write_text("Goodbye world")
    conn = create_project(tmp_db, "test")
    count, _skipped, _ids = import_text_files(conn, folder)
    assert count == 2
    sources = list_sources(conn)
    assert len(sources) == 2
    display_ids = sorted(s["display_id"] for s in sources)
    assert display_ids == ["file1", "file2"]
    assert all(s["source_type"] == "file" for s in sources)
    assert all(
        get_source_content(conn, source["id"])["section_headings_json"] is None
        for source in sources
    )
    conn.close()


def test_import_csv_two_rows(tmp_path):
    """Import a 2-row CSV and verify count and display_ids."""
    csv_path = tmp_path / "two.csv"
    csv_path.write_text("id,text\nA1,hello\nA2,world\n")
    db_path = tmp_path / "two.ace"
    conn = create_project(db_path, "test")
    count, _skipped, _ids = import_csv(conn, csv_path, id_column="id", text_columns=["text"])
    assert count == 2
    sources = list_sources(conn)
    assert [s["display_id"] for s in sources] == ["A1", "A2"]
    conn.close()


def test_import_csv_multi_text_columns(tmp_path):
    """Multi-text-column import combines selected columns into each row source."""
    csv_path = tmp_path / "multi_text.csv"
    csv_path.write_text("id,q1,q2\nR1,ans1,ans2\nR2,ans3,ans4\n")
    db_path = tmp_path / "multi_text.ace"
    conn = create_project(db_path, "test")
    count, _skipped, _ids = import_csv(conn, csv_path, id_column="id", text_columns=["q1", "q2"])
    assert count == 2
    sources = list_sources(conn)
    assert [s["display_id"] for s in sources] == ["R1", "R2"]
    content = get_source_content(conn, sources[0]["id"])["content_text"]
    assert "q1" in content
    assert "ans1" in content
    assert "q2" in content
    assert "ans2" in content
    assert sources[0]["source_column"] is None
    conn.close()


def test_import_csv_skips_blank_text_rows(tmp_path):
    """Rows with no selected text are not imported as empty sources."""
    csv_path = tmp_path / "blank_rows.csv"
    csv_path.write_text("id,text\nblank,\nspaces,   \nfilled,hello\n")
    db_path = tmp_path / "blank_rows.ace"
    conn = create_project(db_path, "test")

    try:
        result = import_csv(conn, csv_path, id_column="id", text_columns=["text"])

        created, duplicate_skipped, ids = result
        assert (created, duplicate_skipped, result.empty_skipped) == (1, 0, 2)
        assert len(ids) == 1
        sources = list_sources(conn)
        assert [s["display_id"] for s in sources] == ["filled"]
        assert get_source_content(conn, sources[0]["id"])["content_text"] == "hello"
    finally:
        conn.close()


def test_import_csv_skips_multi_column_rows_when_all_selected_text_is_blank(tmp_path):
    """Multi-column labels must not make all-blank responses codable."""
    csv_path = tmp_path / "blank_multi_rows.csv"
    csv_path.write_text(
        "id,q1,q2\n"
        "blank,,   \n"
        "partial,answer,   \n"
        "filled,answer,more\n"
    )
    db_path = tmp_path / "blank_multi_rows.ace"
    conn = create_project(db_path, "test")

    try:
        result = import_csv(conn, csv_path, id_column="id", text_columns=["q1", "q2"])

        created, duplicate_skipped, _ids = result
        assert (created, duplicate_skipped, result.empty_skipped) == (2, 0, 1)
        sources = list_sources(conn)
        assert [s["display_id"] for s in sources] == ["partial", "filled"]
        content_row = get_source_content(conn, sources[0]["id"])
        content = content_row["content_text"]
        spans = decode_section_heading_spans(
            content, content_row["section_headings_json"]
        )
        assert [content[start:end] for start, end in spans] == ["q1", "q2"]
        assert content == "q1\nanswer\n\nq2\n   "
    finally:
        conn.close()


def test_import_xlsx(tmp_path):
    """Create an .xlsx with openpyxl and verify import."""
    xlsx_path = tmp_path / "data.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["id", "response", "follow_up", "score"])
    ws.append(["X1", "Good stuff", "Anything else?", 85])
    ws.append(["X2", "Needs work", "More detail.", 62])
    wb.save(xlsx_path)
    wb.close()

    db_path = tmp_path / "xlsx.ace"
    conn = create_project(db_path, "test")
    count, _skipped, _ids = import_csv(
        conn,
        xlsx_path,
        id_column="id",
        text_columns=["response", "follow_up"],
    )
    assert count == 2
    sources = list_sources(conn)
    assert sources[0]["display_id"] == "X1"
    assert sources[1]["display_id"] == "X2"
    meta = json.loads(sources[0]["metadata_json"])
    assert meta["score"] == 85
    content_row = get_source_content(conn, sources[0]["id"])
    spans = decode_section_heading_spans(
        content_row["content_text"], content_row["section_headings_json"]
    )
    assert [
        content_row["content_text"][start:end] for start, end in spans
    ] == ["response", "follow_up"]
    conn.close()


def test_read_tabular_reads_past_stale_dimension_metadata(tmp_path, tmp_db):
    """Stale <dimension> metadata must not hide columns; ragged rows keep keys."""
    xlsx_path = tmp_path / "stale-dim.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["id", "response", "score"])
    ws.append(["S1", "First response", 90])
    ws.append(["S2", "Second response", 75])
    # Ragged final row: "score" cell genuinely omitted from the sheet XML.
    ws.append(["S3", "Trailing omitted"])
    wb.save(xlsx_path)
    wb.close()

    # Rewrite only the worksheet XML dimension metadata to a falsely narrow
    # range, mimicking producers (e.g. Microsoft Forms) with stale dimensions.
    tampered_path = tmp_path / "stale-dim-tampered.xlsx"
    with zipfile.ZipFile(xlsx_path) as zin, zipfile.ZipFile(
        tampered_path, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "xl/worksheets/sheet1.xml":
                xml = data.decode("utf-8")
                xml, replaced = re.subn(
                    r'<dimension ref="[^"]+"\s*/>',
                    '<dimension ref="A1:A2"/>',
                    xml,
                    count=1,
                )
                assert replaced == 1
                data = xml.encode("utf-8")
            zout.writestr(item, data)

    rows, columns = read_tabular(tampered_path)
    assert columns == ["id", "response", "score"]
    assert rows == [
        {"id": "S1", "response": "First response", "score": 90},
        {"id": "S2", "response": "Second response", "score": 75},
        {"id": "S3", "response": "Trailing omitted", "score": None},
    ]

    conn = create_project(tmp_db, "test")
    count, _skipped, _ids = import_csv(
        conn, tampered_path, id_column="id", text_columns=["response"]
    )
    assert count == 3
    sources = list_sources(conn)
    assert [s["display_id"] for s in sources] == ["S1", "S2", "S3"]
    assert json.loads(sources[0]["metadata_json"])["score"] == 90
    assert json.loads(sources[2]["metadata_json"]) == {"score": None}
    conn.close()


def test_import_text_files_two(tmp_path):
    """Create 2 .txt files in tmp_path and verify import."""
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "alpha.txt").write_text("Alpha content")
    (folder / "beta.txt").write_text("Beta content")

    db_path = tmp_path / "txt.ace"
    conn = create_project(db_path, "test")
    count, _skipped, _ids = import_text_files(conn, folder)
    assert count == 2
    sources = list_sources(conn)
    display_ids = sorted(s["display_id"] for s in sources)
    assert display_ids == ["alpha", "beta"]
    content = get_source_content(conn, sources[0]["id"])
    assert content["content_text"] in ("Alpha content", "Beta content")
    conn.close()


def test_import_text_files_md(tmp_path):
    """Markdown files are imported alongside .txt files."""
    folder = tmp_path / "mixed"
    folder.mkdir()
    (folder / "notes.md").write_text("# Markdown content")
    (folder / "readme.txt").write_text("Plain text")
    (folder / "data.csv").write_text("id,text\n1,ignore")  # should be skipped

    db_path = tmp_path / "mixed.ace"
    conn = create_project(db_path, "test")
    count, _skipped, _ids = import_text_files(conn, folder)
    assert count == 2
    sources = list_sources(conn)
    display_ids = sorted(s["display_id"] for s in sources)
    assert display_ids == ["notes", "readme"]
    assert all(s["source_type"] == "file" for s in sources)
    conn.close()


def test_import_csv_skips_duplicate_display_ids(tmp_path):
    """Re-importing the same CSV skips rows whose display_id already exists."""
    csv_path = tmp_path / "dup.csv"
    csv_path.write_text("id,text\nA,first\nB,second\n")
    db_path = tmp_path / "dup.ace"
    conn = create_project(db_path, "test")

    try:
        # First import: both rows created, none skipped.
        created, skipped, ids = import_csv(
            conn, csv_path, id_column="id", text_columns=["text"]
        )
        assert (created, skipped) == (2, 0)
        assert len(ids) == 2
        # Each created id resolves to a real source.
        by_id = {s["id"]: s for s in list_sources(conn)}
        assert {by_id[i]["display_id"] for i in ids} == {"A", "B"}

        # Re-import the same file: nothing new, both rows skipped.
        created, skipped, ids = import_csv(
            conn, csv_path, id_column="id", text_columns=["text"]
        )
        assert (created, skipped) == (0, 2)
        assert ids == []

        # No duplicate rows, original text intact.
        sources = list_sources(conn)
        assert len(sources) == 2
        by_id = {s["display_id"]: s for s in sources}
        assert by_id["A"]["display_id"] == "A"
        assert by_id["B"]["display_id"] == "B"
        assert get_source_content(conn, by_id["A"]["id"])["content_text"] == "first"
        assert get_source_content(conn, by_id["B"]["id"])["content_text"] == "second"
    finally:
        conn.close()


def test_import_csv_skips_only_existing_rows(tmp_path):
    """A mixed re-import (some new, some existing) returns (new, dup) counts."""
    csv_a = tmp_path / "a.csv"
    csv_a.write_text("id,text\nA,first\nB,second\n")
    csv_b = tmp_path / "b.csv"
    csv_b.write_text("id,text\nB,second-updated\nC,third\n")
    db_path = tmp_path / "mixed.ace"
    conn = create_project(db_path, "test")

    try:
        import_csv(conn, csv_a, id_column="id", text_columns=["text"])
        created, skipped, _ids = import_csv(
            conn, csv_b, id_column="id", text_columns=["text"]
        )

        assert (created, skipped) == (1, 1)

        # Existing row's text is preserved (not overwritten by the new file).
        sources = {s["display_id"]: s for s in list_sources(conn)}
        assert set(sources) == {"A", "B", "C"}
        assert get_source_content(conn, sources["B"]["id"])["content_text"] == "second"
        assert get_source_content(conn, sources["C"]["id"])["content_text"] == "third"
    finally:
        conn.close()


def test_import_csv_skips_intra_file_duplicate_ids(tmp_path):
    """Two rows sharing the same id in one file import as a single source.

    The second intra-file row is counted as a skip (``existing`` is updated
    mid-loop, so the duplicate is detected against the just-inserted row) and
    the first row's text is preserved.
    """
    csv_path = tmp_path / "intra.csv"
    csv_path.write_text("id,text\nA,first\nA,second\n")
    db_path = tmp_path / "intra.ace"
    conn = create_project(db_path, "test")

    try:
        created, skipped, _ids = import_csv(
            conn, csv_path, id_column="id", text_columns=["text"]
        )

        assert (created, skipped) == (1, 1)

        # Exactly one source exists, with the first row's text preserved.
        sources = list_sources(conn)
        assert len(sources) == 1
        assert sources[0]["display_id"] == "A"
        assert get_source_content(conn, sources[0]["id"])["content_text"] == "first"
    finally:
        conn.close()


def test_import_csv_rolls_back_batch_when_later_source_fails(tmp_path):
    """A failed row must not leave earlier rows from the batch persisted."""
    csv_path = tmp_path / "rollback.csv"
    csv_path.write_text("id,text\nA,first\nB,second\n", encoding="utf-8")
    conn = create_project(tmp_path / "rollback.ace", "test")
    conn.execute(
        """
        CREATE TRIGGER fail_second_import_source
        BEFORE INSERT ON source
        WHEN NEW.display_id = 'B'
        BEGIN
            SELECT RAISE(ABORT, 'injected import failure');
        END
        """
    )
    conn.commit()

    try:
        with pytest.raises(Exception, match="injected import failure"):
            import_csv(conn, csv_path, id_column="id", text_columns=["text"])

        assert list_sources(conn) == []
        assert not conn.in_transaction
    finally:
        conn.close()


@pytest.mark.parametrize("display_id", [None, "", "   "])
def test_import_csv_rejects_blank_source_labels(tmp_path, display_id):
    """Missing and whitespace-only labels must fail before any rows are inserted."""
    conn = create_project(tmp_path / "blank-label.ace", "test")
    tabular_data = ([{"id": display_id, "text": "hello"}], ["id", "text"])

    try:
        with pytest.raises(ValueError, match="Source labels cannot be blank"):
            import_csv(
                conn,
                tmp_path / "blank-label.csv",
                id_column="id",
                text_columns=["text"],
                tabular_data=tabular_data,
            )

        assert list_sources(conn) == []
    finally:
        conn.close()


def test_import_csv_skips_completely_blank_rows(tmp_path):
    """A blank trailing spreadsheet row remains an empty skipped source."""
    conn = create_project(tmp_path / "blank-row.ace", "test")
    tabular_data = (
        [
            {"id": "A", "text": "hello"},
            {"id": None, "text": None},
        ],
        ["id", "text"],
    )

    try:
        result = import_csv(
            conn,
            tmp_path / "blank-row.xlsx",
            id_column="id",
            text_columns=["text"],
            tabular_data=tabular_data,
        )

        assert (result.created, result.duplicate_skipped, result.empty_skipped) == (
            1,
            0,
            1,
        )
        assert [source["display_id"] for source in list_sources(conn)] == ["A"]
    finally:
        conn.close()


def test_import_csv_serialises_duplicate_checks_across_connections(
    tmp_path, monkeypatch
):
    """Concurrent batches must agree which one created a shared label."""
    csv_path = tmp_path / "concurrent.csv"
    csv_path.write_text("id,text\nA,hello\n", encoding="utf-8")
    db_path = tmp_path / "concurrent.ace"
    conn = create_project(db_path, "test")
    conn.close()

    barrier = threading.Barrier(2)
    original_insert_candidates = importer._insert_candidates

    def synchronised_insert(conn, candidates, empty_skipped=0):
        barrier.wait(timeout=5)
        return original_insert_candidates(
            conn, candidates, empty_skipped=empty_skipped
        )

    monkeypatch.setattr(importer, "_insert_candidates", synchronised_insert)

    def run_import():
        worker_conn = open_project(db_path)
        try:
            return import_csv(
                worker_conn,
                csv_path,
                id_column="id",
                text_columns=["text"],
            )
        finally:
            worker_conn.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run_import) for _ in range(2)]
        imported = [future.result(timeout=10) for future in futures]

    assert sorted(
        (
            result.created,
            result.duplicate_skipped,
            len(result.created_ids),
            result.empty_skipped,
        )
        for result in imported
    ) == [(0, 1, 0, 0), (1, 0, 1, 0)]

    conn = open_project(db_path)
    try:
        assert [source["display_id"] for source in list_sources(conn)] == ["A"]
    finally:
        conn.close()


def test_import_csv_does_not_rollback_an_existing_transaction(tmp_path):
    """Reject nested imports without rolling back caller-owned changes."""
    csv_path = tmp_path / "nested.csv"
    csv_path.write_text("id,text\nA,hello\n", encoding="utf-8")
    conn = create_project(tmp_path / "nested.ace", "test")
    conn.execute("UPDATE project SET name = 'Uncommitted'")

    try:
        with pytest.raises(
            sqlite3.OperationalError,
            match="Cannot import sources inside an existing transaction",
        ):
            import_csv(conn, csv_path, id_column="id", text_columns=["text"])

        assert conn.in_transaction
        assert conn.execute("SELECT name FROM project").fetchone()[0] == "Uncommitted"
        assert list_sources(conn) == []
    finally:
        conn.rollback()
        conn.close()


def test_import_text_files_skips_duplicate_display_ids(tmp_path):
    """Re-importing the same folder skips files whose stem already exists."""
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "one.txt").write_text("First document")
    (folder / "two.txt").write_text("Second document")
    db_path = tmp_path / "docs.ace"
    conn = create_project(db_path, "test")

    try:
        created, skipped, ids = import_text_files(conn, folder)
        assert (created, skipped) == (2, 0)
        # The created ids map to the imported files in order.
        by_id = {s["id"]: s for s in list_sources(conn)}
        assert [by_id[i]["display_id"] for i in ids] == ["one", "two"]

        created, skipped, ids = import_text_files(conn, folder)
        assert (created, skipped) == (0, 2)
        assert ids == []

        sources = {s["display_id"]: s for s in list_sources(conn)}
        assert set(sources) == {"one", "two"}
        assert (
            get_source_content(conn, sources["one"]["id"])["content_text"]
            == "First document"
        )
    finally:
        conn.close()


def test_import_text_files_rolls_back_batch_when_later_source_fails(tmp_path):
    """A failed file must not leave earlier files from the batch persisted."""
    folder = tmp_path / "rollback-files"
    folder.mkdir()
    (folder / "alpha.txt").write_text("Alpha", encoding="utf-8")
    (folder / "beta.txt").write_text("Beta", encoding="utf-8")
    conn = create_project(tmp_path / "rollback-files.ace", "test")
    conn.execute(
        """
        CREATE TRIGGER fail_second_import_file
        BEFORE INSERT ON source
        WHEN NEW.display_id = 'beta'
        BEGIN
            SELECT RAISE(ABORT, 'injected import failure');
        END
        """
    )
    conn.commit()

    try:
        with pytest.raises(Exception, match="injected import failure"):
            import_text_files(conn, folder)

        assert list_sources(conn) == []
        assert not conn.in_transaction
    finally:
        conn.close()


def test_import_text_files_skips_empty_files(tmp_path):
    """Empty and whitespace-only text files are skipped, not imported."""
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "empty.txt").write_text("")
    (folder / "spaces.md").write_text("   \n")
    (folder / "filled.txt").write_text("First document")
    db_path = tmp_path / "docs.ace"
    conn = create_project(db_path, "test")

    try:
        result = import_text_files(conn, folder)

        created, duplicate_skipped, ids = result
        assert (created, duplicate_skipped, result.empty_skipped) == (1, 0, 2)
        assert len(ids) == 1
        sources = list_sources(conn)
        assert [s["display_id"] for s in sources] == ["filled"]
        assert (
            get_source_content(conn, sources[0]["id"])["content_text"]
            == "First document"
        )
    finally:
        conn.close()


def test_import_csv_latin1(tmp_path):
    """Write bytes with a latin-1 char and verify decoding fallback."""
    csv_path = tmp_path / "latin1.csv"
    # \xe9 is 'e' with acute accent in latin-1, invalid in utf-8
    csv_path.write_bytes(b"id,text\nL1,caf\xe9\n")

    db_path = tmp_path / "latin1.ace"
    conn = create_project(db_path, "test")
    count, _skipped, _ids = import_csv(conn, csv_path, id_column="id", text_columns=["text"])
    assert count == 1
    sources = list_sources(conn)
    assert sources[0]["display_id"] == "L1"
    content = get_source_content(conn, sources[0]["id"])
    assert content["content_text"] == "caf\u00e9"
    conn.close()


# ---------------------------------------------------------------------------
# Folder import preview seams: recursive scan, classification, manifest.
#
# These cover the read-only preview contract only. Confirmation/insertion
# behaviour is covered separately once the confirmation seam exists.
# ---------------------------------------------------------------------------


def _build_folder_import_tree(tmp_path: Path) -> Path:
    """Create the standard preview fixture tree used by classification tests.

    Examined regular candidates: top.txt, nested/kept.md, image.png.
    Everything else (hidden file, hidden directory subtree, plain directory,
    directory carrying a supported suffix) must be rejected before totals.
    """
    folder = tmp_path / "import-tree"
    folder.mkdir()
    (folder / "top.txt").write_text("Top-level text", encoding="utf-8")
    nested = folder / "nested"
    nested.mkdir()
    (nested / "kept.md").write_text("# Kept markdown", encoding="utf-8")
    (folder / "image.png").write_bytes(b"\x89PNG fake image bytes")
    (folder / ".hidden.txt").write_text("hidden top-level", encoding="utf-8")
    hidden_dir = folder / ".hidden-dir"
    hidden_dir.mkdir()
    (hidden_dir / "inside.md").write_text("hidden nested", encoding="utf-8")
    (folder / "plain-dir").mkdir()
    (folder / "folder.txt").mkdir()  # directory carrying a supported suffix
    return folder


def _add_posix_non_regular_entries(folder: Path) -> None:
    """Add a file symlink, a directory symlink, and a FIFO under ``folder``."""
    (folder / "link-to-top.txt").symlink_to(folder / "top.txt")
    (folder / "linked-dir").symlink_to(folder / "nested")
    os.mkfifo(folder / "pipe.txt")


def test_folder_import_recursive_discovers_nested_supported_files(tmp_path):
    """Nested TXT/MD candidates are found recursively in deterministic order."""
    folder = _build_folder_import_tree(tmp_path)

    preview = build_folder_import_preview(folder, existing_ids=set())

    ready_entries = preview.manifest.ready_entries
    assert [entry.relative_path for entry in ready_entries] == [
        "nested/kept.md",
        "top.txt",
    ]
    assert [entry.display_id for entry in ready_entries] == ["kept", "top"]
    contents = {entry.display_id: entry.content_text for entry in ready_entries}
    assert contents["top"] == "Top-level text"
    assert contents["kept"] == "# Kept markdown"
    assert all(entry.fingerprint is not None for entry in ready_entries)


def test_folder_import_classification_excludes_hidden_paths_and_directories(tmp_path):
    """Hidden files, hidden subtrees, and directories never become entries."""
    folder = _build_folder_import_tree(tmp_path)

    preview = build_folder_import_preview(folder, existing_ids=set())

    all_paths = {entry.relative_path for entry in preview.manifest.entries}
    assert ".hidden.txt" not in all_paths
    assert ".hidden-dir/inside.md" not in all_paths
    assert "plain-dir" not in all_paths
    assert "folder.txt" not in all_paths  # directory despite supported suffix
    unsupported = [
        entry
        for entry in preview.manifest.entries
        if entry.category == "unsupported"
    ]
    assert [entry.relative_path for entry in unsupported] == ["image.png"]


@pytest.mark.skipif(os.name != "posix", reason="symlinks and FIFOs require POSIX")
def test_folder_import_classification_treats_non_regular_entries_as_excluded(tmp_path):
    """Symlinks (even to supported files) and FIFOs are not candidates."""
    folder = _build_folder_import_tree(tmp_path)
    _add_posix_non_regular_entries(folder)

    preview = build_folder_import_preview(folder, existing_ids=set())

    all_paths = {entry.relative_path for entry in preview.manifest.entries}
    assert "link-to-top.txt" not in all_paths
    assert "pipe.txt" not in all_paths
    # The symlinked directory must not be recursed into: kept.md appears once.
    kept_paths = [
        entry.relative_path
        for entry in preview.manifest.entries
        if entry.display_id == "kept"
    ]
    assert kept_paths == ["nested/kept.md"]


def test_folder_import_hidden_paths_do_not_affect_totals(tmp_path):
    """Totals cover examined regular files only; hidden paths add nothing."""
    folder = _build_folder_import_tree(tmp_path)

    preview = build_folder_import_preview(folder, existing_ids=set())

    assert preview.total_files == 3  # top.txt, nested/kept.md, image.png
    assert preview.counts == {
        "supported-ready": 2,
        "unsupported": 1,
        "unreadable": 0,
        "empty": 0,
        "duplicate": 0,
    }


def test_folder_import_classification_counts_each_regular_file_once(tmp_path):
    """Every examined regular file lands in exactly one of the five categories."""
    folder = _build_folder_import_tree(tmp_path)

    preview = build_folder_import_preview(folder, existing_ids={"kept"})

    assert sum(preview.counts.values()) == preview.total_files
    assert preview.counts == {
        "supported-ready": 1,  # top.txt
        "unsupported": 1,  # image.png
        "unreadable": 0,
        "empty": 0,
        "duplicate": 1,  # nested/kept.md matches the supplied existing label
    }
    categories = {
        entry.relative_path: entry.category for entry in preview.manifest.entries
    }
    assert categories == {
        "top.txt": "supported-ready",
        "nested/kept.md": "duplicate",
        "image.png": "unsupported",
    }


def test_folder_import_classification_reads_utf8_empty_and_unreadable(
    tmp_path, monkeypatch
):
    """Reads use UTF-8; read/decode failures classify without raising."""
    folder = tmp_path / "readability"
    folder.mkdir()
    (folder / "good.txt").write_text("caf\u00e9 unicode", encoding="utf-8")
    (folder / "empty.txt").write_text("", encoding="utf-8")
    (folder / "blank.md").write_text("   \n\t", encoding="utf-8")
    (folder / "binary.md").write_bytes(b"\xff\xfe\x00bad")

    preview = build_folder_import_preview(folder, existing_ids=set())

    by_path = {entry.relative_path: entry for entry in preview.manifest.entries}
    assert by_path["good.txt"].category == "supported-ready"
    assert by_path["good.txt"].content_text == "caf\u00e9 unicode"
    assert by_path["empty.txt"].category == "empty"
    assert by_path["blank.md"].category == "empty"
    assert by_path["binary.md"].category == "unreadable"

    # Ready fingerprints pin content bytes plus immutable identity metadata.
    good_path = folder / "good.txt"
    fingerprint = by_path["good.txt"].fingerprint
    assert fingerprint is not None
    assert fingerprint.content_sha256 == hashlib.sha256(
        good_path.read_bytes()
    ).hexdigest()
    assert fingerprint.size == good_path.stat().st_size
    assert fingerprint.mtime_ns == good_path.stat().st_mtime_ns
    assert fingerprint.device == good_path.stat().st_dev
    assert fingerprint.inode == good_path.stat().st_ino

    # A read failure after listing (permissions revoked, etc.) stays inside
    # the preview: every entry classifies as unreadable, none raises.
    def broken_reader(path):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(importer, "_read_folder_file_bytes", broken_reader)
    failed_preview = build_folder_import_preview(folder, existing_ids=set())
    assert {entry.category for entry in failed_preview.manifest.entries} == {
        "unreadable"
    }
    assert all(entry.fingerprint is None for entry in failed_preview.manifest.entries)


def test_folder_import_in_batch_display_id_collisions_classify_one_ready(tmp_path):
    """Same display ID from several files yields one ready entry, rest duplicate.

    Mirrors confirmed import accounting (``_insert_candidates``): the first
    entry per label in deterministic relative-path order classifies ready and
    claims the label; later collisions classify duplicate even when empty, and
    empty entries claim nothing.
    """
    folder = tmp_path / "collide"
    (folder / "docs").mkdir(parents=True)
    (folder / "deep" / "notes").mkdir(parents=True)
    (folder / "report.md").write_text("root report", encoding="utf-8")
    (folder / "docs" / "report.txt").write_text("nested report", encoding="utf-8")
    (folder / "deep" / "notes" / "report.md").write_text(
        "deep report", encoding="utf-8"
    )
    # Extension variants collide on the same stem.
    (folder / "guide.TXT").write_text("upper guide", encoding="utf-8")
    (folder / "guide.md").write_text("lower guide", encoding="utf-8")
    # A ready file claims its label: the later empty twin is a duplicate.
    (folder / "taken.md").write_text("taken content", encoding="utf-8")
    (folder / "taken.txt").write_text("", encoding="utf-8")
    # An empty file claims nothing: the later filled twin stays ready.
    (folder / "dup.md").write_text("", encoding="utf-8")
    (folder / "dup.txt").write_text("filled", encoding="utf-8")
    (folder / "blank.md").write_text("", encoding="utf-8")
    (folder / "blank.txt").write_text("   \n", encoding="utf-8")
    (folder / "unique.txt").write_text("unique", encoding="utf-8")

    preview = build_folder_import_preview(folder, existing_ids=set())

    categories = {
        entry.relative_path: entry.category for entry in preview.manifest.entries
    }
    assert categories == {
        "blank.md": "empty",
        "blank.txt": "empty",
        "deep/notes/report.md": "supported-ready",
        "docs/report.txt": "duplicate",
        "dup.md": "empty",
        "dup.txt": "supported-ready",
        "guide.TXT": "supported-ready",
        "guide.md": "duplicate",
        "report.md": "duplicate",
        "taken.md": "supported-ready",
        "taken.txt": "duplicate",
        "unique.txt": "supported-ready",
    }
    assert preview.counts == {
        "supported-ready": 5,
        "unsupported": 0,
        "unreadable": 0,
        "empty": 3,
        "duplicate": 4,
    }
    assert sum(preview.counts.values()) == preview.total_files == 12


def test_folder_import_preview_counts_are_immutable_and_derived(tmp_path):
    """Counts derive from the immutable entries and reject external mutation."""
    folder = _build_folder_import_tree(tmp_path)

    preview = build_folder_import_preview(folder, existing_ids=set())

    assert preview.counts == preview.manifest.counts
    assert preview.total_files == len(preview.manifest.entries) == 3
    with pytest.raises(TypeError):
        preview.counts["supported-ready"] = 99
    with pytest.raises(TypeError):
        preview.manifest.counts["unsupported"] = 99


def test_folder_import_fingerprint_includes_filesystem_identity(tmp_path):
    """Fingerprints pin device/inode alongside content, size, and mtime."""
    folder = tmp_path / "fingerprint"
    folder.mkdir()
    path = folder / "note.txt"
    path.write_text("original", encoding="utf-8")

    preview = build_folder_import_preview(folder, existing_ids=set())
    fingerprint = preview.manifest.ready_entries[0].fingerprint

    stat_result = path.lstat()
    assert fingerprint is not None
    assert fingerprint.content_sha256 == hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    assert fingerprint.size == stat_result.st_size
    assert fingerprint.mtime_ns == stat_result.st_mtime_ns
    assert fingerprint.device == stat_result.st_dev
    assert fingerprint.inode == stat_result.st_ino
    # An untouched file keeps a stable fingerprint across previews.
    again = build_folder_import_preview(folder, existing_ids=set())
    assert again.manifest.ready_entries[0].fingerprint == fingerprint


def test_folder_import_fingerprint_detects_metadata_preserving_replacement(tmp_path):
    """Replacement is detected even when size and mtime are preserved.

    Two replacement shapes must both change the fingerprint: an in-place
    rewrite with same-length bytes and a restored mtime (content changes), and
    identical content moved into place under a fresh inode (identity changes).
    """
    folder = tmp_path / "replacement"
    folder.mkdir()
    path = folder / "note.txt"
    path.write_bytes(b"original-bytes")

    fingerprint = build_folder_import_preview(
        folder, existing_ids=set()
    ).manifest.ready_entries[0].fingerprint
    assert fingerprint is not None

    # In-place same-length rewrite with the original mtime restored.
    original_stat = path.lstat()
    path.write_bytes(b"REPLACED-bytes")
    os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
    rewritten = build_folder_import_preview(folder, existing_ids=set())
    rewritten_fp = rewritten.manifest.ready_entries[0].fingerprint
    assert rewritten_fp is not None
    assert rewritten_fp.size == fingerprint.size
    assert rewritten_fp.mtime_ns == fingerprint.mtime_ns
    assert rewritten_fp.content_sha256 != fingerprint.content_sha256
    assert rewritten_fp != fingerprint

    # Identical content restored via a fresh inode, mtime restored again.
    fresh_stat = path.lstat()
    swap = folder / "swap.tmp"
    swap.write_bytes(b"original-bytes")
    os.replace(swap, path)
    os.utime(path, ns=(fresh_stat.st_atime_ns, fresh_stat.st_mtime_ns))
    swapped_stat = path.lstat()
    if swapped_stat.st_ino == fresh_stat.st_ino:
        pytest.skip("filesystem reused the inode; identity change unobservable")
    restored = build_folder_import_preview(folder, existing_ids=set())
    restored_fp = restored.manifest.ready_entries[0].fingerprint
    assert restored_fp is not None
    assert restored_fp.content_sha256 == fingerprint.content_sha256
    assert restored_fp.size == fingerprint.size
    assert restored_fp.mtime_ns == fingerprint.mtime_ns
    assert restored_fp.inode != fingerprint.inode
    assert restored_fp != fingerprint


def test_folder_import_classification_recognises_uppercase_suffixes(tmp_path):
    """Suffix matching is case-insensitive: .TXT and .MD are supported."""
    folder = tmp_path / "uppercase"
    folder.mkdir()
    (folder / "UPPER.TXT").write_text("Upper", encoding="utf-8")
    (folder / "Notes.MD").write_text("# Notes", encoding="utf-8")
    (folder / "photo.PNG").write_bytes(b"\x89PNG")

    preview = build_folder_import_preview(folder, existing_ids=set())

    assert [entry.display_id for entry in preview.manifest.ready_entries] == [
        "Notes",
        "UPPER",
    ]
    assert preview.counts["unsupported"] == 1


def test_folder_import_preview_performs_no_database_writes(tmp_path, tmp_db):
    """Previewing must not create sources or leave a transaction open."""
    folder = _build_folder_import_tree(tmp_path)
    conn = create_project(tmp_path / "preview.ace", "test")

    try:
        before = list_sources(conn)
        preview = preview_folder_import(conn, folder)

        assert list_sources(conn) == before
        assert not conn.in_transaction
        by_path = {entry.relative_path: entry for entry in preview.manifest.entries}
        assert by_path["nested/kept.md"].category == "supported-ready"
    finally:
        conn.close()


def test_folder_import_duplicate_against_live_database_labels(tmp_path, tmp_db):
    """Duplicate classification reads current labels without mutating them."""
    folder = tmp_path / "dup-tree"
    folder.mkdir()
    (folder / "new.txt").write_text("New content", encoding="utf-8")
    (folder / "taken.md").write_text("Taken content", encoding="utf-8")
    conn = create_project(tmp_path / "dup.ace", "test")

    try:
        add_source(
            conn,
            display_id="taken",
            content_text="Existing source",
            source_type="file",
        )

        preview = preview_folder_import(conn, folder)

        by_path = {entry.relative_path: entry for entry in preview.manifest.entries}
        assert by_path["taken.md"].category == "duplicate"
        assert by_path["new.txt"].category == "supported-ready"
        assert preview.counts["duplicate"] == 1
        assert len(list_sources(conn)) == 1  # preview added nothing
    finally:
        conn.close()
