"""Tests for annotation export with merge logic."""

import csv
import io
import json
import uuid

from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.source import add_source
from ace.models.codebook import add_code
from ace.models.annotation import add_annotation
from ace.services.exporter import export_annotations_csv, merge_adjacent_annotations


def test_annotation_export_preserves_exact_spans_and_all_merged_memos(tmp_db, tmp_path):
    conn = create_project(tmp_db, "export-test")
    text = "Hello.\n\n\nWorld."
    source_id = add_source(conn, "S1", text, "row")
    code_id = add_code(conn, "Theme", "#FF0000")
    coder_id = uuid.uuid4().hex
    conn.execute("INSERT INTO coder (id, name) VALUES (?, ?)", (coder_id, "Alice"))
    conn.commit()
    first_id = add_annotation(
        conn, source_id, coder_id, code_id, 0, 6, "Hello.", memo="first memo"
    )
    second_id = add_annotation(
        conn, source_id, coder_id, code_id, 9, 15, "World.", memo="second memo"
    )

    exact_csv = tmp_path / "exact.csv"
    assert export_annotations_csv(conn, exact_csv) == 2
    with exact_csv.open(newline="", encoding="utf-8") as stream:
        exact = list(csv.DictReader(stream))
    assert [(r["start_offset"], r["end_offset"], r["selected_text"], r["memo"])
            for r in exact] == [
        ("0", "6", "Hello.", "first memo"),
        ("9", "15", "World.", "second memo"),
    ]

    merged_csv = tmp_path / "merged.csv"
    assert export_annotations_csv(conn, merged_csv, merge_adjacent=True) == 1
    with merged_csv.open(newline="", encoding="utf-8") as stream:
        merged = list(csv.DictReader(stream))
    assert merged[0]["selected_text"] == text[0:15]
    assert (merged[0]["start_offset"], merged[0]["end_offset"]) == ("0", "15")
    assert json.loads(merged[0]["merged_memos_json"]) == [
        {"annotation_id": first_id, "memo": "first memo"},
        {"annotation_id": second_id, "memo": "second memo"},
    ]


def test_merged_export_groups_interleaved_codes_and_coders_by_id(tmp_db, tmp_path):
    conn = create_project(tmp_db, "export-test")
    source_id = add_source(conn, "S1", "A B C D", "row")
    first_code = add_code(conn, "First", "#FF0000")
    second_code = add_code(conn, "Second", "#00FF00")
    first_coder, second_coder = uuid.uuid4().hex, uuid.uuid4().hex
    conn.executemany("INSERT INTO coder (id, name) VALUES (?, ?)", [
        (first_coder, "Alice"), (second_coder, "Bob")
    ])
    conn.commit()
    for coder, code, start in [
        (first_coder, first_code, 0),
        (first_coder, second_code, 2),
        (second_coder, first_code, 2),
        (first_coder, first_code, 4),
        (first_coder, second_code, 6),
    ]:
        add_annotation(conn, source_id, coder, code, start, start + 1, "A B C D"[start])

    output = tmp_path / "merged.csv"
    assert export_annotations_csv(conn, output, merge_adjacent=True) == 3
    with output.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert [(r["coder_name"], r["code_name"], r["start_offset"],
             r["end_offset"], r["selected_text"]) for r in rows] == [
        ("Alice", "First", "0", "5", "A B C"),
        ("Bob", "First", "2", "3", "B"),
        ("Alice", "Second", "2", "7", "B C D"),
    ]


def test_annotation_download_defaults_to_exact_and_offers_merged(tmp_db):
    conn = create_project(tmp_db, "export-test")
    source_id = add_source(conn, "S1", "A B", "row")
    code_id = add_code(conn, "Theme", "#FF0000")
    coder_id = uuid.uuid4().hex
    conn.execute("INSERT INTO coder (id, name) VALUES (?, ?)", (coder_id, "Alice"))
    conn.commit()
    add_annotation(conn, source_id, coder_id, code_id, 0, 1, "A")
    add_annotation(conn, source_id, coder_id, code_id, 2, 3, "B")
    conn.close()

    app = create_app()
    with TestClient(app) as client:
        app.state.project_path = str(tmp_db)
        exact = client.get("/api/export/annotations")
        merged = client.get("/api/export/annotations?merge_adjacent=true")
    assert exact.status_code == merged.status_code == 200
    assert len(list(csv.DictReader(io.StringIO(exact.text)))) == 2
    merged_rows = list(csv.DictReader(io.StringIO(merged.text)))
    assert len(merged_rows) == 1
    assert merged_rows[0]["selected_text"] == "A B"
    assert "annotations_merged" in merged.headers["content-disposition"]


