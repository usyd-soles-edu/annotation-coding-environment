"""Export annotations to CSV."""

import csv
import json
import sqlite3
import tempfile
from contextlib import closing
from itertools import groupby
from pathlib import Path

_IDENTITY = object()

_EXPORT_QUERY_BASE = """
SELECT
    a.id AS annotation_id,
    a.source_id,
    a.coder_id,
    a.code_id,
    s.sort_order AS source_sort_order,
    s.display_id,
    c.name  AS coder_name,
    cc.name AS code_name,
    a.selected_text,
    a.start_offset,
    a.end_offset,
    a.memo,
    s.metadata_json
FROM annotation a
JOIN source s        ON s.id  = a.source_id
JOIN coder c         ON c.id  = a.coder_id
JOIN codebook_code cc ON cc.id = a.code_id
WHERE a.deleted_at IS NULL
  AND cc.deleted_at IS NULL
"""

_EXPORT_QUERY = _EXPORT_QUERY_BASE + """
ORDER BY s.sort_order, s.id, a.start_offset, a.end_offset, a.coder_id, a.code_id, a.id
"""

_MERGE_QUERY = _EXPORT_QUERY_BASE + """
ORDER BY s.sort_order, s.id, a.coder_id, a.code_id, a.start_offset, a.end_offset, a.id
"""

_FIXED_COLUMNS = [
    "source_id",
    "display_id",
    "coder_name",
    "code_name",
    "selected_text",
    "start_offset",
    "end_offset",
    "memo",
]


def _unique_metadata_fieldname(base: str, used: set[str], reserved: set[str]) -> str:
    name = base
    suffix = 2
    while name in used or name in reserved:
        name = f"{base}_{suffix}"
        suffix += 1
    used.add(name)
    return name


def _metadata_fieldname(key: str, used: set[str], reserved: set[str], fixed: set[str]) -> str:
    if key in fixed:
        return _unique_metadata_fieldname(f"metadata_{key}", used, reserved)
    if key not in used:
        used.add(key)
        return key
    return _unique_metadata_fieldname(key, used, reserved)


def merge_adjacent_annotations(annotations: list[dict], source_text: str) -> list[dict]:
    """Merge adjacent same-code annotations into single entries.

    Annotations are considered adjacent if their offset ranges are within
    5 characters of each other (to account for whitespace/newlines between
    sentence boundaries). Must share the same code_id to be merged.

    Input annotations must share a source and coder, and be sorted by offset.
    Returns new list (does not mutate input).
    """
    if not annotations:
        return []

    result: list[dict] = []
    current = dict(annotations[0])
    current["selected_text"] = source_text[current["start_offset"]:current["end_offset"]]
    current["merged_memos_json"] = json.dumps([{
        "annotation_id": current.get(_IDENTITY, current)["annotation_id"],
        "memo": current["memo"]
    }], ensure_ascii=False)

    for ann in annotations[1:]:
        gap = ann["start_offset"] - current["end_offset"]
        if (ann.get(_IDENTITY, ann)["code_id"]
                == current.get(_IDENTITY, current)["code_id"] and 0 <= gap <= 5):
            current["end_offset"] = ann["end_offset"]
            current["selected_text"] = source_text[current["start_offset"]:current["end_offset"]]
            memos = json.loads(current["merged_memos_json"])
            memos.append({
                "annotation_id": ann.get(_IDENTITY, ann)["annotation_id"],
                "memo": ann["memo"],
            })
            current["merged_memos_json"] = json.dumps(memos, ensure_ascii=False)
        else:
            result.append(current)
            current = dict(ann)
            current["selected_text"] = source_text[current["start_offset"]:current["end_offset"]]
            current["merged_memos_json"] = json.dumps([{
                "annotation_id": current.get(_IDENTITY, current)["annotation_id"],
                "memo": current["memo"]
            }], ensure_ascii=False)

    result.append(current)
    return result


def _export_row(
    row: sqlite3.Row,
    meta_keys: list[str],
    meta_fieldnames: dict[str, str],
    *,
    include_identity: bool = False,
) -> dict:
    out = {col: row[col] for col in _FIXED_COLUMNS}
    raw = row["metadata_json"]
    if raw:
        meta = json.loads(raw)
        for key in meta_keys:
            out[meta_fieldnames[key]] = meta.get(key, "")
    if include_identity:
        # Object key cannot collide with a source metadata column.
        out[_IDENTITY] = {key: row[key] for key in (
            "annotation_id", "coder_id", "code_id", "source_sort_order"
        )}
    return out


