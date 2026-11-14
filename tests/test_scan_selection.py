"""Metinleri Tara: aktarılacak dosyaların seçimi, dili anlaşılamayan dosya uyarısı ve açıklama ipuçları."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QModelIndex, Qt
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.detection import FileKind, TextLikelihood
from nxceviri.core.formats.registry import supported_kinds
from nxceviri.core.formats.scanner import EngineGuess, ScanEntry, ScanReport
from nxceviri.core.pipeline import language_label
from nxceviri.gui.scan_page import (
    COL_IMPORT,
    COL_LANGUAGE,
    COL_PATH,
    MODE_ALL,
    MODE_UNKNOWN_LANGUAGE,
    ReportView,
    ScanPage,
)

pytestmark = pytest.mark.gui

TID = "0100000000010000"
EN = "romfs/Message/USen/a.msbt"
JA = "romfs/Message/JPja/a.msbt"
FR = "romfs/Message/EUfr/a.msbt"
UNKNOWN = [f"romfs/Data/menu_{i}.msbt" for i in range(6)]
OTHER = "romfs/Data/model.bin"
_ALIVE: list[ScanPage] = []


def _entry(path: str, kind: str = FileKind.MSBT.value, likelihood: str = TextLikelihood.HIGH.value) -> ScanEntry:
    return ScanEntry(TID, path, 100, kind, "", likelihood, "base")


def _unsupported_kind() -> str:
    supported = supported_kinds()
    return next(k.value for k in FileKind if k.value not in supported and k != FileKind.OTHER)


def _report(paths: list[str], unsupported: tuple[str, ...] = ()) -> ScanReport:
    entries = [_entry(p) for p in paths] + [_entry(p, _unsupported_kind()) for p in unsupported]
    engine = EngineGuess("nintendo", "Nintendo LMS / NintendoWare", "high", ("msbt",))
    return ScanReport("Oyun", TID, 0, None, engine, entries, [])


def _page(qtbot: QtBot, paths: list[str], unsupported: tuple[str, ...] = ()) -> ScanPage:
    page = ScanPage()
    qtbot.addWidget(page)
    _ALIVE.append(page)  # yalnızca `.report` kullanan testlerde sayfa çöp toplanmasın
    page.show_report(_report(paths, unsupported))
    return page


def _row(view: ReportView, path: str) -> int:
    return next(i for i, e in enumerate(view.model.entries) if e.path == path)


def _checked(view: ReportView) -> set[str]:
    return view.selected_paths()


def _mixed(qtbot: QtBot) -> ScanPage:
    return _page(qtbot, [EN, JA, FR, *UNKNOWN], (OTHER,))


def _use_language(view: ReportView, code: str) -> None:
    view.language.setCurrentIndex(view.language.findData(code))


# --- varsayılan küme -------------------------------------------------------------------------


def test_default_selection_is_source_language_plus_unknown(qtbot: QtBot) -> None:
    view = _mixed(qtbot).report
    assert view.language.currentData() == "en-us"
    assert _checked(view) == {EN, *UNKNOWN}
    ja = view.model.index(_row(view, JA), COL_IMPORT)
    assert view.model.data(ja, Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Unchecked
    assert not view.model.flags(ja) & Qt.ItemFlag.ItemIsEnabled  # kutu devre dışı
    assert view.model.data(ja, Qt.ItemDataRole.ToolTipRole) == "Seçili kaynak dilde değil"


def test_unsupported_rows_have_no_checkbox(qtbot: QtBot) -> None:
    view = _mixed(qtbot).report
    index = view.model.index(_row(view, OTHER), COL_IMPORT)
    assert view.model.data(index, Qt.ItemDataRole.CheckStateRole) is None
    assert not view.model.flags(index) & Qt.ItemFlag.ItemIsUserCheckable
    assert view.model.data(index.siblingAtColumn(COL_LANGUAGE)) == ""
    assert OTHER not in _checked(view)


def test_language_column(qtbot: QtBot) -> None:
    view = _mixed(qtbot).report
    en = view.model.index(_row(view, EN), COL_LANGUAGE)
    unknown = view.model.index(_row(view, UNKNOWN[0]), COL_LANGUAGE)
    assert view.model.data(en) == language_label("en-us")
    assert view.model.data(unknown) == "Bilinmiyor"
    assert view.model.data(unknown, Qt.ItemDataRole.ForegroundRole) is not None  # soluk renk
    assert view.model.data(en, Qt.ItemDataRole.ForegroundRole) is None


# --- kaynak dil değişimi ---------------------------------------------------------------------


def test_source_language_change_rebuilds_marks(qtbot: QtBot) -> None:
    view = _mixed(qtbot).report
    _use_language(view, "ja-jp")
    assert _checked(view) == {JA, *UNKNOWN}
    assert not view.model.is_enabled(_row(view, EN))
    _use_language(view, "en-us")
    assert _checked(view) == {EN, *UNKNOWN}


def test_manual_marks_survive_language_change(qtbot: QtBot) -> None:
    view = _mixed(qtbot).report
    unknown = view.model.index(_row(view, UNKNOWN[0]), COL_IMPORT)
    assert view.model.setData(unknown, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    english = view.model.index(_row(view, EN), COL_IMPORT)
    assert view.model.setData(english, Qt.CheckState.Unchecked, Qt.ItemDataRole.CheckStateRole)
    _use_language(view, "ja-jp")
    assert UNKNOWN[0] not in _checked(view)
    _use_language(view, "en-us")
    assert _checked(view) == set(UNKNOWN[1:])  # elle kaldırılanlar geri gelmez


def test_disabled_checkbox_cannot_be_changed(qtbot: QtBot) -> None:
    view = _mixed(qtbot).report
    ja = view.model.index(_row(view, JA), COL_IMPORT)
    assert not view.model.setData(ja, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    view.model.set_checked([_row(view, JA)], True)
    assert JA not in _checked(view)


# --- toplu seçim, boşluk tuşu ---------------------------------------------------------------


def test_select_and_deselect_visible_only_touch_visible_rows(qtbot: QtBot) -> None:
    view = _mixed(qtbot).report
    view.mode.setCurrentIndex(view.mode.findData(MODE_ALL))
    view.search.setText("menu_")
    view.deselect_visible.click()
    assert _checked(view) == {EN}
    view.search.setText("menu_1")
    view.select_visible.click()
    assert _checked(view) == {EN, UNKNOWN[1]}
    view.search.setText("a.msbt")  # kaynak dilde olmayan dosyaların kutusu toplu seçimde de değişmez
    view.select_visible.click()
    assert JA not in _checked(view)
    assert EN in _checked(view)


def test_space_toggles_selected_rows(qtbot: QtBot) -> None:
    page = _mixed(qtbot)
    page.show()
    view = page.report
    view.mode.setCurrentIndex(view.mode.findData(MODE_UNKNOWN_LANGUAGE))
    view.table.setFocus()
    view.table.selectAll()
    qtbot.keyClick(view.table, Qt.Key.Key_Space)
    assert _checked(view) == {EN}  # hepsi işaretliydi: hepsi kalktı
    qtbot.keyClick(view.table, Qt.Key.Key_Space)
    assert _checked(view) == {EN, *UNKNOWN}


# --- sayaç, düğme, çip -----------------------------------------------------------------------


def test_counter_reports_selection(qtbot: QtBot) -> None:
    view = _mixed(qtbot).report
    view.mode.setCurrentIndex(view.mode.findData(MODE_ALL))
    assert view.count_label.text() == "10 dosya gösteriliyor · 7 dosya aktarılacak"
    view.deselect_visible.click()
    assert view.count_label.text() == "10 dosya gösteriliyor · 0 dosya aktarılacak"


def test_import_button_and_chip_follow_selection(qtbot: QtBot) -> None:
    page = _mixed(qtbot)
    view = page.report
    assert view.import_button.isEnabled()
    assert page.header.chip.text() == "7 / 9 dosya seçili"
    view.mode.setCurrentIndex(view.mode.findData(MODE_ALL))
    view.deselect_visible.click()
    assert not view.import_button.isEnabled()
    assert "işaretleyin" in view.import_button.toolTip()
    assert page.header.chip.text() == "Hiç dosya seçilmedi"
    assert page.header.chip.property("state") == "warning"
    view.select_visible.click()
    assert view.import_button.isEnabled()
    assert view.import_button.toolTip() == ""
    assert page.header.chip.text() == "7 / 9 dosya seçili"
    assert _page(qtbot, [EN, *UNKNOWN[:1]]).header.chip.text() == "2 dosya aktarılabilir"


def test_no_importable_files_keeps_page_meaningful(qtbot: QtBot) -> None:
    page = _page(qtbot, [], (OTHER, "romfs/Data/b.bin"))
    view = page.report
    assert page.header.chip.text() == "Desteklenmeyen biçim"
    assert view.import_button.isHidden()
    assert view.selected_paths() == set()
    assert view.unknown_banner.isHidden()
    assert view.select_visible.isHidden()
    assert view.table.isColumnHidden(COL_IMPORT)
    assert view.count_label.text() == "2 dosya gösteriliyor"  # seçim söylenmez: aktarılabilir dosya yok
    view.mode.setCurrentIndex(view.mode.findData(MODE_UNKNOWN_LANGUAGE))
    assert view.proxy.rowCount() == 0
    for row in range(view.model.rowCount()):
        index = view.model.index(row, COL_IMPORT)
        assert view.model.data(index, Qt.ItemDataRole.CheckStateRole) is None


# --- dili anlaşılamayan dosyalar -------------------------------------------------------------


@pytest.mark.parametrize(("unknown", "shown"), [(0, False), (1, False), (2, True), (6, True)])
def test_unknown_language_banner_threshold(qtbot: QtBot, unknown: int, shown: bool) -> None:
    page = _page(qtbot, [EN, JA, *UNKNOWN[:unknown]])
    banner = page.report.unknown_banner
    assert banner.isHidden() is (not shown)
    if shown:
        assert banner.text.text() == (
            f"{unknown} dosyanın dili anlaşılamadı; hepsi aktarılacak. İstemediklerinizin işaretini kaldırın."
        )
        assert banner.property("state") == "warning"
        assert banner.action_button.text() == "Yalnızca bunları göster"


def test_banner_counts_only_checked_unknown_files(qtbot: QtBot) -> None:
    view = _page(qtbot, [EN, *UNKNOWN[:3]]).report
    assert not view.unknown_banner.isHidden()
    view.model.set_checked([_row(view, p) for p in UNKNOWN[:2]], False)
    assert view.unknown_banner.isHidden()  # işaretli tek dosya kaldı


def test_banner_action_filters_to_unknown_language(qtbot: QtBot) -> None:
    view = _mixed(qtbot).report
    view.unknown_banner.action_button.click()
    assert view.mode.currentData() == MODE_UNKNOWN_LANGUAGE
    shown = {view.proxy.index(i, COL_PATH).data() for i in range(view.proxy.rowCount())}
    assert shown == set(UNKNOWN)


def test_no_language_guessing_from_file_names(qtbot: QtBot) -> None:
    """Adında dil kodu gibi görünen ama tanınan bir kalıba uymayan dosya "Bilinmiyor" kalır."""
    view = _page(qtbot, ["romfs/Data/english_menu.msbt", "romfs/Data/menu_ja.msbt"]).report
    assert [view.model.language_of(i) for i in range(2)] == [None, None]


# --- ipuçları --------------------------------------------------------------------------------


def test_explanatory_tooltips_exist(qtbot: QtBot) -> None:
    view = _mixed(qtbot).report
    for col in range(view.model.columnCount(QModelIndex())):
        tip = view.model.headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
        assert tip
        assert "<table" in tip
    for widget in (view.engine_line, view.engine_evidence, view.game_line, *view.stat_boxes.values()):
        assert widget.toolTip(), widget
    assert "Yüksek" in view.engine_line.toolTip()
    assert "Güncelleme" in view.model.headerData(7, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)


# --- projeye göre varsayılan seçim -----------------------------------------------------------


def _with_project(qtbot: QtBot, paths: list[str], imported: list[str]) -> ReportView:
    page = ScanPage()
    qtbot.addWidget(page)
    _ALIVE.append(page)
    page.show_report(_report(paths), imported)
    return page.report


def test_default_selection_follows_project(qtbot: QtBot) -> None:
    view = _with_project(qtbot, [EN, JA, *UNKNOWN], [EN, UNKNOWN[0]])
    assert _checked(view) == {EN, UNKNOWN[0]}
    new = view.model.index(_row(view, UNKNOWN[1]), COL_IMPORT)
    assert view.model.flags(new) & Qt.ItemFlag.ItemIsEnabled  # projede yok: işaretsiz ama etkin
    assert view.model.flags(new) & Qt.ItemFlag.ItemIsUserCheckable
    assert view.model.setData(new, Qt.CheckState.Checked, Qt.ItemDataRole.CheckStateRole)
    assert UNKNOWN[1] in _checked(view)


def test_empty_project_keeps_everything_checked(qtbot: QtBot) -> None:
    view = _with_project(qtbot, [EN, JA, *UNKNOWN], [])
    assert _checked(view) == {EN, *UNKNOWN}
    assert "projede" not in view.count_label.text()


def test_project_file_in_other_language_stays_unchecked(qtbot: QtBot) -> None:
    view = _with_project(qtbot, [EN, JA], [EN, JA])
    assert _checked(view) == {EN}  # kaynak dil kuralı projeden önce gelir


def test_counter_mentions_files_missing_from_project(qtbot: QtBot) -> None:
    view = _with_project(qtbot, [EN, *UNKNOWN[:3]], [EN])
    view.mode.setCurrentIndex(view.mode.findData(MODE_ALL))
    assert view.count_label.text() == "4 dosya gösteriliyor · 1 dosya aktarılacak · 3 projede olmayan dosya işaretsiz"
    view.select_visible.click()
    assert view.count_label.text() == "4 dosya gösteriliyor · 4 dosya aktarılacak"
