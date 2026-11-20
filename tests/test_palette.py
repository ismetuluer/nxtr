"""Renk paletleri: katman (overlay) sonucu, bütün paletlerde WCAG AA kontrastı, kuruluma yansıma."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from nxceviri.gui import icons
from nxceviri.gui.theme import (
    DEFAULT_PALETTE,
    PALETTES,
    TOKENS,
    ThemeMode,
    apply_theme,
    current_tokens,
    hex_contrast,
    palette_tokens,
)

_AA = 4.5
NEON = "Neon Gün Batımı"

_PAIRS = [
    *(("text", bg) for bg in ("bg", "surface", "surface2", "selection", "row_alt")),
    *(("muted", bg) for bg in ("bg", "surface", "surface2", "row_alt")),
    ("accent", "bg"),
    ("accent", "surface"),
    ("accent_text", "accent"),
    ("accent_text", "accent_hover"),
    ("success", "success_bg"),
    ("warning", "warning_bg"),
    ("danger", "danger_bg"),
]


#: Yeni paletlerde ek olarak: vurgu rengiyle yazılan çip yazısı seçili/ikincil zeminde de okunmalı
#: (varsayılan palet bu sıkı ölçütten önce vardı; değeri değiştirilmez).
_NEW_PALETTE_PAIRS = [("accent", "surface2"), ("accent", "selection")]


@pytest.fixture
def themed_app(qtbot: QtBot) -> Iterator[QApplication]:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    palette, style_sheet, font = app.palette(), app.styleSheet(), app.font()
    icons.clear_cache()
    yield app
    app.setPalette(palette)
    app.setStyleSheet(style_sheet)
    app.setFont(font)
    icons.clear_cache()


def test_default_palette_has_no_overrides() -> None:
    assert DEFAULT_PALETTE == "Varsayılan"
    for scheme in ("light", "dark"):
        assert palette_tokens(scheme, DEFAULT_PALETTE) == TOKENS[scheme]


def test_palette_overlay_changes_only_listed_keys() -> None:
    light = palette_tokens("light", NEON)
    assert light["accent"] == "#C2185B"
    assert light["success"] == TOKENS["light"]["success"]
    assert set(light) == set(TOKENS["light"])
    assert palette_tokens("dark", NEON)["bg"] == "#15122B"
    assert TOKENS["light"]["accent"] != "#C2185B"  # özgün tablo değişmez


def test_unknown_palette_falls_back_to_default() -> None:
    assert palette_tokens("light", "yok böyle") == TOKENS["light"]


def test_palette_overrides_use_known_keys() -> None:
    for name, (light, dark) in PALETTES.items():
        assert set(light) <= set(TOKENS["light"]), name
        assert set(dark) <= set(TOKENS["dark"]), name


@pytest.mark.parametrize("name", list(PALETTES))
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize(("fg", "bg"), _PAIRS)
def test_every_palette_meets_wcag_aa(name: str, scheme: str, fg: str, bg: str) -> None:
    tokens = palette_tokens(scheme, name)
    assert hex_contrast(tokens[fg], tokens[bg]) >= _AA, f"{name}/{scheme}: {fg}/{bg}"


@pytest.mark.parametrize("name", [n for n in PALETTES if n != DEFAULT_PALETTE])
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize(("fg", "bg"), _NEW_PALETTE_PAIRS)
def test_new_palettes_accent_text_on_chip_backgrounds(name: str, scheme: str, fg: str, bg: str) -> None:
    tokens = palette_tokens(scheme, name)
    assert hex_contrast(tokens[fg], tokens[bg]) >= _AA, f"{name}/{scheme}: {fg}/{bg}"


@pytest.mark.parametrize("name", list(PALETTES))
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_progress_highlight_is_visible(name: str, scheme: str) -> None:
    tokens = palette_tokens(scheme, name)
    assert hex_contrast(tokens["accent2"], tokens["surface2"]) >= 3.0


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_semantic_colors_stay_distinct(scheme: str) -> None:
    tokens = palette_tokens(scheme, NEON)
    assert len({tokens["success"], tokens["danger"], tokens["warning"], tokens["accent"]}) == 4


def test_hex_contrast_known_values() -> None:
    assert round(hex_contrast("#000000", "#FFFFFF"), 1) == 21.0
    assert hex_contrast("#777777", "#777777") == 1.0


@pytest.mark.parametrize("name", list(PALETTES))
def test_apply_theme_uses_palette(themed_app: QApplication, name: str) -> None:
    apply_theme(themed_app, ThemeMode.LIGHT, palette=name)
    accent = palette_tokens("light", name)["accent"]
    assert accent in themed_app.styleSheet()
    assert current_tokens()["accent"] == accent
