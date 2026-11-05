"""Durum çubuğu: kalıcı bölmeler (satırlar, ilerleme, sorunlar, sağlayıcı, kayıt) ve güncelleme rozeti."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QFileDialog
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.secrets import MemoryStore
from nxceviri.gui.main_window import STEP_QA, MainWindow

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


def _project(*, changed_source: bool = False) -> Project:
    p = Project.new()
    last = "Start!" if changed_source else "Start"

    def texts(third: str) -> list[ImportedFile]:
        return [
            ImportedFile(
                "Dialogue.tsv",
                "0100",
                "unity",
                "base",
                (
                    TextEntry("d01", 0, "Hello there", ()),
                    TextEntry("d02", 1, "Goodbye", ()),
                    TextEntry("m01", 2, third, ()),
                ),
            )
        ]

    p.import_texts(texts("Start"))
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations([(rows["d01"].id, "Merhaba"), (rows["m01"].id, "Başla")], machine=True)
    if changed_source:
        p.import_texts(texts(last))  # çevirisi olan satırın kaynağı değişti → Hatalı
    return p


def _make_window(qtbot: QtBot, tmp_path: Path, project: Project | None) -> MainWindow:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    if project is not None:
        w._replace_project(project)
    w.show()
    return w


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = _make_window(qtbot, tmp_path, _project())
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


@pytest.fixture
def empty_window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = _make_window(qtbot, tmp_path, None)
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def test_empty_project_shows_only_save(empty_window: MainWindow) -> None:
    seg = empty_window.status_segments
    assert not seg.rows_label.isVisibleTo(empty_window)
    assert not seg.progress.isVisibleTo(empty_window)
    assert not seg.problems_button.isVisibleTo(empty_window)
    assert not seg.provider_label.isVisibleTo(empty_window)
    assert seg.save_label.isVisibleTo(empty_window)
    assert seg.keys_button.isVisibleTo(empty_window)  # anahtar durumu her zaman görünür
    assert seg.keys_button.text() == "Anahtar seçilmedi"


def test_counts_after_translation_commit(qtbot: QtBot, window: MainWindow) -> None:
    seg = window.status_segments
    assert seg.rows_label.isVisibleTo(window)
    assert seg.rows_label.text() == "3 satır"
    assert seg.progress_label.text() == "%67 çevrildi"
    assert seg.progress.value() == 67
    row = next(r for r in window.translate_page.model.rows if r.key == "d02")
    assert window.translate_page.model.apply([(row.id, "Hoşça kal")])  # tablodan düzenleme yolu
    qtbot.waitUntil(lambda: seg.progress_label.text() == "%100 çevrildi", timeout=3000)
    assert seg.progress.value() == 100


def test_problems_segment_visible_only_with_errors(qtbot: QtBot, tmp_path: Path, window: MainWindow) -> None:
    seg = window.status_segments
    assert not seg.problems_button.isVisibleTo(window)
    broken = _make_window(qtbot, tmp_path, _project(changed_source=True))
    try:
        seg2 = broken.status_segments
        assert seg2.problems_button.isVisibleTo(broken)
        assert seg2.problems_button.text() == "1 hatalı"
        qtbot.mouseClick(seg2.problems_button, Qt.MouseButton.LeftButton)
        assert broken.pages.currentIndex() == STEP_QA
    finally:
        broken.dirty = False
        broken.close()
        broken.deleteLater()


def test_provider_text(window: MainWindow) -> None:
    seg = window.status_segments
    assert not seg.provider_label.isVisibleTo(window)
    window.settings.setValue("translate/provider", "ollama")
    window.settings.setValue("ollama/model", "qwen3:14b")
    window._refresh_status()
    assert seg.provider_label.isVisibleTo(window)
    assert seg.provider_label.text() == "Ollama · qwen3:14b"
    window.settings.setValue("translate/provider", "deepl")
    window._refresh_status()
    assert seg.provider_label.text() == "DeepL"
    window.settings.setValue("translate/provider", "")
    window._refresh_status()
    assert not seg.provider_label.isVisibleTo(window)


def test_save_state(window: MainWindow) -> None:
    seg = window.status_segments
    assert seg.save_label.text() == "Kaydedildi"
    window.dirty = True
    window._refresh_status()
    assert seg.save_label.text() == "Kaydedilmedi"
    window.dirty = False
    window._refresh_status()
    assert seg.save_label.text() == "Kaydedildi"


def test_update_badge_behaviour_unchanged(window: MainWindow) -> None:
    assert window.update_badge.parent() is not None
    assert not window.update_badge.isVisibleTo(window)
    window.update_badge.show()
    assert window.update_badge.isVisibleTo(window)
    window.update_badge.hide()
    assert not window.update_badge.isVisibleTo(window)
    assert window.statusBar().isAncestorOf(window.update_badge)


def test_transient_message_still_shown(window: MainWindow) -> None:
    window.statusBar().showMessage("Deneme iletisi")
    assert window.statusBar().currentMessage() == "Deneme iletisi"


def test_keys_segment_opens_key_dialog(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    titles: list[str] = []

    def fake_dialog(_parent: object, title: str, *_args: object) -> tuple[str, str]:
        titles.append(title)
        return "", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", fake_dialog)
    window.status_segments.keys_button.click()
    assert titles == ["prod.keys dosyasını seçin"]
