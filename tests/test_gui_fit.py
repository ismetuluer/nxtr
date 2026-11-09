"""Arayüz: Kontrol Et ekranındaki "Satırları Sığdır" kartı ve ana pencere bağlantısı."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QComboBox
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.qa.checks import KIND_LABELS
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.translate.cleanup import tidy_punctuation
from nxceviri.core.translate.codekinds import KIND_PAGE_BREAK, KIND_VARIABLE, CodeKinds
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import FitConfig, learn_rules, load_config, save_config
from nxceviri.gui.main_window import STEP_QA, MainWindow
from nxceviri.gui.qa_page import QaPage
from tests.task_wait import finish_task

pytestmark = pytest.mark.gui

FIT_KINDS = {"line_too_long", "page_too_tall", "bad_break"}
CODE = "Kod 0x05"


def _project() -> Project:
    p = Project.new()
    p.import_texts(
        [
            ImportedFile(
                "Dialogue.tsv",
                "0100",
                "unity",
                "base",
                (
                    TextEntry("d01", 0, "Hello there, how are you?", ()),
                    TextEntry("d02", 1, "Press ⟦1⟧ now.", (ControlCode(b"\x0e\x05", CODE),)),
                ),
            ),
            ImportedFile("Menu.tsv", "0100", "unity", "base", (TextEntry("m01", 0, "Start", ()),)),
        ]
    )
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations(
        [
            (rows["d01"].id, "Merhaba dostum, nasılsın?"),  # 25 karakter: 20 sınırına sığmaz
            (rows["d02"].id, "Şimdi ⟦1⟧ bas."),
            (rows["m01"].id, "Başla"),
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
        w.task.wait()
    w.dirty = False
    w.close()
    w.deleteLater()


def _rows(w: MainWindow) -> dict[str, TranslationRow]:
    return {r.key: r for r in w.project.translation_rows()}


def _page(w: MainWindow) -> QaPage:
    w.nav.setCurrentRow(STEP_QA)
    page = w.qa_page
    page.tabs.setCurrentIndex(1)
    assert page.tabs.tabText(1) == "Sığdırma"
    return page


def _enable(page: QaPage, width: int, lines: int) -> None:
    page.fit_enabled.setChecked(True)
    page.fit_width.setValue(width)
    page.fit_lines.setValue(lines)


def _kinds_found(page: QaPage) -> set[str]:
    return {i.kind for i in page.model.issues}


def test_no_rules_message(window: MainWindow) -> None:
    page = _page(window)
    assert not page.fit_enabled.isChecked()
    assert page.fit_note.isVisibleTo(page)
    assert page.fit_note.text() == "Sınır girilmedi; sığdırma kapalı."
    for widget in (page.fit_width, page.fit_lines, page.fit_learn, page.fit_kinds, page.fit_scope):
        assert not widget.isEnabled()
    page.check_button.click()
    finish_task(window)
    assert not _kinds_found(page) & FIT_KINDS
    assert load_config(window.project).default is None


def test_fit_card_saves_and_flags(window: MainWindow) -> None:
    page = _page(window)
    page.check_button.click()
    finish_task(window)
    assert KIND_LABELS["line_too_long"] not in page.summary.text()
    _enable(page, 20, 2)
    assert not page.fit_note.isVisibleTo(page)
    assert page.fit_width.isEnabled()
    assert load_config(window.project).default == FitRules(20, 2)
    assert window.dirty
    page.check_button.click()
    finish_task(window)
    assert "1 uyarı" in page.summary.text()

    page.fit_enabled.setChecked(False)  # kapatınca sınır saklanır ama uygulanmaz
    config = load_config(window.project)
    assert not config.enabled
    assert config.default == FitRules(20, 2)
    page.check_button.click()
    finish_task(window)
    assert not _kinds_found(page) & FIT_KINDS


def test_learn_rules_fills_fields(window: MainWindow) -> None:
    page = _page(window)
    _enable(page, 40, 3)
    expected = learn_rules(window.project.translation_rows(), CodeKinds({}))
    assert expected is not None
    page.fit_learn.click()
    assert (page.fit_width.value(), page.fit_lines.value()) == (expected.width, expected.max_lines)
    assert load_config(window.project).default == FitRules(40, 3)  # öğrenilen değer kendiliğinden kaydedilmez
    page.fit_lines.setValue(2)  # kullanıcı değiştirince alanlardaki değerler kaydedilir
    assert load_config(window.project).default == FitRules(expected.width, 2)


def test_learn_rules_for_file_scope(window: MainWindow) -> None:
    page = _page(window)
    _enable(page, 40, 3)
    page.fit_scope.setCurrentIndex(page.fit_scope.findData("Menu.tsv"))
    assert page.fit_inherit.isVisibleTo(page)
    assert page.fit_inherit.isChecked()
    assert not page.fit_width.isEnabled()  # proje sınırı kullanılıyor
    page.fit_learn.click()
    assert not page.fit_inherit.isChecked()
    assert (page.fit_width.value(), page.fit_lines.value()) == (5, 1)  # "Start"
    assert load_config(window.project).per_file == {}
    page.fit_width.setValue(8)
    assert load_config(window.project).per_file == {"Menu.tsv": FitRules(8, 1)}
    assert load_config(window.project).default == FitRules(40, 3)

    page.fit_inherit.setChecked(True)  # dosya yeniden proje sınırını kullanır
    assert load_config(window.project).per_file == {}
    assert (page.fit_width.value(), page.fit_lines.value()) == (40, 3)
    page.fit_scope.setCurrentIndex(0)
    assert not page.fit_inherit.isVisibleTo(page)


def test_learn_without_source_text(window: MainWindow) -> None:
    page = _page(window)
    _enable(page, 40, 3)
    page.show_learned(None)
    assert page.fit_learn_note.text() == "Ölçülecek orijinal metin yok."
    assert (page.fit_width.value(), page.fit_lines.value()) == (40, 3)


def test_code_kind_table_edit_persists(window: MainWindow) -> None:
    page = _page(window)
    _enable(page, 40, 3)
    assert page.fit_kinds.rowCount() == 1
    item = page.fit_kinds.item(0, 0)
    assert item is not None
    assert item.text() == CODE
    combo = page.fit_kinds.cellWidget(0, 1)
    assert isinstance(combo, QComboBox)
    assert combo.currentText() == "Diğer"  # tahmin
    combo.setCurrentIndex(combo.findData(KIND_PAGE_BREAK))
    assert combo.currentText() == "Sayfa sonu"
    assert load_config(window.project).kinds.mapping == {CODE: KIND_PAGE_BREAK}


def test_set_fit_does_not_emit(qtbot: QtBot, window: MainWindow) -> None:
    page = _page(window)
    config = FitConfig(FitRules(30, 2, 4), {"Menu.tsv": FitRules(10, 1)}, CodeKinds({CODE: KIND_VARIABLE}))
    with qtbot.assertNotEmitted(page.fit_changed):
        page.set_fit(config, ["Dialogue.tsv", "Menu.tsv"], [CODE])
    assert page.fit_enabled.isChecked()
    assert (page.fit_width.value(), page.fit_lines.value()) == (30, 2)
    combo = page.fit_kinds.cellWidget(0, 1)
    assert isinstance(combo, QComboBox)
    assert combo.currentData() == KIND_VARIABLE
    assert page.fit_config() == config
    page.fit_scope.setCurrentIndex(page.fit_scope.findData("Menu.tsv"))
    assert not page.fit_inherit.isChecked()
    assert (page.fit_width.value(), page.fit_lines.value()) == (10, 1)


def test_program_fix_applies_fit(window: MainWindow) -> None:
    page = _page(window)
    _enable(page, 20, 2)
    page.run_checks.emit()
    finish_task(window)
    window.apply_fixes(["line_too_long", "page_too_tall", "bad_break"], [])
    assert _rows(window)["d01"].translation == "Merhaba dostum,\nnasılsın?"
    assert not _kinds_found(page) & FIT_KINDS  # denetim kendiliğinden yeniden çalıştı
    assert "Sorun bulunmadı" in page.summary.text()


def test_learned_values_saved_when_checking(window: MainWindow) -> None:
    page = _page(window)
    _enable(page, 40, 3)
    expected = learn_rules(window.project.translation_rows(), CodeKinds({}))
    page.fit_learn.click()
    page.check_button.click()  # denetim kutularda görünen değerlerle yapılır, öneri böylece kaydedilir
    finish_task(window)
    assert load_config(window.project).default == expected
    assert page.fit_learn_note.text() == ""


def test_saved_fit_shown_after_returning(window: MainWindow) -> None:
    page = _page(window)
    _enable(page, 22, 2)
    window.nav.setCurrentRow(0)
    save_config(window.project, FitConfig(FitRules(30, 1)))
    page = _page(window)  # sayfaya dönünce kayıtlı ayar yeniden gösterilir
    assert page.fit_enabled.isChecked()
    assert (page.fit_width.value(), page.fit_lines.value()) == (30, 1)


def test_toggle_on_in_file_scope_seeds_default(window: MainWindow) -> None:
    page = _page(window)
    _enable(page, 20, 2)
    page.fit_scope.setCurrentIndex(page.fit_scope.findData("Menu.tsv"))
    page.fit_enabled.setChecked(False)
    save_config(window.project, FitConfig())  # hiç sınır kayıtlı değil (yeni proje gibi)
    window.nav.setCurrentRow(0)
    page = _page(window)
    assert page.fit_scope.currentData() == "Menu.tsv"  # kapsam korunur
    assert not page.fit_enabled.isChecked()
    page.fit_enabled.setChecked(True)
    config = load_config(window.project)
    assert config.enabled
    assert config.default == FitRules(40, 3)  # açınca proje sınırı tohumlanır
    assert (page.fit_width.value(), page.fit_lines.value()) == (40, 3)
    window.nav.setCurrentRow(0)
    page = _page(window)
    assert page.fit_enabled.isChecked()


def test_toggle_off_keeps_limits(window: MainWindow) -> None:
    page = _page(window)
    _enable(page, 20, 2)
    page.fit_scope.setCurrentIndex(page.fit_scope.findData("Menu.tsv"))
    page.fit_inherit.setChecked(False)
    page.fit_width.setValue(8)
    stored = FitConfig(FitRules(20, 2), {"Menu.tsv": FitRules(8, 2)})
    assert load_config(window.project) == stored
    page.fit_enabled.setChecked(False)
    assert load_config(window.project) == replace(stored, enabled=False)
    assert not page.fit_width.isEnabled()
    assert page.fit_note.text() == "Sığdırma kapalı; sınırlar saklanıyor."
    page.check_button.click()
    finish_task(window)
    assert not _kinds_found(page) & FIT_KINDS

    window.nav.setCurrentRow(0)
    page = _page(window)  # kapalı durum ve değerler sayfaya dönünce korunur
    assert not page.fit_enabled.isChecked()
    assert (page.fit_width.value(), page.fit_lines.value()) == (8, 2)
    page.fit_enabled.setChecked(True)
    assert load_config(window.project) == stored
    assert page.fit_config() == stored


def test_cleanup_fix_tips_match_what_they_do() -> None:
    """Düzeltme ipuçlarındaki örnekler temizliğin gerçekte yaptığıyla aynı olmalı."""
    from nxceviri.gui.qa_page import FIX_TIPS

    for kind in ("extra_dots", "space_before_punct"):
        pairs = re.findall(r"‘([^’]+)’ → ‘([^’]+)’", FIX_TIPS[kind])
        assert pairs
        for before, after in pairs:
            assert tidy_punctuation("x", before) == after


def test_cleanup_options_are_not_a_separate_block(window: MainWindow) -> None:
    """Boşluk ve noktalama temizlikleri ayrı bir "sığdırırken ayrıca" bloğu değil, düzeltme türleridir."""
    page = _page(window)
    assert not hasattr(page, "fit_spaces")
    assert {"double_space", "extra_dots", "space_before_punct"} <= set(page.fix_boxes)