def test_merged_export_metadata_cannot_override_internal_ids(tmp_db, tmp_path):
    conn = create_project(tmp_db, "export-test")
    metadata = {
        "annotation_id": "metadata annotation",
        "coder_id": "metadata coder",
        "code_id": "metadata code",
        "source_sort_order": "metadata order",
    }
    source_id = add_source(conn, "S1", "A B", "row", metadata=metadata)
    code_id = add_code(conn, "Theme", "#FF0000")
    coder_id = uuid.uuid4().hex
    conn.execute("INSERT INTO coder (id, name) VALUES (?, ?)", (coder_id, "Alice"))
    conn.commit()
    add_annotation(conn, source_id, coder_id, code_id, 0, 1, "A")
    add_annotation(conn, source_id, coder_id, code_id, 2, 3, "B")
    other_source_id = add_source(conn, "S2", "C", "row")
    add_annotation(conn, other_source_id, coder_id, code_id, 0, 1, "C")

    output = tmp_path / "merged.csv"
    assert export_annotations_csv(conn, output, merge_adjacent=True) == 2
    with output.open(newline="", encoding="utf-8") as stream:
        row, other_row = list(csv.DictReader(stream))
    assert row["selected_text"] == "A B"
    assert {key: row[key] for key in metadata} == metadata
    assert len(json.loads(row["merged_memos_json"])) == 2
    assert all(other_row[key] == "" for key in metadata)


