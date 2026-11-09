"""Arayüz: çeviri tablosu (sıralama, kaydırma, sütun genişliği), yazı boyutu ve ipucu simgeleri."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QFont
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QToolButton
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.status import Status
from nxceviri.gui.main_window import MainWindow
from nxceviri.gui.theme import DEFAULT_FONT_SIZE, FONT_SIZES, ThemeMode, apply_theme, clamp_font_size
from nxceviri.gui.translate_page import (
    COL_KEY,
    COL_SOURCE,
    COL_STATUS,
    COL_TRANSLATION,
    TranslatePage,
)
from nxceviri.gui.widgets import Card, tip_html

pytestmark = pytest.mark.gui


def _row(
    i: int, source: str, translation: str = "", status: str = Status.UNTRANSLATED, key: str = ""
) -> TranslationRow:
    return TranslationRow(
        id=i,
        file="Data/a_en.bundle",
        key=key or f"K/{i}",
        source=source,
        translation=translation,
        status=status,
        note="",
        code_labels=(),
        max_length=None,
        context=key or f"K/{i}",
    )


SAMPLE = [
    _row(1, "Banana", "Muz", Status.MACHINE, "Z/1"),
    _row(2, "apple", "", Status.UNTRANSLATED, "A/2"),
    _row(3, "Cherry", "Kiraz", Status.APPROVED, "M/3"),
    _row(4, "Date", "Hurma", Status.ERROR, "B/4"),
    _row(5, "çilek", "", Status.UNTRANSLATED, "C/5"),
]


@pytest.fixture
def page(qtbot: QtBot) -> TranslatePage:
    p = TranslatePage()
    qtbot.addWidget(p)
    p.resize(1100, 700)
    p.show()
    p.set_rows(list(SAMPLE))
    return p


def _column(p: TranslatePage, col: int) -> list[str]:
    return [str(p.proxy.index(r, col).data()) for r in range(p.proxy.rowCount())]


def _ids(p: TranslatePage) -> list[int]:
    return [p.model.rows[p.proxy.mapToSource(p.proxy.index(r, 0)).row()].id for r in range(p.proxy.rowCount())]


def test_sort_by_column_and_back_to_original(page: TranslatePage) -> None:
    assert _ids(page) == [1, 2, 3, 4, 5]
    page.model.sort_by(COL_SOURCE, Qt.SortOrder.AscendingOrder)
    assert _ids(page) == [2, 1, 3, 5, 4]  # büyük/küçük harf ayırmaz; "çilek" Cherry'den sonra
    page.model.sort_by(COL_SOURCE, Qt.SortOrder.DescendingOrder)
    assert _ids(page) == [4, 5, 3, 1, 2]
    page.model.sort_by(COL_STATUS)
    assert [page.model.rows[i].status for i in range(5)] == [
        Status.ERROR,
        Status.UNTRANSLATED,
        Status.UNTRANSLATED,
        Status.MACHINE,
        Status.APPROVED,
    ]
    assert _ids(page)[1:3] == [2, 5]  # eşit durumda özgün sıra korunur
    page.model.sort_by(COL_KEY)
    assert _ids(page) == [2, 4, 5, 3, 1]
    page.model.sort_by(-1)
    assert _ids(page) == [1, 2, 3, 4, 5]


def test_header_click_cycles_ascending_descending_original(page: TranslatePage) -> None:
    h = page.table.horizontalHeader()
    x = h.sectionViewportPosition(COL_SOURCE) + 8

    def click() -> None:
        QTest.mouseClick(h.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(x, 4))

    click()
    assert (h.sortIndicatorSection(), h.sortIndicatorOrder()) == (COL_SOURCE, Qt.SortOrder.AscendingOrder)
    assert _ids(page) == [2, 1, 3, 5, 4]
    click()
    assert h.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
    assert _ids(page) == [4, 5, 3, 1, 2]
    click()
    assert h.sortIndicatorSection() == -1
    assert _ids(page) == [1, 2, 3, 4, 5]


def test_editing_while_sorted_does_not_move_rows(page: TranslatePage) -> None:
    page.model.sort_by(COL_TRANSLATION)
    before = _ids(page)
    page.model.commit = lambda changes: [_row(i, "x", t, Status.APPROVED) for i, t in changes]
    assert page.model.apply([(before[0], "ZZZ son")])
    assert _ids(page) == before  # düzenlenen satır yerinde kalır; sıra bir sonraki tıklamada güncellenir
    page.model.sort_by(COL_TRANSLATION, Qt.SortOrder.DescendingOrder)
    assert _ids(page)[0] == before[0]


def test_sort_keeps_filter_and_is_fast_on_large_tables(qtbot: QtBot) -> None:
    p = TranslatePage()
    qtbot.addWidget(p)
    p.resize(1100, 700)
    p.show()
    rows = [_row(i, f"Line {(i * 7919) % 20000:05d}", "") for i in range(1, 30001)]
    p.set_rows(rows)
    start = time.perf_counter()
    p.model.sort_by(COL_SOURCE, Qt.SortOrder.DescendingOrder)
    assert time.perf_counter() - start < 3.0
    assert p.proxy.index(0, COL_SOURCE).data() == "Line 19999"
    p.search.setText("Line 0000")
    assert 0 < p.proxy.rowCount() < 30000


def test_clearing_search_keeps_selected_row_in_view(qtbot: QtBot) -> None:
    """Arama temizlenince tablo başa dönmez; seçili satırın olduğu yerden devam eder."""
    p = TranslatePage()
    qtbot.addWidget(p)
    p.resize(900, 240)
    p.show()
    p.set_rows([_row(i, f"Satır {i:04d}", f"Çeviri {i:04d}") for i in range(1, 201)])
    p.search.setText("Satır 0150")
    assert p.proxy.rowCount() == 1
    p._select_proxy_row(0)
    p.search.clear()
    qtbot.waitUntil(lambda: p.table.rowAt(0) > 0)
    index = p.table.currentIndex()
    assert index.isValid()
    selected = p.proxy.mapToSource(index).row()
    assert selected == p.model.position(150)
    bottom = p.table.rowAt(p.table.viewport().height() - 1)
    assert p.table.rowAt(0) <= selected <= (bottom if bottom >= 0 else selected)


def test_columns_are_user_resizable_and_remembered(qtbot: QtBot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat)
    p = TranslatePage()
    qtbot.addWidget(p)
    p.bind_settings(settings)
    p.resize(1100, 700)
    p.show()
    p.set_rows(list(SAMPLE))
    h = p.table.horizontalHeader()
    for col in range(5):  # hepsi sürükleyerek ayarlanabilir (sabit/uzatılmış sütun yok)
        assert h.sectionResizeMode(col) == h.ResizeMode.Interactive
    h.resizeSection(COL_SOURCE, 333)
    assert str(settings.value("translate/column_widths")).split(",")[COL_SOURCE] == "333"

    q = TranslatePage()
    qtbot.addWidget(q)
    q.bind_settings(settings)
    q.resize(1100, 700)
    q.show()
    assert q.table.horizontalHeader().sectionSize(COL_SOURCE) == 333
    q.resize(1300, 700)  # elle ayarlanmış genişlikler pencere değişince bozulmaz
    assert q.table.horizontalHeader().sectionSize(COL_SOURCE) == 333


def _visible_width(p: TranslatePage) -> int:
    h = p.table.horizontalHeader()
    return sum(h.sectionSize(c) for c in range(h.count()) if not h.isSectionHidden(c))


def test_columns_fill_width_until_user_resizes(page: TranslatePage, qtbot: QtBot) -> None:
    assert abs(_visible_width(page) - page.table.viewport().width()) < 8
    page.resize(1400, 700)
    qtbot.waitUntil(lambda: abs(_visible_width(page) - page.table.viewport().width()) < 8)


def test_word_wrap_shows_whole_text(qtbot: QtBot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "w.ini"), QSettings.Format.IniFormat)
    p = TranslatePage()
    qtbot.addWidget(p)
    p.bind_settings(settings)
    p.resize(900, 600)
    p.show()
    long_text = "Uzun bir cümle " * 30
    p.set_rows([_row(1, "Short", "Kısa"), _row(2, long_text.strip(), long_text.strip())])
    assert p.table.wordWrap()  # varsayılan açık
    qtbot.waitUntil(lambda: p.table.rowHeight(1) > 3 * p.table.rowHeight(0))
    p.wrap_box.setChecked(False)
    qtbot.waitUntil(lambda: p.table.rowHeight(1) == p.table.rowHeight(0))
    assert not p.table.wordWrap()
    assert settings.value("translate/wrap") == "0"


def test_newlines_are_shown_as_real_breaks_not_symbols(qtbot: QtBot, page: TranslatePage) -> None:
    text = "Birinci satır\nİkinci satır"
    page.set_rows([_row(1, text, text), _row(2, "Tek", "Tek")])
    assert page.proxy.index(0, COL_SOURCE).data() == text
    assert page.proxy.index(0, COL_TRANSLATION).data() == text
    assert "⏎" not in str(page.proxy.index(0, COL_SOURCE).data())
    # Satır sonu gerçek satır olarak çizilir: hücre iki satırdan kısa olmaz.
    qtbot.waitUntil(lambda: page.table.rowHeight(0) > page.table.rowHeight(1) + 4)
    # Kaydırma kapalıyken satır sonları boşluğa döner; metin tek satırda kalır.
    page.wrap_box.setChecked(False)
    assert page.proxy.index(0, COL_SOURCE).data() == "Birinci satır İkinci satır"
    qtbot.waitUntil(lambda: page.table.rowHeight(0) == page.table.rowHeight(1))


def test_qa_table_shows_newlines_as_real_breaks() -> None:
    from nxceviri.core.qa.checks import QaIssue
    from nxceviri.gui.qa_page import COL_SOURCE as QA_SOURCE
    from nxceviri.gui.qa_page import COL_TRANSLATION as QA_TRANSLATION
    from nxceviri.gui.qa_page import IssueModel

    source, translation = "Birinci\nİkinci", "Birinci\nİkinci"
    rows = {1: _row(1, source, translation)}
    model = IssueModel()
    model.set_issues([QaIssue(1, "K/1", "spaces", "warning", "Sorun")], rows)
    assert model.index(0, QA_SOURCE).data() == source
    assert model.index(0, QA_TRANSLATION).data() == translation


def test_row_heights_are_measured_lazily(qtbot: QtBot) -> None:
    p = TranslatePage()
    qtbot.addWidget(p)
    p.resize(900, 600)
    p.show()
    text = "Çok uzun bir metin " * 40
    p.set_rows([_row(i, text, text) for i in range(1, 5001)])
    qtbot.waitUntil(lambda: p.table.rowHeight(0) > 80)
    single = p.table.verticalHeader().defaultSectionSize()
    assert p.table.rowHeight(4000) == single  # ekrandan uzaktaki satırlar ölçülmedi (arayüz donmaz)
    p.table.scrollToBottom()
    qtbot.waitUntil(lambda: p.table.rowHeight(4999) > 80)


def test_font_size_clamp_and_stylesheet(qtbot: QtBot) -> None:
    assert clamp_font_size(10.4) == 10
    assert clamp_font_size(100) == max(FONT_SIZES)
    assert clamp_font_size(-3) == min(FONT_SIZES)
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    original = QFont(app.font())
    palette, style = app.palette(), app.styleSheet()
    try:
        apply_theme(app, ThemeMode.LIGHT, 14)
        assert "font-size: 14pt" in app.styleSheet()
        assert "font-size: 23.8pt" in app.styleSheet()  # sayfa başlığı 1,7 kat
        assert app.font().pointSizeF() == 14
    finally:
        # Tema uygulaması uygulama genelindedir; sonraki testlerin ölçülerini etkilememesi için geri alınır.
        app.setFont(original)
        app.setPalette(palette)
        app.setStyleSheet(style)


def test_font_size_menu_shortcuts_and_persistence(qtbot: QtBot, tmp_path: Path) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    original = QFont(app.font())
    palette, style = app.palette(), app.styleSheet()
    settings = QSettings(str(tmp_path / "f.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.show()
    try:
        w._set_font_size(12)
        # FontChange olayı gecikebilir; genişliği olay döngüsüne bırakmadan aynı işleyiciyi çağır.
        w._update_nav_width()
        small = w.nav_column.maximumWidth()
        w._set_font_size(18)
        w._update_nav_width()
        assert w.nav_column.maximumWidth() > small  # adım listesi büyük yazıda da sığar
        w._set_font_size(12)
        assert settings.value("ui/font_size") == 12
        assert app.font().pointSizeF() == 12
        w._step_font_size(1)
        assert w._font_size() == 14
        w._step_font_size(-1)
        w._step_font_size(-1)
        assert w._font_size() == 11
        checked = [a.text() for a in w.size_group.actions() if a.isChecked()]
        assert checked == ["11 punto"]
        w._set_font_size(max(FONT_SIZES))
        w._step_font_size(1)  # üst sınırda kalır
        assert w._font_size() == max(FONT_SIZES)
        w._set_font_size(DEFAULT_FONT_SIZE)
        assert w._font_size() == DEFAULT_FONT_SIZE
        settings.setValue("ui/font_size", "bozuk")
        assert w._font_size() == DEFAULT_FONT_SIZE
    finally:
        w.dirty = False
        w.close()
        app.setFont(original)
        app.setPalette(palette)
        app.setStyleSheet(style)


def test_card_hint_is_title_tooltip(qtbot: QtBot) -> None:
    card = Card("Başlık", hint="Uzun bir açıklama <b>etiketi</b> & işareti")
    qtbot.addWidget(card)
    tip = card.title.toolTip()
    assert "Uzun bir açıklama" in tip
    assert "&lt;b&gt;" in tip  # kullanıcı metni HTML olarak yorumlanmaz
    assert tip == tip_html("Uzun bir açıklama <b>etiketi</b> & işareti")
    assert not card.findChildren(QToolButton)  # "i" düğmesi yok; bilgi başlığın ipucunda
    assert "<br>" in tip_html("a\nb")
    plain = Card("Açıklamasız")
    qtbot.addWidget(plain)
    assert not plain.title.toolTip()


def test_pages_have_no_long_visible_descriptions(qtbot: QtBot, tmp_path: Path) -> None:
    """Uzun açıklamalar ipucuna taşındı: sayfalarda görünen açıklama etiketleri kısa kalır."""
    from PySide6.QtWidgets import QLabel

    settings = QSettings(str(tmp_path / "t.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.show()
    try:
        for page in (w.add_page, w.scan_page, w.translate_page, w.qa_page, w.export_page):
            for lbl in page.findChildren(QLabel):
                if lbl.property("role") == "muted" and lbl.text() and not lbl.text().startswith("<"):
                    assert len(lbl.text()) <= 90, lbl.text()
        for page in (w.qa_page, w.export_page, w.scan_page):  # Çevir sayfasında başlık yok (tablo tüm yeri kullanır)
            titles = [lbl for lbl in page.findChildren(QLabel) if lbl.property("role") == "pageTitle"]
            assert titles
            assert titles[0].toolTip(), "açıklama başlığın ipucu olarak durmalı"
        assert COL_KEY == 4
    finally:
        w.dirty = False
        w.close()


def test_copy_selected_rows_to_clipboard(page: TranslatePage) -> None:
    clipboard = QApplication.clipboard()
    page.table.selectRow(0)
    page.table.selectionModel().select(
        page.proxy.index(2, 0),
        page.table.selectionModel().SelectionFlag.Select | page.table.selectionModel().SelectionFlag.Rows,
    )
    page.copy_to_clipboard("source")
    assert clipboard.text() == "Banana\nCherry"
    page.copy_to_clipboard("translation")
    assert clipboard.text() == "Muz\nKiraz"
    page.copy_to_clipboard("both")
    assert clipboard.text() == "Banana\nMuz\n\nCherry\nKiraz"


def test_copy_follows_table_order_and_ctrl_c_copies_both(page: TranslatePage, qtbot: QtBot) -> None:
    page.model.sort_by(COL_SOURCE, Qt.SortOrder.DescendingOrder)  # Date, çilek, Cherry, Banana, apple
    page.table.selectAll()
    page.copy_to_clipboard("source")
    assert QApplication.clipboard().text() == "Date\nçilek\nCherry\nBanana\napple"
    QApplication.clipboard().clear()
    page.table.selectRow(0)
    page.table.setFocus()
    QTest.keyClick(page.table, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == "Date\nHurma"


def test_copy_without_selection_does_nothing(page: TranslatePage) -> None:
    QApplication.clipboard().setText("eski")
    page.table.clearSelection()
    page.copy_to_clipboard("both")
    assert QApplication.clipboard().text() == "eski"


def test_search_looks_only_at_source_and_translation(qtbot: QtBot) -> None:
    """Arama kutusu anahtar ve dosya adında aramaz: "/(" gibi kod parçaları anahtardan dolayı hepsini getirmesin."""
    p = TranslatePage()
    qtbot.addWidget(p)
    p.set_rows(
        [
            _row(1, "Start", "Başla", key="/(ui_story)"),
            _row(2, "Quit", "Çık\n/(leaked_key)", key="ui_quit"),
            _row(3, "Menu", "Menü", key="menu_a_en"),
        ]
    )
    p.search.setText("/(")
    assert [p.proxy.index(r, COL_SOURCE).data() for r in range(p.proxy.rowCount())] == [
        "Quit"
    ]  # yalnızca çeviride geçen
    p.search.setText("ui_story")
    assert p.proxy.rowCount() == 0  # anahtarda geçiyor ama metinde değil
    p.search.setText("a_en.bundle")
    assert p.proxy.rowCount() == 0  # dosya adı
    p.search.setText("başla")
    assert p.proxy.rowCount() == 1
    assert "Orijinal ve çeviri" in p.search.toolTip()


def test_translate_page_has_no_title_row(qtbot: QtBot) -> None:
    p = TranslatePage()
    qtbot.addWidget(p)
    texts = {w.text() for w in p.findChildren(QLabel) if w.isVisibleTo(p)}
    assert "Çevir" not in texts  # sayfa başlığı yok
    assert "Çeviri tablosu" not in texts  # kart başlığı yok
