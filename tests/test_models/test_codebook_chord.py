"""Tests for chord computation in list_codes_with_tree.

Chord shortcuts are derived at read time from the position rank of each code,
not stored in the database. The first SINGLE_KEY_LIMIT codes get a NULL chord
(they use single-key shortcuts 1-9, 0, a-y); the rest get a 2-letter chord.
"""

from ace.db.connection import open_project, create_project
from ace.models.codebook import (
    SINGLE_KEY_LIMIT,
    add_code,
    list_codes_with_tree,
    reorder_codes,
)


def _fresh_project(tmp_path):
    path = tmp_path / "fresh.ace"
    create_project(str(path), "Test")
    return str(path)


def _codes(tree):
    return [r for r in tree if r["kind"] == "code"]


def test_first_thirty_one_codes_have_null_chord(tmp_path):
    path = _fresh_project(tmp_path)
    conn = open_project(path)
    try:
        for i in range(SINGLE_KEY_LIMIT):
            add_code(conn, f"Code {i:02d}", "#A91818")
        codes = _codes(list_codes_with_tree(conn))
        assert all(c["chord"] is None for c in codes)
    finally:
        conn.close()


def test_thirty_second_code_gets_chord(tmp_path):
    path = _fresh_project(tmp_path)
    conn = open_project(path)
    try:
        for i in range(SINGLE_KEY_LIMIT):
            add_code(conn, f"Filler {i:02d}", "#A91818")
        cid = add_code(conn, "Privacy of data", "#557FE6")
        codes = _codes(list_codes_with_tree(conn))
        assert all(c["chord"] is None for c in codes[:SINGLE_KEY_LIMIT])
        thirty_second = next(c for c in codes if c["id"] == cid)
        assert thirty_second["chord"] == "pd"
    finally:
        conn.close()


def test_chord_tail_is_complete_and_unique(tmp_path):
    path = _fresh_project(tmp_path)
    conn = open_project(path)
    try:
        for i in range(35):
            add_code(conn, f"Code {i:02d}", "#A91818")
        codes = _codes(list_codes_with_tree(conn))

        assert all(c["chord"] is None for c in codes[:SINGLE_KEY_LIMIT])
        tail = codes[SINGLE_KEY_LIMIT:]
        assert all(c["chord"] is not None for c in tail)
        chords = [c["chord"] for c in tail]
        assert len(chords) == len(set(chords))
    finally:
        conn.close()


def test_reorder_demotes_chord_back_to_single_key(tmp_path):
    """Move a chord-range code into single-key range — chord disappears."""
    path = _fresh_project(tmp_path)
    conn = open_project(path)
    try:
        ids = [add_code(conn, f"Code {i:02d}", "#A91818") for i in range(35)]
        # Pick the last code (rank 34, has a chord) and move it to rank 0.
        new_order = [ids[-1]] + ids[:-1]
        reorder_codes(conn, new_order)

        codes = _codes(list_codes_with_tree(conn))
        moved = next(c for c in codes if c["id"] == ids[-1])
        assert moved["chord"] is None  # now in single-key range
        # The displaced code at the new rank 31 should have a chord.
        rank_31 = codes[SINGLE_KEY_LIMIT]
        assert rank_31["chord"] is not None
    finally:
        conn.close()


def test_chord_results_are_deterministic(tmp_path):
    """Same input → same chords across calls."""
    path = _fresh_project(tmp_path)
    conn = open_project(path)
    try:
        for i in range(35):
            add_code(conn, f"Code {i:02d}", "#A91818")

        first = [(c["id"], c["chord"]) for c in _codes(list_codes_with_tree(conn))]
        second = [(c["id"], c["chord"]) for c in _codes(list_codes_with_tree(conn))]
        assert first == second
    finally:
        conn.close()
