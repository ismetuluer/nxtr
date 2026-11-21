"""Tablo başlıkları sütunlarının içeriğiyle aynı hizadadır: metin sola, sayı sağa."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QTableView, QTableWidget
from pytestqt.qtbot import QtBot

from nxceviri.core.formats import registry
from nxceviri.core.project import Change
from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.core.translate.terms import TermSuggestion
from nxceviri.gui.changes_dialog import ChangesDialog
from nxceviri.gui.limits_table import LimitsTable
from nxceviri.gui.machine_dialogs import GlossaryDialog, TermSuggestionsDialog
from nxceviri.gui.plugins_dialog import PluginsDialog
from nxceviri.gui.qa_page import QaPage
from nxceviri.gui.scan_page import COL_SIZE
from nxceviri.gui.spell_window import SpellWindow
from tests.test_scan_selection import _page as scan_page

pytestmark = pytest.mark.gui


def _is_left(header: QHeaderView) -> bool:
    return bool(header.defaultAlignment() & Qt.AlignmentFlag.AlignLeft)


def _header_align(table: QTableWidget | QTableView, col: int) -> Qt.AlignmentFlag:
    """Başlığın gerçekte çizileceği hiza: modelin verdiği, yoksa varsayılan."""
    value = table.model().headerData(col, Qt.Orientation.Horizontal, Qt.ItemDataRole.TextAlignmentRole)
    if value is None:
        return table.horizontalHeader().defaultAlignment()
    return Qt.AlignmentFlag(int(value))


def _is_right(table: QTableWidget | QTableView, col: int) -> bool:
    return bool(_header_align(table, col) & Qt.AlignmentFlag.AlignRight)


def test_scan_table_headers(qtbot: QtBot) -> None:
    table = scan_page(qtbot, ["romfs/Message/USen/a.msbt"]).report.table
    assert _is_left(table.horizontalHeader())
    assert _is_right(table, COL_SIZE)  # hücreler sağa yaslı
    assert not _is_right(table, COL_SIZE - 1)


def test_limits_table_headers(qtbot: QtBot) -> None:
    table = LimitsTable()
    qtbot.addWidget(table)
    assert _is_left(table.view.horizontalHeader())
    assert not _is_right(table.view, 0)
    assert _is_right(table.view, 1)


def test_qa_page_headers(qtbot: QtBot) -> None:
    page = QaPage()
    qtbot.addWidget(page)
    assert _is_left(page.font_table.horizontalHeader())
    assert _is_left(page.fit_kinds.horizontalHeader())


def test_plugins_dialog_headers(qtbot: QtBot, tmp_path: Path) -> None:
    dialog = PluginsDialog(
        None,
        report=registry.load_user_plugins([]),
        builtin=registry.BUILTIN_PLUGINS,
        install_dir=tmp_path,
        opener=lambda _path: None,
    )
    qtbot.addWidget(dialog)
    assert _is_left(dialog.table.horizontalHeader())


def test_changes_dialog_headers(qtbot: QtBot) -> None:
    changes = [Change(1, "Konusma/1", "Kaynak", "Eski", "machine", "", "Yeni", "retranslate", "")]
    dialog = ChangesDialog(None, "Değişiklikler", changes)
    qtbot.addWidget(dialog)
    assert _is_left(dialog.table.horizontalHeader())


def test_spell_window_headers(qtbot: QtBot) -> None:
    window = SpellWindow(None)
    qtbot.addWidget(window)
    assert _is_left(window.table.horizontalHeader())
    assert not _is_right(window.table, 0)
    assert _is_right(window.table, 1)  # "Sayı"


def test_glossary_dialog_headers(qtbot: QtBot, tmp_path: Path) -> None:
    dialog = GlossaryDialog(None, [GlossaryTerm("Sheriff", "Şerif", "unvan")], tmp_path)
    qtbot.addWidget(dialog)
    assert _is_left(dialog.table.horizontalHeader())


def test_term_suggestions_headers(qtbot: QtBot) -> None:
    dialog = TermSuggestionsDialog(None, [TermSuggestion("Mara", "Mara", "", 2)])
    qtbot.addWidget(dialog)
    assert _is_left(dialog.table.horizontalHeader())
    assert not _is_right(dialog.table, 0)
    assert _is_right(dialog.table, 3)  # "Geçiş" sayısı