def _iter_merged_export_rows(
    conn: sqlite3.Connection,
    meta_keys: list[str],
    meta_fieldnames: dict[str, str],
):
    """Merge one source/coder/code group at a time without loading all rows."""
    key = lambda row: (row["source_id"], row["coder_id"], row["code_id"])
    for (source_id, _coder_id, _code_id), group in groupby(
        conn.execute(_MERGE_QUERY), key=key
    ):
        source_row = conn.execute(
            "SELECT content_text FROM source_content WHERE source_id = ?", (source_id,)
        ).fetchone()
        if source_row is None:
            raise ValueError(f"Missing source text for {source_id}")
        source_text = source_row["content_text"]
        current = None
        memos = []
        for row in group:
            out = _export_row(row, meta_keys, meta_fieldnames, include_identity=True)
            memo = {"annotation_id": row["annotation_id"], "memo": row["memo"]}
            gap = out["start_offset"] - current["end_offset"] if current else None
            if gap is not None and 0 <= gap <= 5:
                current["end_offset"] = out["end_offset"]
                current["selected_text"] = source_text[
                    current["start_offset"]:current["end_offset"]
                ]
                memos.append(memo)
            else:
                if current is not None:
                    current["merged_memos_json"] = json.dumps(memos, ensure_ascii=False)
                    yield current
                current = out
                current["selected_text"] = source_text[
                    current["start_offset"]:current["end_offset"]
                ]
                memos = [memo]
        if current is not None:
            current["merged_memos_json"] = json.dumps(memos, ensure_ascii=False)
            yield current


def _export_annotations_csv_in_snapshot(
    conn: sqlite3.Connection,
    output_path: str | Path,
    merge_adjacent: bool = False,
) -> int:
    """Export non-deleted annotations with bounded Python-side row storage."""
    # Discover all metadata keys in their original source/annotation order.
    meta_keys: list[str] = []
    seen: set[str] = set()
    for row in conn.execute(_EXPORT_QUERY):
        raw = row["metadata_json"]
        if raw:
            for key in json.loads(raw):
                if key not in seen:
                    meta_keys.append(key)
                    seen.add(key)

    fixed_columns = _FIXED_COLUMNS + (["merged_memos_json"] if merge_adjacent else [])
    used_fieldnames = set(fixed_columns)
    reserved_meta_fieldnames = {key for key in meta_keys if key not in fixed_columns}
    meta_fieldnames = {
        key: _metadata_fieldname(key, used_fieldnames, reserved_meta_fieldnames, set(fixed_columns))
        for key in meta_keys
    }
    fieldnames = fixed_columns + [meta_fieldnames[key] for key in meta_keys]

    if not merge_adjacent:
        count = 0
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in conn.execute(_EXPORT_QUERY):
                out = _export_row(row, meta_keys, meta_fieldnames)
                writer.writerow({key: out.get(key, "") for key in fieldnames})
                count += 1
        return count

    # Grouping uses code order, while the CSV contract uses source position
    # order. Sort merged rows in a disk-backed temporary database.
    with tempfile.TemporaryDirectory(prefix="ace-export-") as temp_dir:
        with closing(sqlite3.connect(Path(temp_dir) / "merged.sqlite")) as sort_conn:
            sort_conn.execute("PRAGMA temp_store = FILE")
            sort_conn.execute("""
                CREATE TABLE export_rows (
                    source_sort_order INTEGER, source_id TEXT,
                    start_offset INTEGER, end_offset INTEGER,
                    coder_id TEXT, code_id TEXT, annotation_id TEXT,
                    payload TEXT NOT NULL
                )
            """)
            sort_conn.execute("""
                CREATE INDEX export_order ON export_rows (
                    source_sort_order, source_id, start_offset, end_offset,
                    coder_id, code_id, annotation_id
                )
            """)
            count = 0
            for out in _iter_merged_export_rows(conn, meta_keys, meta_fieldnames):
                identity = out[_IDENTITY]
                payload = json.dumps(
                    {key: out.get(key, "") for key in fieldnames}, ensure_ascii=False
                )
                sort_conn.execute(
                    "INSERT INTO export_rows VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (identity["source_sort_order"], out["source_id"],
                     out["start_offset"], out["end_offset"],
                     identity["coder_id"], identity["code_id"],
                     identity["annotation_id"], payload),
                )
                count += 1
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for (payload,) in sort_conn.execute(
                    "SELECT payload FROM export_rows ORDER BY "
                    "source_sort_order, source_id, start_offset, end_offset, "
                    "coder_id, code_id, annotation_id"
                ):
                    writer.writerow(json.loads(payload))
            return count


def export_annotations_csv(
    conn: sqlite3.Connection,
    output_path: str | Path,
    merge_adjacent: bool = False,
) -> int:
    """Export a consistent snapshot without materialising all annotations."""
    conn.execute("SAVEPOINT ace_export_snapshot")
    try:
        return _export_annotations_csv_in_snapshot(conn, output_path, merge_adjacent)
    finally:
        conn.execute("RELEASE SAVEPOINT ace_export_snapshot")
