"""Çevir tablosu hücre çizimi: semboller, sözcük sınırında kaydırma, yazım çizgisi, salt okunur Orijinal görünümü."""

from __future__ import annotations

import time
from collections.abc import Collection

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QImage, QPainter, QTextCharFormat, QTextDocument
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
from pytestqt.qtbot import QtBot

from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.gui.marked_delegate import _SourceViewer
from nxceviri.gui.translate_page import COL_SOURCE, COL_TRANSLATION, TranslatePage
from tests.test_marked_delegate import _restore_app, delegate_for, make_page, make_row, option_for  # noqa: F401

pytestmark = pytest.mark.gui

PAD = 2 * 4  # yatay iç boşluk (iki kenar)
WORDS = ["onları", "yiyorsun", "yer", "misin", "ve", "yemek", "için", "bas", "var"]


class CountingSpell(SpellChecker):
    """Kaç kez hesaplandığını sayar (önbellek testi)."""

    def __init__(self) -> None:
        super().__init__(BloomFilter.build(WORDS, error_rate=0.0001))
        self.calls = 0

    def unknown_spans(
        self, text: str, source: str = "", extra: Collection[str] = frozenset()
    ) -> list[tuple[int, int, str]]:
        self.calls += 1
        return super().unknown_spans(text, source, extra)


def line_texts(doc: QTextDocument) -> list[str]:
    """Belgenin görsel satırları (kaydırma sonrası), sıfır genişlikli bölme işaretleri atılmış."""
    doc.size()  # yerleşimi zorlar
    out: list[str] = []
    block = doc.begin()
    while block.isValid():
        text = block.text()
        layout = block.layout()
        assert layout is not None
        for i in range(layout.lineCount()):
            line = layout.lineAt(i)
            out.append(text[line.textStart() : line.textStart() + line.textLength()].replace("\u200b", ""))
        block = block.next()
    return out


def narrow_option(page: TranslatePage, before: str, word: str) -> QStyleOptionViewItem:
    """`before + word` tek satıra sığmayacak, `word` tek başına sığacak genişlikte seçenek."""
    metrics = page.table.fontMetrics()
    full = metrics.horizontalAdvance(before + word)
    width = full - metrics.horizontalAdvance(word) // 2 + PAD  # sözcüğün yarısı kadar taşar
    return option_for(page, width)


@pytest.mark.parametrize("symbols", [False, True])
def test_wrap_breaks_at_word_boundary_not_inside_word(qtbot: QtBot, symbols: bool) -> None:
    page = make_page(qtbot, [make_row(1, "Onları yiyorsun.", "Onları yiyorsun.")])
    page.set_view(symbols, "left")
    option = narrow_option(page, "Onları ", "yiyorsun.")
    for column in (COL_SOURCE, COL_TRANSLATION):
        delegate = delegate_for(page, column)
        lines = line_texts(delegate.document(option, page.proxy.index(0, column)))
        words = [w.strip("·¶") for line in lines for w in line.replace("·", " ").split()]
        assert words == ["Onları", "yiyorsun."]
        assert len(lines) == 2
        assert lines[1].replace("·", " ").strip() == "yiyorsun."


def test_word_longer_than_cell_is_split_as_last_resort(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "Süpercalifragilistikekspiyalidoşıs", "x")])
    page.set_view(True, "left")
    delegate = delegate_for(page, COL_SOURCE)
    lines = line_texts(delegate.document(option_for(page, 70), page.proxy.index(0, COL_SOURCE)))
    assert len(lines) > 1
    assert "".join(lines) == "Süpercalifragilistikekspiyalidoşıs"


def test_symbols_cover_space_newline_tab_nbsp_and_code_chip(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "a b\nc\td e ⟦1⟧", "x", labels=("Satır sonu",))])
    page.set_view(True, "left")
    delegate = delegate_for(page, COL_SOURCE)
    doc = delegate.document(option_for(page, 400), page.proxy.index(0, COL_SOURCE))
    shown = doc.toPlainText()
    for glyph in ("·", "¶", "→", "°", "↵1"):
        assert glyph in shown, glyph
    page.set_view(False, "left")
    plain = delegate.document(option_for(page, 400), page.proxy.index(0, COL_SOURCE)).toPlainText()
    for glyph in ("·", "¶", "→", "°"):
        assert glyph not in plain, glyph


def test_symbols_are_painted(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "a b\nc", "x")])
    delegate = delegate_for(page, COL_SOURCE)
    index = page.proxy.index(0, COL_SOURCE)

    def render(symbols: bool) -> QImage:
        page.set_view(symbols, "left")
        option = option_for(page, 200)
        size = delegate.sizeHint(option, index)
        option.rect.setSize(size)
        image = QImage(size, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        delegate.paint(painter, option, index)
        painter.end()
        return image

    assert render(True) != render(False)


def test_size_hint_matches_painted_document(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "Onları yiyorsun. Onları yer misin? Hepsini yemek için bas.", "x")])
    page.set_view(True, "left")
    delegate = delegate_for(page, COL_SOURCE)
    index = page.proxy.index(0, COL_SOURCE)
    option = option_for(page, 150)
    doc = delegate.document(option, index)
    hint = delegate.sizeHint(option, index)
    assert hint.height() == int(doc.size().height()) + 6
    lines = line_texts(doc)
    assert len(lines) >= 3
    assert doc.size().height() >= len(lines) * page.table.fontMetrics().height()  # hiçbir satır kesilmez


def test_default_alignment_is_left(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "a", "b")])
    assert page.view_actions.align == "left"
    assert delegate_for(page, COL_TRANSLATION).align == "left"


# --- yazım çizgisi ----------------------------------------------------------------------


