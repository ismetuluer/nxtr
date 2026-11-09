"""Bul ve Değiştir çubuğu: sayaç, gezinme, seçenekler, vurgu, önizleme, değiştirme ve geri alma."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.status import Status
from nxceviri.gui import find_replace
from nxceviri.gui.find_replace import (
    FIELD_SOURCE,
    FIND_SPANS_ROLE,
    SCOPE_SELECTED,
    SCOPE_VISIBLE,
    FindCell,
)
from nxceviri.gui.main_window import STEP_TRANSLATE, MainWindow
from nxceviri.gui.marked_delegate import ROW_ROLE
from nxceviri.gui.translate_page import COL_SOURCE, COL_TRANSLATION, TranslatePage
from tests.test_editor import _project, _rows
from tests.test_marked_delegate import make_row

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


class Writer:
    """Sayfanın `replace_fn` yolu yerine: çağrıları kaydeder ve satırları günceller."""

    def __init__(self, page: TranslatePage) -> None:
        self.page = page
        self.calls: list[list[tuple[int, str]]] = []

    def __call__(self, changes: list[tuple[int, str]]) -> list[TranslationRow]:
        self.calls.append(list(changes))
        updated: list[TranslationRow] = []
        for row_id, text in changes:
            row = self.page.model.row_by_id(row_id)
            assert row is not None
            updated.append(replace(row, translation=text, status=Status.MACHINE))
        self.page.model.update_rows(updated)
        return updated


def make_rows() -> list[TranslationRow]:
    return [
        make_row(1, "Have a drink", "Benimle bir içki iç."),
        make_row(2, "That's the limit", "Bu limit! İçki yok."),
        make_row(3, "Make ⟦1⟧ the goal", "Hedefi ⟦1⟧ yap", labels=("Satır sonu",)),
        make_row(4, "Not me", "Ben içmem."),
        make_row(5, "Empty", ""),
    ]


def make_page(qtbot: QtBot) -> tuple[TranslatePage, Writer]:
    page = TranslatePage()
    qtbot.addWidget(page)
    page.resize(1300, 1000)
    page.show()
    writer = Writer(page)
    page.replace_fn = writer
    page.set_rows(make_rows())
    return page, writer


def spans_of(page: TranslatePage, row_id: int, column: int = COL_TRANSLATION) -> tuple[tuple[int, int], ...] | None:
    position = page.model.position(row_id)
    assert position is not None
    cell = page.model.index(position, column).data(FIND_SPANS_ROLE)
    return None if cell is None else cell.spans


def fire(page: TranslatePage, keys: str) -> None:
    """Kısayolun çalıştırdığı sayfa yöntemini çağırır. Tuşlar ana pencerenin menü eylemlerindedir ve kayıt
    defterinden gelir (tests/test_menus.py); gerçek tuş vuruşu Qt'nin tuş durumunu bozup başka testleri etkiler."""
    {
        "Ctrl+F": lambda: page.open_find(False),
        "Ctrl+H": lambda: page.open_find(True),
        "Ctrl+Shift+F": page.focus_search,
        "F3": page.find_next,
        "Shift+F3": page.find_previous,
    }[keys]()


def activate(qtbot: QtBot, page: TranslatePage) -> None:
    """Odak testleri için pencereyi etkin yapar (ekransız ortamda odak ancak etkin pencerede olur)."""
    page.activateWindow()
    qtbot.waitUntil(page.isActiveWindow, timeout=3000)


