"""The coding view reuses unchanged source segmentation without stale offsets."""

from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project
from ace.models.assignment import _ensure_assignments_no_commit
from ace.models.project import list_coders
from ace.models.source import _add_source_no_commit
from ace.services.coding_context_cache import CodingContextCache
from ace.services import text_splitter


def test_sentence_cache_tracks_text_headings_and_project(tmp_path, monkeypatch):
    first_project = tmp_path / "first.ace"
    second_project = tmp_path / "second.ace"
    create_project(str(first_project), "First").close()
    create_project(str(second_project), "Second").close()
    text = "First sentence. Second sentence. " * 40
    calls = []
    original = text_splitter.split_into_units

    def counted(value, headings):
        calls.append((value, headings))
        return original(value, headings)

    monkeypatch.setattr(text_splitter, "split_into_units", counted)
    cache = CodingContextCache()
    try:
        units = cache.get_sentence_units(str(first_project), "source", text, ())
        units[0]["text"] = "changed by caller"
        assert cache.get_sentence_units(str(first_project), "source", text, ())[0]["text"] == "First sentence."
        assert len(calls) == 1

        changed_text = text.replace("First", "Other", 1)
        assert cache.get_sentence_units(str(first_project), "source", changed_text, ())[0]["text"] == "Other sentence."
        assert len(calls) == 2

        heading = ((0, 15),)
        assert cache.get_sentence_units(str(first_project), "source", text, heading)[0]["type"] == "heading"
        assert len(calls) == 3

        cache.get_sentence_units(str(second_project), "source", text, ())
        cache.get_sentence_units(str(first_project), "source", text, ())
        assert len(calls) == 5
        cache.close()
        cache.get_sentence_units(str(first_project), "source", text, ())
        assert len(calls) == 6
    finally:
        cache.close()


def test_sentence_cache_has_a_size_limit(tmp_path):
    project = tmp_path / "limited.ace"
    create_project(str(project), "Limited").close()
    cache = CodingContextCache()
    try:
        for index in range(5):
            text = f"- {index}" + "x" * 69_997
            cache.get_sentence_units(str(project), f"source-{index}", text, ())
        assert cache._sentence_chars <= 250_000
        assert len(cache._sentence_units) <= 3
    finally:
        cache.close()


def test_sentence_cache_discards_replaced_project(tmp_path, monkeypatch):
    project = tmp_path / "project.ace"
    replacement = tmp_path / "replacement.ace"
    create_project(str(project), "Original").close()
    create_project(str(replacement), "Replacement").close()
    text = "A source sentence. " * 80
    calls = []
    original = text_splitter.split_into_units

    def counted(value, headings):
        calls.append(value)
        return original(value, headings)

    monkeypatch.setattr(text_splitter, "split_into_units", counted)
    cache = CodingContextCache()
    try:
        cache.get_sentence_units(str(project), "source", text, ())
        replacement.replace(project)
        cache.get_sentence_units(str(project), "source", text, ())
        assert len(calls) == 2
    finally:
        cache.close()


def test_navigation_reuses_sentence_units_for_a_revisited_source(tmp_path, monkeypatch):
    project = tmp_path / "navigation.ace"
    conn = create_project(str(project), "Navigation")
    coder_id = list_coders(conn)[0]["id"]
    _add_source_no_commit(conn, "Short", "Short source.", "row")
    long_text = "A longer source sentence. " * 100
    _add_source_no_commit(conn, "Long", long_text, "row")
    _ensure_assignments_no_commit(conn, coder_id)
    conn.commit()
    conn.close()

    calls = []
    original = text_splitter.split_into_units

    def counted(value, headings):
        if value == long_text:
            calls.append(value)
        return original(value, headings)

    monkeypatch.setattr(text_splitter, "split_into_units", counted)
    app = create_app()
    with TestClient(app) as client:
        app.state.project_path = str(project)
        app.state.coder_id = coder_id
        assert client.get("/code?index=0").status_code == 200
        for start, end in ((0, 1), (1, 0), (0, 1)):
            response = client.post(
                "/api/navigation",
                data={"from_index": start, "to_index": end},
                headers={"HX-Request": "true"},
            )
            assert response.status_code == 200
        assert len(calls) == 1
