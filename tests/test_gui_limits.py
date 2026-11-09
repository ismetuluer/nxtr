"""Arayüz: grup ve anahtar sınırları tablosu (`LimitsTable`)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import FitConfig
from nxceviri.gui.limits_table import LimitsTable

pytestmark = pytest.mark.gui


def _row(key: str, source: str, file: str = "a.msbt", context: str = "") -> TranslationRow:
    return TranslationRow(1, file, key, source, "", "untranslated", "", (), None, context)


ROWS = [
    _row("menu_a", "kısa", "Dialogue.tsv", "Dialogue/menu_a"),
    _row("menu_b", "iki\nsatır", "Dialogue.tsv", "Dialogue/menu_b"),
    _row("talk_1", "uzun bir konuşma satırı", "Story.tsv", "Story/talk_1"),
]


def _table(qtbot: QtBot, config: FitConfig | None = None, learned: dict[str, FitRules] | None = None) -> LimitsTable:
    table = LimitsTable()
    qtbot.addWidget(table)
    table.set_data(ROWS, config or FitConfig(), learned or {})
    return table


def _find(table: LimitsTable, scope: str) -> int:
    for r in range(table.model_row_count()):
        if table.scope_at(r) == scope:
            return r
    raise AssertionError(scope)


def test_lists_groups_with_counts(qtbot: QtBot) -> None:
    table = _table(qtbot, learned={"Dialogue": FitRules(10, 2)})
    r = _find(table, "group:Dialogue")
    assert table.cell_text(r, 0) == "Dialogue"
    assert table.cell_text(r, 1) == "2"
    assert table.cell_text(r, 2) == "5"
    assert table.cell_text(r, 3) == "10 × 2"
    assert table.cell_text(r, 4) == ""
    assert table.cell_text(_find(table, "group:Story"), 3) == "—"


def test_edit_manual_group_limit_emits_config(qtbot: QtBot) -> None:
    table = _table(qtbot)
    r = _find(table, "group:Story")
    with qtbot.waitSignal(table.rule_edited) as sig:
        assert table.edit_cell(r, 4, "30 × 2")
    assert sig.args == ["group:Story", FitRules(30, 2)]
    assert table.cell_text(r, 4) == "30 × 2"


def test_edit_manual_limit_accepts_comma_and_single_number(qtbot: QtBot) -> None:
    table = _table(qtbot, FitConfig(per_group={"Dialogue": FitRules(20, 3)}))
    r = _find(table, "group:Dialogue")
    with qtbot.waitSignal(table.rule_edited) as sig:
        table.edit_cell(r, 4, "25")
    assert sig.args == ["group:Dialogue", FitRules(25, 3)]  # satır sayısı eskisi kalır
    with qtbot.waitSignal(table.rule_edited) as sig:
        table.edit_cell(r, 4, "18, 4")
    assert sig.args == ["group:Dialogue", FitRules(18, 4)]


def test_clearing_manual_limit_removes_it(qtbot: QtBot) -> None:
    table = _table(qtbot, FitConfig(per_group={"Story": FitRules(30, 2)}))
    r = _find(table, "group:Story")
    for text in ("0", ""):
        table.set_data(ROWS, FitConfig(per_group={"Story": FitRules(30, 2)}), {})
        with qtbot.waitSignal(table.rule_edited) as sig:
            assert table.edit_cell(r, 4, text)
        assert sig.args == ["group:Story", None]


def test_invalid_manual_limit_rejected(qtbot: QtBot) -> None:
    table = _table(qtbot)
    r = _find(table, "group:Story")
    with qtbot.assertNotEmitted(table.rule_edited):
        assert not table.edit_cell(r, 4, "abc")
        assert not table.edit_cell(r, 4, "-3 × 2")
    assert table.cell_text(r, 4) == ""
    assert table.status_text() != ""


def test_add_key_pattern_shows_match_count(qtbot: QtBot) -> None:
    table = _table(qtbot)
    assert table.add_pattern("menu_*")
    r = _find(table, "key:menu_*")
    assert table.cell_text(r, 0) == "Anahtar: menu_*"
    assert table.cell_text(r, 1) == "2"
    assert "2" in table.status_text()


def test_add_pattern_rejects_empty_and_duplicate(qtbot: QtBot) -> None:
    table = _table(qtbot)
    assert not table.add_pattern("   ")
    assert table.add_pattern("menu_*")
    assert not table.add_pattern("MENU_*")
    assert sum(1 for r in range(table.model_row_count()) if table.scope_at(r).startswith("key:")) == 1


def test_manual_limit_on_key_pattern_and_remove(qtbot: QtBot) -> None:
    table = _table(qtbot)
    table.add_pattern("menu_*")
    r = _find(table, "key:menu_*")
    with qtbot.waitSignal(table.rule_edited) as sig:
        table.edit_cell(r, 4, "12 × 1")
    assert sig.args == ["key:menu_*", FitRules(12, 1)]
    table.select_row(r)
    with qtbot.waitSignal(table.rule_edited) as sig:
        table.remove_selected_pattern()
    assert sig.args == ["key:menu_*", None]
    assert all(not table.scope_at(i).startswith("key:") for i in range(table.model_row_count()))


def test_remove_button_only_for_key_rows(qtbot: QtBot) -> None:
    table = _table(qtbot)
    table.add_pattern("menu_*")
    table.select_row(_find(table, "group:Story"))
    assert not table.remove_button.isEnabled()
    table.select_row(_find(table, "key:menu_*"))
    assert table.remove_button.isEnabled()


def test_saved_key_patterns_listed(qtbot: QtBot) -> None:
    table = _table(qtbot, FitConfig(per_key={"talk_*": FitRules(40, 2)}))
    r = _find(table, "key:talk_*")
    assert table.cell_text(r, 4) == "40 × 2"
    assert table.cell_text(r, 1) == "1"


def test_learn_all_button_emits_signal(qtbot: QtBot) -> None:
    table = _table(qtbot)
    with qtbot.waitSignal(table.learn_all_requested):
        table.learn_button.click()


def test_search_filters_rows(qtbot: QtBot) -> None:
    table = _table(qtbot)
    table.search.setText("story")
    assert table.visible_row_count() == 1
    table.search.setText("")
    assert table.visible_row_count() == 2


def test_manual_cell_is_editable_others_not(qtbot: QtBot) -> None:
    table = _table(qtbot)
    r = _find(table, "group:Story")
    assert table.cell_flags(r, 4) & Qt.ItemFlag.ItemIsEditable
    assert not table.cell_flags(r, 1) & Qt.ItemFlag.ItemIsEditable


def test_thousands_of_groups(qtbot: QtBot) -> None:
    rows = [_row(f"k{i}", "abc\nde", f"f{i}.msbt") for i in range(5000)]
    table = LimitsTable()
    qtbot.addWidget(table)
    table.set_data(rows, FitConfig(), {})
    assert table.model_row_count() == 5000
