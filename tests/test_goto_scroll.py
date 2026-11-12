"""Çeviri tablosu: satıra git (Bul sonraki, Kontrol Et'ten aç) satır yükseklikleri oturunca da görünür kalır."""

from __future__ import annotations

from dataclasses import replace

import pytest
from PySide6.QtCore import QRect
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.status import Status
from nxceviri.gui.translate_page import COL_TRANSLATION, TranslatePage

pytestmark = pytest.mark.gui

ROWS = 3000


def _row(i: int) -> TranslationRow:
    # Her 7. satır çok uzun: sarılan metin yüzünden satır yükseklikleri düzensiz.
    words = "uzun bir cümle " * (40 if i % 7 == 0 else 1 + i % 3)
    return TranslationRow(
        id=i,
        file="a.bundle",
        key=f"K/{i}",
        source=f"Source {i} {words}",
        translation=f"Çeviri {i} {words}",
        status=Status.MACHINE,
        note="",
        code_labels=(),
        max_length=None,
        context=f"K/{i}",
    )


@pytest.fixture
def page(qtbot: QtBot) -> TranslatePage:
    p = TranslatePage()
    qtbot.addWidget(p)
    p.resize(900, 600)
    p.show()
    p.set_rows([_row(i) for i in range(1, ROWS + 1)])
    qtbot.wait(150)
    return p


def _row_visible(p: TranslatePage, row_id: int) -> bool:
    source = p.model.position(row_id)
    assert source is not None
    index = p.proxy.mapFromSource(p.model.index(source, COL_TRANSLATION))
    rect = p.table.visualRect(index)
    return rect.isValid() and QRect(p.table.viewport().rect()).intersects(rect)


@pytest.mark.parametrize("target", [2500, 1200, 3])
def test_find_goto_keeps_row_visible_after_heights_settle(qtbot: QtBot, page: TranslatePage, target: int) -> None:
    assert page.find_goto(target)
    qtbot.wait(400)  # bekleyen satır yüksekliği ayarı bitsin
    assert _row_visible(page, target)
    current = page.current_row()
    assert current is not None
    assert current.id == target


def test_select_row_from_qa_keeps_row_visible(qtbot: QtBot, page: TranslatePage) -> None:
    page.select_row(2222)
    qtbot.wait(400)
    assert _row_visible(page, 2222)
    page.find_goto(700)
    page.select_row(2800)
    qtbot.wait(400)
    assert _row_visible(page, 2800)


def _big_page(qtbot: QtBot, count: int) -> TranslatePage:
    p = TranslatePage()
    qtbot.addWidget(p)
    p.resize(900, 600)
    p.show()
    p.set_rows([_row(i) for i in range(1, count + 1)])
    return p


def test_search_is_debounced_on_large_tables(qtbot: QtBot) -> None:
    from nxceviri.gui.translate_page import SEARCH_DEBOUNCE_ROWS

    p = _big_page(qtbot, SEARCH_DEBOUNCE_ROWS + 10)
    total = p.proxy.rowCount()
    p.search.setText("Source 1234 ")
    assert p.proxy.rowCount() == total  # yazarken süzülmez
    qtbot.waitUntil(lambda: p.proxy.rowCount() < total, timeout=3000)
    assert p.proxy.rowCount() == 1


def test_search_enter_and_clear_apply_immediately(qtbot: QtBot) -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from nxceviri.gui.translate_page import SEARCH_DEBOUNCE_ROWS

    p = _big_page(qtbot, SEARCH_DEBOUNCE_ROWS + 10)
    total = p.proxy.rowCount()
    p.search.setText("Source 1234 ")
    QTest.keyClick(p.search, Qt.Key.Key_Return)
    assert p.proxy.rowCount() == 1
    p.search.clear()
    assert p.proxy.rowCount() == total


def test_search_is_instant_on_small_tables(qtbot: QtBot) -> None:
    p = _big_page(qtbot, 50)
    p.search.setText("Source 7 ")
    assert p.proxy.rowCount() == 1


def test_filter_cache_follows_edits(qtbot: QtBot) -> None:
    p = _big_page(qtbot, 20)
    p.search.setText("zzz")
    assert p.proxy.rowCount() == 0
    row = p.model.rows[4]
    p.model.update_rows([replace(row, translation="ZZZ yeni")])
    p.search.setText("zzz ")
    p.search.setText("zzz")
    assert p.proxy.rowCount() == 1
