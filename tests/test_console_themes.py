"""Konsol temaları: yazı tipi paketi (Türkçe glifler, lisans), kayıt, sabit şema, yazı tipi geri yükleme, kilit."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMenu
from pytestqt.qtbot import QtBot

from nxceviri.gui import icons
from nxceviri.gui.console_themes import CIFT_KUMANDA, CONSOLE_THEMES, PIKSEL_GRI
from nxceviri.gui.theme import (
    DEFAULT_PALETTE,
    MODE_LOCK_TIP,
    PALETTES,
    STYLES,
    ThemeMode,
    _qss,
    apply_theme,
    current_style,
    current_tokens,
    effective_scheme,
    palette_tokens,
)
from nxceviri.gui.theme_style import DEFAULT_STYLE
from tests.test_statusbar import _make_window, _project


@pytest.fixture
def themed_app(qtbot: QtBot) -> Iterator[QApplication]:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    palette, style_sheet, font = app.palette(), app.styleSheet(), app.font()
    icons.clear_cache()
    yield app
    apply_theme(app, ThemeMode.LIGHT, palette=DEFAULT_PALETTE)
    app.setPalette(palette)
    app.setStyleSheet(style_sheet)
    app.setFont(font)
    icons.clear_cache()


def test_there_are_five_console_themes() -> None:
    assert list(CONSOLE_THEMES) == ["Çift Kumanda", "Mor Küp", "Yeşil Işık", "Gece Mavisi", "Piksel Gri"]
    assert list(PALETTES)[:2] == [DEFAULT_PALETTE, "Neon Gün Batımı"]
    assert set(STYLES) == set(CONSOLE_THEMES)


# --- sabit şema ve belirteçler -----------------------------------------------------------------


@pytest.mark.parametrize("name", list(CONSOLE_THEMES))
@pytest.mark.parametrize("mode", list(ThemeMode))
def test_console_theme_forces_its_scheme(themed_app: QApplication, name: str, mode: ThemeMode) -> None:
    wanted = STYLES[name].scheme
    assert wanted in ("light", "dark")
    assert apply_theme(themed_app, mode, palette=name) == wanted
    assert effective_scheme(mode, name) == wanted
    assert current_tokens()["bg"] == palette_tokens("light", name)["bg"] == palette_tokens("dark", name)["bg"]
    assert current_style() is STYLES[name]


def test_piksel_is_light_and_cift_is_dark() -> None:
    assert STYLES[PIKSEL_GRI].scheme == "light"
    assert STYLES[CIFT_KUMANDA].scheme == "dark"


def test_default_palette_restores_chosen_mode_and_style(themed_app: QApplication) -> None:
    apply_theme(themed_app, ThemeMode.DARK, palette=PIKSEL_GRI)
    assert apply_theme(themed_app, ThemeMode.DARK, palette=DEFAULT_PALETTE) == "dark"
    assert current_style() is DEFAULT_STYLE
    assert apply_theme(themed_app, ThemeMode.LIGHT, palette=DEFAULT_PALETTE) == "light"


def test_body_font_is_applied_and_restored(themed_app: QApplication) -> None:
    apply_theme(themed_app, ThemeMode.LIGHT, palette=DEFAULT_PALETTE)
    original = themed_app.font().family()
    apply_theme(themed_app, ThemeMode.LIGHT, palette=PIKSEL_GRI)
    assert themed_app.font().family() == "IBM Plex Mono"
    apply_theme(themed_app, ThemeMode.LIGHT, 12, palette=CIFT_KUMANDA)
    assert themed_app.font().family() == "Rubik"
    assert themed_app.font().pointSizeF() == 12
    apply_theme(themed_app, ThemeMode.LIGHT, palette=DEFAULT_PALETTE)
    assert themed_app.font().family() == original


def test_heading_and_mono_fonts_in_stylesheet(themed_app: QApplication) -> None:
    apply_theme(themed_app, ThemeMode.DARK, palette="Yeşil Işık")
    sheet = themed_app.styleSheet()
    assert 'font-family: "Chakra Petch"' in sheet
    assert 'QLabel[role="statValue"] { font-family: "JetBrains Mono"; }' in sheet
    apply_theme(themed_app, ThemeMode.DARK, palette="Gece Mavisi")
    assert 'QLabel[role="pageTitle"] { font-style: italic; }' in themed_app.styleSheet()
    apply_theme(themed_app, ThemeMode.DARK, palette=DEFAULT_PALETTE)
    assert "font-family" not in themed_app.styleSheet()


def test_stylesheet_uses_theme_shape() -> None:
    sheet = _qss(palette_tokens("dark", "Çift Kumanda"), 10, STYLES["Çift Kumanda"])
    assert "border-radius: 24px" in sheet
    assert "border-top-right-radius: 24px" in sheet
    piksel = _qss(palette_tokens("light", PIKSEL_GRI), 10, STYLES[PIKSEL_GRI])
    assert "border: 2px solid #1F1D1A" in piksel
    assert "border-radius: 6px" not in piksel
    mor = _qss(palette_tokens("dark", "Mor Küp"), 10, STYLES["Mor Küp"])
    assert "border-bottom: 4px solid #A7780E" in mor
    assert "border-bottom: 4px solid #120D29" in mor


# --- menü ve ayarlar ---------------------------------------------------------------------------


def test_menu_labels_and_lock(qtbot: QtBot, tmp_path: Path) -> None:
    w = _make_window(qtbot, tmp_path, _project())
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    palette, style_sheet, font = app.palette(), app.styleSheet(), app.font()
    try:
        view = next(a.menu() for a in w.menuBar().actions() if a.text().replace("&", "") == "Görünüm")
        assert isinstance(view, QMenu)
        titles = [a.text().replace("&", "") for a in view.actions()]
        assert "Açık / Koyu" in titles
        assert "Tema" in titles
        assert "Renk paleti" not in titles
        w._set_theme(ThemeMode.DARK)
        assert all(a.isEnabled() for a in w.theme_group.actions())
        w._set_palette(PIKSEL_GRI)
        assert not any(a.isEnabled() for a in w.theme_group.actions())
        assert all(a.toolTip() == MODE_LOCK_TIP for a in w.theme_group.actions())
        assert w._theme_mode() == ThemeMode.DARK  # kayıtlı seçim ezilmez
        w._set_palette(DEFAULT_PALETTE)
        assert all(a.isEnabled() for a in w.theme_group.actions())
        assert w._theme_mode() == ThemeMode.DARK
    finally:
        w._set_palette(DEFAULT_PALETTE)
        app.setPalette(palette)
        app.setStyleSheet(style_sheet)
        app.setFont(font)
        w.dirty = False
        w.close()
        w.deleteLater()
