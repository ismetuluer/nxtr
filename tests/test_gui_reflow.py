"""Arayüz: grup başına sığdırma sınırı ve "Satırları yeniden böl" eylemleri."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMenu
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import EACH_GROUP, GROUP_PREFIX, FitConfig, load_config, save_config
from nxceviri.core.translate.status import Status
from nxceviri.gui.main_window import STEP_QA, MainWindow
from nxceviri.gui.qa_page import QaPage

pytestmark = pytest.mark.gui

LONG = "word " * 19 + "end"  # 98 karakter
BREAK = ControlCode(b"\x0e\x01", "Satır sonu")


def _project() -> Project:
    p = Project.new()
    p.import_texts(
        [
            ImportedFile(
                "Tables.tsv",
                "0100",
                "unity",
                "base",
                (
                    TextEntry("a1", 0, LONG, (), context="Dialogue/a1"),
                    TextEntry("a2", 1, "short talk here", (), context="Dialogue/a2"),
                    TextEntry("m1", 2, "Start the game now please", (), context="Menu/m1"),
                    TextEntry("m2", 3, "Quit", (), context="Menu/m2"),
                    TextEntry("c1", 4, "Left⟦1⟧Right text here", (BREAK,), context="Code/c1"),
                ),
            )
        ]
    )
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations(
        [
            (rows["a1"].id, "bir iki üç dört beş altı\nyedi sekiz dokuz on onbir on iki on üç"),
            (rows["a2"].id, "kısa konuşma burada"),
            (rows["m1"].id, "oyunu şimdi\nbaşlat lütfen"),
            (rows["m2"].id, "Çık"),
            (rows["c1"].id, "Sol taraf bu metin⟦1⟧Sağ"),
        ],
        machine=True,
    )
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.show()
    yield w
    if w.task is not None:
        w.task.cancel()


def _rows(w: MainWindow) -> dict[str, TranslationRow]:
    return {r.key: r for r in w.project.translation_rows()}


def _page(w: MainWindow) -> QaPage:
    w.nav.setCurrentRow(STEP_QA)
    w.qa_page.tabs.setCurrentIndex(1)
    return w.qa_page


def test_scope_lists_groups_and_each_group(window: MainWindow) -> None:
    page = _page(window)
    page.fit_enabled.setChecked(True)
    data = [page.fit_scope.itemData(i) for i in range(page.fit_scope.count())]
    assert data[0] == ""
    assert GROUP_PREFIX + "Dialogue" in data
    assert GROUP_PREFIX + "Menu" in data
    assert data[-1] == EACH_GROUP


def test_group_scope_saves_own_rules_and_inherit_removes(window: MainWindow) -> None:
    page = _page(window)
    page.fit_enabled.setChecked(True)
    page.fit_width.setValue(100)
    page.fit_lines.setValue(2)
    page.fit_scope.setCurrentIndex(page.fit_scope.findData(GROUP_PREFIX + "Menu"))
    assert page.fit_inherit.isVisibleTo(page)
    assert page.fit_inherit.isChecked()
    page.fit_inherit.setChecked(False)
    page.fit_width.setValue(30)
    assert load_config(window.project).per_group == {"Menu": FitRules(30, 2)}
    assert load_config(window.project).default == FitRules(100, 2)
    page.fit_inherit.setChecked(True)
    assert load_config(window.project).per_group == {}


def test_learn_single_group(window: MainWindow) -> None:
    page = _page(window)
    page.fit_enabled.setChecked(True)
    page.fit_scope.setCurrentIndex(page.fit_scope.findData(GROUP_PREFIX + "Menu"))
    page.fit_learn.click()
    assert (page.fit_width.value(), page.fit_lines.value()) == (25, 1)  # "Start the game now please"
    assert load_config(window.project).per_group == {}  # öneri kendiliğinden kaydedilmez


def test_learn_each_group_writes_only_needed_rules(window: MainWindow) -> None:
    page = _page(window)
    page.fit_enabled.setChecked(True)
    page.fit_width.setValue(98)
    page.fit_lines.setValue(1)
    page.fit_scope.setCurrentIndex(page.fit_scope.findData(EACH_GROUP))
    assert not page.fit_width.isEnabled()
    page.fit_learn.click()
    config = load_config(window.project)
    assert config.default == FitRules(98, 1)
    assert config.per_group == {"Menu": FitRules(25, 1), "Code": FitRules(15, 2)}  # Dialogue proje sınırıyla aynı
    assert "güncellendi" in page.fit_learn_note.text()
    page.fit_learn.click()  # ikinci kez: değişen yok
    assert "gerekmedi" in page.fit_learn_note.text()
    assert load_config(window.project).per_group == config.per_group


def test_group_rules_apply_in_checks(window: MainWindow) -> None:
    save_config(window.project, FitConfig(FitRules(100, 3), per_group={"Menu": FitRules(10, 3)}))
    window._push_fit_to_page()
    page = _page(window)
    page.check_button.click()
    flagged = {i.row_id for i in page.model.issues if i.kind == "line_too_long"}
    assert flagged == {_rows(window)["m1"].id}


def test_reflow_selected_rows_and_undo(window: MainWindow) -> None:
    save_config(window.project, FitConfig(FitRules(24, 3)))
    window._push_fit_to_page()
    before = _rows(window)
    window.reflow_selected([before["a1"].id, before["m1"].id])
    after = _rows(window)
    assert after["a1"].translation != before["a1"].translation
    assert all(len(line) <= 24 for line in after["a1"].translation.split("\n"))
    assert " ".join(after["a1"].translation.split()) == " ".join(before["a1"].translation.split())
    assert after["a2"].translation == before["a2"].translation  # seçilmeyen satıra dokunulmadı
    assert after["a1"].status == Status.MACHINE
    window.undo_last()
    assert _rows(window)["a1"].translation == before["a1"].translation
    assert _rows(window)["m1"].translation == before["m1"].translation


def test_reflow_keeps_codes(window: MainWindow) -> None:
    before = _rows(window)["c1"]
    window.reflow_selected([before.id])
    after = _rows(window)["c1"]
    assert placeholders.tokens_in(after.translation) == placeholders.tokens_in(before.translation)
    assert after.translation != before.translation
    assert after.status == before.status


def test_context_menu_reflow_action(window: MainWindow) -> None:
    save_config(window.project, FitConfig(FitRules(24, 3)))
    window._push_fit_to_page()
    page = window.translate_page
    row_id = _rows(window)["a1"].id
    page.select_row(row_id)
    page._show_context_menu(page.table.visualRect(page.proxy.index(0, 0)).center())
    menu = page.table.findChild(QMenu)
    assert menu is not None
    edit = next(a.menu() for a in menu.actions() if a.text() == "Düzenle")
    assert isinstance(edit, QMenu)
    reflow = next(a for a in edit.actions() if a.text().startswith("Satırları yeniden böl"))
    assert reflow.isEnabled()
    reflow.trigger()
    menu.close()
    assert all(len(line) <= 24 for line in _rows(window)["a1"].translation.split("\n"))
    assert "yeniden bölündü" in page.banner.text.text()


def test_scope_hides_single_file_basename_groups(window: MainWindow) -> None:
    save_config(window.project, FitConfig(FitRules(100, 3), per_group={"Tables.tsv": FitRules(9, 1)}))
    window._refresh_qa()
    page = _page(window)
    data = [page.fit_scope.itemData(i) for i in range(page.fit_scope.count())]
    assert GROUP_PREFIX + "Tables.tsv" not in data


def test_reflow_of_approved_row_does_not_touch_translation_memory(window: MainWindow) -> None:
    save_config(window.project, FitConfig(FitRules(24, 3)))
    window._push_fit_to_page()
    before = _rows(window)["a1"]
    window.translate_page.model.apply([(before.id, before.translation)])  # onayla: belleğe insan çevirisi olarak girer
    memory = window.project.memory_lookup([before.source])
    window.reflow_selected([before.id])
    after = _rows(window)["a1"]
    assert after.translation != before.translation
    assert after.status == Status.APPROVED
    assert window.project.memory_lookup([before.source]) == memory  # yeniden bölme belleği değiştirmez
