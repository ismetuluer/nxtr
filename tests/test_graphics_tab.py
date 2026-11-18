"""Kontrol Et → Grafik sekmesi: klasör seçimi, arka plan denetimi, süzgeç, onay, kipler, izleyici, iptal."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Collection, Iterator
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QFileDialog
from pytestqt.qtbot import QtBot

from nxceviri.core.errors import OperationCancelled
from nxceviri.core.formats.derived import GraphicsSupport
from nxceviri.core.project import Project
from nxceviri.core.qa import graphics as qa_graphics
from nxceviri.core.qa.graphics import GraphicsItem
from nxceviri.gui.graphics_check import (
    BADGE_APPROVED,
    BADGE_ERROR,
    BADGE_MISSING,
    BADGE_READY,
    BADGE_UNCHANGED,
    FILTER_ALL,
    FILTER_MISSING,
    FILTER_PROBLEMS,
    MODE_FLIP,
    MODE_OVERLAY,
    MODE_SIDE,
    PAGE_ERROR,
    PAGE_LOADING,
    PAGE_NO_FOLDER,
    PAGE_NO_ORIGINALS,
    PAGE_RESULTS,
    CompareView,
)
from nxceviri.gui.graphics_controller import APPROVED_KEY, FOLDER_KEY, INFO_NO_SUPPORT
from nxceviri.gui.main_window import MainWindow
from nxceviri.gui.step_nav import STEP_QA
from nxceviri.gui.tasks import Task
from tests.test_statusbar import _make_window, _project


def _image(path: Path, size: tuple[int, int] = (40, 20), box: tuple[int, int, int, int] = (6, 6, 30, 14)) -> None:
    """Saydam zeminde beyaz dikdörtgen "yazı"."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(image).rectangle(box, fill=(255, 255, 255, 255))
    image.save(path)


def _folder(root: Path) -> Path:
    """a: hazır (yazı farklı), b: Türkçesi eksik, c: özgünle aynı, d: boyutu farklı (hata)."""
    folder = root / "grafik"
    for name in "abcd":
        _image(folder / "orijinal" / f"{name}.png")
    _image(folder / "turkce" / "a.png", box=(4, 6, 32, 14))
    (folder / "turkce" / "c.png").write_bytes((folder / "orijinal" / "c.png").read_bytes())
    _image(folder / "turkce" / "d.png", size=(38, 20))
    return folder


@pytest.fixture
def win(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = _make_window(qtbot, tmp_path, _project())
    w.notifier._tray.show_message = lambda *_a: None  # type: ignore[method-assign]
    w.notifier._sound = lambda _level: None
    yield w
    w.dirty = False
    w.close()  # closeEvent grafik denetimini iptal edip bekler
    assert w.graphics_check.task is None


def _show_tab(w: MainWindow) -> None:
    w.nav.setCurrentRow(STEP_QA)
    w.qa_page.tabs.setCurrentWidget(w.qa_page.graphics)


def _wait(qtbot: QtBot, w: MainWindow) -> None:
    qtbot.waitUntil(lambda: w.graphics_check.task is None, timeout=10000)


def _use_folder(qtbot: QtBot, w: MainWindow, monkeypatch: pytest.MonkeyPatch, folder: Path) -> None:
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_a, **_k: str(folder))
    _show_tab(w)
    w.qa_page.graphics.choose_empty.click()
    _wait(qtbot, w)


def _badges(w: MainWindow) -> dict[str, str]:
    return {row.item.name: row.badge for row in w.graphics_check.rows()}


def test_tab_is_last_and_empty_without_folder(win: MainWindow) -> None:
    tabs = win.qa_page.tabs
    assert tabs.tabText(tabs.count() - 1) == "Grafik"
    assert tabs.widget(tabs.count() - 1) is win.qa_page.graphics
    _show_tab(win)
    tab = win.qa_page.graphics
    assert tab.page() == PAGE_NO_FOLDER
    assert tab.choose_empty.isVisibleTo(tab)
    assert tab.info.text() == INFO_NO_SUPPORT
    assert tab.info.isVisibleTo(tab)
    assert win.graphics_check.task is None  # klasör yokken iş parçacığı açılmaz


def test_choose_folder_rejects_folder_without_subfolders(
    win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrong = tmp_path / "rastgele"
    (wrong / "orijinal").mkdir(parents=True)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_a, **_k: str(wrong))
    win.qa_page.graphics.choose_empty.click()
    assert win.project.setting(FOLDER_KEY) == ""
    notice = win.notifier.history[0]
    assert notice.title == "Bu klasör grafik klasörü değil"
    assert "orijinal/" in notice.text
    assert "turkce/" in notice.text


