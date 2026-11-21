"""Tema biçimi katmanı: varsayılan stil, doğrulama, paketlenen yazı tipleri (Türkçe glifler, lisans, kayıt)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fontTools.ttLib import TTFont
from PySide6.QtGui import QFont, QFontDatabase, QFontInfo, QFontMetrics
from pytestqt.qtbot import QtBot

from nxceviri.gui.theme import palette_style
from nxceviri.gui.theme_style import DEFAULT_STYLE, FONT_ROOT, OPTIONAL_TOKENS, ThemeStyle, nav_color, register_fonts

TURKISH = "çğıİöşüÇĞÖŞÜ"
BASIC = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
FONT_FILES = sorted(FONT_ROOT.glob("*/*.ttf"))

#: Yazı tipi klasörü → o klasörün kaydettiği aile adı.
FAMILIES = {
    "rubik": "Rubik",
    "nunito": "Nunito",
    "baloo2": "Baloo 2",
    "manrope": "Manrope",
    "pixelifysans": "Pixelify Sans",
    "jetbrainsmono": "JetBrains Mono",
    "fraunces": "Fraunces",
    "chakrapetch": "Chakra Petch",
    "ibmplexmono": "IBM Plex Mono",
}


def test_default_style_matches_todays_values() -> None:
    assert (DEFAULT_STYLE.radius_small, DEFAULT_STYLE.radius_control, DEFAULT_STYLE.radius_button) == (4, 6, 8)
    assert (DEFAULT_STYLE.radius_panel, DEFAULT_STYLE.radius_card, DEFAULT_STYLE.radius_pill) == (8, 12, 12)
    assert DEFAULT_STYLE.border == 1
    assert DEFAULT_STYLE.scheme is None
    assert palette_style("Neon Gün Batımı") is DEFAULT_STYLE
    assert palette_style("yok böyle") is DEFAULT_STYLE


def test_style_rejects_unknown_values() -> None:
    with pytest.raises(ValueError, match="düğme"):
        ThemeStyle(button="yok")
    with pytest.raises(ValueError, match="şema"):
        ThemeStyle(scheme="mor")
    with pytest.raises(ValueError, match="gezinme"):
        ThemeStyle(nav_position="alt")


def test_nav_color_falls_back_to_todays_token() -> None:
    tokens = {"surface": "#111111", "selection": "#222222", "text": "#333333", "accent": "#444444"}
    assert nav_color(tokens, "nav_bg") == "#111111"
    assert nav_color(tokens, "nav_sel_bg") == "#222222"
    assert nav_color(tokens, "nav_icon") == "#444444"
    assert nav_color({**tokens, "nav_bg": "#abcdef"}, "nav_bg") == "#abcdef"
    assert set(OPTIONAL_TOKENS) >= {"nav_bg", "nav_text", "nav_sel_bg", "nav_sel_text"}


def test_every_font_folder_ships_its_license() -> None:
    folders = {p.parent for p in FONT_FILES}
    assert {f.name for f in folders} == set(FAMILIES)
    for folder in folders:
        assert (folder / "OFL.txt").is_file(), folder.name


@pytest.mark.parametrize("path", FONT_FILES, ids=[f"{p.parent.name}/{p.name}" for p in FONT_FILES])
def test_bundled_font_has_turkish_and_basic_latin(path: Path) -> None:
    cmap = TTFont(path).getBestCmap()
    missing = [c for c in TURKISH + BASIC if ord(c) not in cmap]
    assert not missing, f"{path.name}: eksik harfler {''.join(missing)}"


@pytest.mark.parametrize(("folder", "family"), list(FAMILIES.items()))
def test_family_registers_with_semibold_or_bolder_style(qtbot: QtBot, folder: str, family: str) -> None:
    assert family in register_fonts((folder,)) or family in QFontDatabase.families()
    weights = [QFontDatabase.weight(family, s) for s in QFontDatabase.styles(family)]
    assert max(weights) >= 600, (family, weights)


@pytest.mark.parametrize(("folder", "family"), [(k, v) for k, v in FAMILIES.items() if "Mono" not in v])
def test_bold_weight_resolves_to_a_wider_face(qtbot: QtBot, folder: str, family: str) -> None:
    register_fonts((folder,))
    text = "Çevir ğüşiöı İSTANBUL Hello World"
    regular, bold = QFont(family, 14), QFont(family, 14)
    regular.setWeight(QFont.Weight.Normal)
    bold.setWeight(QFont.Weight.Bold)
    assert QFontInfo(bold).family() == family
    assert QFontMetrics(bold).horizontalAdvance(text) != QFontMetrics(regular).horizontalAdvance(text)
