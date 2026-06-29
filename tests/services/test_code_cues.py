"""Tests for FTS5-backed codebook cues."""

import sqlite3

import pytest

from ace.db.connection import create_project
from ace.models.codebook import add_code, add_folder, delete_code


def _require_fts5(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("CREATE VIRTUAL TABLE temp.__fts5_check USING fts5(value)")
        conn.execute("DROP TABLE temp.__fts5_check")
    except sqlite3.OperationalError as exc:
        pytest.skip(f"SQLite FTS5 unavailable: {exc}")


def _suggest_code_cues():
    try:
        from ace.services.code_cues import suggest_code_cues
    except ModuleNotFoundError as exc:
        raise AssertionError(
            "Expected ace.services.code_cues.suggest_code_cues to exist"
        ) from exc
    return suggest_code_cues


def test_suggest_code_cues_ranks_code_name_and_definition_matches(tmp_path):
    conn = create_project(str(tmp_path / "cues.ace"), "Cue Test")
    try:
        _require_fts5(conn)
        suggest_code_cues = _suggest_code_cues()

        feedback = add_code(
            conn,
            "Feedback uptake",
            "#3366cc",
            definition="Uses feedback comments to revise assessment work.",
        )
        add_code(
            conn,
            "Group logistics",
            "#cc6633",
            definition="Coordinates group meetings, roles, and deadlines.",
        )

        cues = suggest_code_cues(
            conn,
            "I revised my assessment after reading the tutor feedback comments.",
            limit=3,
        )

        assert cues
        assert cues[0]["code_id"] == feedback
        assert cues[0]["rank"] > 0
        assert {"feedback", "comments"} & set(cues[0]["matched_terms"])
    finally:
        conn.close()


def test_suggest_code_cues_prefers_code_name_match_over_definition_repetition(tmp_path):
    conn = create_project(str(tmp_path / "cues.ace"), "Cue Test")
    try:
        _require_fts5(conn)
        suggest_code_cues = _suggest_code_cues()

        name_match = add_code(
            conn,
            "Feedback",
            "#3366cc",
            definition="Broad code for learner response.",
        )
        add_code(
            conn,
            "Reflection",
            "#cc6633",
            definition="Feedback feedback feedback feedback comments repeated in a definition.",
        )

        cues = suggest_code_cues(conn, "feedback", limit=2)

        assert cues
        assert cues[0]["code_id"] == name_match
    finally:
        conn.close()


def test_suggest_code_cues_filters_folders_deleted_codes_and_stopword_queries(tmp_path):
    conn = create_project(str(tmp_path / "cues.ace"), "Cue Test")
    try:
        _require_fts5(conn)
        suggest_code_cues = _suggest_code_cues()

        folder_id = add_folder(conn, "Feedback comments")
        deleted = add_code(
            conn,
            "Feedback archive",
            "#999999",
            definition="Old feedback comments code that should not be cued.",
        )
        delete_code(conn, deleted)
        active = add_code(
            conn,
            "Revision planning",
            "#3366cc",
            definition="Plans specific revisions after marker feedback.",
        )

        weak_cues = suggest_code_cues(conn, "the and of to in is", limit=3)
        assert weak_cues == []

        cues = suggest_code_cues(
            conn,
            "Marker feedback shaped the planned revisions.",
            limit=3,
        )

        ids = [cue["code_id"] for cue in cues]
        assert active in ids
        assert deleted not in ids
        assert folder_id not in ids
        assert len(cues) <= 3
    finally:
        conn.close()


def test_suggest_code_cues_handles_punctuation_quotes_and_fts_operators(tmp_path):
    conn = create_project(str(tmp_path / "cues.ace"), "Cue Test")
    try:
        _require_fts5(conn)
        suggest_code_cues = _suggest_code_cues()

        feedback = add_code(
            conn,
            "Feedback uptake",
            "#3366cc",
            definition="Learners use quoted feedback comments to revise work.",
        )

        cues = suggest_code_cues(
            conn,
            '"feedback" NEAR comments (revise*) AND assessment',
            limit=3,
        )

        assert cues
        assert cues[0]["code_id"] == feedback
        assert "feedback" in cues[0]["matched_terms"]
    finally:
        conn.close()


def test_create_temp_index_falls_back_when_porter_tokenizer_is_unavailable():
    import ace.services.code_cues as code_cues

    class FakeConn:
        def __init__(self):
            self.create_sql: list[str] = []

        def execute(self, sql: str):
            if "CREATE VIRTUAL TABLE" in sql:
                self.create_sql.append(sql)
                if "porter unicode61" in sql:
                    raise sqlite3.OperationalError("no such tokenizer: porter")
            return []

    conn = FakeConn()

    assert code_cues._create_temp_index(conn) is True
    assert len(conn.create_sql) == 2
    assert "porter unicode61" in conn.create_sql[0]
    assert "tokenize = 'unicode61'" in conn.create_sql[1]


def test_suggest_code_cues_uses_temp_fts_without_main_schema_change(tmp_path):
    conn = create_project(str(tmp_path / "cues.ace"), "Cue Test")
    try:
        _require_fts5(conn)
        suggest_code_cues = _suggest_code_cues()
        add_code(
            conn,
            "Feedback uptake",
            "#3366cc",
            definition="Uses feedback comments to revise assessment work.",
        )

        before_schema = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'index', 'trigger', 'view')"
            ).fetchall()
        }

        suggest_code_cues(conn, "feedback comments", limit=3)

        after_schema = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table', 'index', 'trigger', 'view')"
            ).fetchall()
        }
        temp_names = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_temp_master WHERE type = 'table'"
            ).fetchall()
        }

        assert after_schema == before_schema
        assert "code_cue_fts" in temp_names
        assert "code_cue_fts" not in after_schema
    finally:
        conn.close()


def test_suggest_code_cues_degrades_to_empty_when_fts_operation_fails(
    tmp_path,
    monkeypatch,
):
    conn = create_project(str(tmp_path / "cues.ace"), "Cue Test")
    try:
        _require_fts5(conn)
        add_code(
            conn,
            "Feedback uptake",
            "#3366cc",
            definition="Uses feedback comments to revise assessment work.",
        )

        import ace.services.code_cues as code_cues

        def fail_index_codes(_conn):
            raise sqlite3.OperationalError("fts5 unavailable")

        monkeypatch.setattr(code_cues, "_index_codes", fail_index_codes)

        assert code_cues.suggest_code_cues(conn, "feedback comments", limit=3) == []
    finally:
        conn.close()


def test_suggest_code_cues_1000_code_smoke(tmp_path):
    conn = create_project(str(tmp_path / "cues.ace"), "Cue Test")
    try:
        _require_fts5(conn)
        suggest_code_cues = _suggest_code_cues()
        target = add_code(
            conn,
            "Feedback uptake target",
            "#3366cc",
            definition="Uses feedback comments to revise assessment work.",
        )
        for i in range(999):
            add_code(
                conn,
                f"Logistics distractor {i}",
                "#999999",
                definition=f"Coordinates unrelated group meeting item {i}.",
            )

        cues = suggest_code_cues(
            conn,
            "Feedback comments helped me revise my assessment work.",
            limit=3,
        )

        assert cues
        assert cues[0]["code_id"] == target
    finally:
        conn.close()
