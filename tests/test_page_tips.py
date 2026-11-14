"""Dışa Aktar ve Kontrol Et sayfalarındaki terimlerin üzerine gelince açıklama ipuçları."""

from __future__ import annotations

from pathlib import Path

from pytestqt.qtbot import QtBot

from nxceviri.core.export.layeredfs import LAYOUT_ATMOSPHERE, LAYOUT_EMULATOR
from nxceviri.core.qa import transliterate
from nxceviri.gui.export_page import ExportPage
from nxceviri.gui.qa_page import QaPage


def test_export_terms_have_tooltips(qtbot: QtBot) -> None:
    page = ExportPage()
    qtbot.addWidget(page)
    widgets = (
        page.layout_buttons[LAYOUT_ATMOSPHERE],
        page.layout_buttons[LAYOUT_EMULATOR],
        page.mod_name,
        page.folder,
        page.export_button,
        page.open_button,
        page.graphics_open,
    )
    for widget in widgets:
        assert widget.toolTip(), widget
    assert "SD kart" in page.layout_buttons[LAYOUT_ATMOSPHERE].toolTip()
    assert "mods" in page.layout_buttons[LAYOUT_EMULATOR].toolTip()


def test_export_target_line_tells_what_to_do(qtbot: QtBot, tmp_path: Path) -> None:
    """Hedef satırı teknik klasör yapısını değil, kullanıcının ne yapacağını söyler; yapı ipucundadır."""
    page = ExportPage()
    qtbot.addWidget(page)
    page.folder.setText(str(tmp_path))
    page.mod_name.setText("Turkce")
    page.update_target()
    assert "SD kart" in page.target.text()
    assert "<TitleID>" not in page.target.text()
    assert "atmosphere/contents/&lt;TitleID&gt;/romfs" in page.target.toolTip()
    page.layout_buttons[LAYOUT_EMULATOR].setChecked(True)
    assert "emülatör" in page.target.text()
    assert "&lt;TitleID&gt;/Turkce/romfs" in page.target.toolTip()


def test_check_page_terms_have_tooltips(qtbot: QtBot) -> None:
    page = QaPage()
    qtbot.addWidget(page)
    widgets = (
        page.font_button,
        *page.mode_buttons.values(),
        page.check_button,
        page.fit_enabled,
        page.fit_inherit,
        page.fit_width,
        page.fit_lines,
    )
    for widget in widgets:
        assert widget.toolTip(), widget
    assert "ğ→g" in page.mode_buttons[transliterate.MODE_MISSING].toolTip()
