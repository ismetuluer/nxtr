"""Tablo hücreleri: semboller, hiza ve kod çipleri (ham metin değişmeden)."""

from __future__ import annotations

import re
import time
from collections.abc import Iterator

import pytest
from PySide6.QtCore import QModelIndex, QRect, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem, QWidget
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.status import Status
from nxceviri.gui.marked_delegate import ROW_ROLE, MarkedDelegate
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.translate_page import COL_SOURCE, COL_TRANSLATION, TranslatePage, TranslationDelegate, _Editor

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _restore_app(qtbot: QtBot) -> Iterator[None]:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    palette, style_sheet, font = app.palette(), app.styleSheet(), app.font()
    yield
    app.setPalette(palette)
    app.setStyleSheet(style_sheet)
    app.setFont(font)


def make_row(
    row_id: int,
    source: str,
    translation: str = "",
    labels: tuple[str, ...] = (),
    status: str = Status.MACHINE,
) -> TranslationRow:
    return TranslationRow(
        id=row_id,
        file="a.msbt",
        key=f"k{row_id}",
        source=source,
        translation=translation,
        status=status,
        note="",
        code_labels=labels,
        max_length=None,
    )


def make_page(qtbot: QtBot, rows: list[TranslationRow]) -> TranslatePage:
    page = TranslatePage()
    qtbot.addWidget(page)
    page.set_rows(rows)
    return page


def delegate_for(page: TranslatePage, column: int) -> MarkedDelegate:
    delegate = page.table.itemDelegateForColumn(column)
    assert isinstance(delegate, MarkedDelegate)
    return delegate


def option_for(page: TranslatePage, width: int = 300) -> QStyleOptionViewItem:
    option = QStyleOptionViewItem()
    option.font = page.table.font()
    option.rect = QRect(0, 0, width, 40)
    return option


def plain(markup: str) -> str:
    return re.sub(r"<[^>]+>", "", markup)


def test_both_text_columns_use_marked_delegate(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "a")])
    assert delegate_for(page, COL_SOURCE).field == "source"
    translation = delegate_for(page, COL_TRANSLATION)
    assert translation.field == "translation"
    assert isinstance(translation, TranslationDelegate)


def test_row_role_returns_the_row(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(7, "a", "b")])
    index = page.proxy.index(0, COL_SOURCE)
    row = index.data(ROW_ROLE)
    assert isinstance(row, TranslationRow)
    assert row.id == 7


def test_cells_render_chips_not_raw_codes(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "Press ⟦1⟧ now", "Şimdi ⟦1⟧ bas", labels=("Satır sonu",))])
    delegate = delegate_for(page, COL_TRANSLATION)
    index = page.proxy.index(0, COL_TRANSLATION)
    out = delegate.html_for(index)
    assert "⟦" not in plain(out)
    assert "↵1" in plain(out)  # satır sonu kodu: simge + numara
    assert index.data(Qt.ItemDataRole.EditRole) == "Şimdi ⟦1⟧ bas"  # ham metin değişmez
    assert page.model.rows[0].translation == "Şimdi ⟦1⟧ bas"


def test_symbols_toggle_changes_rendering(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "a b", "c d")])
    delegate = delegate_for(page, COL_SOURCE)
    index = page.proxy.index(0, COL_SOURCE)
    page.set_view(False, "left")
    assert "·" not in delegate.html_for(index)
    page.set_view(True, "left")
    assert "·" in delegate.html_for(index)


def test_symbols_with_wrap_off_keep_single_line_height(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "satır bir\nsatır iki", "x")])
    delegate = delegate_for(page, COL_SOURCE)
    index = page.proxy.index(0, COL_SOURCE)
    page.wrap_box.setChecked(False)
    page.set_view(True, "left")
    out = delegate.html_for(index)
    assert "<br>" not in out
    assert "¶" in out
    one_line = page.table.fontMetrics().height()
    assert delegate.sizeHint(option_for(page), index).height() < 2 * one_line + 12


def test_alignment_applied(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "metin", "çeviri")])
    delegate = delegate_for(page, COL_SOURCE)
    index = page.proxy.index(0, COL_SOURCE)
    for name, flag in (("right", Qt.AlignmentFlag.AlignRight), ("center", Qt.AlignmentFlag.AlignHCenter)):
        page.set_view(False, name)
        doc = delegate.document(option_for(page), index)
        assert doc.defaultTextOption().alignment() & flag
        assert doc.firstBlock().blockFormat().alignment() & flag
    page.set_view(False, "left")
    assert (
        delegate.document(option_for(page), index).firstBlock().blockFormat().alignment() & Qt.AlignmentFlag.AlignLeft
    )


def test_issue_color_preserved(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "Press ⟦1⟧", "Bas", labels=("Satır sonu",))])
    delegate = delegate_for(page, COL_TRANSLATION)
    index = page.proxy.index(0, COL_TRANSLATION)
    color = delegate.text_color(option_for(page), index)
    assert color == QColor(current_tokens()["danger"])  # kontrol kodu hatası


