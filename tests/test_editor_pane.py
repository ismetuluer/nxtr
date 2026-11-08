"""Düzenleme paneli: özgün/çeviri, kod çipleri, sayaç ve kaydetme kuralları."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QTextOption
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.codekinds import KIND_LINE_BREAK, KIND_OTHER, KIND_PAGE_BREAK
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.status import Status
from nxceviri.gui.editor_pane import (
    BASIS_MANUAL,
    BASIS_MAX_LENGTH,
    BASIS_NONE,
    BASIS_ORIGINAL,
    BASIS_RULE,
    EditorPane,
    counter_info,
    overflow_spans,
)
from nxceviri.gui.theme import current_tokens

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


def kind_of(number: int) -> str:
    return {1: KIND_LINE_BREAK, 2: KIND_PAGE_BREAK}.get(number, KIND_OTHER)


def make_row(
    source: str = "Press A", translation: str = "A'ya bas", labels: tuple[str, ...] = (), status: str = Status.MACHINE
) -> TranslationRow:
    return TranslationRow(
        id=42,
        file="Menu/a.msbt",
        key="Menu_Start",
        source=source,
        translation=translation,
        status=status,
        note="",
        code_labels=labels,
        max_length=None,
    )


def make_pane(qtbot: QtBot, row: TranslationRow | None = None, rules: FitRules | None = None) -> EditorPane:
    pane = EditorPane()
    qtbot.addWidget(pane)
    pane.resize(600, 400)
    pane.show()
    pane.set_row(row, kind_of, rules)
    return pane


def type_text(qtbot: QtBot, pane: EditorPane, text: str) -> None:
    pane.translation_edit.setFocus()
    pane.translation_edit.selectAll()
    qtbot.keyClicks(pane.translation_edit, text)


def test_counter_info_variants() -> None:
    rules = FitRules(10, 2)
    # Sığdırma kuralı varsa sınır odur (en uzun satır + sayfa satırı).
    c = counter_info("Bu çok uzun bir satır", kind_of, rules, None, source="x")
    assert (c.text, c.state, c.basis, c.limit) == ("En uzun satır 21 / 10 · Sayfa 1/2", "danger", BASIS_RULE, 10)
    assert counter_info("kısa", kind_of, rules, None).text == "En uzun satır 4 / 10 · Sayfa 1/2"
    assert counter_info("kısa", kind_of, rules, None).state == ""
    assert counter_info("a\nb\nc", kind_of, rules, None).state == "danger"  # 3 satır > 2
    two_pages = "a⟦2⟧b\nc"
    assert counter_info(two_pages, kind_of, rules, None).text == "En uzun satır 1 / 10 · Sayfa 2/2"
    # Kural yoksa orijinalin en uzun satırı.
    c = counter_info("abcdef", kind_of, None, None, source="ab\ncdefg")
    assert (c.text, c.state, c.basis) == ("En uzun satır 6 / 5", "danger", BASIS_ORIGINAL)
    assert counter_info("abc", kind_of, None, None, source="ab\ncdefg").state == ""
    # Elle sınır her şeyden önce gelir.
    c = counter_info("abcdef", kind_of, rules, None, source="abcdefghij", manual=6)
    assert (c.text, c.state, c.basis, c.limit) == ("En uzun satır 6 / 6", "", BASIS_MANUAL, 6)
    assert counter_info("abcdefg", kind_of, rules, None, manual=6).state == "danger"
    # Yalnızca max_length varsa toplam karakter.
    assert counter_info("abcde", kind_of, None, 3, source="x").text == "5 / 3"
    assert counter_info("abc", kind_of, None, 3).basis == BASIS_MAX_LENGTH
    assert counter_info("abc", kind_of, None, 3).state == ""
    # Sınır yok (boş orijinal): yalnızca görünen karakter sayısı; kodlar sayılmaz.
    c = counter_info("a⟦1⟧bc", kind_of, None, None, source="")
    assert (c.text, c.basis) == ("3 karakter", BASIS_NONE)


def test_counter_counts_codes_like_fit() -> None:
    # Satır sonu kodu satırı böler, değişken kodu `variable_width` genişlik sayılır (fit.py hesabı).
    rules = FitRules(8, 3, variable_width=4)

    def kinds(number: int) -> str:
        return {1: KIND_LINE_BREAK, 2: "variable"}.get(number, KIND_OTHER)

    assert counter_info("abc⟦1⟧defghij", kinds, rules, None).text.startswith("En uzun satır 7 / 8")
    assert counter_info("ab⟦2⟧cd", kinds, rules, None).text.startswith("En uzun satır 8 / 8")


def test_overflow_spans_cover_end_of_long_lines() -> None:
    assert overflow_spans("abcdefgh\nxy", kind_of, 5) == [(5, 8)]
    assert overflow_spans("abc", kind_of, 5) == []
    text = "abcdefg⟦1⟧hijklmn"  # satır sonu kodundan sonra ikinci satır
    assert overflow_spans(text, kind_of, 5) == [(5, 7), (15, 17)]


def test_live_counter_turns_red_and_highlights_overflow(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row(source="Press A", translation="kısa"), FitRules(10, 3))
    assert pane.counter_label.property("role") == "muted"
    type_text(qtbot, pane, "bu satir on karakterden uzun")
    assert pane.counter_label.text().startswith("En uzun satır 28 / 10")
    assert pane.counter_label.property("role") == "danger"
    danger_bg = current_tokens()["danger_bg"]
    spans = [
        (s.cursor.selectionStart(), s.cursor.selectionEnd())
        for s in pane.translation_edit.extraSelections()
        if s.format.background().color().name().lower() == danger_bg.lower()
    ]
    assert spans == [(10, 28)]
    type_text(qtbot, pane, "kisa")
    assert pane.counter_label.property("role") == "muted"
    assert not [
        s
        for s in pane.translation_edit.extraSelections()
        if s.format.background().color().name().lower() == danger_bg.lower()
    ]


def test_counter_limit_from_rule_original_or_manual(qtbot: QtBot) -> None:
    row = make_row(source="12345678\n123", translation="12345678901")
    pane = make_pane(qtbot, row, FitRules(20, 3))
    assert pane.counter_label.text().startswith("En uzun satır 11 / 20")  # satır kuralı
    pane.set_row(row, kind_of, None)
    assert pane.counter_label.text() == "En uzun satır 11 / 8"  # kural yok: orijinalin en uzun satırı
    assert pane.counter_label.property("role") == "danger"
    pane.limit_box.setChecked(True)  # elle sınır
    pane.limit_spin.setValue(12)
    assert pane.counter_label.text() == "En uzun satır 11 / 12"
    assert pane.counter_label.property("role") == "muted"
    assert pane.manual_limit == 12


def test_manual_limit_signal_and_restore(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row(), None)
    seen: list[int] = []
    pane.manual_limit_changed.connect(seen.append)
    pane.limit_box.setChecked(True)
    pane.limit_spin.setValue(30)
    pane.limit_box.setChecked(False)
    assert seen[0] > 0
    assert seen[-2:] == [30, 0]
    assert pane.manual_limit is None
    seen.clear()
    pane.set_manual_limit(40)  # kayıtlı değeri yüklemek sinyal yaymaz
    assert seen == []
    assert pane.limit_spin.value() == 40
    assert pane.limit_box.isChecked()
    assert pane.limit_spin.isVisibleTo(pane)


def test_title_shows_short_identity_and_full_key_in_tooltip(qtbot: QtBot) -> None:
    row = make_row()
    pane = make_pane(qtbot, row)
    pane.set_row(row, kind_of, None, number=120)
    assert pane.title_label.text() == "No 120 · a.msbt"
    assert "Menu_Start" in pane.title_label.toolTip()
    pane.set_row(row, kind_of, None, selected_count=3, number=120)
    assert pane.title_label.text() == "3 satır seçili · No 120 · a.msbt"
    pane.set_row(row, kind_of, None)  # numarası bilinmiyorsa yalnızca grup
    assert pane.title_label.text() == "a.msbt"


def test_source_view_is_selectable_and_copyable(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row(source="Kopyalanacak metin"))
    flags = pane.source_view.textInteractionFlags()
    assert flags & Qt.TextInteractionFlag.TextSelectableByMouse
    assert flags & Qt.TextInteractionFlag.TextSelectableByKeyboard
    assert pane.source_view.isReadOnly()
    QApplication.clipboard().clear()
    pane.source_view.setFocus()
    pane.source_view.selectAll()
    qtbot.keyClick(pane.source_view, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == "Kopyalanacak metin"


def test_set_row_fills_and_disables_when_none(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row())
    assert pane.translation_edit.isEnabled()
    assert pane.source_view.toPlainText() == "Press A"
    assert pane.translation_edit.toPlainText() == "A'ya bas"
    pane.set_row(None, kind_of, None)
    assert not pane.translation_edit.isEnabled()
    assert pane.title_label.text() == "Satır seçin"
    assert pane.translation_edit.toPlainText() == ""


def test_multi_selection_label(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row())
    pane.set_row(make_row(), kind_of, None, selected_count=3)
    assert "3 satır seçili" in pane.title_label.text()
    assert pane.source_view.toPlainText() == "Press A"


def test_status_badge_follows_row(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row(status=Status.APPROVED))
    assert pane.status_badge.text() == "Onaylandı"
    pane.set_row(make_row(status=Status.ERROR), kind_of, None)
    assert pane.status_badge.text() == "Hatalı"


def test_enter_commits_shift_enter_newline_esc_reverts(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row())
    type_text(qtbot, pane, "yeni")
    with qtbot.waitSignal(pane.commit_requested) as blocker:
        qtbot.keyClick(pane.translation_edit, Qt.Key.Key_Return)
    assert blocker.args == [42, "yeni"]
    with qtbot.assertNotEmitted(pane.commit_requested):
        qtbot.keyClick(pane.translation_edit, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert pane.translation_edit.toPlainText() == "yeni\n"
    qtbot.keyClick(pane.translation_edit, Qt.Key.Key_Escape)
    assert pane.translation_edit.toPlainText() == "yeni"  # son kaydedilen hâle döner


def test_escape_reverts_to_row_text_when_never_saved(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row())
    type_text(qtbot, pane, "degisti")  # QTest, Windows'ta ASCII dışı tuşlarda süreci çökertir; ASCII kullanılır
    qtbot.keyClick(pane.translation_edit, Qt.Key.Key_Escape)
    assert pane.translation_edit.toPlainText() == "A'ya bas"
    assert not pane.has_pending()


def test_flush_commits_pending_only_if_changed(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row())
    with qtbot.assertNotEmitted(pane.commit_requested):
        pane.flush()
    type_text(qtbot, pane, "yeni")
    assert pane.has_pending()
    with qtbot.waitSignal(pane.commit_requested) as blocker:
        pane.flush()
    assert blocker.args == [42, "yeni"]
    assert not pane.has_pending()


def test_chip_click_inserts_raw_code_at_cursor(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row(source="A ⟦1⟧ B ⟦2⟧", translation="x", labels=("Satır sonu", "Kod 0x05")))
    assert pane.chips_row.isVisibleTo(pane)
    assert len(pane.chip_buttons) == 2
    pane.translation_edit.moveCursor(QTextCursor.MoveOperation.End)
    qtbot.mouseClick(pane.chip_buttons[1], Qt.MouseButton.LeftButton)
    assert pane.translation_edit.toPlainText() == "x⟦2⟧"


def test_chips_row_hidden_without_codes(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row())
    assert not pane.chips_row.isVisibleTo(pane)
    assert pane.chip_buttons == []


def test_symbols_use_qt_flags_and_trailing_space_selection(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row(translation="son  \nsatır"))
    warning_bg = current_tokens()["warning_bg"].lower()

    def trailing_selections() -> int:
        return sum(
            1
            for sel in pane.translation_edit.extraSelections()
            if sel.format.background().color().name().lower() == warning_bg
        )

    assert trailing_selections() == 0
    pane.set_view(True, "left")
    flags = pane.translation_edit.document().defaultTextOption().flags()
    assert flags & QTextOption.Flag.ShowTabsAndSpaces
    assert flags & QTextOption.Flag.ShowLineAndParagraphSeparators
    assert trailing_selections() >= 1
    pane.set_view(False, "left")
    assert not (pane.translation_edit.document().defaultTextOption().flags() & QTextOption.Flag.ShowTabsAndSpaces)
    assert trailing_selections() == 0


def test_alignment_applied_to_both_editors(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row())
    pane.set_view(False, "center")
    for edit in (pane.source_view, pane.translation_edit):
        assert edit.document().defaultTextOption().alignment() & Qt.AlignmentFlag.AlignHCenter


def test_trailing_space_warning_only_when_source_has_none(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row(source="y", translation="x "))
    assert "boşluk" in pane.warning_label.text()
    pane.set_row(make_row(source="y ", translation="x "), kind_of, None)
    assert pane.warning_label.text() == ""


def test_read_only_during_machine_run(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row())
    pane.set_read_only(True)
    assert pane.translation_edit.isReadOnly()
    assert not pane.approve_button.isEnabled()
    pane.set_read_only(False)
    assert not pane.translation_edit.isReadOnly()


def test_show_error_keeps_text_and_pending(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row())
    type_text(qtbot, pane, "yeni")
    qtbot.keyClick(pane.translation_edit, Qt.Key.Key_Return)
    pane.show_error("Kaydedilemedi")
    assert pane.error_label.text() == "Kaydedilemedi"
    assert pane.translation_edit.toPlainText() == "yeni"
    assert pane.has_pending()


def test_cursor_moved_emits_line_and_column(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row(translation="ab\ncd"))
    with qtbot.waitSignal(pane.cursor_moved) as blocker:
        cursor = pane.translation_edit.textCursor()
        cursor.setPosition(4)
        pane.translation_edit.setTextCursor(cursor)
    assert blocker.args == [2, 2]


def test_navigation_shortcut_and_buttons_emit(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row())
    pane.translation_edit.setFocus()
    with qtbot.waitSignal(pane.navigate_requested) as down:
        qtbot.keyClick(pane.translation_edit, Qt.Key.Key_Down, Qt.KeyboardModifier.AltModifier)
    assert down.args == [1]
    with qtbot.waitSignal(pane.navigate_requested) as up:
        qtbot.mouseClick(pane.prev_button, Qt.MouseButton.LeftButton)
    assert up.args == [-1]


def test_approve_button_emits(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row())
    with qtbot.waitSignal(pane.approve_requested):
        qtbot.mouseClick(pane.approve_button, Qt.MouseButton.LeftButton)


def test_empty_and_very_long_text(qtbot: QtBot) -> None:
    pane = make_pane(qtbot, make_row(source="", translation=""))
    assert pane.counter_label.text()
    long_text = "kelime " * 1500
    pane.set_row(make_row(source=long_text, translation=long_text), kind_of, FitRules(40, 3))
    assert pane.counter_label.text()
    assert pane.translation_edit.toPlainText() == long_text


def test_chips_layout_does_not_accumulate_spacers(qtbot: QtBot) -> None:
    row = make_row(source="A ⟦1⟧ B ⟦2⟧", translation="x", labels=("Satır sonu", "Kod 0x05"))
    pane = make_pane(qtbot, row)
    for _ in range(3):
        pane.set_row(row, kind_of, None)
    assert pane._chips_layout.count() == len(pane.chip_buttons) + 1  # yalnızca tek esneme boşluğu


def test_text_boxes_show_three_lines_at_least(qtbot: QtBot) -> None:
    # Oyun metinleri çoğu zaman üç satırlık sayfalardır; kutular kaydırmadan üç satırı göstermeli.
    pane = EditorPane()
    qtbot.addWidget(pane)
    for box in (pane.source_view, pane.translation_edit):
        line = box.fontMetrics().lineSpacing()
        assert box.minimumHeight() >= 3 * line + 2 * box.document().documentMargin()


def _head_state(pane: EditorPane) -> dict[str, bool]:
    """Başlık satırındaki öğelerin tam görünüp görünmediği (genişlik ≥ doğal genişlik)."""
    return {
        "badge": pane.status_badge.width() >= pane.status_badge.sizeHint().width(),
        "approve": pane.approve_button.width() >= pane.approve_button.sizeHint().width(),
    }


@pytest.mark.parametrize("width", [360, 320, 280])
def test_narrow_head_keeps_badge_and_approve_whole(qtbot: QtBot, width: int) -> None:
    row = make_row(status=Status.UNTRANSLATED)
    row = dataclasses.replace(row, key="Menu_Very_Long_Row_Name_That_Would_Eat_The_Header", file="Menu/a.msbt")
    pane = EditorPane()
    qtbot.addWidget(pane)
    pane.set_row(row, kind_of, None)
    pane.resize(width, 400)
    pane.show()
    qtbot.waitUntil(lambda: pane.width() == width or pane.width() > width)
    assert pane.status_badge.text() == "Çevrilmedi"
    assert _head_state(pane) == {"badge": True, "approve": True}
    assert pane.title_label.width() > 0
    assert pane.title_label.text() != "Menu_Very_Long_Row_Name_That_Would_Eat_The_Header" or width > 360


def test_head_hides_arrows_only_when_cramped(qtbot: QtBot) -> None:
    pane = EditorPane()
    qtbot.addWidget(pane)
    pane.set_row(make_row(status=Status.UNTRANSLATED), kind_of, None)
    pane.show()
    pane.resize(600, 400)
    assert pane.prev_button.isVisibleTo(pane)
    assert pane.next_button.isVisibleTo(pane)
    pane.setMinimumWidth(0)
    pane.resize(220, 400)
    QApplication.processEvents()
    assert pane.width() == 220
    assert not pane.prev_button.isVisibleTo(pane)
    assert not pane.next_button.isVisibleTo(pane)
    assert _head_state(pane) == {"badge": True, "approve": True}
    pane.resize(600, 400)
    assert pane.prev_button.isVisibleTo(pane)  # genişleyince oklar geri gelir
