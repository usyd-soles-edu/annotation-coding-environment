"""Tests for palette functions absorbed into codebook module."""

import json
from pathlib import Path

from ace.models.codebook import COLOUR_PALETTE, next_colour

PALETTE_PATH = Path("src/ace/static/code_palette.json")


def test_palette_has_36_entries():
    assert len(COLOUR_PALETTE) == 36


def test_palette_is_loaded_from_static_json():
    raw = json.loads(PALETTE_PATH.read_text(encoding="utf-8"))
    assert COLOUR_PALETTE == [(item["hex"], item["label"]) for item in raw]


def test_palette_entries_are_hex_tuples():
    for hex_val, label in COLOUR_PALETTE:
        assert hex_val.startswith("#")
        assert len(hex_val) == 7
        assert label


def test_palette_is_grouped_into_colour_families():
    families = [label.rsplit(" ", 1)[0] for _hex_val, label in COLOUR_PALETTE]
    assert families == [
        "Blue", "Blue", "Blue", "Blue",
        "Teal", "Teal", "Teal", "Teal",
        "Green", "Green", "Green", "Green",
        "Olive", "Olive", "Olive", "Olive",
        "Orange", "Orange", "Orange", "Orange",
        "Red", "Red", "Red", "Red",
        "Pink", "Pink", "Pink", "Pink",
        "Purple", "Purple", "Purple", "Purple",
        "Neutral", "Neutral", "Neutral", "Neutral",
    ]


def test_palette_colours_are_visible_on_white():
    def channel_to_linear(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    def luminance(hex_val: str) -> float:
        r = channel_to_linear(int(hex_val[1:3], 16))
        g = channel_to_linear(int(hex_val[3:5], 16))
        b = channel_to_linear(int(hex_val[5:7], 16))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    for hex_val, _label in COLOUR_PALETTE:
        contrast = 1.05 / (luminance(hex_val) + 0.05)
        assert contrast >= 3


def test_next_colour_returns_hex_string():
    c = next_colour(0)
    assert isinstance(c, str)
    assert c.startswith("#")
    assert len(c) == 7


def test_next_colour_cycles_at_36():
    assert next_colour(0) == next_colour(36)
    assert next_colour(1) == next_colour(37)
    assert next_colour(35) == next_colour(71)


def test_frontend_colour_swatch_palette_comes_from_page_data():
    bridge_js = Path("src/ace/static/js/bridge.js").read_text(encoding="utf-8")
    coding_html = Path("src/ace/templates/coding.html").read_text(encoding="utf-8")
    assert "const _COLOUR_PALETTE" not in bridge_js
    assert "window.__aceColourPalette" in bridge_js
    assert "window.__aceColourPalette" in coding_html
