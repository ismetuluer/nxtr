"""Sorunlar panosu: çip listesi, düzeltme paneli, kapsam, yerinde düzenleme, bağlam menüsü."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QListWidgetItem, QMenu
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.autofix import FIX_KINDS
from nxceviri.core.qa.checks import KIND_LABELS, QaIssue
from nxceviri.gui.issue_kinds import KindList
from nxceviri.gui.qa_page import (
    FIX_TIPS,
    RISKY_FIX_KINDS,
    SORT_FILE,
    SORT_FINDING,
    SORT_NUMBER,
    SORT_SEVERITY,
    IssueModel,
    QaPage,
)

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


def _click(
    qtbot: QtBot, lst: KindList, item: QListWidgetItem, mod: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier
) -> None:
    qtbot.mouseClick(lst.viewport(), Qt.MouseButton.LeftButton, mod, lst.visualItemRect(item).center())


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


def test_kind_list_shows_only_kinds_with_findings_and_counts(page: QaPage) -> None:
    kinds = page.kind_list.visible_kinds()
    assert kinds == ["placeholder", "spelling", "end_punctuation", "spaces"]  # grup sırası: önemden küçüğe
    assert page.kind_list.count_of("spaces") == 2
    assert page.kind_list.kind_item("spaces").text() == KIND_LABELS["spaces"]
    assert "markup" not in kinds


def test_kind_selection_filters_table(qtbot: QtBot, page: QaPage) -> None:
    lst = page.kind_list
    ctrl = Qt.KeyboardModifier.ControlModifier
    assert page.proxy.rowCount() == 4  # bilgi (yazım) varsayılan gizli
    _click(qtbot, lst, lst.kind_item("spaces"))
    assert page.proxy.rowCount() == 2
    _click(qtbot, lst, lst.kind_item("end_punctuation"), ctrl)
    assert page.proxy.rowCount() == 3
    _click(qtbot, lst, lst.kind_item("spaces"), ctrl)
    _click(qtbot, lst, lst.kind_item("end_punctuation"), ctrl)
    assert page.proxy.rowCount() == 4  # hiçbiri seçili değil: hepsi
    _click(qtbot, lst, lst.kind_item("spelling"))
    assert page.proxy.rowCount() == 1


def test_selected_kind_dropped_when_it_disappears(qtbot: QtBot, page: QaPage) -> None:
    _click(qtbot, page.kind_list, page.kind_list.kind_item("placeholder"))
    page.show_issues([i for i in _issues() if i.kind != "placeholder"], [_row(i) for i in range(1, 5)])
    assert page.kind_list.selected_kinds() == frozenset()
    assert page.proxy.rowCount() == 3


def test_summary_is_short(page: QaPage) -> None:
    assert page.summary.text() == "1 hata · 3 uyarı"


def test_fix_tips_cover_all_kinds() -> None:
    assert set(FIX_TIPS) == set(FIX_KINDS)
    assert all(FIX_TIPS[k].strip() for k in FIX_KINDS)
    assert set(FIX_KINDS) >= RISKY_FIX_KINDS
    assert {"end_punctuation", "code_position", "newlines"} <= RISKY_FIX_KINDS


def test_no_options_menu_or_side_panel_any_more(page: QaPage) -> None:
    for name in ("fix_body", "fix_toggle", "scope_selected", "scope_all", "fix_boxes", "fix_options", "fix_menu"):
        assert not hasattr(page, name)
    assert not hasattr(page, "fix_kinds_changed")


def test_fix_bar_all_view_counts_only_safe_kinds(page: QaPage) -> None:
    # "Tüm bulgular": kod 1 + boşluk 2; sondaki noktalama riskli olduğundan sayılmaz ve uyarı çıkmaz.
    assert page.fix_bar.isVisibleTo(page)
    assert page.fix_text.text() == "3 bulgu güvenle düzeltilebilir."
    assert page.fix_button.text() == "3 bulguyu düzelt"
    assert not page.fix_warning.isVisibleTo(page.fix_bar)
    assert page.fix_button.isEnabled()


def test_fix_bar_selected_kind_counts_all_visible_and_warns_for_risky(qtbot: QtBot, page: QaPage) -> None:
    _click(qtbot, page.kind_list, page.kind_list.kind_item("spaces"))
    assert page.fix_text.text() == "Bu 2 bulgu kendiliğinden düzeltilebilir."
    assert page.fix_button.text() == "2 bulguyu düzelt"
    assert not page.fix_warning.isVisibleTo(page.fix_bar)
    _click(qtbot, page.kind_list, page.kind_list.kind_item("end_punctuation"))  # riskli tür: seçmek onaydır
    assert page.fix_text.text() == "Bu 1 bulgu kendiliğinden düzeltilebilir."
    assert page.fix_button.text() == "1 bulguyu düzelt"
    assert page.fix_warning.isVisibleTo(page.fix_bar)
    assert page.fix_warning.text() == "Bu düzeltmeler yanılabilir; sonucu gözden geçirin."
    assert page.fix_button.isEnabled()


def test_fix_bar_follows_row_selection_including_risky(page: QaPage) -> None:
    _select(page, 2)  # yalnızca boşluk
    assert page.fix_text.text() == "Seçili 1 bulgu kendiliğinden düzeltilebilir."
    assert page.fix_button.text() == "Seçili 1 bulguyu düzelt"
    assert not page.fix_warning.isVisibleTo(page.fix_bar)
    _select(page, 2, 3)  # boşluk, boşluk, sondaki noktalama (riskli, açık seçim onaydır)
    assert page.fix_text.text() == "Seçili 3 bulgu kendiliğinden düzeltilebilir."
    assert page.fix_button.text() == "Seçili 3 bulguyu düzelt"
    assert page.fix_warning.isVisibleTo(page.fix_bar)
    page.table.clearSelection()
    assert page.fix_button.text() == "3 bulguyu düzelt"


def test_fix_bar_hidden_when_scope_is_empty(qtbot: QtBot, page: QaPage) -> None:
    _click(qtbot, page.kind_list, page.kind_list.kind_item("spelling"))  # yalnızca düzeltilemeyen tür
    assert not page.fix_bar.isVisibleTo(page)
    page.show_issues([], [])
    assert not page.fix_bar.isVisibleTo(page)
    only_risky = [QaIssue(3, "k3", "end_punctuation", "warning", "nokta")]
    page.show_issues(only_risky, [_row(3)])  # "Tüm bulgular"da yalnızca riskli tür: kapsam boş
    assert not page.fix_bar.isVisibleTo(page)


def test_fix_button_emits_scope_kinds_and_row_ids(qtbot: QtBot, page: QaPage) -> None:
    got: list[tuple[list[str], list[int]]] = []
    page.fix_requested.connect(lambda k, r: got.append((k, r)))
    page.fix_button.click()
    assert got == [(["placeholder", "spaces"], [1, 2, 3])]  # Tüm bulgular: riskli sondaki noktalama yok
    _select(page, 2, 3)
    page.fix_button.click()
    kinds, row_ids = got[-1]
    assert set(kinds) == {"spaces", "end_punctuation"}
    assert row_ids == [2, 3]
    page.table.clearSelection()
    _click(qtbot, page.kind_list, page.kind_list.kind_item("end_punctuation"))
    page.fix_button.click()
    assert got[-1] == (["end_punctuation"], [3])


def test_check_button_becomes_secondary_after_first_check(qtbot: QtBot) -> None:
    p = QaPage()
    qtbot.addWidget(p)
    assert (p.check_button.text(), p.check_button.property("kind")) == ("Denetle", "primary")
    p.show_issues(_issues(), [_row(i) for i in range(1, 5)])
    assert (p.check_button.text(), p.check_button.property("kind")) == ("Yeniden Denetle", None)
    assert p.fix_button.property("kind") == "primary"  # ekrandaki tek dolu düğme düzeltme düğmesi
    p.reset()
    assert (p.check_button.text(), p.check_button.property("kind")) == ("Denetle", "primary")


def test_inline_edit_signal(page: QaPage) -> None:
    got: list[tuple[int, str]] = []
    page.translation_edited.connect(lambda i, t: got.append((i, t)))
    src = next(n for n, i in enumerate(page.model.issues) if i.row_id == 2)
    index = page.model.index(src, 0)
    assert index.flags() & Qt.ItemFlag.ItemIsEditable
    page.model.setData(index, "Yeni", Qt.ItemDataRole.EditRole)
    assert got == [(2, "Yeni")]
    page.model.setData(index, "Merhaba.", Qt.ItemDataRole.EditRole)  # değişmedi
    assert got == [(2, "Yeni")]


def test_replace_row_issues(page: QaPage) -> None:
    _select(page, 3)
    assert len(page._selected_row_ids()) == 1
    page.table.verticalScrollBar().setValue(0)
    page.replace_row_issues(3, [QaIssue(3, "k3", "spaces", "warning", "boşluk")], _row(3, "Yeni"))
    assert "end_punctuation" not in page.kind_list.visible_kinds()
    assert page.kind_list.count_of("spaces") == 2
    assert page.kind_list.count_of("end_punctuation") == 0
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


def test_context_menu_by_kind(qtbot: QtBot, page: QaPage) -> None:
    assert _menu_texts(page) == ["Yazım sözlüğünü aç…", "-", "Sırala"]
    _select(page, 2)
    assert _menu_texts(page) == [
        "Bu satırı düzelt",
        "Tüm “Boşluk” bulgularını düzelt",
        "Çevir'de göster",
        "Bulguyu yok say",
        "-",
        "Yazım sözlüğünü aç…",
        "-",
        "Sırala",
    ]
    assert all(a.isEnabled() for a in page.context_menu().actions())
    _click(qtbot, page.kind_list, page.kind_list.kind_item("spelling"))
    _select(page, 4)
    assert _menu_texts(page) == [
        "Çevir'de göster",
        "Bulguyu yok say",
        "-",
        "Yazım sözlüğüne ekle…",
        "Yazım sözlüğünü aç…",
        "-",
        "Sırala",
    ]


def test_context_menu_fix_actions(page: QaPage) -> None:
    got: list[tuple[list[str], list[int]]] = []
    page.fix_requested.connect(lambda k, r: got.append((k, r)))
    opened: list[int] = []
    page.open_row.connect(opened.append)
    _select(page, 3)  # iki bulgu: boşluk, sondaki noktalama
    actions = {a.text(): a for a in page.context_menu().actions()}
    actions["Bu satırı düzelt"].trigger()
    actions["Bu türlerdeki tüm bulguları düzelt"].trigger()
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


# --- Sırala alt menüsü ve sıralama düzenleri ---


def _order(model: IssueModel) -> list[tuple[int, str]]:
    return [(i.row_id, i.kind) for i in model.issues]


def _mixed() -> tuple[list[QaIssue], list[TranslationRow]]:
    issues = [
        QaIssue(3, "k3", "spaces", "warning", "Boşluk"),
        QaIssue(1, "k1", "spelling", "info", "yazım"),
        QaIssue(2, "k2", "placeholder", "error", "Kod"),
        QaIssue(1, "k1", "spaces", "warning", "boşluk"),
    ]
    rows = [
        TranslationRow(1, "b.msbt", "k1", "H", "M", "machine", "", (), None),
        TranslationRow(2, "a.msbt", "k2", "H", "M", "machine", "", (), None),
    ]
    return issues, rows


def test_sort_modes_order(qtbot: QtBot) -> None:
    issues, rows = _mixed()
    model = IssueModel()
    model.set_issues(issues, {r.id: r for r in rows})
    assert _order(model) == [(2, "placeholder"), (1, "spaces"), (3, "spaces"), (1, "spelling")]
    model.set_sort(SORT_NUMBER)
    assert _order(model) == [(1, "spaces"), (1, "spelling"), (2, "placeholder"), (3, "spaces")]
    model.set_sort(SORT_FINDING)
    assert [i.message for i in model.issues] == ["boşluk", "Boşluk", "Kod", "yazım"]
    assert [i.row_id for i in model.issues][:2] == [1, 3]
    model.set_sort(SORT_FILE)
    # dosyası olmayan satır (3) boş dize olarak başa gelir; sonra a.msbt, b.msbt
    assert [i.row_id for i in model.issues] == [3, 2, 1, 1]
    model.set_sort("bilinmeyen")
    assert model.sort_mode == SORT_SEVERITY


def test_replace_row_respects_sort_mode() -> None:
    issues, rows = _mixed()
    for mode, expected in (
        (SORT_NUMBER, [1, 1, 2, 2, 3]),
        (SORT_FILE, [3, 2, 2, 1, 1]),
        (SORT_FINDING, [1, 2, 3, 2, 1]),
    ):
        model = IssueModel()
        model.set_issues(issues, {r.id: r for r in rows})
        model.set_sort(mode)
        model.replace_row(2, [QaIssue(2, "k2", "spaces", "warning", "boşluk"), issues[2]], rows[1])
        assert [i.row_id for i in model.issues] == expected, mode


def _sort_menu(p: QaPage) -> QMenu:
    menu = next(a.menu() for a in p.context_menu().actions() if a.text() == "Sırala")
    assert isinstance(menu, QMenu)
    return menu


def test_sort_submenu_and_choice(qtbot: QtBot, page: QaPage) -> None:
    sub = _sort_menu(page)
    assert [a.text() for a in sub.actions()] == ["Önem sırası", "Satır numarası", "Bulguya göre", "Dosyaya göre"]
    assert [a.isChecked() for a in sub.actions()] == [True, False, False, False]
    sub.actions()[1].trigger()
    assert page.model.sort_mode == SORT_NUMBER
    assert [i.row_id for i in page.model.issues] == [1, 2, 3, 3, 4]
    sub2 = _sort_menu(page)
    assert [a.isChecked() for a in sub2.actions()] == [False, True, False, False]


def test_sort_choice_persists(qtbot: QtBot, tmp_path: Path) -> None:
    ini = tmp_path / "s.ini"
    p = QaPage()
    qtbot.addWidget(p)
    p.bind_settings(QSettings(str(ini), QSettings.Format.IniFormat))
    p.set_sort_mode(SORT_FILE)
    q = QaPage()
    qtbot.addWidget(q)
    q.bind_settings(QSettings(str(ini), QSettings.Format.IniFormat))
    assert q.model.sort_mode == SORT_FILE
    bad = QSettings(str(tmp_path / "b.ini"), QSettings.Format.IniFormat)
    bad.setValue("qa/sort", "saçma")
    r = QaPage()
    qtbot.addWidget(r)
    r.bind_settings(bad)
    assert r.model.sort_mode == SORT_SEVERITY
