import hashlib
import json

import pytest

from ace.db.connection import create_project
from ace.models.source import (
    add_source,
    decode_section_heading_spans,
    get_source,
    get_source_content,
    list_sources,
)


def test_add_source(tmp_db):
    conn = create_project(tmp_db, "Test")
    sid = add_source(conn, "S001", "Hello world", "file", filename="hello.txt")
    assert isinstance(sid, str)
    assert len(sid) == 32  # uuid4().hex
    row = conn.execute("SELECT * FROM source WHERE id = ?", (sid,)).fetchone()
    assert row is not None
    assert row["display_id"] == "S001"


def test_get_source_returns_metadata_without_content(tmp_db):
    conn = create_project(tmp_db, "Test")
    sid = add_source(conn, "S001", "Hello world", "file")
    row = get_source(conn, sid)
    assert row["display_id"] == "S001"
    assert "content_text" not in row.keys()


def test_get_source_content(tmp_db):
    conn = create_project(tmp_db, "Test")
    sid = add_source(conn, "S001", "Hello world", "file")
    row = get_source_content(conn, sid)
    assert row["content_text"] == "Hello world"
    assert row["section_headings_json"] is None


def test_list_sources_returns_all_ordered(tmp_db):
    conn = create_project(tmp_db, "Test")
    add_source(conn, "S001", "First", "file")
    add_source(conn, "S002", "Second", "file")
    add_source(conn, "S003", "Third", "file")
    rows = list_sources(conn)
    assert len(rows) == 3
    assert [r["display_id"] for r in rows] == ["S001", "S002", "S003"]


def test_content_hash_is_sha256(tmp_db):
    conn = create_project(tmp_db, "Test")
    content = "Hello world"
    sid = add_source(conn, "S001", content, "file")
    row = get_source_content(conn, sid)
    expected = hashlib.sha256(content.encode()).hexdigest()
    assert row["content_hash"] == expected
    assert len(row["content_hash"]) == 64


def test_section_heading_spans_round_trip_as_content_offsets(tmp_db):
    conn = create_project(tmp_db, "Test")
    content = "Question 1. Why?\nAn answer."
    spans = [(0, len("Question 1. Why?"))]

    sid = add_source(
        conn,
        "S001",
        content,
        "row",
        section_heading_spans=spans,
    )

    row = get_source_content(conn, sid)
    assert json.loads(row["section_headings_json"]) == [[0, 16]]
    decoded = decode_section_heading_spans(
        content, row["section_headings_json"]
    )
    assert decoded == ((0, 16),)
    assert [content[start:end] for start, end in decoded] == ["Question 1. Why?"]


@pytest.mark.parametrize(
    "stored",
    [
        "{",
        "{}",
        "[[0, 0]]",
        "[[-1, 2]]",
        "[[0, 4], [3, 5]]",
        "[[0, 99]]",
        "[[true, 2]]",
        "[[0, 2, 3]]",
    ],
)
def test_section_heading_decoder_fails_closed(stored):
    assert decode_section_heading_spans("abcdef", stored) == ()


def test_add_source_rejects_invalid_heading_spans_without_inserting(tmp_db):
    conn = create_project(tmp_db, "Test")

    with pytest.raises(ValueError, match="Section heading spans"):
        add_source(
            conn,
            "S001",
            "abcdef",
            "row",
            section_heading_spans=[(0, 4), (3, 5)],
        )

    assert list_sources(conn) == []
