"""Tema: Windows vurgu rengi türetimi ve tema değişince simgelerin yenilenmesi."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QPushButton
from pytestqt.qtbot import QtBot

from nxceviri.gui import icons, theme
from nxceviri.gui.theme import TOKENS, ThemeMode, apply_theme, contrast_ratio, derive_accent


@pytest.fixture(autouse=True)
def _restore_app(qtbot: QtBot) -> Iterator[None]:
    """Testler temayı değiştirir; sonrakiler bozulmasın diye uygulama durumu geri konur."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    palette, style_sheet, font = app.palette(), app.styleSheet(), app.font()
    icons.clear_cache()
    yield
    app.setPalette(palette)
    app.setStyleSheet(style_sheet)
    app.setFont(font)
    icons.clear_cache()


@pytest.mark.parametrize("accent", ["#0078D4", "#FFB900", "#107C10", "#D13438", "#7A7574"])
@pytest.mark.parametrize("dark", [False, True])
def test_derive_accent_keeps_text_readable(accent: str, dark: bool) -> None:
    base = TOKENS["dark" if dark else "light"]
    derived = derive_accent(base, QColor(accent), dark)
    if derived["accent"] == base["accent"]:
        return  # kontrast yetersizse sabit renge dönülür; ayrı testte
    text_best = max(contrast_ratio(QColor(c), QColor(derived["accent"])) for c in ("#FFFFFF", "#0E1116"))
    assert contrast_ratio(QColor(derived["accent_text"]), QColor(derived["accent"])) == pytest.approx(text_best)
    assert derived["accent"].lower() == QColor(accent).name().lower()


@pytest.mark.parametrize("bad", [QColor(), QColor(0, 0, 0, 0)])
def test_derive_accent_rejects_invalid_or_transparent(bad: QColor) -> None:
    assert derive_accent(TOKENS["light"], bad, dark=False) == TOKENS["light"]


def test_derive_accent_rejects_low_contrast_to_surface() -> None:
    assert derive_accent(TOKENS["light"], QColor("#FAFAFA"), dark=False) == TOKENS["light"]
    assert derive_accent(TOKENS["dark"], QColor("#1E2126"), dark=True) == TOKENS["dark"]


def test_derive_accent_does_not_mutate_input() -> None:
    before = dict(TOKENS["light"])
    derive_accent(TOKENS["light"], QColor("#0078D4"), dark=False)
    assert TOKENS["light"] == before


def test_extreme_colors_white_and_black() -> None:
    white_on_dark = derive_accent(TOKENS["dark"], QColor("#FFFFFF"), dark=True)
    assert white_on_dark["accent_text"] in ("#FFFFFF", "#0E1116")
    black_on_light = derive_accent(TOKENS["light"], QColor("#000000"), dark=False)
    assert black_on_light["accent_text"] in ("#FFFFFF", "#0E1116")
    assert contrast_ratio(QColor(black_on_light["accent_text"]), QColor(black_on_light["accent"])) >= 4.5


def test_system_mode_uses_system_accent(monkeypatch: pytest.MonkeyPatch) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    monkeypatch.setattr(theme, "_system_accent", lambda: QColor("#D13438"))
    apply_theme(app, ThemeMode.SYSTEM)
    assert theme.current_tokens()["accent"].lower() == "#d13438"
    assert app.palette().highlight().color().name().lower() == "#d13438"


@pytest.mark.parametrize("mode", [ThemeMode.LIGHT, ThemeMode.DARK])
def test_manual_modes_use_fixed_tokens(monkeypatch: pytest.MonkeyPatch, mode: ThemeMode) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    monkeypatch.setattr(theme, "_system_accent", lambda: QColor("#D13438"))
    apply_theme(app, mode)
    assert theme.current_tokens() == TOKENS[mode.value]


def _first_opaque(button: QPushButton) -> QColor:
    image = button.icon().pixmap(18, 18).toImage()
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 200:
                return image.pixelColor(x, y)
    raise AssertionError("simge boş çizildi")


def test_apply_theme_refreshes_bound_icons() -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    button = QPushButton("x")
    apply_theme(app, ThemeMode.LIGHT)
    icons.bind_icon(button, "search")
    light = _first_opaque(button)
    apply_theme(app, ThemeMode.DARK)  # refresh_icons'u elle çağırmadan simge yeni renge geçmeli
    dark = _first_opaque(button)
    assert light.lightness() < 128 < dark.lightness()
