"""Bul ve Değiştir çubuğu düzeltmeleri: değiştirme şablonu, süzgeç koruması, hız ve zaman sınırı."""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from nxceviri.core.translate.regexguard import RISKY_MESSAGE, TIMEOUT_MESSAGE, Deadline, SearchTimeout, is_risky
from nxceviri.core.translate.replace import find_pattern, plan_replace, replacement_error
from nxceviri.gui.find_replace import SCOPE_ALL, SCOPE_VISIBLE
from nxceviri.gui.main_window import MANUAL_LIMIT_KEY, STEP_TRANSLATE, MainWindow
from nxceviri.gui.translate_page import TranslatePage
from tests.test_editor import _project
from tests.test_find_bar import Writer, make_page
from tests.test_marked_delegate import make_row

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


# --- 1. Hatalı değiştirme şablonu ---------------------------------------------------------


@pytest.mark.parametrize("template", ["\\2", "x\\", "\\g<yok>", "\\q"])
def test_bad_replacement_template_is_reported_not_raised(template: str) -> None:
    rows = [make_row(1, "a", "abc")]
    plan = plan_replace(rows, "(b)", template, regex=True)
    assert plan.changes == []
    assert plan.error.startswith("Değiştirme metni geçersiz")


def test_valid_replacement_templates_pass() -> None:
    pattern = find_pattern(r"(?P<ad>b)(c)", regex=True)
    assert pattern is not None
    assert replacement_error(pattern, r"\2\1\g<ad>") == ""
    assert replacement_error(pattern, "düz") == ""


def test_bar_shows_replacement_error_and_blocks_actions(qtbot: QtBot) -> None:
    page, writer = make_page(qtbot)
    bar = page.find_bar
    page.open_find(True)
    bar.regex_button.setChecked(True)
    bar.find_edit.setText("(içki)")
    bar.preview_box.setChecked(True)
    bar.replace_edit.setText("\\2")  # tek grup var
    assert bar.replace_error.startswith("Değiştirme metni geçersiz")
    assert bar.status_label.text() == bar.replace_error
    assert not bar.replace_button.isEnabled()
    assert not bar.replace_all_button.isEnabled()
    assert not bar.preview_box.isEnabled()
    assert page.model.find_marks.preview == {}
    bar.replace_all()
    bar.replace_current()
    assert writer.calls == []
    bar.replace_edit.setText("x\\")
    assert bar.replace_error
    bar.replace_edit.setText("[\\1]")
    assert bar.replace_error == ""
    assert bar.replace_all_button.isEnabled()
    assert bar.preview_box.isEnabled()


# --- 2. Süzgeç bul çubuğu tarafından temizlenmez ---------------------------------------------


