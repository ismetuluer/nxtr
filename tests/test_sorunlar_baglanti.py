"""C aşaması bağlantıları: Sorunlar panosunda yerinde düzenleme ve sınırlar tablosunun kaydı (ana pencere üzerinden)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import load_config
from nxceviri.gui.main_window import MainWindow
from tests.test_statusbar import _make_window, _project

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = _make_window(qtbot, tmp_path, _project())
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def _row_id(w: MainWindow, key: str) -> int:
    return next(r.id for r in w.project.translation_rows() if r.key == key)


def test_inline_edit_on_issues_board_saves_and_rechecks(window: MainWindow) -> None:
    row_id = _row_id(window, "d01")
    window.project.set_translations([(row_id, " Merhaba")])  # baştaki boşluk orijinalde yok: uyarı
    window._reload_rows()
    window.run_checks()
    assert any(i.row_id == row_id and i.kind == "spaces" for i in window.qa_page.model.issues)

    window.qa_page.translation_edited.emit(row_id, "Merhaba")

    saved = next(r for r in window.project.translation_rows() if r.id == row_id)
    assert saved.translation == "Merhaba"
    assert not any(i.row_id == row_id and i.kind == "spaces" for i in window.qa_page.model.issues)
    shown = next(r for r in window.translate_page.model.rows if r.id == row_id)
    assert shown.translation == "Merhaba"  # Çevir tablosu da güncel


def test_limits_table_edit_is_saved_with_key_patterns(window: MainWindow) -> None:
    window._refresh_qa()
    limits = window.qa_page.limits
    limits.rule_edited.emit("group:Dialogue", FitRules(30, 2))
    limits.rule_edited.emit("key:m*", FitRules(12, 1))
    saved = load_config(window.project)
    assert saved.per_key == {"m*": FitRules(12, 1)}
    assert saved.per_group.get("Dialogue") == FitRules(30, 2)
    assert window.qa_page.fit_config().per_key == {"m*": FitRules(12, 1)}  # kart desenleri düşürmez


def test_suspicious_code_kind_is_flagged_on_fit_tab(window: MainWindow) -> None:
    from nxceviri.core.formats.base import ControlCode, TextEntry
    from nxceviri.core.project import ImportedFile

    code = ControlCode(b"\x05", "Kod 0x05")
    entries = tuple(TextEntry(f"k{i}", i, f"Bir⟦1⟧iki {i}", (code,)) for i in range(3))
    window.project.import_texts([ImportedFile("Kod.bin", "0100", "msbt", "base", entries)])
    window._reload_rows()
    window.nav.setCurrentRow(3)  # Kontrol Et
    window.qa_page.tabs.setCurrentIndex(1)  # Sığdırma
    window._refresh_limits()
    assert window.qa_page.fit_kind_warning.isVisibleTo(window.qa_page)
    assert "Kod 0x05" in window.qa_page.fit_kind_warning.text()
    window.qa_page.fit_kind_warning.click()
    assert window.qa_page.fit_advanced.body.isVisibleTo(window.qa_page)  # Gelişmiş açıldı
