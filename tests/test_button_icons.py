"""Düğmelere simge: metinler aynı kalır, yalnızca simge eklenir."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QToolButton, QWidget
from pytestqt.qtbot import QtBot

from nxceviri.gui import icons
from nxceviri.gui.add_game_page import AddGamePage
from nxceviri.gui.export_page import ExportPage
from nxceviri.gui.find_replace import FindReplaceDialog
from nxceviri.gui.qa_page import QaPage
from nxceviri.gui.translate_page import TranslatePage

GUI_DIR = Path(icons.__file__).parent

#: (dosya, düğme metni, simge adı): `button("metin", ..., icon="ad")` biçiminde kodda bulunmalı.
BUTTON_ICONS = [
    ("add_game_page.py", "prod.keys Seç…", "key-round"),
    ("add_game_page.py", "Metinleri Tara  →", "scan-search"),
    ("scan_page.py", "Yeniden Tara", "refresh-cw"),
    ("scan_page.py", "Metinleri Çeviri Tablosuna Aktar  →", "languages"),
    ("scan_page.py", "Taramayı Başlat", "scan-search"),
    ("scan_page.py", "Tekrar Dene", "refresh-cw"),
    ("qa_page.py", "Fontları Tara", "scan-search"),
    ("qa_page.py", "Denetle", "shield-check"),
    ("qa_page.py", "Seçilenleri Düzelt", "refresh-cw"),
    ("export_page.py", "Seç…", "folder-open"),
    ("export_page.py", "Modu Oluştur", "package"),
    ("export_page.py", "Mod Klasörünü Aç", "folder-open"),
    ("machine_dialogs.py", "Modelleri Listele", "refresh-cw"),
    ("find_replace.py", "Sonrakini Bul", "search"),
    ("csv_dialog.py", "Vazgeç", "x"),
    ("main_window.py", "Yeni sürüm var", "download"),
]


@pytest.mark.parametrize(("file", "text", "icon"), BUTTON_ICONS)
def test_button_has_icon_in_source(file: str, text: str, icon: str) -> None:
    source = (GUI_DIR / file).read_text(encoding="utf-8")
    pattern = re.compile(r'button\(\s*"' + re.escape(text) + r'"[^)]*?icon="' + re.escape(icon) + '"')
    assert pattern.search(source), f'{file}: button("{text}", icon="{icon}") bulunamadı'


def _buttons(root: QWidget) -> dict[str, QPushButton]:
    return {b.text(): b for b in root.findChildren(QPushButton)}


def test_page_buttons_have_icons_and_keep_text(qtbot: QtBot) -> None:
    add = AddGamePage()
    qa = QaPage()
    export = ExportPage()
    for page in (add, qa, export):
        qtbot.addWidget(page)
    assert not add.keys_button.icon().isNull()
    assert add.keys_button.text() == "prod.keys Seç…"
    assert not add.next_button.icon().isNull()
    for button_ in (qa.font_button, qa.check_button, qa.fix_button):
        assert not button_.icon().isNull(), button_.text()
    assert qa.check_button.text() == "Denetle"
    assert qa.fix_button.text() == "Seçilenleri Düzelt"
    assert not export.export_button.icon().isNull()
    assert not export.open_button.icon().isNull()


def test_find_replace_dialog_buttons(qtbot: QtBot) -> None:
    dialog = FindReplaceDialog(None, [], [], ())
    qtbot.addWidget(dialog)
    buttons = _buttons(dialog)
    assert not buttons["Sonrakini Bul"].icon().isNull()


def test_cancel_and_start_buttons_in_dialog_boxes_have_icons() -> None:
    source = (GUI_DIR / "machine_dialogs.py").read_text(encoding="utf-8")
    assert re.search(r'bind_icon\(\s*self\.start,\s*"play"', source)
    assert len(re.findall(r'bind_icon\(.*"x"\)', source)) == 3  # "Vazgeç" düğmeleri (sözlük önerileri dahil)


def test_translate_page_title_and_icons(qtbot: QtBot) -> None:
    page = TranslatePage()
    qtbot.addWidget(page)
    titles = [lbl for lbl in page.findChildren(QLabel) if lbl.property("role") == "pageTitle"]
    assert [t.text() for t in titles] == ["Çevir"]
    assert [lbl for lbl in page.findChildren(QLabel) if lbl.objectName() == "titleIcon"]
    for name in ("machine_button", "run_cancel"):
        assert not getattr(page, name).icon().isNull(), name
    assert page.machine_button.text() == "Makine Çevirisi…"
    for name in ("more_button", "view_button"):
        tool = getattr(page, name)
        assert isinstance(tool, QToolButton)
        assert not tool.icon().isNull(), name
        assert tool.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    assert page.more_button.text() == "Daha Fazla"
    assert page.view_button.text() == "Görünüm"
