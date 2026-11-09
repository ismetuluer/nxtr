"""Anlık denetim: `LiveChecker` (önbellek, tür seçimi, artımlı tutarlılık) ve Çevir modeline bağlanması."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import KIND_LABELS
from nxceviri.core.qa.live import DEFAULT_LIVE_KINDS, LIVE_KINDS, LiveChecker, LiveContext, parse_live_kinds
from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import FitConfig
from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.core.translate.status import Status
from nxceviri.gui.settings_dialog import PAGE_LIVE, SettingsDialog
from nxceviri.gui.theme import DEFAULT_FONT_SIZE, ThemeMode
from nxceviri.gui.translate_page import COL_STATUS, COL_TRANSLATION, TranslatePage
from nxceviri.gui.view_actions import ViewActions
from tests.test_marked_delegate import make_page, make_row

pytestmark = pytest.mark.gui


def kinds_of(checker: LiveChecker, row: TranslationRow) -> set[str]:
    return {i.kind for i in checker.check(row)}


def fake_spell() -> SpellChecker:
    return SpellChecker(BloomFilter.build(["merhaba", "dünya", "selam"], error_rate=0.0001))


def test_all_kinds_known_and_default_is_everything() -> None:
    for kind in ("inconsistent", "spelling", "placeholder"):
        assert kind in LIVE_KINDS
    assert len(set(LIVE_KINDS)) == len(LIVE_KINDS)
    assert all(kind in KIND_LABELS for kind in LIVE_KINDS)
    assert frozenset(LIVE_KINDS) == DEFAULT_LIVE_KINDS


def test_detects_row_problems_with_default_context() -> None:
    checker = LiveChecker()
    row = make_row(1, "Hi ⟦1⟧", "Selam", labels=("<c>",))
    assert "placeholder" in kinds_of(checker, row)
    assert checker.check(make_row(2, "Bye", "")) == []


def test_disabled_kind_is_not_reported() -> None:
    checker = LiveChecker()
    row = make_row(1, "Hi\nthere", "Selam")
    assert "newlines" in kinds_of(checker, row)
    checker.set_context(LiveContext(kinds=DEFAULT_LIVE_KINDS - {"newlines"}))
    assert "newlines" not in kinds_of(checker, row)


def test_context_change_clears_cache() -> None:
    checker = LiveChecker()
    row = make_row(1, "Hi", "Şu çok")
    assert "glyph" not in kinds_of(checker, row)
    checker.set_context(LiveContext(missing_letters="Ş"))
    assert "glyph" in kinds_of(checker, row)
    checker.set_context(LiveContext(missing_letters="Ş", transliterated="Ş"))
    assert "glyph" not in kinds_of(checker, row)


def test_result_is_cached_until_row_changes() -> None:
    checker = LiveChecker()
    row = make_row(1, "Hi", "Selam")
    first = checker.check(row)
    assert checker.check(row) is first
    other = make_row(1, "Hi", "Selam dünya ve ve")
    assert checker.check(other) is not first


def test_glossary_and_spelling_findings_are_live() -> None:
    checker = LiveChecker()
    checker.set_context(LiveContext(glossary=(GlossaryTerm("Pines", "Çam"),), spell=fake_spell()))
    row = make_row(1, "Silver Pines", "Gümüş Ormanı")
    found = {i.kind: i for i in checker.check(row)}
    assert "glossary" in found
    assert "spelling" in found
    assert found["spelling"].words
    assert found["spelling"].severity == "info"


def test_glossary_words_are_not_spelling_errors() -> None:
    checker = LiveChecker()
    checker.set_context(LiveContext(glossary=(GlossaryTerm("Pines", "Çamlık"),), spell=fake_spell()))
    row = make_row(1, "The Pines", "Merhaba çamlık")
    assert "spelling" not in kinds_of(checker, row)


def test_fit_rules_report_long_line() -> None:
    checker = LiveChecker()
    fit = FitConfig(default=FitRules(width=10, max_lines=2))
    checker.set_context(LiveContext(fit=fit))
    row = make_row(1, "Hello there my friend", "Selam benim çok sevgili dostum")
    assert "line_too_long" in kinds_of(checker, row)


def test_inconsistent_updates_other_rows_incrementally() -> None:
    checker = LiveChecker()
    a = make_row(1, "Yes", "Evet")
    b = make_row(2, "Yes", "Evet")
    c = make_row(3, "No", "Hayır")
    checker.set_rows([a, b, c])
    assert "inconsistent" not in kinds_of(checker, a)
    b2 = make_row(2, "Yes", "Tamam")
    assert checker.update_row(b2) == {1}
    assert "inconsistent" in kinds_of(checker, a)
    assert "inconsistent" in kinds_of(checker, b2)
    assert "inconsistent" not in kinds_of(checker, c)
    b3 = make_row(2, "Yes", "Evet")
    assert checker.update_row(b3) == {1}
    assert "inconsistent" not in kinds_of(checker, a)


def test_update_row_reports_nothing_when_kind_off_or_alone() -> None:
    checker = LiveChecker()
    a, b, c = make_row(1, "Yes", "Evet"), make_row(2, "Yes", "Evet"), make_row(3, "No", "Hayır")
    checker.set_rows([a, b, c])
    assert checker.update_row(make_row(3, "No", "Yok")) == set()
    checker.set_context(LiveContext(kinds=DEFAULT_LIVE_KINDS - {"inconsistent"}))
    assert checker.update_row(make_row(2, "Yes", "Tamam")) == set()


def test_all_approved_group_is_not_inconsistent() -> None:
    checker = LiveChecker()
    a = make_row(1, "Yes", "Evet", status=Status.APPROVED)
    b = make_row(2, "Yes", "Tamam", status=Status.APPROVED)
    checker.set_rows([a, b])
    assert "inconsistent" not in kinds_of(checker, a)


def test_parse_live_kinds_valid_empty_and_broken() -> None:
    assert parse_live_kinds("spelling,newlines") == frozenset({"spelling", "newlines"})
    assert parse_live_kinds("") == frozenset()
    assert parse_live_kinds("spelling,nonsense") == DEFAULT_LIVE_KINDS
    assert parse_live_kinds(None) == DEFAULT_LIVE_KINDS


# --- Çevir modeli ------------------------------------------------------------------------


def test_model_shows_live_findings_and_refreshes_peers(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "Yes", "Evet"), make_row(2, "Yes", "Evet")])
    model = page.model
    assert not model.issues(model.rows[0])
    changed: list[int] = []
    model.dataChanged.connect(lambda top, bottom, *_roles: changed.append(top.row()))
    model.update_rows([make_row(2, "Yes", "Tamam")])
    assert any(i.kind == "inconsistent" for i in model.issues(model.rows[0]))
    assert 0 in changed  # öteki satırın hücreleri yenilendi


def test_model_context_applies_and_refreshes(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "Hi", "Şu çok")])
    assert not page.model.issues(page.model.rows[0])
    page.set_live_context(LiveContext(missing_letters="Ş"))
    assert [i.kind for i in page.model.issues(page.model.rows[0])] == ["glyph"]
    page.set_live_context(LiveContext(missing_letters="Ş", kinds=frozenset({"newlines"})))
    assert not page.model.issues(page.model.rows[0])


def test_model_merges_qa_without_duplicates(qtbot: QtBot) -> None:
    from nxceviri.core.qa.checks import run_checks

    row = make_row(1, "Hi ⟦1⟧", "Selam", labels=("<c>",))
    page = make_page(qtbot, [row])
    page.set_qa_issues(run_checks([row], "", ""), [row])
    kinds = [i.kind for i in page.model.issues(row)]
    assert kinds.count("placeholder") == 1


def test_status_cell_summary_uses_live_context(qtbot: QtBot) -> None:
    page = make_page(qtbot, [make_row(1, "Hi", "Şu çok")])
    page.set_live_context(LiveContext(missing_letters="Ş"))
    text = page.model.index(0, COL_STATUS).data(Qt.ItemDataRole.DisplayRole)
    assert "1 uyarı" in text
    assert page.model.index(0, COL_TRANSLATION).data(Qt.ItemDataRole.ToolTipRole) is not None


# --- Ayarlar sayfası ---------------------------------------------------------------------


def _dialog(tmp_path: Path, **kwargs: object) -> SettingsDialog:
    from nxceviri.core.secrets import MemoryStore
    from nxceviri.gui.shortcuts import ShortcutRegistry

    settings = QSettings(str(tmp_path / "ayar.ini"), QSettings.Format.IniFormat)
    registry = ShortcutRegistry()
    registry.bind_settings(settings)
    view = ViewActions()
    view.bind_settings(settings)
    actions = []
    for name in ("a", "b", "c"):
        action = QAction(name)
        action.setCheckable(True)
        actions.append(action)
    options: dict[str, object] = {
        "theme": ThemeMode.SYSTEM,
        "font_size": DEFAULT_FONT_SIZE,
        "wrap": actions[0],
        "issue_colors": actions[1],
        "error_rows": actions[2],
        "updates_available": True,
    }
    options.update(kwargs)
    dialog = SettingsDialog(None, settings, registry, view, MemoryStore(), **options)  # type: ignore[arg-type]
    dialog._test_actions = actions  # type: ignore[attr-defined]  # eylemler pencereyle birlikte yaşasın
    return dialog


def test_settings_live_page_lists_every_kind(qtbot: QtBot, tmp_path: Path) -> None:
    dialog = _dialog(tmp_path, live_kinds=["spelling", "newlines"])
    qtbot.addWidget(dialog)
    dialog.show_page(PAGE_LIVE)
    assert dialog.current_page == PAGE_LIVE
    assert set(dialog.live_checks) == set(LIVE_KINDS)
    assert {k for k, box in dialog.live_checks.items() if box.isChecked()} == {"spelling", "newlines"}
    assert dialog.live_checks["spelling"].text() == KIND_LABELS["spelling"]


def test_settings_live_toggle_emits_list_and_does_not_write(qtbot: QtBot, tmp_path: Path) -> None:
    dialog = _dialog(tmp_path, live_kinds=LIVE_KINDS)
    qtbot.addWidget(dialog)
    with qtbot.waitSignal(dialog.live_kinds_changed) as blocker:
        dialog.live_checks["newlines"].setChecked(False)
    emitted = blocker.args[0]
    assert "newlines" not in emitted
    assert "spelling" in emitted
    assert [k for k in LIVE_KINDS if k in emitted] == emitted  # gösterim sırası
    assert dialog._settings.value("qa/live_kinds") is None


def test_settings_live_all_and_none_buttons(qtbot: QtBot, tmp_path: Path) -> None:
    dialog = _dialog(tmp_path, live_kinds=["spelling"])
    qtbot.addWidget(dialog)
    last: list[list[str]] = []
    dialog.live_kinds_changed.connect(last.append)
    dialog.live_all.click()
    assert all(box.isChecked() for box in dialog.live_checks.values())
    assert last[-1] == list(LIVE_KINDS)
    dialog.live_none.click()
    assert not any(box.isChecked() for box in dialog.live_checks.values())
    assert last[-1] == []


# --- Süre --------------------------------------------------------------------------------


def test_fifty_thousand_rows_first_paint_and_edit_under_half_second(qtbot: QtBot) -> None:
    rows = [make_row(i, f"Kaynak metin {i % 5000}", f"Çeviri metni {i % 4000}") for i in range(1, 50_001)]
    page = TranslatePage()
    qtbot.addWidget(page)
    page.set_rows(rows)
    page.set_live_context(LiveContext(spell=fake_spell()))
    model = page.model
    start = time.perf_counter()
    for r in range(40):
        for col in range(model.columnCount()):
            model.index(r, col).data(Qt.ItemDataRole.DisplayRole)
            model.index(r, col).data(Qt.ItemDataRole.ToolTipRole)
        model.index(r, COL_TRANSLATION).data(Qt.ItemDataRole.ForegroundRole)
    target = model.rows[0]
    model.update_rows([make_row(target.id, target.source, "Başka bir çeviri")])
    assert any(i.kind == "inconsistent" for i in model.issues(model.rows[model.position(target.id + 5000) or 0]))
    elapsed = time.perf_counter() - start
    assert elapsed < 0.5, f"{elapsed:.2f} sn"


# --- Ana pencere -------------------------------------------------------------------------


def _window(qtbot: QtBot, tmp_path: Path, saved: str | None = None):  # type: ignore[no-untyped-def]
    from nxceviri.core.project import Project
    from nxceviri.core.secrets import MemoryStore
    from nxceviri.gui.main_window import MainWindow

    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    if saved is not None:
        settings.setValue("qa/live_kinds", saved)
    window = MainWindow(settings)
    window.secrets = MemoryStore()
    window._replace_project(Project.new())
    qtbot.addWidget(window)
    return window


def test_window_default_kinds_when_unset(qtbot: QtBot, tmp_path: Path) -> None:
    window = _window(qtbot, tmp_path)
    assert window._live_kinds == DEFAULT_LIVE_KINDS
    window.dirty = False


def test_window_broken_setting_falls_back_to_default(qtbot: QtBot, tmp_path: Path) -> None:
    window = _window(qtbot, tmp_path, saved="spelling,bozuk")
    assert window._live_kinds == DEFAULT_LIVE_KINDS
    window.dirty = False


def test_window_saves_and_applies_kinds_from_settings_signal(qtbot: QtBot, tmp_path: Path) -> None:
    window = _window(qtbot, tmp_path)
    window._set_live_kinds(["spelling", "newlines"])
    assert window.settings.value("qa/live_kinds") == "newlines,spelling"
    assert window.translate_page.model.live._context.kinds == frozenset({"spelling", "newlines"})
    reopened = _window(qtbot, tmp_path, saved=str(window.settings.value("qa/live_kinds")))
    assert reopened._live_kinds == frozenset({"spelling", "newlines"})
    window.dirty = False
    reopened.dirty = False


def test_window_empty_setting_means_none(qtbot: QtBot, tmp_path: Path) -> None:
    window = _window(qtbot, tmp_path, saved="")
    assert window._live_kinds == frozenset()
    window.dirty = False