def test_ctrl_f_and_ctrl_h_open_the_bar_and_esc_closes(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    activate(qtbot, page)
    bar = page.find_bar
    assert not bar.isVisibleTo(page)
    fire(page, "Ctrl+F")
    assert bar.isVisibleTo(page)
    assert bar.find_edit.hasFocus()
    assert not bar.replace_row.isVisibleTo(page)
    fire(page, "Ctrl+H")
    assert bar.replace_row.isVisibleTo(page)  # Ctrl+H değiştir alanını da açar
    qtbot.keyClick(bar.find_edit, Qt.Key.Key_Escape)
    assert not bar.isVisibleTo(page)
    assert page.table.hasFocus()


def test_ctrl_shift_f_still_reaches_the_table_filter(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    activate(qtbot, page)
    fire(page, "Ctrl+Shift+F")
    assert page.search.hasFocus()
    assert not page.find_bar.isVisibleTo(page)


def test_counter_next_previous_select_rows_without_filtering(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    bar = page.find_bar
    page.open_find(False)
    bar.find_edit.setText("içki")  # satır 1 ve 2 (büyük/küçük harf yok sayılır)
    assert bar.count_label.text() == "1 / 2"
    assert bar.match_count == 2
    assert page.proxy.rowCount() == 5  # tablo süzülmez
    current = page.current_row()
    assert current is not None
    assert current.id == 1
    bar.next()
    assert bar.count_label.text() == "2 / 2"
    current = page.current_row()
    assert current is not None
    assert current.id == 2
    bar.next()  # sona gelince başa döner
    assert bar.count_label.text() == "1 / 2"
    bar.previous()
    assert bar.count_label.text() == "2 / 2"
    bar.find_edit.setText("yokboyle")
    assert bar.count_label.text() == "Eşleşme yok"
    assert not bar.next_button.isEnabled()


def test_typing_starts_from_the_current_row(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    page._select_proxy_row(1)
    page.open_find(False)
    page.find_bar.find_edit.setText("içki")
    assert page.find_bar.current_id == 2  # geçerli satırdan sonraki ilk eşleşme, başa atlamaz
    assert page.find_bar.count_label.text() == "2 / 2"


def test_f3_and_shift_f3_navigate_only_while_open(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    page.open_find(False)
    page.find_bar.find_edit.setText("i")
    first = page.find_bar.current_id
    fire(page, "F3")
    assert page.find_bar.current_id != first
    fire(page, "Shift+F3")
    assert page.find_bar.current_id == first
    page.find_bar.close_bar()
    page._select_proxy_row(0)
    fire(page, "F3")  # çubuk kapalı: sonraki bakılacak satıra gider (bul gezinmesi değil)
    assert not page.find_bar.isVisibleTo(page)


def test_options_case_whole_word_regex(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    bar = page.find_bar
    page.open_find(False)
    bar.find_edit.setText("ben")
    assert bar.match_count == 2  # "Benimle", "Ben"
    bar.case_button.setChecked(True)
    assert bar.match_count == 0  # küçük "ben" yok
    bar.case_button.setChecked(False)
    bar.word_button.setChecked(True)
    assert bar.match_count == 1  # yalnızca "Ben" sözcüğü
    bar.word_button.setChecked(False)
    bar.regex_button.setChecked(True)
    bar.find_edit.setText("B[ae]n")
    assert bar.match_count == 2
    bar.find_edit.setText("içk(")
    assert bar.count_label.text() == "Geçersiz"
    assert bar.error.startswith("Düzenli ifade geçersiz")
    assert not bar.replace_all_button.isEnabled()


def test_scope_visible_and_selected(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    bar = page.find_bar
    page.open_find(False)
    bar.find_edit.setText("içki")
    assert bar.match_count == 2
    page.search.setText("limit")  # tabloda yalnızca satır 2 görünür
    assert bar.match_count == 2  # kapsam "Tümü": süzgeçten bağımsız
    bar.set_scope(SCOPE_VISIBLE)
    assert bar.match_count == 1
    page.search.setText("")
    page._select_proxy_row(0)
    bar.set_scope(SCOPE_SELECTED)
    assert bar.match_count == 1
    bar.next()  # gezinirken seçim değişse bile kapsam seçildiği andaki satırlarda kalır
    assert bar.match_count == 1
    assert bar.current_id == 1


def test_spans_are_painted_and_cleared(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    page.open_find(False)
    page.find_bar.find_edit.setText("İçki")
    assert spans_of(page, 1) == ((12, 16),)
    assert spans_of(page, 4) is None
    assert spans_of(page, 1, COL_SOURCE) is None
    cell = page.model.index(0, COL_TRANSLATION).data(FIND_SPANS_ROLE)
    assert isinstance(cell, FindCell)
    assert cell.current  # o anki eşleşme
    other = page.model.index(1, COL_TRANSLATION).data(FIND_SPANS_ROLE)
    assert isinstance(other, FindCell)
    assert not other.current
    page.find_bar.close_bar()
    assert spans_of(page, 1) is None


def test_field_source_finds_in_original_and_cannot_replace(qtbot: QtBot) -> None:
    page, writer = make_page(qtbot)
    bar = page.find_bar
    page.open_find(True)
    bar.set_field(FIELD_SOURCE)
    bar.find_edit.setText("drink")
    assert bar.match_count == 1
    assert spans_of(page, 1, COL_SOURCE) == ((7, 12),)
    assert spans_of(page, 1, COL_TRANSLATION) is None
    bar.replace_edit.setText("x")
    assert not bar.replace_button.isEnabled()
    assert not bar.replace_all_button.isEnabled()
    bar.replace_all()
    assert writer.calls == []


def test_preview_shows_new_text_without_writing(qtbot: QtBot) -> None:
    page, writer = make_page(qtbot)
    bar = page.find_bar
    page.open_find(True)
    bar.find_edit.setText("içki")
    bar.replace_edit.setText("su")
    display = Qt.ItemDataRole.DisplayRole
    assert page.model.index(0, COL_TRANSLATION).data(display) == "Benimle bir içki iç."  # önizleme kapalı
    bar.preview_box.setChecked(True)
    assert page.model.index(0, COL_TRANSLATION).data(display) == "Benimle bir su iç."
    assert page.model.index(1, COL_TRANSLATION).data(display) == "Bu limit! İçki yok.".replace("İçki", "su")
    assert page.model.index(3, COL_TRANSLATION).data(display) == "Ben içmem."  # eşleşmeyen satır
    assert page.model.index(0, COL_TRANSLATION).data(Qt.ItemDataRole.EditRole) == "Benimle bir içki iç."
    shown = page.model.index(0, COL_TRANSLATION).data(ROW_ROLE)  # hücre çizimi satırı bu rolden okur
    assert shown.translation == "Benimle bir su iç."
    assert page.model.index(3, COL_TRANSLATION).data(ROW_ROLE).translation == "Ben içmem."
    assert writer.calls == []  # hiçbir şey yazılmadı
    row = page.model.row_by_id(1)
    assert row is not None
    assert row.translation == "Benimle bir içki iç."
    bar.preview_box.setChecked(False)
    assert page.model.index(0, COL_TRANSLATION).data(display) == "Benimle bir içki iç."
    bar.preview_box.setChecked(True)
    bar.close_bar()  # çubuk kapanınca önizleme kaybolur
    assert page.model.index(0, COL_TRANSLATION).data(display) == "Benimle bir içki iç."


def test_replace_current_writes_one_row_and_moves_on(qtbot: QtBot) -> None:
    page, writer = make_page(qtbot)
    bar = page.find_bar
    page.open_find(True)
    bar.find_edit.setText("içki")
    bar.replace_edit.setText("su")
    bar.replace_button.click()
    assert writer.calls == [[(1, "Benimle bir su iç.")]]
    assert bar.match_count == 1
    assert bar.current_id == 2  # sonraki eşleşmeye geçti
    assert "1 satır değiştirildi" in bar.status_label.text()
    bar.replace_button.click()
    assert [c[0][0] for c in writer.calls] == [1, 2]
    assert bar.match_count == 0
    assert not bar.replace_button.isEnabled()


def test_replace_that_still_matches_moves_to_the_next_row(qtbot: QtBot) -> None:
    page, writer = make_page(qtbot)
    bar = page.find_bar
    page.open_find(True)
    bar.find_edit.setText("içki")
    bar.replace_edit.setText("içkiler")  # yerine yazılan metin aranan metni içeriyor
    bar.replace_button.click()
    assert writer.calls == [[(1, "Benimle bir içkiler iç.")]]
    assert bar.current_id == 2  # aynı satırda takılmaz


def test_replace_all_is_one_call_and_reports_count(qtbot: QtBot) -> None:
    page, writer = make_page(qtbot)
    bar = page.find_bar
    page.open_find(True)
    bar.find_edit.setText("içki")
    bar.replace_edit.setText("su")
    bar.replace_all_button.click()
    assert writer.calls == [[(1, "Benimle bir su iç."), (2, "Bu limit! su yok.")]]
    assert "2 satır değiştirildi" in bar.status_label.text()
    assert bar.match_count == 0


def test_replace_never_breaks_control_codes(qtbot: QtBot) -> None:
    page, writer = make_page(qtbot)
    bar = page.find_bar
    page.open_find(True)
    bar.find_edit.setText("1")  # ⟦1⟧ kodunun içi: değişirse kod bozulur
    bar.replace_edit.setText("2")
    assert bar.match_count == 1
    bar.replace_all_button.click()
    assert writer.calls == []  # hiçbir şey yazılmadı
    assert "1 satır atlandı" in bar.status_label.text()
    row = page.model.row_by_id(3)
    assert row is not None
    assert row.translation == "Hedefi ⟦1⟧ yap"


def test_edits_made_elsewhere_refresh_matches(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    bar = page.find_bar
    page.open_find(False)
    bar.find_edit.setText("içki")
    assert bar.match_count == 2
    row = page.model.row_by_id(2)
    assert row is not None
    page.model.update_rows([replace(row, translation="Bu limit!")])  # tabloda elle düzenleme / geri alma
    qtbot.waitUntil(lambda: bar.match_count == 1, timeout=3000)
    assert bar.count_label.text() == "1 / 1"


def test_busy_machine_job_disables_replace(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    bar = page.find_bar
    page.open_find(True)
    bar.find_edit.setText("içki")
    assert bar.replace_all_button.isEnabled()
    page.set_machine_running(True)
    assert not bar.replace_all_button.isEnabled()
    page.set_machine_running(False)
    assert bar.replace_all_button.isEnabled()


def test_match_spans_skip_empty_matches() -> None:
    import re

    assert find_replace.match_spans(re.compile("a*"), "baab") == ((1, 3),)


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    from nxceviri.core.secrets import MemoryStore

    w = MainWindow(QSettings(str(tmp_path / "b.ini"), QSettings.Format.IniFormat))
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.resize(1180, 780)
    w.show()
    w.nav.setCurrentRow(STEP_TRANSLATE)
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def test_replace_all_in_app_is_one_undo_step(window: MainWindow) -> None:
    page = window.translate_page
    window._menu_find_replace()  # Düzen menüsü: çubuk değiştir alanıyla açılır
    bar = page.find_bar
    assert bar.isVisibleTo(page)
    assert bar.replace_row.isVisibleTo(page)
    bar.find_edit.setText("i")
    bar.replace_edit.setText("ı")
    assert bar.match_count == 3
    bar.replace_all_button.click()
    rows = _rows(window)
    assert rows["s01"].translation == "Benımle bır ıçkı ıç."
    assert rows["s02"].translation == "Bu lımıt!"
    assert rows["s04"].translation == "Ben ıçmem."
    assert rows["s04"].status == Status.APPROVED  # onaylı satır onaylı kalır
    assert rows["s01"].status == Status.MACHINE
    assert page.changes_button.text() == "Son İşin Değişiklikleri (3)…"
    window.undo_last()  # Ctrl+Z hepsini birden geri alır
    rows = _rows(window)
    assert rows["s01"].translation == "Benimle bir içki iç."
    assert rows["s02"].translation == "Bu limit!"
    assert rows["s04"].translation == "Ben içmem."


def test_single_replace_in_app_is_its_own_undo_step(window: MainWindow) -> None:
    page = window.translate_page
    window._menu_find_replace()
    bar = page.find_bar
    bar.find_edit.setText("içki")
    bar.replace_edit.setText("su")
    bar.replace_button.click()
    assert _rows(window)["s01"].translation == "Benimle bir su iç."
    window.undo_last()
    assert _rows(window)["s01"].translation == "Benimle bir içki iç."


def test_edit_menu_find_opens_the_bar(window: MainWindow) -> None:
    window._menu_find()
    assert window.translate_page.find_bar.isVisibleTo(window.translate_page)
    assert not window.translate_page.find_bar.replace_row.isVisibleTo(window.translate_page)
    texts = [a.text() for a in window.menuBar().actions()]
    assert any("Düzen" in t.replace("&", "") for t in texts)
