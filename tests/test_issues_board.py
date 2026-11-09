"""Sorunlar panosu: çip listesi, düzeltme paneli, kapsam, yerinde düzenleme, bağlam menüsü."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.autofix import FIX_KINDS
from nxceviri.core.qa.checks import KIND_LABELS, QaIssue
from nxceviri.gui.qa_page import COL_TRANSLATION, FIX_TIPS, RISKY_FIX_KINDS, QaPage

pytestmark = pytest.mark.gui


def _row(i: int, translation: str = "Merhaba.") -> TranslationRow:
    return TranslationRow(i, "f", f"k{i}", "Hello", translation, "machine", "", (), None)


def _issues() -> list[QaIssue]:
    return [
        QaIssue(1, "k1", "placeholder", "error", "kod"),
        QaIssue(2, "k2", "spaces", "warning", "boşluk"),
        QaIssue(3, "k3", "spaces", "warning", "boşluk"),
        QaIssue(3, "k3", "end_punctuation", "warning", "nokta"),
        QaIssue(4, "k4", "spelling", "info", "yazım", ("başlatt",)),
    ]


@pytest.fixture
def page(qtbot: QtBot) -> QaPage:
    p = QaPage()
    qtbot.addWidget(p)
    p.resize(1400, 800)
    p.show()
    p.show_issues(_issues(), [_row(i) for i in range(1, 5)])
    return p


def _select(p: QaPage, *row_ids: int) -> None:
    p.table.clearSelection()
    for r in range(p.proxy.rowCount()):
        src = p.proxy.mapToSource(p.proxy.index(r, 0)).row()
        if p.model.issues[src].row_id in row_ids:
            p.table.selectionModel().select(
                p.proxy.index(r, 0),
                p.table.selectionModel().SelectionFlag.Select | p.table.selectionModel().SelectionFlag.Rows,
            )


def test_tab_is_named_sorunlar(page: QaPage) -> None:
    assert page.tabs.tabText(0) == "Sorunlar"


def test_chips_show_only_kinds_with_findings_and_counts(page: QaPage) -> None:
    kinds = page.chip_bar.visible_kinds()
    assert kinds == ["placeholder", "spaces", "spelling", "end_punctuation"]
    assert page.chip_bar.chips["spaces"].text() == f"{KIND_LABELS['spaces']} 2"
    assert page.chip_bar.chips["markup"].isHidden()


def test_chip_selection_filters_table(page: QaPage) -> None:
    assert page.proxy.rowCount() == 4  # bilgi (yazım) varsayılan gizli
    page.chip_bar.chips["spaces"].click()
    assert page.proxy.rowCount() == 2
    page.chip_bar.chips["end_punctuation"].click()
    assert page.proxy.rowCount() == 3
    page.chip_bar.chips["spaces"].click()
    page.chip_bar.chips["end_punctuation"].click()
    assert page.proxy.rowCount() == 4  # hiçbiri seçili değil: hepsi
    page.chip_bar.chips["spelling"].click()
    assert page.proxy.rowCount() == 1


def test_selected_chip_dropped_when_kind_disappears(page: QaPage) -> None:
    page.chip_bar.chips["placeholder"].click()
    page.show_issues([i for i in _issues() if i.kind != "placeholder"], [_row(i) for i in range(1, 5)])
    assert page.chip_bar.selected_kinds() == frozenset()
    assert page.proxy.rowCount() == 3


def test_summary_is_short(page: QaPage) -> None:
    assert page.summary.text() == "1 hata · 3 uyarı"


def test_fix_tips_cover_all_kinds() -> None:
    assert set(FIX_TIPS) == set(FIX_KINDS)
    assert all(FIX_TIPS[k].strip() for k in FIX_KINDS)
    assert set(FIX_KINDS) >= RISKY_FIX_KINDS
    assert {"end_punctuation", "code_position", "newlines"} <= RISKY_FIX_KINDS


def test_fix_boxes_hidden_without_findings_and_have_tips(page: QaPage) -> None:
    assert page.fix_boxes["spaces"].isVisibleTo(page)
    assert not page.fix_boxes["markup"].isVisibleTo(page)
    assert "Boşluk" in page.fix_boxes["spaces"].text()
    assert page.fix_boxes["spaces"].toolTip()


def test_risky_kinds_unchecked_on_first_open(page: QaPage) -> None:
    assert page.fix_boxes["spaces"].isChecked()
    for kind in RISKY_FIX_KINDS:
        assert not page.fix_boxes[kind].isChecked()
    page.set_checked_fix_kinds(["end_punctuation"])  # kayıtlı seçime uyulur
    assert page.checked_fix_kinds() == ["end_punctuation"]


def test_panel_collapse_and_persistence(qtbot: QtBot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat)
    p = QaPage()
    qtbot.addWidget(p)
    p.bind_settings(settings)
    p.resize(1400, 800)
    p.show()
    assert not p.fixes_collapsed()
    assert p.fix_body.isVisibleTo(p)
    p.fix_toggle.click()
    assert p.fixes_collapsed()
    assert not p.fix_body.isVisibleTo(p)
    assert str(settings.value("qa/fixes_collapsed")) in ("1", "true")
    q = QaPage()
    qtbot.addWidget(q)
    q.bind_settings(settings)
    q.resize(1400, 800)
    q.show()
    assert q.fixes_collapsed()
    q.fix_toggle.click()
    assert not q.fixes_collapsed()


def test_panel_starts_collapsed_when_narrow(qtbot: QtBot) -> None:
    p = QaPage()
    qtbot.addWidget(p)
    p.resize(800, 600)
    p.show()
    assert p.fixes_collapsed()


def test_scope_radios(page: QaPage) -> None:
    assert not page.scope_selected.isEnabled()
    assert page.scope_all.isChecked()
    assert page.scope_all.text() == "Tüm bulgular (3)"  # işaretli türlerdeki bulgular: kod 1 + boşluk 2
    _select(page, 2, 3)
    assert page.scope_selected.isEnabled()
    assert page.scope_selected.isChecked()
    assert page.scope_selected.text() == "Listede seçili 3 bulgu"
    got: list[tuple[list[str], list[int]]] = []
    page.fix_requested.connect(lambda k, r: got.append((k, r)))
    page.fix_button.click()
    assert got == [(["placeholder", "spaces"], [2, 3])]
    page.scope_all.setChecked(True)
    page.fix_button.click()
    assert got[-1] == (["placeholder", "spaces"], [])


def test_inline_edit_signal(page: QaPage) -> None:
    got: list[tuple[int, str]] = []
    page.translation_edited.connect(lambda i, t: got.append((i, t)))
    index = page.model.index(1, COL_TRANSLATION)
    assert index.flags() & Qt.ItemFlag.ItemIsEditable
    assert not page.model.index(1, 0).flags() & Qt.ItemFlag.ItemIsEditable
    page.model.setData(index, "Yeni", Qt.ItemDataRole.EditRole)
    assert got == [(2, "Yeni")]
    page.model.setData(index, "Merhaba.", Qt.ItemDataRole.EditRole)  # değişmedi
    assert got == [(2, "Yeni")]


def test_replace_row_issues(page: QaPage) -> None:
    _select(page, 3)
    assert len(page._selected_row_ids()) == 1
    page.table.verticalScrollBar().setValue(0)
    page.replace_row_issues(3, [QaIssue(3, "k3", "spaces", "warning", "boşluk")], _row(3, "Yeni"))
    assert page.chip_bar.chips["end_punctuation"].isHidden()
    assert page.chip_bar.chips["spaces"].text() == f"{KIND_LABELS['spaces']} 2"
    assert page.fix_counts["end_punctuation"] == 0
    assert page._selected_row_ids() == [3]  # seçim korundu
    src = [i for i in page.model.issues if i.row_id == 3]
    assert len(src) == 1
    assert page.model.rows[3].translation == "Yeni"
    page.replace_row_issues(3, [], _row(3, "Temiz"))
    assert [i.row_id for i in page.model.issues] == [1, 2, 4]
    assert page.summary.text() == "1 hata · 1 uyarı"
    assert page._selected_row_ids() == []


def _menu_texts(p: QaPage) -> list[str]:
    return [a.text() if not a.isSeparator() else "-" for a in p.context_menu().actions()]


def test_context_menu_by_kind(page: QaPage) -> None:
    assert _menu_texts(page) == ["Yazım sözlüğünü aç…"]
    _select(page, 2)
    assert _menu_texts(page) == [
        "Bu satırı düzelt",
        "Bu türdeki tümünü düzelt",
        "Çevir'de göster",
        "-",
        "Yazım sözlüğünü aç…",
    ]
    assert all(a.isEnabled() for a in page.context_menu().actions())
    page.chip_bar.chips["spelling"].click()
    _select(page, 4)
    assert _menu_texts(page) == ["Çevir'de göster", "-", "Yazım sözlüğüne ekle…", "Yazım sözlüğünü aç…"]


def test_context_menu_fix_actions(page: QaPage) -> None:
    got: list[tuple[list[str], list[int]]] = []
    page.fix_requested.connect(lambda k, r: got.append((k, r)))
    opened: list[int] = []
    page.open_row.connect(opened.append)
    _select(page, 3)  # iki bulgu: boşluk, sondaki noktalama
    actions = {a.text(): a for a in page.context_menu().actions()}
    actions["Bu satırı düzelt"].trigger()
    actions["Bu türdeki tümünü düzelt"].trigger()
    actions["Çevir'de göster"].trigger()
    assert got == [(["spaces", "end_punctuation"], [3]), (["spaces", "end_punctuation"], [])]
    assert opened == [3]


def test_fit_code_kinds_under_advanced(qtbot: QtBot) -> None:
    p = QaPage()
    qtbot.addWidget(p)
    p.resize(1400, 800)
    p.show()
    p.tabs.setCurrentIndex(1)
    assert not p.fit_advanced.body.isVisibleTo(p)
    p.fit_advanced.toggle.click()
    assert p.fit_advanced.body.isVisibleTo(p)
