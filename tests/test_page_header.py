"""Sayfa başlığı, eylem satırı ve durum çipi; dört sayfanın başlık eylemleri."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QWidget
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.detection import FileKind, TextLikelihood
from nxceviri.core.formats.registry import supported_kinds
from nxceviri.core.formats.scanner import EngineGuess, ScanEntry, ScanReport
from nxceviri.gui.add_game_page import AddGamePage
from nxceviri.gui.export_page import ExportPage
from nxceviri.gui.qa_page import QaPage
from nxceviri.gui.scan_page import ScanPage
from nxceviri.gui.theme import ThemeMode, apply_theme
from nxceviri.gui.widgets import ActionBar, Card, PageHeader, StatusChip, button

pytestmark = pytest.mark.gui


def _open(qtbot: QtBot, chip: StatusChip) -> None:
    chip.show()
    qtbot.mouseClick(chip, Qt.MouseButton.LeftButton)


def _popup_text(chip: StatusChip) -> str:
    assert chip.popup is not None
    return " ".join(lbl.text() for lbl in chip.popup.findChildren(QLabel))


def test_chip_hidden_without_text(qtbot: QtBot) -> None:
    chip = StatusChip()
    qtbot.addWidget(chip)
    chip.show_status("warning", "", ["x"])
    assert chip.isHidden()
    chip.show_status("", "metin", ["x"])
    assert chip.isHidden()


def test_chip_shows_state_and_text(qtbot: QtBot) -> None:
    chip = StatusChip()
    qtbot.addWidget(chip)
    chip.show_status("danger", "2 sorun", ["a satırı", "b satırı"])
    assert not chip.isHidden()
    assert chip.text() == "2 sorun"
    assert chip.property("state") == "danger"
    assert chip.details() == ("a satırı", "b satırı")
    assert "a satırı" in chip.toolTip()
    assert "b satırı" in chip.toolTip()


def test_chip_click_opens_details_popup(qtbot: QtBot) -> None:
    chip = StatusChip()
    qtbot.addWidget(chip)
    chip.show_status("warning", "1 uyarı", ["Ayrıntı satırı"])
    _open(qtbot, chip)
    assert chip.popup is not None
    assert chip.popup.isVisible()
    assert "Ayrıntı satırı" in _popup_text(chip)


def test_chip_popup_closes_on_escape(qtbot: QtBot) -> None:
    chip = StatusChip()
    qtbot.addWidget(chip)
    chip.show_status("warning", "1 uyarı", ["Ayrıntı"])
    _open(qtbot, chip)
    assert chip.popup is not None
    qtbot.keyClick(chip.popup, Qt.Key.Key_Escape)
    assert not chip.popup.isVisible()


def test_chip_without_details_does_not_open(qtbot: QtBot) -> None:
    chip = StatusChip()
    qtbot.addWidget(chip)
    chip.show_status("info", "Hazır", [])
    _open(qtbot, chip)
    assert chip.popup is None or not chip.popup.isVisible()


def test_chip_popup_shows_new_details_after_update(qtbot: QtBot) -> None:
    chip = StatusChip()
    qtbot.addWidget(chip)
    chip.show_status("warning", "1 uyarı", ["eski"])
    _open(qtbot, chip)
    assert chip.popup is not None
    chip.popup.hide()
    chip.show_status("warning", "1 uyarı", ["yeni"])
    _open(qtbot, chip)
    text = _popup_text(chip)
    assert "yeni" in text
    assert "eski" not in text


def test_chip_long_details_fit_on_screen(qtbot: QtBot) -> None:
    chip = StatusChip()
    qtbot.addWidget(chip)
    chip.show_status("warning", "31 uyarı", ["x" * 420] + [f"satır {i}" for i in range(30)])
    _open(qtbot, chip)
    assert chip.popup is not None
    geo = chip.popup.geometry()
    assert geo.width() <= 440
    assert geo.height() <= 340


def test_header_actions_in_order_right_side(qtbot: QtBot) -> None:
    header = PageHeader("Başlık", "package")
    qtbot.addWidget(header)
    first, primary = button("A"), button("B", "primary")
    header.add_action(first)
    header.add_action(primary)
    header.resize(800, 60)
    header.show()
    qtbot.waitExposed(header)
    assert first.geometry().x() < primary.geometry().x()
    assert primary.geometry().x() > header.title.geometry().right()


def test_header_long_title_keeps_actions_visible(qtbot: QtBot) -> None:
    header = PageHeader("Çok uzun bir başlık " * 10, "package")
    qtbot.addWidget(header)
    action = button("Modu Oluştur", "primary")
    header.add_action(action)
    header.resize(420, 60)
    header.show()
    qtbot.waitExposed(header)
    assert action.isVisible()
    assert action.mapTo(header, action.rect().bottomRight()).x() <= header.width()


def test_header_info_is_title_tooltip(qtbot: QtBot) -> None:
    header = PageHeader("Başlık", "package", info="uzun bilgi")
    qtbot.addWidget(header)
    assert header.title.text() == "Başlık"
    assert "uzun bilgi" in header.title.toolTip()
    assert header.chip.isHidden()


def test_action_bar_status_and_actions(qtbot: QtBot) -> None:
    bar = ActionBar()
    qtbot.addWidget(bar)
    action = button("X")
    bar.add_action(action)
    bar.status.setText("Henüz denetlenmedi.")
    assert bar.isAncestorOf(action)
    assert bar.status.property("role") == "muted"


def test_card_without_title_hides_header(qtbot: QtBot) -> None:
    card = Card("")
    qtbot.addWidget(card)
    card.show()
    assert not card.title.isVisible()
    titled = Card("Başlık")
    qtbot.addWidget(titled)
    titled.show()
    assert titled.title.isVisible()


# --- Oyunu Ekle ------------------------------------------------------------------------


def test_add_page_next_in_header(qtbot: QtBot) -> None:
    page = AddGamePage()
    qtbot.addWidget(page)
    assert page.header.isAncestorOf(page.next_button)


def test_add_page_reason_in_chip_and_tooltip(qtbot: QtBot) -> None:
    page = AddGamePage()
    qtbot.addWidget(page)
    page.set_can_continue(False, "Önce anahtar seçin")
    assert page.header.chip.text() == "Önce anahtar seçin"
    assert not page.header.chip.isHidden()
    assert "Önce anahtar seçin" in page.next_button.toolTip()
    assert not page.next_button.isEnabled()
    page.set_can_continue(True, "")
    assert page.header.chip.isHidden()
    assert page.next_button.isEnabled()


def test_add_page_busy_text_in_chip(qtbot: QtBot) -> None:
    page = AddGamePage()
    qtbot.addWidget(page)
    page.set_busy(True, "Dosya okunuyor…")
    assert page.header.chip.text() == "Dosya okunuyor…"
    page.set_busy(False, "")
    assert page.header.chip.isHidden()


def test_add_page_drop_texts_short(qtbot: QtBot) -> None:
    page = AddGamePage()
    qtbot.addWidget(page)
    page.set_keys_state("danger", None)
    assert page.drop.text.text() == "Önce anahtar dosyası seçin"
    page.set_keys_state("success", Path("prod.keys"))
    assert page.drop.text.text() == "NSP / NSZ dosyalarını bırakın"


def test_add_page_long_reason_goes_to_details(qtbot: QtBot) -> None:
    page = AddGamePage()
    qtbot.addWidget(page)
    reason = "Güncelleme dosyası ana oyunla aynı TitleID'ye ait değil: 0100000000010000 ≠ 0100000000020000."
    page.set_can_continue(False, reason)
    assert page.header.chip.text() == "Devam edilemiyor"
    assert page.header.chip.details() == (reason,)


# --- Metinleri Tara ---------------------------------------------------------------------


def _entry(path: str, kind: str) -> ScanEntry:
    return ScanEntry("0100000000010000", path, 100, kind, "", TextLikelihood.HIGH.value, "base")


def _report(entries: list[ScanEntry], warnings: list[str] | None = None) -> ScanReport:
    engine = EngineGuess("nintendo", "Nintendo LMS / NintendoWare", "high", ("msbt",))
    return ScanReport("Oyun", "0100000000010000", 0, None, engine, entries, warnings or [])


def _unsupported_kind() -> str:
    supported = supported_kinds()
    return next(k.value for k in FileKind if k.value not in supported and k != FileKind.OTHER)


def _scan_visible(page: ScanPage) -> set[QWidget]:
    widgets = (
        page.start_button,
        page.retry_button,
        page.back_button,
        page.report.rescan_button,
        page.report.language,
        page.report.import_button,
    )
    return {w for w in widgets if not w.isHidden()}


def _scan_page(qtbot: QtBot) -> ScanPage:
    page = ScanPage()
    qtbot.addWidget(page)
    return page


def test_scan_header_empty_state(qtbot: QtBot) -> None:
    page = _scan_page(qtbot)
    page.show_empty()
    assert _scan_visible(page) == {page.start_button}
    assert page.header.isAncestorOf(page.start_button)
    assert not page.empty.findChildren(QPushButton)


def test_scan_header_loading_has_no_actions(qtbot: QtBot) -> None:
    page = _scan_page(qtbot)
    page.show_loading("Taranıyor")
    assert _scan_visible(page) == set()


def test_scan_header_error_state(qtbot: QtBot) -> None:
    page = _scan_page(qtbot)
    page.show_error("bozuk")
    assert _scan_visible(page) == {page.retry_button, page.back_button}
    assert not page.error.findChildren(QPushButton)


def test_scan_header_report_state(qtbot: QtBot) -> None:
    page = _scan_page(qtbot)
    page.show_report(_report([_entry("romfs/Message/USen/a.msbt", FileKind.MSBT.value)]))
    assert _scan_visible(page) == {page.report.rescan_button, page.report.import_button}
    page.show_loading("Taranıyor")  # yeniden tarama: rapor eylemleri gizlenir
    assert _scan_visible(page) == set()


def test_scan_header_language_only_with_choice(qtbot: QtBot) -> None:
    page = _scan_page(qtbot)
    page.show_report(
        _report(
            [
                _entry("romfs/Message/USen/a.msbt", FileKind.MSBT.value),
                _entry("romfs/Message/JPja/a.msbt", FileKind.MSBT.value),
            ]
        )
    )
    assert page.report.language in _scan_visible(page)
    assert not page.report.language_label.isHidden()


def test_scan_warnings_go_to_chip(qtbot: QtBot) -> None:
    page = _scan_page(qtbot)
    page.show_report(_report([_entry("romfs/Message/USen/a.msbt", FileKind.MSBT.value)], ["uyarı a", "uyarı b"]))
    chip = page.header.chip
    assert not chip.isHidden()
    assert chip.property("state") == "warning"
    assert chip.text() == "2 uyarı"
    assert "uyarı a" in chip.details()
    assert "uyarı b" in chip.details()


def test_scan_supported_without_warnings_is_success_chip(qtbot: QtBot) -> None:
    page = _scan_page(qtbot)
    page.show_report(_report([_entry("romfs/Message/USen/a.msbt", FileKind.MSBT.value)]))
    assert page.header.chip.property("state") == "success"
    assert page.header.chip.text() == "1 dosya aktarılabilir"


def test_scan_unsupported_chip_is_warning(qtbot: QtBot) -> None:
    page = _scan_page(qtbot)
    page.show_report(_report([_entry("romfs/x.bin", _unsupported_kind())]))
    assert page.header.chip.property("state") == "warning"
    assert page.header.chip.text() == "Desteklenmeyen biçim"
    assert page.report.import_button.isHidden()


def test_scan_chip_hidden_outside_report(qtbot: QtBot) -> None:
    page = _scan_page(qtbot)
    page.show_report(_report([_entry("romfs/Message/USen/a.msbt", FileKind.MSBT.value)], ["uyarı"]))
    page.show_loading("Taranıyor")
    assert page.header.chip.isHidden()


def _many_files_page(qtbot: QtBot, width: int, height: int) -> ScanPage:
    page = _scan_page(qtbot)
    page.show_report(_report([_entry(f"romfs/Message/USen/{i:03d}.msbt", FileKind.MSBT.value) for i in range(200)]))
    page.resize(width, height)
    page.show()
    qtbot.waitExposed(page)
    for _ in range(3):  # yerleşim birkaç turda oturur
        QApplication.processEvents()
    return page


def test_scan_report_has_single_scrollbar_at_normal_size(qtbot: QtBot) -> None:
    page = _many_files_page(qtbot, 1280, 800)
    assert page.report_scroll.verticalScrollBar().maximum() == 0
    table = page.report.table
    assert table.verticalScrollBar().maximum() > 0
    bottom = table.mapTo(page.report_scroll.viewport(), table.rect().bottomLeft()).y()
    assert bottom < page.report_scroll.viewport().height()


def test_scan_report_single_scrollbar_at_1000x700(qtbot: QtBot) -> None:
    page = _many_files_page(qtbot, 1000, 700)
    assert page.report_scroll.verticalScrollBar().maximum() == 0
    assert page.report.table.verticalScrollBar().maximum() > 0


def test_scan_report_table_keeps_minimum_height_in_tiny_window(qtbot: QtBot) -> None:
    page = _many_files_page(qtbot, 700, 360)
    assert page.report.table.height() >= page.report.table.minimumHeight() >= 150
    assert page.report_scroll.verticalScrollBar().maximum() > 0


# --- Kontrol Et -------------------------------------------------------------------------


def _qa(qtbot: QtBot) -> QaPage:
    qa = QaPage()
    qtbot.addWidget(qa)
    return qa


def test_qa_check_actions_in_bar(qtbot: QtBot) -> None:
    qa = _qa(qtbot)
    assert qa.check_bar.isAncestorOf(qa.check_button)
    assert not hasattr(qa, "fix_menu_button")  # üst çubukta yalnızca birincil “Denetle” kalır
    assert not qa.check_card.isAncestorOf(qa.check_button)


def test_qa_summary_is_bar_status(qtbot: QtBot) -> None:
    qa = _qa(qtbot)
    assert qa.summary is qa.check_bar.status
    assert qa.summary.text() == "Henüz denetlenmedi."


def test_qa_fit_and_font_bars(qtbot: QtBot) -> None:
    qa = _qa(qtbot)
    assert qa.fit_bar.isAncestorOf(qa.fit_enabled)
    assert qa.fit_bar.isAncestorOf(qa.fit_learn)
    assert qa.font_bar.isAncestorOf(qa.font_button)


def test_qa_cards_have_no_tab_title(qtbot: QtBot) -> None:
    qa = _qa(qtbot)
    for card in (qa.check_card, qa.fit_card, qa.font_card):
        assert card.title.text() == ""


def test_qa_open_hint_is_table_tooltip(qtbot: QtBot) -> None:
    qa = _qa(qtbot)
    assert "Çift tıklayın" in qa.table.toolTip()
    assert not [lbl for lbl in qa.findChildren(QLabel) if lbl.text().startswith("Çift tıklayın")]


# --- Dışa Aktar -------------------------------------------------------------------------


def _export(qtbot: QtBot) -> ExportPage:
    page = ExportPage()
    qtbot.addWidget(page)
    return page


def test_export_button_in_header(qtbot: QtBot) -> None:
    page = _export(qtbot)
    assert page.header.isAncestorOf(page.export_button)
    assert not hasattr(page, "version_banner")


def test_export_notes_problems_first(qtbot: QtBot) -> None:
    page = _export(qtbot)
    page.set_notes(["Anahtar dosyası seçilmedi."], ["Fontlar henüz taranmadı."])
    chip = page.header.chip
    assert chip.property("state") == "danger"
    assert chip.text() == "1 sorun · 1 uyarı"
    assert chip.details() == ("Anahtar dosyası seçilmedi.", "Fontlar henüz taranmadı.")


def test_export_notes_only_warnings(qtbot: QtBot) -> None:
    page = _export(qtbot)
    page.set_notes([], ["a", "b"])
    assert page.header.chip.property("state") == "warning"
    assert page.header.chip.text() == "2 uyarı"


def test_export_notes_empty_hides_chip(qtbot: QtBot) -> None:
    page = _export(qtbot)
    page.set_notes(["x"], [])
    page.set_notes([], [])
    assert page.header.chip.isHidden()


def test_export_summary_one_line(qtbot: QtBot) -> None:
    page = _export(qtbot)
    page.set_summary(written=21, errors=0, untranslated=10, conversion="yok", can_export=True)
    assert page.summary.text() == "21 yazılacak · 0 hatalı · 10 çevrilmemiş · Harf dönüştürme: yok"


def test_export_running_disables_header_action(qtbot: QtBot) -> None:
    page = _export(qtbot)
    page.set_summary(written=1, errors=0, untranslated=0, conversion="yok", can_export=True)
    page.show_running()
    assert not page.export_button.isEnabled()
    page.show_form()
    assert page.export_button.isEnabled()


def test_export_running_keeps_disabled_export_disabled(qtbot: QtBot) -> None:
    page = _export(qtbot)
    page.set_summary(written=0, errors=0, untranslated=0, conversion="yok", can_export=False)
    page.show_running()
    page.show_form()
    assert not page.export_button.isEnabled()


def test_chip_popup_lines_have_no_gaps(qtbot: QtBot) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    palette, style_sheet, font = app.palette(), app.styleSheet(), app.font()
    apply_theme(app, ThemeMode.LIGHT)  # temanın yazı tipi boyu ölçüyü değiştirir
    try:
        _check_popup_compact(qtbot)
    finally:
        app.setPalette(palette)
        app.setStyleSheet(style_sheet)
        app.setFont(font)


def _check_popup_compact(qtbot: QtBot) -> None:
    chip = StatusChip()
    qtbot.addWidget(chip)
    long_line = "Fontlar henüz taranmadı; “Kontrol Et” adımında Türkçe harfleri denetlemeniz önerilir. " * 2
    chip.show_status("danger", "3 not", ["Kısa satır.", "Bir kısa satır daha.", long_line])
    _open(qtbot, chip)
    popup = chip.popup
    assert popup is not None
    labels = sorted(popup.findChildren(QLabel), key=lambda lbl: lbl.mapTo(popup, lbl.rect().topLeft()).y())
    for upper, lower in pairwise(labels):
        gap = lower.mapTo(popup, lower.rect().topLeft()).y() - upper.mapTo(popup, upper.rect().bottomLeft()).y()
        assert gap <= 10, gap
    for lbl in labels:  # satır, metninin gerektirdiğinden yüksek değil (metin ortalanıp boşluk bırakmaz)
        assert lbl.height() <= lbl.heightForWidth(lbl.width()) + 4, (lbl.text()[:20], lbl.height())


def test_add_page_reason_chip_is_neutral(qtbot: QtBot) -> None:
    page = AddGamePage()
    qtbot.addWidget(page)
    page.set_can_continue(False, "Anahtar dosyası seçin")
    assert page.header.chip.property("state") == "neutral"  # mavi "info" düğmeye benziyordu


# --- son inceleme düzeltmeleri ----------------------------------------------------------


def test_scan_header_fits_minimum_window_with_language_choice(qtbot: QtBot) -> None:
    page = _scan_page(qtbot)
    page.show_report(
        _report(
            [
                _entry("romfs/Message/USen/a.msbt", FileKind.MSBT.value),
                _entry("romfs/Message/JPja/a.msbt", FileKind.MSBT.value),
            ]
        )
    )
    assert not page.report.language.isHidden()
    # En küçük pencerede (820 px) kenar çubuğu ve kenar boşluklarından sonra başlığa kalan genişlik.
    assert page.header.minimumSizeHint().width() <= 584


def test_qa_open_hint_reaches_row_tooltips() -> None:
    from nxceviri.core.project import TranslationRow
    from nxceviri.core.qa.checks import QaIssue
    from nxceviri.gui.qa_page import IssueModel

    model = IssueModel()
    row = TranslationRow(1, "f", "k", "Hello", "Merhaba", "machine", "", (), None)
    model.set_issues([QaIssue(1, "k", "overflow", "warning", "Uzun")], {1: row})
    for col in range(model.columnCount()):
        tip = model.data(model.index(0, col), Qt.ItemDataRole.ToolTipRole)
        assert "Çift tıklayın" in tip, col


def test_error_state_has_no_empty_button_row(qtbot: QtBot) -> None:
    from nxceviri.gui.widgets import ErrorState

    state = ErrorState()
    qtbot.addWidget(state)
    assert not hasattr(state, "buttons_row")
