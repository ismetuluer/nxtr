"""İsteğe bağlı "Hatalı Satırları Vurgula": hatası olan satırın tüm hücreleri hata rengine boyanır."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor
from pytestqt.qtbot import QtBot

from nxceviri.core.qa.checks import SEVERITY_ERROR
from nxceviri.gui.theme import current_tokens
from nxceviri.gui.translate_page import COL_KEY, COL_SOURCE, COL_TRANSLATION, TranslatePage
from tests.test_marked_delegate import make_page, make_row

pytestmark = pytest.mark.gui


def _page(qtbot: QtBot) -> TranslatePage:
    # 1: kontrol kodu çeviride yok (hata); 2: sorunsuz.
    page = make_page(qtbot, [make_row(1, "Hi ⟦1⟧", "Selam", labels=("<c>",)), make_row(2, "Bye", "Hoşça kal")])
    assert any(i.severity == SEVERITY_ERROR for i in page.model.issues(page.model.rows[0]))
    assert not page.model.issues(page.model.rows[1])
    return page


def _background(page: TranslatePage, row: int, col: int) -> object:
    return page.model.index(row, col).data(Qt.ItemDataRole.BackgroundRole)


def test_off_by_default_and_no_background(qtbot: QtBot) -> None:
    page = _page(qtbot)
    assert not page.error_rows_box.isChecked()
    assert _background(page, 0, COL_TRANSLATION) is None


def test_on_paints_every_cell_of_error_rows_only(qtbot: QtBot) -> None:
    page = _page(qtbot)
    page.error_rows_box.setChecked(True)
    danger = QColor(current_tokens()["danger_bg"])
    for col in (COL_SOURCE, COL_TRANSLATION, COL_KEY):
        assert _background(page, 0, col) == danger
        assert _background(page, 1, col) is None


def test_choice_is_remembered(qtbot: QtBot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "ayar.ini"), QSettings.Format.IniFormat)
    page = _page(qtbot)
    page.bind_settings(settings)
    page.error_rows_box.setChecked(True)
    again = _page(qtbot)
    again.bind_settings(settings)
    assert again.error_rows_box.isChecked()
