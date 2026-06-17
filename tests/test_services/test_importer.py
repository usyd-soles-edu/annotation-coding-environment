import json

import openpyxl

from ace.db.connection import create_project
from ace.models.source import list_sources, get_source_content
from ace.services.importer import (
    import_csv,
    import_text_files,
    get_random_previews,
)


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
    count, _skipped = import_csv(conn, sample_csv, id_column="participant_id", text_columns=["reflection"])
    assert count == 3
    sources = list_sources(conn)
    assert len(sources) == 3
    assert sources[0]["display_id"] == "P001"
    assert sources[0]["source_type"] == "row"
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
    count, _skipped = import_csv(conn, csv_path, id_column="id", text_columns=["question1", "question2"])
    assert count == 2
    sources = list_sources(conn)
    assert len(sources) == 2
    assert [s["display_id"] for s in sources] == ["S1", "S2"]
    content = get_source_content(conn, sources[0]["id"])["content_text"]
    assert "question1" in content
    assert "Answer A" in content
    assert "question2" in content
    assert "Answer X" in content
    assert sources[0]["source_column"] is None
    conn.close()


def test_import_text_files(tmp_path, tmp_db):
    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "file1.txt").write_text("Hello world")
    (folder / "file2.txt").write_text("Goodbye world")
    conn = create_project(tmp_db, "test")
    count, _skipped = import_text_files(conn, folder)
    assert count == 2
    sources = list_sources(conn)
    assert len(sources) == 2
    display_ids = sorted(s["display_id"] for s in sources)
    assert display_ids == ["file1", "file2"]
    assert all(s["source_type"] == "file" for s in sources)
    conn.close()


def test_import_csv_two_rows(tmp_path):
    """Import a 2-row CSV and verify count and display_ids."""
    csv_path = tmp_path / "two.csv"
    csv_path.write_text("id,text\nA1,hello\nA2,world\n")
    db_path = tmp_path / "two.ace"
    conn = create_project(db_path, "test")
    count, _skipped = import_csv(conn, csv_path, id_column="id", text_columns=["text"])
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
    count, _skipped = import_csv(conn, csv_path, id_column="id", text_columns=["q1", "q2"])
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


def test_import_xlsx(tmp_path):
    """Create an .xlsx with openpyxl and verify import."""
    xlsx_path = tmp_path / "data.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["id", "response", "score"])
    ws.append(["X1", "Good stuff", 85])
    ws.append(["X2", "Needs work", 62])
    wb.save(xlsx_path)
    wb.close()

    db_path = tmp_path / "xlsx.ace"
    conn = create_project(db_path, "test")
    count, _skipped = import_csv(conn, xlsx_path, id_column="id", text_columns=["response"])
    assert count == 2
    sources = list_sources(conn)
    assert sources[0]["display_id"] == "X1"
    assert sources[1]["display_id"] == "X2"
    meta = json.loads(sources[0]["metadata_json"])
    assert meta["score"] == 85
    conn.close()


def test_import_text_files_two(tmp_path):
    """Create 2 .txt files in tmp_path and verify import."""
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "alpha.txt").write_text("Alpha content")
    (folder / "beta.txt").write_text("Beta content")

    db_path = tmp_path / "txt.ace"
    conn = create_project(db_path, "test")
    count, _skipped = import_text_files(conn, folder)
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
    count, _skipped = import_text_files(conn, folder)
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
        created, skipped = import_csv(
            conn, csv_path, id_column="id", text_columns=["text"]
        )
        assert (created, skipped) == (2, 0)

        # Re-import the same file: nothing new, both rows skipped.
        created, skipped = import_csv(
            conn, csv_path, id_column="id", text_columns=["text"]
        )
        assert (created, skipped) == (0, 2)

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
        created, skipped = import_csv(
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
        created, skipped = import_csv(
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


def test_import_text_files_skips_duplicate_display_ids(tmp_path):
    """Re-importing the same folder skips files whose stem already exists."""
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "one.txt").write_text("First document")
    (folder / "two.txt").write_text("Second document")
    db_path = tmp_path / "docs.ace"
    conn = create_project(db_path, "test")

    try:
        created, skipped = import_text_files(conn, folder)
        assert (created, skipped) == (2, 0)

        created, skipped = import_text_files(conn, folder)
        assert (created, skipped) == (0, 2)

        sources = {s["display_id"]: s for s in list_sources(conn)}
        assert set(sources) == {"one", "two"}
        assert (
            get_source_content(conn, sources["one"]["id"])["content_text"]
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
    count, _skipped = import_csv(conn, csv_path, id_column="id", text_columns=["text"])
    assert count == 1
    sources = list_sources(conn)
    assert sources[0]["display_id"] == "L1"
    content = get_source_content(conn, sources[0]["id"])
    assert content["content_text"] == "caf\u00e9"
    conn.close()