def test_filter_active_makes_scope_visible_and_marks_counter(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    bar = page.find_bar
    page.search.setText("limit")
    page.open_find(False)
    bar.find_edit.setText("içki")
    assert bar.scope == SCOPE_VISIBLE
    assert bar.match_count == 1
    assert "süzgeçli" in bar.count_label.text()
    assert page.search.text() == "limit"  # süzgeç dokunulmadan kaldı


def test_scope_all_with_hidden_match_offers_clear_filter_link(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    bar = page.find_bar
    page.search.setText("limit")
    page.open_find(False)
    bar.set_scope(SCOPE_ALL)
    bar.find_edit.setText("içmem")  # yalnızca süzgeçle gizli satır 4'te
    current = page.current_row()
    assert current is None or current.id != 4
    assert page.search.text() == "limit"  # kendiliğinden temizlenmedi
    assert bar.notice_label.isVisibleTo(bar)
    assert "süzgeç nedeniyle gizli" in bar.notice_label.text()
    assert bar.clear_filters_link.isVisibleTo(bar)
    bar.clear_filters_link.click()
    assert page.search.text() == ""
    assert not bar.notice_label.isVisibleTo(bar)
    current = page.current_row()
    assert current is not None
    assert current.id == 4


def test_filter_keeps_group_and_key_filters(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    page.search.setText("limit")
    page.open_find(False)
    page.find_bar.set_scope(SCOPE_ALL)
    page.find_bar.find_edit.setText("içmem")
    assert page.search.text() == "limit"
    assert page.proxy.rowCount() == 1


# --- 3. Görünmez süzgeç ----------------------------------------------------------------------


def test_pending_filter_on_hidden_column_is_dropped(qtbot: QtBot) -> None:
    from PySide6.QtCore import QSettings

    from nxceviri.gui.translate_page import COL_KEY

    page = TranslatePage()
    qtbot.addWidget(page)
    page.resize(1300, 800)
    page.show()
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        settings = QSettings(tmp + "/s.ini", QSettings.Format.IniFormat)
        page.bind_settings(settings)
        page.set_project_key("A")
        rows = [make_row(1, "a", "x"), make_row(2, "b", "y")]
        page.set_rows(rows)
        page.key_filter.set_selected({"k1"})
        assert page.proxy.rowCount() == 1
        page.set_project_key("B")  # başka proje
        page.table.setColumnHidden(COL_KEY, True)  # uygulama geneli sütun gizleme
        page.set_project_key("A")
        page.set_rows(rows)
        assert not page.key_filter.active
        assert page.proxy.rowCount() == 2
        assert not page.filter_chip.isVisibleTo(page)


def test_filter_chip_shows_when_a_filter_is_active_and_clears(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    assert not page.filter_chip.isVisibleTo(page)
    page.search.setText("limit")
    assert page.filter_chip.isVisibleTo(page)
    assert "Süzgeç etkin" in page.filter_chip.text()
    page.filter_chip.click()
    assert page.search.text() == ""
    assert not page.filter_chip.isVisibleTo(page)


# --- 6. Felaket regex --------------------------------------------------------------------------


def test_catastrophic_regex_stops_with_message(qtbot: QtBot) -> None:
    page, _ = make_page(qtbot)
    bar = page.find_bar
    page.open_find(False)
    page.model.update_rows([])
    from dataclasses import replace

    row = page.model.row_by_id(1)
    assert row is not None
    page.model.update_rows([replace(row, translation="a" * 40 + "!")])
    bar.regex_button.setChecked(True)
    started = time.perf_counter()
    bar.find_edit.setText("(a+)+$")
    elapsed = time.perf_counter() - started
    assert elapsed < 5
    assert bar.error == RISKY_MESSAGE
    assert bar.notice_label.text() == RISKY_MESSAGE
    assert bar.count_label.text() == "Durduruldu"
    assert not bar.replace_all_button.isEnabled()
    bar.find_edit.setText("içki")  # sade desen yine çalışır
    assert bar.error == ""
    assert bar.match_count >= 1


def test_pattern_re_compiles_still() -> None:
    assert find_pattern("a", regex=True) == re.compile("a", re.IGNORECASE)


@pytest.mark.parametrize("pattern", ["(a+)+$", "(a*)*", r"(\w+\s?)+", "(a|aa)+", "(x+x+)+y", "((a+))+", "(a+){2,}"])
def test_risky_patterns_are_detected(pattern: str) -> None:
    assert is_risky(pattern)


@pytest.mark.parametrize(
    "pattern",
    ["a+", "(foo|bar)+", r"(\d+)", "a+b+", "(ab)+", r"\(a+\)+", "(?i)a+", "(?P<n>a)+", "(a+)?", "x{", r"(\w+) (\w+)"],
)
def test_safe_patterns_are_not_flagged(pattern: str) -> None:
    assert not is_risky(pattern)


def test_deadline_stops_a_slow_search(monkeypatch: pytest.MonkeyPatch) -> None:
    deadline = Deadline(0.0)
    time.sleep(0.01)
    with pytest.raises(SearchTimeout):
        deadline.check()
    rows = [make_row(i, "s", "metin") for i in range(5)]
    plan = plan_replace(rows, "metin", "x", budget=-1.0)
    assert plan.error == TIMEOUT_MESSAGE
    assert plan.changes == []


def test_bar_reports_budget_overrun(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> None:
    from nxceviri.gui import find_replace

    page, _ = make_page(qtbot)
    monkeypatch.setattr(find_replace, "SEARCH_BUDGET", -1.0)
    page.open_find(False)
    page.find_bar.find_edit.setText("içki")
    assert page.find_bar.error == TIMEOUT_MESSAGE
    assert page.find_bar.notice_label.text() == TIMEOUT_MESSAGE
    assert page.find_bar.match_count == 0


# --- 7. Ölçüm ---------------------------------------------------------------------------------


def test_keystroke_work_on_large_table_is_fast(qtbot: QtBot) -> None:
    page = TranslatePage()
    qtbot.addWidget(page)
    page.resize(1300, 900)
    page.show()
    rows = [make_row(i, f"Source {i}", f"Çeviri metni numara {i} içki") for i in range(1, 50001)]
    page.replace_fn = Writer(page)
    page.set_rows(rows)
    bar = page.find_bar
    page.open_find(True)
    bar.preview_box.setChecked(True)
    bar.replace_edit.setText("su")
    bar.flush()
    QApplication.processEvents()
    started = time.perf_counter()
    bar.find_edit.setText("çeviri")
    bar.flush()
    QApplication.processEvents()
    cost = time.perf_counter() - started
    print(f"50.000 satır, tuş vuruşu başına arayüz işi: {cost * 1000:.0f} ms")
    assert cost < 0.25  # tek başına ~0,1 sn; tam set yükünde 0,19 sn görüldü (kaçak saniyeleri yakalamak yeter)


# --- 8. Elle sınır proje başına -------------------------------------------------------------------


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    from nxceviri.core.secrets import MemoryStore

    w = MainWindow(QSettings(str(tmp_path / "b.ini"), QSettings.Format.IniFormat))
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.resize(1180, 780)
    w.show()
    w.nav.setCurrentRow(STEP_TRANSLATE)
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def test_manual_limit_is_saved_per_project(window: MainWindow) -> None:
    pane = window.translate_page.pane
    pane.limit_box.setChecked(True)
    pane.limit_spin.setValue(37)
    assert window.project.setting(MANUAL_LIMIT_KEY) == "37"
    window._replace_project(_project())  # başka proje: sınır taşınmaz
    assert pane.manual_limit is None
    pane.limit_box.setChecked(True)
    pane.limit_spin.setValue(12)
    assert window.project.setting(MANUAL_LIMIT_KEY) == "12"
    pane.limit_box.setChecked(False)
    assert window.project.setting(MANUAL_LIMIT_KEY) == "0"
    window.project.set_setting(MANUAL_LIMIT_KEY, "44")
    window._push_fit_to_page()
    assert pane.manual_limit == 44


def test_stopped_sidebar_animations_do_not_pile_up(
    window: MainWindow, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtCore import QCoreApplication, QEvent

    from nxceviri.gui import main_window
    from nxceviri.gui.spring import SpringAnimator

    monkeypatch.setattr(main_window, "animations_enabled", lambda: True)
    for _ in range(6):  # her çağrı öncekini durdurur
        window.set_nav_collapsed(not window._nav_collapsed)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert len(window.findChildren(SpringAnimator)) <= 1
    qtbot.waitUntil(lambda: window._nav_anim is None, timeout=3000)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert window.findChildren(SpringAnimator) == []
