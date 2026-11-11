"""Export annotations to CSV."""

import csv
import json
import sqlite3
from itertools import groupby
from pathlib import Path

_IDENTITY = object()

_EXPORT_QUERY = """
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
ORDER BY s.sort_order, s.id, a.start_offset, a.end_offset, a.coder_id, a.code_id, a.id
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


def export_annotations_csv(
    conn: sqlite3.Connection,
    output_path: str | Path,
    merge_adjacent: bool = False,
) -> int:
    """Export all non-deleted annotations to a CSV file.

    Returns the number of rows written (excluding the header).
    """
    rows = conn.execute(_EXPORT_QUERY).fetchall()

    # Discover all metadata keys across rows for flattening
    meta_keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
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

    # Convert rows to dicts for processing
    dicts: list[dict] = []
    for row in rows:
        out: dict[str, object] = {col: row[col] for col in _FIXED_COLUMNS}
        raw = row["metadata_json"]
        if raw:
            meta = json.loads(raw)
            for key in meta_keys:
                out[meta_fieldnames[key]] = meta.get(key, "")
        # Object key cannot collide with a source metadata column.
        out[_IDENTITY] = {key: row[key] for key in (
            "annotation_id", "coder_id", "code_id", "source_sort_order"
        )}
        dicts.append(out)

    if merge_adjacent:
        # Stable IDs keep namesakes distinct; sorting makes interleaved codes merge correctly.
        dicts.sort(key=lambda d: (
            d[_IDENTITY]["source_sort_order"], d["source_id"],
            d[_IDENTITY]["coder_id"], d[_IDENTITY]["code_id"],
            d["start_offset"], d["end_offset"], d[_IDENTITY]["annotation_id"]
        ))
        merged: list[dict] = []
        for (source_id, _coder_id, _code_id), group in groupby(
            dicts, key=lambda d: (
                d["source_id"], d[_IDENTITY]["coder_id"], d[_IDENTITY]["code_id"]
            )
        ):
            source_row = conn.execute(
                "SELECT content_text FROM source_content WHERE source_id = ?", (source_id,)
            ).fetchone()
            if source_row is None:
                raise ValueError(f"Missing source text for {source_id}")
            merged.extend(merge_adjacent_annotations(list(group), source_row["content_text"]))
        dicts = sorted(merged, key=lambda d: (
            d[_IDENTITY]["source_sort_order"], d["source_id"], d["start_offset"],
            d["end_offset"], d[_IDENTITY]["coder_id"], d[_IDENTITY]["code_id"],
            d[_IDENTITY]["annotation_id"]
        ))

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for out in dicts:
            writer.writerow({key: out.get(key, "") for key in fieldnames})

    return len(dicts)