def test_export_annotations_csv(tmp_db, tmp_path):
    conn = create_project(tmp_db, "export-test")

    # 1 source with metadata
    source_id = add_source(
        conn,
        display_id="P001",
        content_text="The quick brown fox jumps over the lazy dog.",
        source_type="row",
        metadata={"age": 22},
    )

    # 1 code
    code_id = add_code(conn, name="Theme-A", colour="#FF0000")

    # 1 coder (manual insert)
    coder_id = uuid.uuid4().hex
    conn.execute("INSERT INTO coder (id, name) VALUES (?, ?)", (coder_id, "Alice"))
    conn.commit()

    # 1 annotation
    add_annotation(
        conn,
        source_id=source_id,
        coder_id=coder_id,
        code_id=code_id,
        start_offset=0,
        end_offset=9,
        selected_text="The quick",
        memo="interesting phrase",
    )

    output_csv = tmp_path / "export.csv"
    row_count = export_annotations_csv(conn, output_csv)
    assert row_count == 1

    with open(output_csv, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 1
    row = rows[0]
    assert row["source_id"] == source_id
    assert row["display_id"] == "P001"
    assert row["coder_name"] == "Alice"
    assert row["code_name"] == "Theme-A"
    assert row["selected_text"] == "The quick"
    assert row["start_offset"] == "0"
    assert row["end_offset"] == "9"
    assert row["memo"] == "interesting phrase"
    assert row["age"] == "22"

    conn.close()


def test_export_annotations_prefixes_metadata_columns_that_collide_with_fixed_fields(tmp_db, tmp_path):
    conn = create_project(tmp_db, "export-test")
    source_id = add_source(
        conn,
        display_id="P001",
        content_text="The quick brown fox.",
        source_type="row",
        metadata={
            "code_name": "metadata code",
            "memo": "metadata memo",
            "participant_group": "control",
        },
    )
    code_id = add_code(conn, name="Theme-A", colour="#FF0000")
    coder_id = uuid.uuid4().hex
    conn.execute("INSERT INTO coder (id, name) VALUES (?, ?)", (coder_id, "Alice"))
    conn.commit()
    add_annotation(
        conn,
        source_id=source_id,
        coder_id=coder_id,
        code_id=code_id,
        start_offset=0,
        end_offset=9,
        selected_text="The quick",
        memo="annotation memo",
    )

    output_csv = tmp_path / "export.csv"
    export_annotations_csv(conn, output_csv, merge_adjacent=False)

    with open(output_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert reader.fieldnames == [
        "source_id",
        "display_id",
        "coder_name",
        "code_name",
        "selected_text",
        "start_offset",
        "end_offset",
        "memo",
        "metadata_code_name",
        "metadata_memo",
        "participant_group",
    ]
    row = rows[0]
    assert row["code_name"] == "Theme-A"
    assert row["memo"] == "annotation memo"
    assert row["metadata_code_name"] == "metadata code"
    assert row["metadata_memo"] == "metadata memo"
    assert row["participant_group"] == "control"
    conn.close()


def test_export_annotations_preserves_non_fixed_metadata_names_before_prefixed_collisions(
    tmp_db, tmp_path
):
    conn = create_project(tmp_db, "export-test")
    source_id = add_source(
        conn,
        display_id="P001",
        content_text="The quick brown fox.",
        source_type="row",
        metadata={
            "memo": "metadata memo",
            "metadata_memo": "already prefixed import column",
        },
    )
    code_id = add_code(conn, name="Theme-A", colour="#FF0000")
    coder_id = uuid.uuid4().hex
    conn.execute("INSERT INTO coder (id, name) VALUES (?, ?)", (coder_id, "Alice"))
    conn.commit()
    add_annotation(
        conn,
        source_id=source_id,
        coder_id=coder_id,
        code_id=code_id,
        start_offset=0,
        end_offset=9,
        selected_text="The quick",
        memo="annotation memo",
    )

    output_csv = tmp_path / "export.csv"
    export_annotations_csv(conn, output_csv, merge_adjacent=False)

    with open(output_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert reader.fieldnames == [
        "source_id",
        "display_id",
        "coder_name",
        "code_name",
        "selected_text",
        "start_offset",
        "end_offset",
        "memo",
        "metadata_memo_2",
        "metadata_memo",
    ]
    row = rows[0]
    assert row["memo"] == "annotation memo"
    assert row["metadata_memo"] == "already prefixed import column"
    assert row["metadata_memo_2"] == "metadata memo"
    conn.close()


def test_merge_no_annotations():
    assert merge_adjacent_annotations([], "") == []


def test_merge_single_annotation_unchanged():
    anns = [{"annotation_id": "a1", "memo": None, "code_id": "c1", "start_offset": 0, "end_offset": 6, "selected_text": "Hello."}]
    result = merge_adjacent_annotations(anns, "Hello.")
    assert len(result) == 1
    assert result[0]["start_offset"] == 0
    assert result[0]["end_offset"] == 6


def test_merge_adjacent_same_code():
    anns = [
        {"annotation_id": "a1", "memo": None, "code_id": "c1", "start_offset": 0, "end_offset": 6, "selected_text": "First."},
        {"annotation_id": "a2", "memo": None, "code_id": "c1", "start_offset": 7, "end_offset": 14, "selected_text": "Second."},
    ]
    result = merge_adjacent_annotations(anns, "First. Second.")
    assert len(result) == 1
    assert result[0]["start_offset"] == 0
    assert result[0]["end_offset"] == 14
    assert result[0]["selected_text"] == "First. Second."


def test_merge_adjacent_different_code_not_merged():
    anns = [
        {"annotation_id": "a1", "memo": None, "code_id": "c1", "start_offset": 0, "end_offset": 6, "selected_text": "First."},
        {"annotation_id": "a2", "memo": None, "code_id": "c2", "start_offset": 7, "end_offset": 14, "selected_text": "Second."},
    ]
    result = merge_adjacent_annotations(anns, "First. Second.")
    assert len(result) == 2


def test_merge_non_adjacent_same_code_not_merged():
    anns = [
        {"annotation_id": "a1", "memo": None, "code_id": "c1", "start_offset": 0, "end_offset": 6, "selected_text": "First."},
        {"annotation_id": "a2", "memo": None, "code_id": "c1", "start_offset": 50, "end_offset": 56, "selected_text": "Third."},
    ]
    result = merge_adjacent_annotations(anns, "First." + " " * 44 + "Third.")
    assert len(result) == 2


def test_merge_three_adjacent():
    anns = [
        {"annotation_id": "a1", "memo": None, "code_id": "c1", "start_offset": 0, "end_offset": 4, "selected_text": "One."},
        {"annotation_id": "a2", "memo": None, "code_id": "c1", "start_offset": 5, "end_offset": 9, "selected_text": "Two."},
        {"annotation_id": "a3", "memo": None, "code_id": "c1", "start_offset": 10, "end_offset": 16, "selected_text": "Three."},
    ]
    result = merge_adjacent_annotations(anns, "One. Two. Three.")
    assert len(result) == 1
    assert result[0]["start_offset"] == 0
    assert result[0]["end_offset"] == 16
    assert result[0]["selected_text"] == "One. Two. Three."
