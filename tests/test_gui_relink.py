"""Taşınan oyun dosyalarını yeniden bağlama (arayüz): açılışta otomatik, elle klasör gösterme."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from nxceviri.gui.main_window import MainWindow
from nxceviri.gui.translate_page import COL_TRANSLATION
from tests.conftest import GameFiles
from tests.test_gui import _wait_idle

pytestmark = pytest.mark.gui


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.show()
    yield w
    if w.task is not None:
        w.task.cancel()
        w.task.wait()
    w.dirty = False
    w.close()
    w.deleteLater()


def _saved_project(qtbot: QtBot, window: MainWindow, game: GameFiles, tmp_path: Path) -> Path:
    """Oyun dosyaları proje klasörünün altındaki "oyun" klasöründe; proje taranmış, aktarılmış, kaydedilmiş."""
    folder = tmp_path / "proje"
    (folder / "oyun").mkdir(parents=True)
    copies = [folder / "oyun" / p.name for p in (game.base_nsp, game.update_nsp)]
    for src, dst in zip((game.base_nsp, game.update_nsp), copies, strict=True):
        dst.write_bytes(src.read_bytes())
    window.load_keys_file(game.keys_path)
    window.add_files(copies)
    _wait_idle(qtbot, window)
    window.start_scan()
    _wait_idle(qtbot, window)
    window.import_texts()
    _wait_idle(qtbot, window)
    page = window.translate_page
    hello = next(i for i, r in enumerate(page.model.rows) if r.key == "Menu_Hello")
    assert page.model.setData(page.model.index(hello, COL_TRANSLATION), "Merhaba ⟦1⟧Kael⟦2⟧!")
    target = folder / "Deneme.nxproj"
    assert window.save_to(target)
    return target


def _translations(window: MainWindow) -> dict[str, str]:
    return {r.key: r.translation for r in window.translate_page.model.rows if r.translation}


def test_moved_game_folder_is_relinked_on_open(
    qtbot: QtBot, window: MainWindow, game: GameFiles, tmp_path: Path
) -> None:
    target = _saved_project(qtbot, window, game, tmp_path)
    before = _translations(window)
    assert before
    (tmp_path / "proje" / "oyun").rename(tmp_path / "proje" / "taşındı")
    window.new_project()
    assert window.open_project(target)
    assert all(s.path.parent.name == "taşındı" and s.path.is_file() for s in window.sources)
    assert [s.path for s in window.project.sources()] == [s.path for s in window.sources]  # projeye yazıldı
    assert window.report is not None  # tarama raporu silinmedi
    assert window.project.latest_scan() is not None
    assert _translations(window) == before
    assert "yeni yeri bulundu ve bağlandı" in window.add_page.files_banner.text.text()
    assert window.add_page.next_button.isEnabled()


def test_manual_relink_chooses_folder_and_reports_the_rest(
    qtbot: QtBot, window: MainWindow, game: GameFiles, tmp_path: Path
) -> None:
    target = _saved_project(qtbot, window, game, tmp_path)
    before = _translations(window)
    base, update = (s.path for s in window.sources)
    away = tmp_path / "uzak" / "başka"  # proje klasörünün dışında: açılışta bulunamaz
    away.mkdir(parents=True)
    other = tmp_path / "ötekiler"
    other.mkdir()
    base.rename(away / base.name)
    update.rename(other / update.name)
    window.new_project()
    window.open_project(target)
    banner = window.add_page.files_banner
    assert "bulunamadı" in banner.text.text()
    assert banner.action_button.isVisible()
    assert not any(s.path.is_file() for s in window.sources)

    chosen: list[Path] = []

    def ask(start: Path) -> Path | None:
        chosen.append(start)
        return away

    window.ask_relink_folder = ask  # type: ignore[method-assign]
    banner.action_button.click()
    assert chosen
    assert "1 oyun dosyasının" in banner.text.text()
    assert update.name in banner.text.text()  # hâlâ bulunamayan dosya adıyla bildirilir
    assert [s.path.is_file() for s in window.sources] == [True, False]
    assert window.report is not None
    assert _translations(window) == before

    (other / update.name).rename(away / update.name)  # menüden de aynı yol: kalan dosya da bağlanır
    window.relink_sources_dialog()
    assert all(s.path.is_file() for s in window.sources)
    assert [s.path for s in window.project.sources()] == [s.path for s in window.sources]


def test_manual_relink_cancelled_changes_nothing(
    qtbot: QtBot, window: MainWindow, game: GameFiles, tmp_path: Path
) -> None:
    target = _saved_project(qtbot, window, game, tmp_path)
    (tmp_path / "proje" / "oyun").rename(tmp_path / "uzakta")
    window.new_project()
    window.open_project(target)
    window.ask_relink_folder = lambda _start: None  # type: ignore[method-assign, assignment]
    window.relink_sources_dialog()
    assert not any(s.path.is_file() for s in window.sources)


def test_manual_relink_with_nothing_missing_says_so(window: MainWindow) -> None:
    window.relink_sources_dialog()
    assert "unamayan" in window.statusBar().currentMessage()
