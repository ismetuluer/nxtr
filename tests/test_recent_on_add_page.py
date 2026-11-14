"""Boş Oyunu Ekle ekranındaki "Son projeler" kartı."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QToolButton
from pytestqt.qtbot import QtBot

from nxceviri.core.project import SourceRecord
from nxceviri.gui.add_game_page import AddGamePage
from nxceviri.gui.main_window import MainWindow
from nxceviri.gui.recent import RecentProjects

pytestmark = pytest.mark.gui


def _projects(tmp_path: Path, n: int = 2) -> list[Path]:
    paths = []
    for i in range(n):
        p = tmp_path / f"oyun{i}.nxproj"
        p.write_bytes(b"")
        paths.append(p)
    return paths


def _links(page: AddGamePage) -> list[QToolButton]:
    return page.recent_card.findChildren(QToolButton)


def _page(qtbot: QtBot) -> AddGamePage:
    page = AddGamePage()
    qtbot.addWidget(page)
    page.show()
    return page


def test_missing_paths_skipped(qtbot: QtBot, tmp_path: Path) -> None:
    page = _page(qtbot)
    page.set_recent([*_projects(tmp_path), tmp_path / "yok.nxproj"])
    assert page.recent_card.isVisible()
    assert [b.text() for b in _links(page)] == ["oyun0", "oyun1"]
    assert _links(page)[0].toolTip() == str(tmp_path / "oyun0.nxproj")


def test_empty_list_hides_card(qtbot: QtBot, tmp_path: Path) -> None:
    page = _page(qtbot)
    page.set_recent(_projects(tmp_path))
    page.set_recent([])
    assert not page.recent_card.isVisible()
    assert _links(page) == []


def test_click_emits_path(qtbot: QtBot, tmp_path: Path) -> None:
    page = _page(qtbot)
    paths = _projects(tmp_path)
    page.set_recent(paths)
    with qtbot.waitSignal(page.open_recent) as sig:
        _links(page)[1].click()
    assert sig.args == [paths[1]]


def test_hidden_when_sources_present(qtbot: QtBot, tmp_path: Path) -> None:
    page = _page(qtbot)
    page.set_recent(_projects(tmp_path))
    source = SourceRecord(
        path=tmp_path / "a.nsp",
        kind="base",
        name="A",
        title_id="0100",
        application_id="0100",
        version=0,
        display_version="",
        file_size=1,
    )
    page.set_sources([source])
    assert not page.recent_card.isVisible()
    page.set_sources([])
    assert page.recent_card.isVisible()


def test_main_window_shows_recent(qtbot: QtBot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    paths = _projects(tmp_path, 1)
    RecentProjects(settings).remember(paths[0])
    w = MainWindow(settings)
    qtbot.addWidget(w)
    w.show()
    assert w.add_page.recent_card.isVisible()
    assert [b.text() for b in _links(w.add_page)] == ["oyun0"]
    w.dirty = False
