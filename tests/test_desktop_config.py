from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_tauri_loopback_capability_allows_desktop_dialogs():
    capability = json.loads(
        (ROOT / "desktop/src-tauri/capabilities/default.json").read_text(
            encoding="utf-8"
        )
    )

    assert capability["remote"]["urls"] == [
        "http://127.0.0.1:18080/*",
        "http://localhost:18080/*",
    ]
    assert "dialog:allow-open" in capability["permissions"]