def test_inline_editor_unchanged(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "a", "b")])
    delegate = delegate_for(page, COL_TRANSLATION)
    assert isinstance(delegate, TranslationDelegate)
    parent = QWidget()
    qtbot.addWidget(parent)
    editor = delegate.createEditor(parent, option_for(page), page.proxy.index(0, COL_TRANSLATION))
    assert isinstance(editor, _Editor)
    with qtbot.waitSignal(editor.committed):
        QTest.keyClick(editor, Qt.Key.Key_Return)


def test_html_cache_is_bounded(qtbot: QtBot) -> None:
    rows = [make_row(i, f"metin {i}", f"çeviri {i}") for i in range(1, 201)]
    page = make_page(qtbot, rows)
    delegate = delegate_for(page, COL_SOURCE)
    delegate.cache_limit = 50
    for i in range(200):
        delegate.html_for(page.proxy.index(i, COL_SOURCE))
    assert delegate.cache_size() <= 50


def test_cache_follows_text_changes(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "eski", "x")])
    delegate = delegate_for(page, COL_SOURCE)
    first = delegate.html_for(page.proxy.index(0, COL_SOURCE))
    page.set_rows([make_row(1, "yeni", "x")])
    assert "yeni" in plain(delegate.html_for(page.proxy.index(0, COL_SOURCE)))
    assert "eski" in plain(first)


def test_5000_rows_fit_rows_fast(qtbot: QtBot) -> None:
    rows = [make_row(i, f"Line {i}: Hello there, how are you doing today?", f"Satır {i}: Merhaba") for i in range(5000)]
    page = TranslatePage()
    qtbot.addWidget(page)
    page.resize(1000, 700)
    page.show()
    start = time.perf_counter()
    page.set_rows(rows)
    page._fit_rows()
    assert time.perf_counter() - start < 3.0


def test_very_long_line_and_html_characters(qtbot: QtBot) -> None:
    long_text = "kelime " * 1500
    page = make_page(qtbot, [make_row(1, long_text, "<div> & ⟦ yarım"), make_row(2, "<b>kalın</b>", "")])
    for column in (COL_SOURCE, COL_TRANSLATION):
        delegate = delegate_for(page, column)
        for i in range(2):
            index: QModelIndex = page.proxy.index(i, column)
            assert delegate.html_for(index)
            assert delegate.sizeHint(option_for(page), index).height() > 0
    assert page.model.rows[0].source == long_text
    assert page.model.rows[1].source == "<b>kalın</b>"
    assert "<b>" not in delegate_for(page, COL_SOURCE).html_for(page.proxy.index(1, COL_SOURCE))


def test_find_spans_paint_matches_in_cell(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "a", "Bir iki üç")])
    page.open_find(False)
    page.find_bar.find_edit.setText("iki")
    delegate = delegate_for(page, COL_TRANSLATION)
    out = delegate.html_for(page.proxy.index(0, COL_TRANSLATION))
    tokens = current_tokens()
    assert f"background-color:{tokens['accent']}" in out  # tek eşleşme aynı zamanda o anki eşleşme
    assert "iki" in plain(out)
    other = delegate_for(page, COL_SOURCE).html_for(page.proxy.index(0, COL_SOURCE))
    assert f"background-color:{tokens['accent']}" not in other  # alan çeviri; orijinal hücresi boyanmaz


def test_find_preview_row_is_drawn_with_new_text_and_no_stale_spans(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "a", "Bir iki üç")])
    page.open_find(True)
    page.find_bar.find_edit.setText("iki")
    page.find_bar.replace_edit.setText("dört")
    page.find_bar.preview_box.setChecked(True)
    delegate = delegate_for(page, COL_TRANSLATION)
    out = delegate.html_for(page.proxy.index(0, COL_TRANSLATION))
    assert "dört" in plain(out)
    assert "iki" not in plain(out)
    assert f"background-color:{current_tokens()['accent']}" not in out  # eski metne ait aralıklar boyanmaz
    assert page.model.rows[0].translation == "Bir iki üç"  # yazılmadı


def test_delegate_underlines_copied_words_only_when_flagged(qtbot: QtBot) -> None:
    from nxceviri.core.spell.bloom import BloomFilter
    from nxceviri.core.spell.checker import SpellChecker

    spell = SpellChecker(BloomFilter.build(["merhaba", "oyun"], error_rate=0.0001))
    page = make_page(qtbot, [make_row(1, "Sunflare Spike", "Merhaba Sunflare Spike")])
    page.set_spell(spell, frozenset())
    index = page.proxy.index(0, COL_TRANSLATION)
    assert "text-decoration:underline" not in page.translation_delegate.html_for(index)
    spell.flag_copied = True
    page.set_spell(spell, frozenset())  # ayar değişince ana pencere yeniden bağlar
    assert "text-decoration:underline" in page.translation_delegate.html_for(index)
