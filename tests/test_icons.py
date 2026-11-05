"""Simge sistemi: Lucide SVG dosyalarından temaya uyan QIcon üretimi."""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from pytestqt.qtbot import QtBot

from nxceviri.gui import icons
from nxceviri.gui.theme import ThemeMode, apply_theme

GUI_DIR = Path(icons.__file__).parent


@pytest.fixture(autouse=True)
def _fresh_cache(qtbot: QtBot) -> Iterator[None]:
    """Testler temayı değiştirir; sonraki testler (ör. yerleşim) bozulmasın diye uygulama durumu geri konur."""
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    palette, style_sheet, font = app.palette(), app.styleSheet(), app.font()
    icons.clear_cache()
    yield
    app.setPalette(palette)
    app.setStyleSheet(style_sheet)
    app.setFont(font)
    icons.clear_cache()


def _opaque_colors(pixmap: QPixmap) -> list[QColor]:
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    return [
        image.pixelColor(x, y)
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 200
    ]


def test_all_known_icons_render_in_both_themes() -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    assert icons.KNOWN_ICONS
    for mode in (ThemeMode.LIGHT, ThemeMode.DARK):
        apply_theme(app, mode)
        icons.clear_cache()
        for name in sorted(icons.KNOWN_ICONS):
            pixmap = icons.icon(name).pixmap(18, 18)
            assert not pixmap.isNull(), name
            assert _opaque_colors(pixmap), f"{name} boş çiziliyor ({mode})"


def test_color_changes_pixels() -> None:
    red = _opaque_colors(icons.icon("search", "#ff0000").pixmap(18, 18))
    blue = _opaque_colors(icons.icon("search", "#0000ff").pixmap(18, 18))
    assert red
    assert blue
    assert all(c.red() > 200 and c.blue() < 60 for c in red[:20])
    assert all(c.blue() > 200 and c.red() < 60 for c in blue[:20])


def test_cache_returns_same_pixmap_for_same_key() -> None:
    first = icons.pixmap("search", "#123456", 18, 1.0)
    second = icons.pixmap("search", "#123456", 18, 1.0)
    assert first is second
    assert icons.pixmap("search", "#123456", 18, 2.0) is not first


def test_dpr_two_doubles_pixmap() -> None:
    pixmap = icons.pixmap("search", "#000000", 18, 2.0)
    assert pixmap.width() == 36
    assert pixmap.height() == 36
    assert pixmap.devicePixelRatio() == 2.0


def test_unknown_icon_returns_null_and_warns(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        result = icons.icon("yok-boyle-bir-simge")
    assert result.isNull()
    assert "yok-boyle-bir-simge" in caplog.text


def test_corrupt_svg_returns_null_and_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "bozuk.svg").write_text("<svg bu xml degil", encoding="utf-8")
    monkeypatch.setattr(icons, "ICON_DIR", tmp_path)
    with caplog.at_level(logging.WARNING):
        result = icons.icon("bozuk")
    assert result.isNull()
    assert "bozuk" in caplog.text


def test_bind_icon_refreshes_on_theme_change() -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    button = QPushButton("x")
    icons.bind_icon(button, "search")
    apply_theme(app, ThemeMode.LIGHT)
    icons.clear_cache()
    icons.refresh_icons()
    light = _opaque_colors(button.icon().pixmap(18, 18))
    apply_theme(app, ThemeMode.DARK)
    icons.clear_cache()
    icons.refresh_icons()
    dark = _opaque_colors(button.icon().pixmap(18, 18))
    assert light
    assert dark
    assert light[0].lightness() < 128 < dark[0].lightness()


def test_bind_icon_on_label_sets_and_refreshes_pixmap() -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    label = QLabel()
    apply_theme(app, ThemeMode.LIGHT)
    icons.bind_icon(label, "search", size=22)
    pixmap = label.pixmap()
    assert pixmap is not None
    assert not pixmap.isNull()
    light = _opaque_colors(pixmap)[0]
    apply_theme(app, ThemeMode.DARK)
    refreshed = label.pixmap()
    assert refreshed is not None
    dark = _opaque_colors(refreshed)[0]
    assert light.lightness() < 128 < dark.lightness()


def test_refresh_skips_deleted_widgets() -> None:
    button = QPushButton("x")
    icons.bind_icon(button, "search")
    button.deleteLater()
    QApplication.sendPostedEvents(None, 0)
    del button
    icons.refresh_icons()  # silinmiş bileşen için hata vermemeli


def test_disabled_mode_uses_muted_pixmap() -> None:
    from PySide6.QtGui import QIcon

    result = icons.icon("search", "#ff0000")
    normal = _opaque_colors(result.pixmap(18, 18, QIcon.Mode.Normal))
    disabled = _opaque_colors(result.pixmap(18, 18, QIcon.Mode.Disabled))
    assert normal
    assert disabled
    assert normal[0].name() != disabled[0].name()


_LITERALS = (
    re.compile(r"""\bicon\(\s*["']([a-z0-9-]+)["']"""),
    re.compile(r"""\bbind_icon\([^,()]+,\s*["']([a-z0-9-]+)["']"""),
    re.compile(r"""\bicon=["']([a-z0-9-]+)["']"""),
)


def test_every_literal_icon_name_exists() -> None:
    missing: list[str] = []
    for path in sorted(GUI_DIR.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for pattern in _LITERALS:
            for name in pattern.findall(text):
                if name not in icons.KNOWN_ICONS:
                    missing.append(f"{path.name}: {name}")
    assert not missing


def test_new_view_icons_exist() -> None:
    names = ("pilcrow", "align-left", "align-center", "align-right", "panel-bottom", "panel-right", "chevron-up")
    for name in names:
        assert name in icons.KNOWN_ICONS, name
        assert not icons.icon(name).pixmap(18, 18).isNull(), name
