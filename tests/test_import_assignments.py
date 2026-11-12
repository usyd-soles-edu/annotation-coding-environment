"""Later imports must remain aligned with the coder's source indices."""

import re

import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project, open_project
from ace.models.assignment import get_assignments_for_coder, set_flagged
from ace.models.codebook import add_code
from ace.models.project import list_coders
from ace.models.source import list_sources
from ace.models.source_note import get_note, upsert_note


@pytest.mark.parametrize("kind", ["csv", "folder"])
def test_second_import_is_immediately_codable(tmp_path, kind):
    project = tmp_path / "project.ace"
    conn = create_project(project, "Test")
    coder_id = list_coders(conn)[0]["id"]
    code_id = add_code(conn, "Code", "#123456")
    conn.close()
    app = create_app()

    def import_batch(client, index):
        if kind == "csv":
            path = tmp_path / f"batch{index}.csv"
            path.write_text(f"id,text\nS{index},Text {index}\n", encoding="utf-8")
            assert client.post("/api/import/file", data={"path": str(path)}).status_code == 200
            response = client.post("/api/import/commit", data={
                "stage_token": app.state.import_stage_token,
                "id_column": "id", "text_columns": '["text"]',
            })
        else:
            folder = tmp_path / f"batch{index}"
            folder.mkdir()
            (folder / f"S{index}.txt").write_text(f"Text {index}", encoding="utf-8")
            preview = client.post("/api/import/folder", data={"path": str(folder)})
            token = re.search(r'name="manifest_token" value="([^"]+)"', preview.text).group(1)
            response = client.post("/api/import/folder/confirm", data={"manifest_token": token})
        assert response.status_code == 200
        assert "Import complete" in response.text

    with TestClient(app) as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        import_batch(client, 0)
        assert client.get("/code").status_code == 200
        conn = open_project(project)
        first = list_sources(conn)[0]["id"]
        set_flagged(conn, first, coder_id, True)
        upsert_note(conn, first, coder_id, "Keep this note")
        original_assignment = dict(get_assignments_for_coder(conn, coder_id)[0])
        conn.close()

        import_batch(client, 1)
        # Applying directly proves the import itself creates the assignment.
        response = client.post("/api/code/apply", data={
            "code_id": code_id, "current_index": 1,
            "start_offset": 0, "end_offset": 4, "selected_text": "Text",
        })
        assert response.status_code == 200
        for _ in range(2):
            assert client.get("/code?index=1").status_code == 200

    conn = open_project(project)
    try:
        sources = list_sources(conn)
        assignments = get_assignments_for_coder(conn, coder_id)
        assert [a["source_id"] for a in assignments] == [s["id"] for s in sources]
        assert dict(assignments[0]) == original_assignment
        assert get_note(conn, first, coder_id) == "Keep this note"
        annotation = conn.execute("SELECT source_id FROM annotation").fetchone()
        assert annotation["source_id"] == sources[1]["id"]
    finally:
        conn.close()


def test_reconcile_repairs_partial_legacy_assignments_without_changing_existing(tmp_path):
    from ace.models.assignment import add_assignment, ensure_assignments
    from ace.models.project import add_coder
    from ace.models.source import add_source
    from ace.routes.pages import _coding_context

    conn = create_project(tmp_path / "legacy.ace", "Test")
    try:
        coder_id = list_coders(conn)[0]["id"]
        other_coder = add_coder(conn, "Other coder")
        first = add_source(conn, "First", "First text.", "row")
        second = add_source(conn, "Second", "Second text.", "row")
        add_assignment(conn, first, coder_id)
        set_flagged(conn, first, coder_id, True)
        original = dict(get_assignments_for_coder(conn, coder_id)[0])

        context = _coding_context(conn, coder_id, 1)
        assert context["current_source"]["id"] == second
        assert context["total_sources"] == 2
        ensure_assignments(conn, coder_id)
        ensure_assignments(conn, coder_id)
        assignments = get_assignments_for_coder(conn, coder_id)
        assert [a["source_id"] for a in assignments] == [first, second]
        assert dict(assignments[0]) == original
        assert get_assignments_for_coder(conn, other_coder) == []
    finally:
        conn.close()


def test_import_assigns_all_coders_and_rolls_back_assignment_failure(tmp_path):
    import sqlite3

    from ace.models.project import add_coder
    from ace.services.importer import import_csv

    conn = create_project(tmp_path / "atomic.ace", "Test")
    try:
        add_coder(conn, "Other coder")
        path = tmp_path / "data.csv"
        path.write_text("id,text\nFirst,First text\n", encoding="utf-8")
        import_csv(conn, path, "id", ["text"])
        before = [dict(a) for a in conn.execute("SELECT * FROM assignment ORDER BY id")]
        assert len(before) == 2
        # A duplicate-only batch must not create or modify assignments.
        import_csv(conn, path, "id", ["text"])
        assert [dict(a) for a in conn.execute("SELECT * FROM assignment ORDER BY id")] == before
        conn.execute("""
            CREATE TRIGGER fail_new_assignment BEFORE INSERT ON assignment
            WHEN (SELECT display_id FROM source WHERE id = NEW.source_id) = 'Second'
            BEGIN SELECT RAISE(ABORT, 'injected assignment failure'); END
        """)
        conn.commit()
        path.write_text("id,text\nSecond,Second text\n", encoding="utf-8")
        with pytest.raises(sqlite3.IntegrityError, match="injected assignment failure"):
            import_csv(conn, path, "id", ["text"])
        assert [s["display_id"] for s in list_sources(conn)] == ["First"]
        assert conn.execute("SELECT COUNT(*) FROM source_content").fetchone()[0] == 1
        assert [dict(a) for a in conn.execute("SELECT * FROM assignment ORDER BY id")] == before
        assert not conn.in_transaction
    finally:
        conn.close()
