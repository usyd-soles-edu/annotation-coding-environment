from ace.app import create_app


def _paths() -> set[str]:
    return {route.path for route in create_app().routes}


def test_api_route_split_preserves_core_routes():
    paths = _paths()
    expected = {
        "/api/native/pick-file",
        "/api/native/pick-folder",
        "/api/native/pick-files",
        "/api/project/create",
        "/api/project/open",
        "/api/import/file",
        "/api/import/commit",
        "/api/import/folder",
        "/api/import/remove-last",
        "/api/code/{code_id}/view-data",
        "/api/import/preview",
        "/api/export/annotations",
        "/api/code/apply",
        "/api/code/delete-annotation",
        "/api/undo",
        "/api/redo",
        "/api/navigation",
        "/api/code/flag",
        "/api/source-note/{source_id}",
        "/api/export/notes",
        "/api/code/apply-sentence",
        "/api/code/delete-sentence",
        "/api/codes/tree",
        "/api/codes",
        "/api/codes/folder",
        "/api/codes/{code_id}/parent",
        "/api/codes/{code_id}/indent-promote",
        "/api/codes/cut-paste",
        "/api/codes/reorder-in-scope",
        "/api/codes/reorder",
        "/api/codes/export",
        "/api/codes/import/preview-path",
        "/api/codes/import/preview-map",
        "/api/codes/import",
        "/api/codes/{code_id}/convert-to-folder",
        "/api/codes/{code_id}",
        "/api/agreement/preview",
        "/api/agreement/compute",
        "/api/agreement/progress",
        "/api/agreement/clear",
        "/api/agreement/export/results",
        "/api/agreement/export/raw",
        "/api/agreement/export/references",
        "/api/agreement/export/methodology",
    }
    assert expected <= paths
