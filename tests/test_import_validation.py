"""Reject tabular shapes that would silently discard selected data."""

import csv

import openpyxl
import pytest
from fastapi.testclient import TestClient

from ace.app import create_app
from ace.db.connection import create_project, open_project
from ace.models.source import list_sources
from ace.services.importer import read_tabular


def _write_table(path, headings, values):
    if path.suffix == ".xlsx":
        workbook = openpyxl.Workbook()
        workbook.active.append(headings)
        workbook.active.append(values)
        workbook.save(path)
        workbook.close()
    else:
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(headings)
            writer.writerow(values)


@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_duplicate_headings_rejected_before_mapping(tmp_path, suffix):
    path = tmp_path / ("duplicate" + suffix)
    _write_table(path, ["id", "response", "response"], ["A", "First answer", "Second answer"])
    with pytest.raises(ValueError, match="Duplicate column heading.*response"):
        read_tabular(path)


def test_generated_excel_heading_cannot_collide(tmp_path):
    path = tmp_path / "generated.xlsx"
    _write_table(path, ["id", None, "col_1"], ["A", "First answer", "Second answer"])
    with pytest.raises(ValueError, match="Duplicate column heading.*col_1"):
        read_tabular(path)


def test_extra_csv_fields_rejected(tmp_path):
    path = tmp_path / "extra.csv"
    path.write_text("id,text\nA,hello,world\n", encoding="utf-8")
    with pytest.raises(ValueError, match="more fields than column headings"):
        read_tabular(path)


@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_invalid_headings_cannot_be_imported(tmp_path, suffix):
    project = tmp_path / "project.ace"
    create_project(project, "Test").close()
    path = tmp_path / ("duplicate" + suffix)
    _write_table(path, ["id", "response", "response"], ["A", "First", "Second"])
    app = create_app()
    with TestClient(app) as client:
        app.state.project_path = str(project)
        preview = client.post("/api/import/file", data={"path": str(path)})
        assert "Duplicate column heading" in preview.text
        assert 'id="import-form"' not in preview.text
        response = client.post("/api/import/commit", data={"id_column": "id", "text_columns": '["response"]'})
        assert "Import complete" not in response.text
    conn = open_project(project)
    try:
        assert list_sources(conn) == []
    finally:
        conn.close()
