from __future__ import annotations

import builtins
import importlib
import sys


def test_text_preview_helpers_do_not_import_openpyxl(monkeypatch, tmp_path):
    sys.modules.pop("ace.services.importer", None)
    sys.modules.pop("openpyxl", None)
    original_import = builtins.__import__

    def import_without_openpyxl(name, *args, **kwargs):
        if name == "openpyxl" or name.startswith("openpyxl."):
            raise AttributeError("module 'numpy' has no attribute 'short'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_openpyxl)

    importer = importlib.import_module("ace.services.importer")

    folder = tmp_path / "texts"
    folder.mkdir()
    (folder / "one.txt").write_text("First document", encoding="utf-8")

    total, previews = importer.get_random_previews(folder)
    assert total == 1
    assert previews[0]["filename"] == "one.txt"