def waves(doc: QTextDocument) -> list[str]:
    found: list[str] = []
    block = doc.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.charFormat().underlineStyle() == QTextCharFormat.UnderlineStyle.WaveUnderline:
                found.append(fragment.text())
            it += 1
        block = block.next()
    return found


def test_translation_cell_underlines_unknown_words_only(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "Eat them all, Xyzzy.", "Onları yiyorsun xqzv, Qwxp ve yer misin")])
    page.set_spell(CountingSpell(), frozenset())
    option = option_for(page, 600)
    translation = delegate_for(page, COL_TRANSLATION).document(option, page.proxy.index(0, COL_TRANSLATION))
    assert waves(translation) == ["xqzv"]  # cümle ortasındaki büyük harfli sözcük özel ad sayılır
    source = delegate_for(page, COL_SOURCE).document(option, page.proxy.index(0, COL_SOURCE))
    assert waves(source) == []  # yalnızca çeviri hücresi denetlenir


def test_spell_skips_source_words_glossary_and_user_words(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "Zorg here", "Zorg xqzv terimx")])
    spell = CountingSpell()
    page.set_spell(spell, frozenset({"terimx"}))
    option = option_for(page, 600)
    delegate = delegate_for(page, COL_TRANSLATION)
    index = page.proxy.index(0, COL_TRANSLATION)
    assert waves(delegate.document(option, index)) == ["xqzv"]
    spell.add_user_words(["xqzv"])
    page.set_spell(spell, frozenset({"terimx"}))  # sözlük değişince önbellek geçersiz olur
    assert waves(delegate.document(option, index)) == []


def test_spell_results_are_cached_per_row_and_text(qtbot: QtBot) -> None:
    rows = [make_row(i, "src", f"yer xq{i}") for i in range(1, 6)]
    page = make_page(qtbot, rows)
    spell = CountingSpell()
    page.set_spell(spell, frozenset())
    delegate = delegate_for(page, COL_TRANSLATION)
    spell.calls = 0
    for _ in range(3):
        for i in range(5):
            delegate.html_for(page.proxy.index(i, COL_TRANSLATION))
    assert spell.calls == 5  # her satır yalnızca bir kez denetlendi
    page.set_rows([make_row(1, "src", "yer yeniden"), *rows[1:]])
    delegate.html_for(page.proxy.index(0, COL_TRANSLATION))
    assert spell.calls == 6  # metin değişince yeniden hesaplanır


def test_only_painted_cells_are_checked(qtbot: QtBot) -> None:
    rows = [make_row(i, "src", f"yer xq{i}") for i in range(1, 2001)]
    page = TranslatePage()
    qtbot.addWidget(page)
    page.resize(900, 600)
    page.show()
    page.set_rows(rows)
    spell = CountingSpell()
    page.set_spell(spell, frozenset())
    QTest.qWait(50)
    assert 0 < spell.calls < 400  # 2.000 satırın yalnızca görünenleri (ve kenar payı) ölçüldü


def test_5000_rows_scrolling_stays_fast(qtbot: QtBot) -> None:
    rows = [
        make_row(i, f"Line {i}: Hello there, how are you doing today?", f"Satır {i}: Merhaba yer xq{i}")
        for i in range(5000)
    ]
    page = TranslatePage()
    qtbot.addWidget(page)
    page.resize(1000, 700)
    page.show()
    page.set_rows(rows)
    page.set_spell(CountingSpell(), frozenset())
    page.set_view(True, "left")
    bar = page.table.verticalScrollBar()
    start = time.perf_counter()
    for step in range(30):
        bar.setValue(step * 150)
        page._fit_rows()
        page.table.viewport().repaint()
    assert time.perf_counter() - start < 6.0


# --- Orijinal hücresi: salt okunur görünüm ----------------------------------------------


def test_double_click_on_source_opens_readonly_selectable_viewer(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "Kopyalanacak metin ⟦1⟧", "x")])
    page.resize(900, 500)
    page.show()
    delegate = delegate_for(page, COL_SOURCE)
    assert delegate.viewer is None
    index = page.proxy.index(0, COL_SOURCE)
    rect = page.table.visualRect(index)
    QTest.mouseClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(rect.center()))
    QTest.mouseDClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(rect.center()))
    viewer: object = delegate.viewer
    assert isinstance(viewer, _SourceViewer)
    assert viewer.isReadOnly()
    assert viewer.toPlainText() == "Kopyalanacak metin ⟦1⟧"
    QApplication.clipboard().clear()
    viewer.selectAll()
    QTest.keyClick(viewer, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == "Kopyalanacak metin ⟦1⟧"
    QTest.keyClick(viewer, Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(viewer, "yazma")
    assert viewer.toPlainText() == "Kopyalanacak metin ⟦1⟧"  # metin değişmez
    assert page.model.rows[0].source == "Kopyalanacak metin ⟦1⟧"
    QTest.keyClick(viewer, Qt.Key.Key_Escape)
    qtbot.waitUntil(lambda: delegate.viewer is None)


def test_translation_without_spell_checker_has_no_waves(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "a", "xqzv")])
    doc = delegate_for(page, COL_TRANSLATION).document(option_for(page, 300), page.proxy.index(0, COL_TRANSLATION))
    assert waves(doc) == []


def test_double_click_on_translation_still_edits(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "a", "b")])
    page.resize(900, 500)
    page.show()
    index = page.proxy.index(0, COL_TRANSLATION)
    rect = page.table.visualRect(index)
    QTest.mouseClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(rect.center()))
    QTest.mouseDClick(page.table.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(rect.center()))
    assert page.table.state() == page.table.State.EditingState
    assert delegate_for(page, COL_SOURCE).viewer is None