def test_choose_folder_stores_setting_and_lists(
    qtbot: QtBot, win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _folder(tmp_path)
    win.dirty = False
    _use_folder(qtbot, win, monkeypatch, folder)
    assert win.project.setting(FOLDER_KEY) == str(folder)
    assert win.dirty  # kaydedilmemiş projede ayar değişikliği "değişti" sayılır
    tab = win.qa_page.graphics
    assert tab.page() == PAGE_RESULTS
    assert _badges(win) == {"a": BADGE_READY, "b": BADGE_MISSING, "c": BADGE_UNCHANGED, "d": BADGE_ERROR}
    assert tab.counter.text() == "2 / 4 hazır · 2 sorun · 1 eksik"
    assert win.qa_page.tabs.tabText(win.qa_page.tabs.indexOf(tab)) == "Grafik (2)"
    assert tab.visible_names() == ["a", "b", "c", "d"]
    tab.filter_chips[FILTER_PROBLEMS].click()
    assert tab.visible_names() == ["c", "d"]
    tab.filter_chips[FILTER_MISSING].click()
    assert tab.visible_names() == ["b"]
    tab.filter_chips[FILTER_ALL].click()
    assert tab.visible_names() == ["a", "b", "c", "d"]


def test_legacy_temiz_folder_is_accepted(
    qtbot: QtBot, win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _folder(tmp_path)
    (folder / "turkce").rename(folder / "temiz")
    _use_folder(qtbot, win, monkeypatch, folder)
    assert _badges(win)["a"] == BADGE_READY


def test_approve_stores_digest_and_drops_when_file_changes(
    qtbot: QtBot, win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _folder(tmp_path)
    _use_folder(qtbot, win, monkeypatch, folder)
    tab = win.qa_page.graphics
    tab.select("d")
    assert not tab.approve_button.isEnabled()  # hatalı resim onaylanamaz
    tab.select("a")
    assert tab.approve_button.isEnabled()
    tab.approve_button.click()
    digest = next(i.digest for i in win.graphics_check.items or [] if i.name == "a")
    assert json.loads(win.project.setting(APPROVED_KEY)) == {"a": digest}
    assert _badges(win)["a"] == BADGE_APPROVED
    assert tab.approve_button.text() == "Onayı Kaldır"
    assert "1 onaylı" in tab.counter.text()

    _image(folder / "turkce" / "a.png", box=(2, 6, 34, 14))  # kullanıcı resmi yeniden kaydetti
    win.graphics_check._watch_due()  # izleyicinin toplanmış tetiği
    _wait(qtbot, win)
    assert _badges(win)["a"] == BADGE_READY  # onay kendiliğinden düştü
    assert tab.current_name() == "a"


def test_unapprove_and_shortcut(qtbot: QtBot, win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _folder(tmp_path)
    _use_folder(qtbot, win, monkeypatch, folder)
    tab = win.qa_page.graphics
    assert tab.approve_action.shortcut().toString() == "Ctrl+Return"
    tab.select("c")  # değişmemiş (uyarı) resim de onaylanabilir: bilerek aynı bırakılmış olabilir
    tab.approve_action.trigger()
    assert _badges(win)["c"] == BADGE_APPROVED
    assert win.qa_page.tabs.tabText(win.qa_page.tabs.indexOf(tab)) == "Grafik (1)"
    tab.approve_button.click()
    assert _badges(win)["c"] == BADGE_UNCHANGED
    assert json.loads(win.project.setting(APPROVED_KEY)) == {}


def _turkish_shown(view: CompareView) -> bool:
    return view.show_turkish


def _flag(view: CompareView, name: str) -> bool:
    """mypy daraltmasını aşmak için bayrağı çağrıyla okur (değer tıklamayla değişir)."""
    return bool(getattr(view, name))


def test_compare_modes_and_guide(
    qtbot: QtBot, win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_folder(qtbot, win, monkeypatch, _folder(tmp_path))
    tab = win.qa_page.graphics
    tab.select("a")
    view = tab.compare
    assert view.original is not None
    assert view.turkish is not None
    assert view.mode == MODE_SIDE
    assert not tab.blend.isVisibleTo(tab)
    tab.mode_chips[MODE_OVERLAY].click()
    assert view.mode == MODE_OVERLAY
    assert tab.blend.isVisibleTo(tab)
    tab.blend.setValue(80)
    assert view.blend == pytest.approx(0.8)
    tab.mode_chips[MODE_FLIP].click()
    assert view.mode == MODE_FLIP
    assert _turkish_shown(view)
    qtbot.mouseClick(view, Qt.MouseButton.LeftButton)
    assert not _turkish_shown(view)
    qtbot.keyClick(view, Qt.Key.Key_Space)
    assert _turkish_shown(view)
    assert not _flag(view, "guide")
    tab.guide_box.setChecked(True)
    assert _flag(view, "guide")
    assert view.original_box == (6, 6, 31, 15)
    tab.actual_chip.click()
    assert not _flag(view, "fit")
    assert not tab.view_scroll.widgetResizable()
    tab.fit_chip.click()
    assert _flag(view, "fit")
    view.grab()  # bütün kiplerde çizim hata vermez (kılavuz açık)
    for mode in (MODE_SIDE, MODE_OVERLAY):
        tab.mode_chips[mode].click()
        view.grab()


def test_watcher_rechecks_after_new_file(
    qtbot: QtBot, win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _folder(tmp_path)
    _use_folder(qtbot, win, monkeypatch, folder)
    watched = {Path(p) for p in win.graphics_check.watcher.directories()}
    assert watched == {folder, folder / "orijinal", folder / "turkce"}
    _image(folder / "turkce" / "b.png", box=(5, 6, 30, 14))
    win.graphics_check.timer.timeout.emit()
    _wait(qtbot, win)
    assert _badges(win)["b"] == BADGE_READY


def test_half_written_file_keeps_list_and_retries(
    qtbot: QtBot, win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _folder(tmp_path)
    _use_folder(qtbot, win, monkeypatch, folder)
    real = qa_graphics.check_folders
    calls: list[int] = []

    def locked(original: Path, turkish: Path, *, cancel: Callable[[], bool] | None = None) -> list[GraphicsItem]:
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError(13, "Erişim engellendi")
        return real(original, turkish, cancel=cancel)

    monkeypatch.setattr(qa_graphics, "check_folders", locked)
    win.graphics_check._watch_due()
    _wait(qtbot, win)
    tab = win.qa_page.graphics
    assert tab.page() == PAGE_RESULTS  # korkutucu hata yok; liste yerinde
    assert win.graphics_check.timer.isActive()  # kısa süre sonra yeniden denenir
    win.graphics_check.timer.stop()
    win.graphics_check._watch_due()
    _wait(qtbot, win)
    assert len(calls) == 2
    assert tab.page() == PAGE_RESULTS


def test_read_error_on_refresh_shows_error_state(
    qtbot: QtBot, win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = _folder(tmp_path)
    _use_folder(qtbot, win, monkeypatch, folder)

    def locked(*_a: object, **_k: object) -> list[GraphicsItem]:
        raise PermissionError(13, "Erişim engellendi")

    monkeypatch.setattr(qa_graphics, "check_folders", locked)
    win.qa_page.graphics.refresh_button.click()
    _wait(qtbot, win)
    tab = win.qa_page.graphics
    assert tab.page() == PAGE_ERROR
    assert "Yenile" in tab.error.banner.text.text()


def test_missing_stored_folder_asks_again(win: MainWindow, tmp_path: Path) -> None:
    win.project.set_setting(FOLDER_KEY, str(tmp_path / "tasindi"))
    win.graphics_check.sync_folder()
    _show_tab(win)
    tab = win.qa_page.graphics
    assert tab.page() == PAGE_NO_FOLDER
    assert "bulunamadı" in tab.no_folder.text.text()


def _blocking_check(started: threading.Event) -> Callable[..., list[GraphicsItem]]:
    def check(_o: Path, _t: Path, *, cancel: Callable[[], bool] | None = None) -> list[GraphicsItem]:
        started.set()
        assert cancel is not None
        while not cancel():
            threading.Event().wait(0.01)
        raise OperationCancelled

    return check


def _start_blocking(qtbot: QtBot, w: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Task:
    folder = _folder(tmp_path)
    w.project.set_setting(FOLDER_KEY, str(folder))
    started = threading.Event()
    monkeypatch.setattr(qa_graphics, "check_folders", _blocking_check(started))
    _show_tab(w)
    w.graphics_check.sync_folder()
    task = w.graphics_check.task
    assert task is not None
    assert started.wait(5)
    assert w.qa_page.graphics.page() == PAGE_LOADING
    return task


def test_check_runs_outside_window_task_and_stops_on_project_replace(
    qtbot: QtBot, win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    task = _start_blocking(qtbot, win, tmp_path, monkeypatch)
    assert win.task is None
    assert not win.busy
    win._replace_project(Project.new())
    assert task.isFinished()
    assert win.graphics_check.task is None
    assert win.graphics_check.items is None


def test_project_switch_clears_tab_count(
    qtbot: QtBot, win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_folder(qtbot, win, monkeypatch, _folder(tmp_path))
    tabs = win.qa_page.tabs
    assert tabs.tabText(tabs.count() - 1) == "Grafik (2)"
    other = Project.new()
    other.set_setting(FOLDER_KEY, str(_folder(tmp_path / "baska")))
    win._replace_project(other)  # açılış Oyunu Ekle adımına döner: sekme görünmez, denetim başlamaz
    assert win.graphics_check.task is None
    assert tabs.tabText(tabs.count() - 1) == "Grafik"


def test_shown_picks_up_changed_folder(
    qtbot: QtBot, win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use_folder(qtbot, win, monkeypatch, _folder(tmp_path))
    second = _folder(tmp_path / "ikinci")
    (second / "orijinal" / "a.png").unlink()
    win.project.set_setting(FOLDER_KEY, str(second))  # Dışa Aktar'a uğranmadan klasör değişti
    win.nav.setCurrentRow(0)
    _show_tab(win)
    _wait(qtbot, win)
    assert _badges(win)["a"] == BADGE_ERROR  # yeni klasörde özgünü yok: yetim


def test_check_stops_on_close(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    w = _make_window(qtbot, tmp_path, _project())
    task = _start_blocking(qtbot, w, tmp_path, monkeypatch)
    w.dirty = False
    w.close()
    assert task.isFinished()
    assert w.graphics_check.task is None
    assert w.graphics_check.watcher.directories() == []


def test_hidden_tab_does_not_start_check(win: MainWindow, tmp_path: Path) -> None:
    win.project.set_setting(FOLDER_KEY, str(_folder(tmp_path)))
    win.graphics_check.sync_folder()
    assert win.graphics_check.task is None  # sekme görünmüyor: yalnızca bayat işaretlenir


def test_graphics_support_game_offers_extraction(
    qtbot: QtBot, win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "grafik_temizleme"

    def export(_reader: object, _files: Collection[str], target: Path) -> list[str]:
        return []

    support = GraphicsSupport("grafik_temizleme", export)
    monkeypatch.setattr(win, "_graphics", lambda: (support, folder))
    extracted: list[bool] = []
    monkeypatch.setattr(win, "extract_graphics", lambda: extracted.append(True))
    _show_tab(win)
    win._refresh_graphics()
    tab = win.qa_page.graphics
    assert tab.page() == PAGE_NO_ORIGINALS
    assert tab.extract_button.isVisibleTo(tab)
    assert not tab.choose_originals.isVisibleTo(tab)
    assert not tab.info.isVisibleTo(tab)
    tab.extract_button.click()
    assert extracted == [True]

    _image(folder / "orijinal" / "MAP.png")  # çıkarma bitti
    (folder / "turkce").mkdir()
    win._refresh_graphics()
    _wait(qtbot, win)
    assert tab.page() == PAGE_RESULTS
    assert _badges(win) == {"MAP": BADGE_MISSING}
    assert not tab.choose_button.isVisibleTo(tab)  # klasör eklentiden gelir; elle seçilmez


def test_manual_folder_without_originals_offers_choose(
    win: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "bos"
    (folder / "orijinal").mkdir(parents=True)
    (folder / "turkce").mkdir()
    win.project.set_setting(FOLDER_KEY, str(folder))
    _show_tab(win)
    win.graphics_check.sync_folder()
    tab = win.qa_page.graphics
    assert tab.page() == PAGE_NO_ORIGINALS
    assert not tab.extract_button.isVisibleTo(tab)
    assert tab.choose_originals.isVisibleTo(tab)


def test_approve_shortcut_is_in_catalogue_without_conflict() -> None:
    from PySide6.QtGui import QKeySequence

    from nxceviri.gui.shortcuts import COMMANDS_BY_ID, ShortcutRegistry, reserved_reason

    command = COMMANDS_BY_ID["qa.graphics_approve"]
    seq = QKeySequence(command.default)
    assert command.default == "Ctrl+Return"
    assert reserved_reason(seq) is None
    assert ShortcutRegistry().conflicts(command.id, seq) == []


def test_settings_survive_reopen(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = _folder(tmp_path)
    path = tmp_path / "proje.nxproj"
    project = _project()
    project.save_as(path)
    project.set_setting(FOLDER_KEY, str(folder))
    project.close()
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    try:
        w.open_project(path)
        _show_tab(w)
        _wait(qtbot, w)
        assert set(_badges(w)) == {"a", "b", "c", "d"}
    finally:
        w.dirty = False
        w.close()
