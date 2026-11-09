"""Çeviri ekranının görsel düzeni: hizalama, boşluk, taşma.

Bu testler işlevi değil, kullanıcının gördüğü düzeni ölçer (gerçek oyundaki gibi uzun anahtarlarla ve üç pencere
boyutunda). 0.31.1'de düzenleme panelinde "Orijinal" ile "Çeviri" kutularının farklı yükseklikte durduğu, aralarında
büyük boşluklar açıldığı ve uzun anahtarların tablo satırlarını dört satıra çıkardığı bu yüzden gözden kaçmıştı.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QSettings
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.secrets import MemoryStore
from nxceviri.gui.main_window import STEP_TRANSLATE, MainWindow
from nxceviri.gui.translate_page import COL_KEY, TranslatePage

LB = ControlCode(b"\n", "Satır sonu")
KEY = "despelote_loc_monsterFile/01_Kids\\Conversations\\ArmarArcoDiscussion/Nina1_01/conversation/"
LINES = [
    ("I've got an idea.", (), "Aklıma bir fikir geldi."),
    (
        "We could make⟦1⟧the goal out of sticks, or...⟦2⟧out of...",
        (LB, LB),
        "Çubuklardan bir kale yaparız, ya da... ne bileyim...⟦1⟧başka bir şeyden...⟦2⟧",
    ),
    ("We could use the trees.", (), "Ağaçları kullanabiliriz."),
] * 10
SIZES = [(1920, 990), (1180, 780)]
#: Windows'un yazı tipi Linux'takinden iri; düzen her ikisinde de sığmalı.
FONT_POINTS = [10, 12]


def _project() -> Project:
    p = Project.new()
    entries = tuple(TextEntry(KEY + str(i), i, s, c) for i, (s, c, _) in enumerate(LINES))
    p.import_texts([ImportedFile("resources.assets>despelote_loc_monsterFile", "0100", "unity", "base", entries)])
    rows = p.translation_rows()
    p.set_translations([(r.id, t) for r, (_, _, t) in zip(rows, LINES, strict=True)], machine=True)
    return p


@pytest.fixture(
    params=[(size, pt) for size in SIZES for pt in FONT_POINTS], ids=lambda p: f"{p[0][0]}x{p[0][1]}-{p[1]}pt"
)
def page(request: pytest.FixtureRequest, qtbot: QtBot, tmp_path: Path) -> Iterator[TranslatePage]:
    size, points = request.param
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    old_font = app.font()
    font = QFont(old_font)
    font.setPointSize(points)
    app.setFont(font)
    w = MainWindow(QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat))
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.resize(*size)
    w.show()
    w.nav.setCurrentRow(STEP_TRANSLATE)
    w.translate_page._select_proxy_row(1)
    QTest.qWait(400)  # satır yüksekliği ve sütunlar gecikmeli ayarlanır
    yield w.translate_page
    w.dirty = False
    w.close()
    w.deleteLater()
    app.setFont(old_font)


def _top(widget: QWidget, ref: QWidget) -> int:
    return widget.mapTo(ref, QPoint(0, 0)).y()


def test_long_keys_do_not_make_rows_tall(page: TranslatePage) -> None:
    single = page.table.verticalHeader().defaultSectionSize()  # tek satırlık satırın yüksekliği
    assert page.table.rowHeight(0) <= single + 4  # kısa metinli satır, anahtar ne kadar uzun olursa olsun tek satır
    tip = page.model.index(0, COL_KEY).data(3)  # Qt.ToolTipRole
    assert KEY in tip


def test_machine_button_text_is_not_covered(page: TranslatePage) -> None:
    assert page.machine_button.width() >= page.machine_button.sizeHint().width()


def test_changes_dialog_keeps_text_columns_wide_with_long_row_names(qtbot: QtBot) -> None:
    from nxceviri.core.project import Change
    from nxceviri.gui.changes_dialog import ChangesDialog

    long_name = "[en]shop convo senor enojado_shopkeeper " * 8 + KEY * 3
    changes = [
        Change(
            i,
            long_name,
            "We could use the trees.",
            "Ağaçları kullanabiliriz.",
            "machine",
            "",
            "Ağaçları kullanırız.",
            "autofix",
            "2026-10-25T12:00:00",
        )
        for i in range(36)
    ]
    dialog = ChangesDialog(None, "Otomatik düzeltme: değişiklikler", changes)
    qtbot.addWidget(dialog)
    dialog.show()
    QTest.qWait(100)
    h = dialog.table.horizontalHeader()
    assert all(h.sectionSize(col) >= 150 for col in (2, 3, 4)), [h.sectionSize(c) for c in range(5)]
    assert dialog.table.rowHeight(0) < dialog.table.fontMetrics().height() * 4  # satırlar harf harf uzamıyor
    name = dialog.table.item(0, 1)
    assert name is not None
    assert name.toolTip() == long_name


def test_qa_list_wraps_long_texts_instead_of_cutting_them(qtbot: QtBot) -> None:
    from nxceviri.core.project import TranslationRow
    from nxceviri.core.qa.checks import QaIssue
    from nxceviri.gui.qa_page import QaPage

    qa = QaPage()
    qtbot.addWidget(qa)
    qa.resize(1180, 780)
    qa.show()
    row = TranslationRow(
        1,
        "f",
        "k",
        "We could make the goal out of sticks, or out of something else entirely, who knows.",
        "Çubuklardan bir kale yaparız ya da tamamen başka bir şeyden, kim bilir ne olur.",
        "machine",
        "",
        (),
        None,
    )
    qa.show_issues([QaIssue(1, "k", "overflow", "warning", "Çeviri orijinalden %62 uzun. " * 3)], [row])
    QTest.qWait(150)
    assert qa.table.rowHeight(0) > qa.table.fontMetrics().height() * 2  # metin alt satıra kaydı, kesilmedi
