"""Durum süzgeci şeridi: tek seçimli simge düğmeleri, ipucu, erişilebilir ad, klavye ve çeviri sayfasına bağlanma."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QToolButton
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.status import Status
from nxceviri.gui.status_filter import FilterOption, StatusFilterBar
from nxceviri.gui.translate_page import CHANGED_FILTER, ISSUES_FILTER, TranslatePage


def _options() -> list[FilterOption]:
    return [
        FilterOption("", "list", None, "Tümü", "Bütün satırlar", "1.234"),
        FilterOption("machine", "monitor", "accent", "Makine", "Makine çevirisi olan satırlar"),
        FilterOption("error", "triangle-alert", "danger", "Hatalı", "Hatalı satırlar"),
    ]


def _bar(qtbot: QtBot) -> StatusFilterBar:
    bar = StatusFilterBar()
    qtbot.addWidget(bar)
    bar.set_options(_options())
    bar.show()
    return bar


def _buttons(bar: StatusFilterBar) -> list[QToolButton]:
    return bar.findChildren(QToolButton)


def test_bar_builds_one_button_per_option(qtbot: QtBot) -> None:
    bar = _bar(qtbot)
    buttons = _buttons(bar)
    assert [b.accessibleName() for b in buttons] == ["Tümü", "Makine", "Hatalı"]
    assert [b.toolTip() for b in buttons][1] == "Makine çevirisi olan satırlar"
    assert buttons[0].text() == "1.234"
    assert buttons[1].text() == ""
    assert all(b.isCheckable() and not b.icon().isNull() for b in buttons)
    assert bar.current() == ""
    assert buttons[0].isChecked()


def test_bar_click_selects_exclusively_and_emits(qtbot: QtBot) -> None:
    bar = _bar(qtbot)
    seen: list[str] = []
    bar.changed.connect(seen.append)
    machine = _buttons(bar)[1]
    QTest.mouseClick(machine, Qt.MouseButton.LeftButton)
    assert bar.current() == "machine"
    assert [b.isChecked() for b in _buttons(bar)] == [False, True, False]
    QTest.mouseClick(machine, Qt.MouseButton.LeftButton)  # seçili düğmeye yeniden basmak seçimi kaldırmaz
    assert bar.current() == "machine"
    assert seen == ["machine"]


def test_bar_keyboard_space_and_enter_select(qtbot: QtBot) -> None:
    bar = _bar(qtbot)
    buttons = _buttons(bar)
    buttons[1].setFocus()
    QTest.keyClick(buttons[1], Qt.Key.Key_Space)
    assert bar.current() == "machine"
    buttons[2].setFocus()
    QTest.keyClick(buttons[2], Qt.Key.Key_Return)
    assert bar.current() == "error"
    QTest.keyClick(buttons[0], Qt.Key.Key_Enter)
    assert bar.current() == ""


def test_bar_set_current_falls_back_to_all(qtbot: QtBot) -> None:
    bar = _bar(qtbot)
    seen: list[str] = []
    bar.changed.connect(seen.append)
    bar.set_current("error")
    assert bar.current() == "error"
    bar.set_current("yok-boyle-bir-deger")
    assert bar.current() == ""
    bar.set_current("")  # değişiklik yoksa sinyal gelmez
    assert seen == ["error", ""]


def test_bar_set_options_keeps_current_silently(qtbot: QtBot) -> None:
    bar = _bar(qtbot)
    bar.set_current("error")
    seen: list[str] = []
    bar.changed.connect(seen.append)
    bar.set_options(_options())
    assert bar.current() == "error"
    bar.set_options(_options()[:2])  # seçili seçenek kalkınca "Tümü"ne düşer
    assert bar.current() == ""
    assert seen == []  # yeniden kurma sinyal vermez; çağıran sayfa durumu kendisi karşılaştırır
    assert len(_buttons(bar)) == 2


def test_bar_set_text_updates_button(qtbot: QtBot) -> None:
    bar = _bar(qtbot)
    bar.set_text("error", "3")
    assert _buttons(bar)[2].text() == "3"
    assert _buttons(bar)[2].toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    bar.set_text("error", "")
    assert _buttons(bar)[2].text() == ""
    assert _buttons(bar)[2].toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly


# --- çeviri sayfasında ----------------------------------------------------------------------------


def _row(i: int, status: Status, translation: str = "") -> TranslationRow:
    return TranslationRow(
        id=i,
        file="a.msbt",
        key=f"k{i}",
        source=f"Orijinal {i}",
        translation=translation,
        status=status,
        note="",
        code_labels=(),
        max_length=None,
        context=f"k{i}",
    )


def _page(qtbot: QtBot, rows: list[TranslationRow]) -> TranslatePage:
    p = TranslatePage()
    qtbot.addWidget(p)
    p.resize(1100, 700)
    p.show()
    p.set_rows(rows)
    return p


def test_page_options_follow_row_statuses(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(1, Status.UNTRANSLATED), _row(2, Status.ERROR, "x"), _row(3, Status.ERROR, "y")])
    assert p.status_filter.values() == [
        "",
        "untranslated",
        "approved",
        "error",
        ISSUES_FILTER,
    ]  # makine/redakte/değişen yok
    buttons = p.status_filter.findChildren(QToolButton)
    assert buttons[0].text() == "3"  # Tümü: toplam satır sayısı
    assert buttons[3].text() == "2"  # Hatalı: o durumdaki satır sayısı
    assert buttons[1].text() == ""
    p.set_rows([_row(1, Status.MACHINE, "m")])
    assert "machine" in p.status_filter.values()
    assert all(b.text() == "" for b in p.status_filter.findChildren(QToolButton)[2:])  # hatalı sayısı 0 → yalnız simge


def test_page_changed_option_appears_with_count(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(1, Status.MACHINE, "a"), _row(2, Status.MACHINE, "b")])
    p.set_last_changes({1: "eski"})
    assert p.status_filter.values()[-1] == CHANGED_FILTER
    assert p.status_filter.findChildren(QToolButton)[-1].text() == "1"
    p.status_filter.set_current(CHANGED_FILTER)
    assert p.proxy.rowCount() == 1
    p.set_last_changes({})  # seçenek kalkınca süzgeç "Tümü"ne düşer ve satırlar geri gelir
    assert p.status_filter.current() == ""
    assert p.proxy.rowCount() == 2


def test_page_filter_applies_and_clear_resets(qtbot: QtBot) -> None:
    p = _page(qtbot, [_row(1, Status.UNTRANSLATED), _row(2, Status.MACHINE, "m")])
    p.status_filter.set_current("machine")
    assert p.proxy.rowCount() == 1
    assert p._clear_filters()
    assert p.status_filter.current() == ""
    assert p.proxy.rowCount() == 2


def test_page_selected_status_stays_after_last_row_changes(qtbot: QtBot) -> None:
    """Seçili durumdaki son satır düzenlenip durumu değişse de süzgeç "Tümü"ne düşmez, tablo yer değiştirmez."""
    p = _page(qtbot, [_row(1, Status.UNTRANSLATED), _row(2, Status.MACHINE, "m")])
    p.status_filter.set_current("machine")
    assert p.proxy.rowCount() == 1
    p.model.update_rows([_row(2, Status.REDACTED, "m")])
    qtbot.wait(400)  # durum şeridinin gecikmeli yenilenmesi
    assert p.status_filter.current() == "machine"
    assert "machine" in p.status_filter.values()
    assert p.proxy.rowCount() == 1
    p.set_rows([_row(1, Status.UNTRANSLATED), _row(2, Status.REDACTED, "m")])  # yeniden yükleme de aynı kural
    assert p.status_filter.current() == "machine"
