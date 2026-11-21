"""Çevir tablosunun sağ tık menüsünden önerilen düzeltmeyi uygulamak (Kontrol Et'e gitmeden)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project
from nxceviri.gui.main_window import MainWindow
from nxceviri.gui.translate_page import FIX_MENU_ROWS
from tests.test_menus import _select
from tests.test_statusbar import _make_window

pytestmark = pytest.mark.gui


def _project() -> Project:
    p = Project.new()
    entries = (
        TextEntry("a", 0, "Very nice", ()),
        TextEntry("b", 1, "Hello there", ()),
        TextEntry("c", 2, "Good", ()),
    )
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations(
        [(rows["a"].id, "Çok  güzel"), (rows["b"].id, "Merhaba orada."), (rows["c"].id, "İyi")], machine=True
    )
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = _make_window(qtbot, tmp_path, _project())
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _menu(w: MainWindow, keys: set[str]) -> QMenu:
    _select(w, keys)
    page = w.translate_page
    return page.build_context_menu(page.selected_rows())


def _fix_action(menu: QMenu) -> QAction | None:
    return next((a for a in menu.actions() if a.text().startswith("Düzelt")), None)


def _translation(w: MainWindow, key: str) -> str:
    return next(r.translation for r in w.translate_page.model.rows if r.key == key)


def test_context_menu_applies_suggested_fix_in_place(window: MainWindow) -> None:
    action = _fix_action(_menu(window, {"a"}))
    assert action is not None
    assert action.text() == "Düzelt: Çift boşluk"
    action.trigger()
    assert _translation(window, "a") == "Çok güzel"
    assert "düzeltildi" in window.translate_page.notice_text


def test_context_menu_has_no_fix_for_clean_row(window: MainWindow) -> None:
    assert _fix_action(_menu(window, {"c"})) is None


def test_risky_fix_only_offered_for_single_row(window: MainWindow) -> None:
    single = _fix_action(_menu(window, {"b"}))
    assert single is not None
    assert "Sondaki noktalama" in single.text()
    both = _fix_action(_menu(window, {"a", "b"}))
    assert both is not None
    assert "Sondaki noktalama" not in both.text()  # toplu riskli düzeltme Kontrol Et'te


def test_fix_menu_skipped_for_huge_selection(window: MainWindow) -> None:
    page = window.translate_page
    rows = page.model.rows[:1] * (FIX_MENU_ROWS + 1)
    assert _fix_action(page.build_context_menu(rows)) is None
