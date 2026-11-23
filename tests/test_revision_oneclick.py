"""Dış redaksiyon / dış çeviri tek tık: son ayarlarla doğrudan yazma, Ayarlar penceresinin hatırlanması, dosyayı
pencereye bırakarak içe aktarma."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QDropEvent, QGuiApplication
from PySide6.QtWidgets import QFileDialog
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.csvio import (
    MODE_REDACTION,
    MODE_TRANSLATION,
    export_translation_txt,
    export_translation_xlsx,
    export_txt,
    export_xlsx,
    revision_file_kind,
)
from nxceviri.gui import main_window as main_window_module
from nxceviri.gui.csv_dialog import FORMAT_TXT, CsvExportDialog
from nxceviri.gui.main_window import STEP_TRANSLATE, MainWindow
from tests.test_editor import _project
from tests.test_statusbar import _make_window

pytestmark = pytest.mark.gui


def _row(i: int) -> TranslationRow:
    return TranslationRow(i, "a.msbt", f"k{i}", f"Hello {i}", f"Merhaba {i}", "machine", "", (), None)


@pytest.mark.parametrize(
    ("write", "kind"),
    [
        (export_xlsx, MODE_REDACTION),
        (export_txt, MODE_REDACTION),
        (export_translation_xlsx, MODE_TRANSLATION),
        (export_translation_txt, MODE_TRANSLATION),
    ],
)
def test_revision_file_kind_reads_header(tmp_path: Path, write: object, kind: str) -> None:
    """Bırakılan dosyanın dış çeviri mi redaksiyon mu olduğu başlıktan anlaşılır (“yeni çeviri” / “düzeltme”)."""
    assert callable(write)
    paths = write([_row(1), _row(2)], tmp_path / "dosya")
    assert revision_file_kind(paths[0]) == kind


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = _make_window(qtbot, tmp_path, _project())
    w.nav.setCurrentRow(STEP_TRANSLATE)
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


class _Never(CsvExportDialog):
    def exec(self) -> int:
        raise AssertionError("tek tıkta pencere açılmamalı")


def test_first_export_asks_then_one_click_with_last_settings(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """İlk kez Ayarlar penceresi ve kaydetme sorulur; sonra Dosya Oluştur tek tıktır: aynı klasöre, son biçimle,
    eski dosyanın üzerine yazmadan yazar ve talimatı panoya koyar."""
    out = tmp_path / "çıktı"
    out.mkdir()

    class TxtOnce(CsvExportDialog):
        def exec(self) -> int:
            self.txt_radio.setChecked(True)
            return CsvExportDialog.DialogCode.Accepted

    monkeypatch.setattr(main_window_module, "CsvExportDialog", TxtOnce)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_a, **_k: (str(out / "ilk.txt"), ""))
    window.export_csv()
    assert (out / "ilk.txt").is_file()

    monkeypatch.setattr(main_window_module, "CsvExportDialog", _Never)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *_a, **_k: pytest.fail("kaydetme sorulmamalı"))
    QGuiApplication.clipboard().setText("")
    window.export_csv()
    window.export_csv()
    written = sorted(p for p in out.iterdir() if p.name != "ilk.txt")
    assert len(written) == 2  # ikinci tık birincinin üzerine yazmaz
    assert all(p.suffix == ".txt" for p in written)  # son ayar: TXT
    assert "düzeltme" in written[0].read_text(encoding="utf-8-sig").splitlines()[0]
    assert "⟦1⟧" in QGuiApplication.clipboard().text()
    notice = window.notifier.history[0]
    labels = [a.label for a in notice.actions]
    assert "Klasörü Aç" in labels
    assert "Ayarlar" in labels
    seen: list[str] = []

    class Settings(CsvExportDialog):
        def exec(self) -> int:
            seen.append(self.format())  # pencere son ayarla açılır
            return 0

    monkeypatch.setattr(main_window_module, "CsvExportDialog", Settings)
    next(a for a in notice.actions if a.label == "Ayarlar").callback()
    assert seen == [FORMAT_TXT]


def test_right_click_export_takes_selected_rows(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    window.settings.setValue("csv/dir", str(tmp_path))
    monkeypatch.setattr(main_window_module, "CsvExportDialog", _Never)
    page = window.translate_page
    page.table.selectRow(0)
    page.csv_export_requested.emit()
    written = [p for p in tmp_path.iterdir() if p.suffix == ".xlsx"]
    assert len(written) == 1
    assert "1 satır yazıldı" in window.notifier.history[0].title + window.notifier.history[0].text


def test_dialog_remembers_settings(qtbot: QtBot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat)
    rows = [_row(i) for i in range(1, 9)]
    first = CsvExportDialog(None, selected=[], visible=rows, all_rows=rows, settings=settings)
    qtbot.addWidget(first)
    first.txt_radio.setChecked(True)
    first.split_box.setChecked(True)
    first.part_spin.setValue(3)
    first.save_choices()
    again = CsvExportDialog(None, selected=[], visible=rows, all_rows=rows, settings=settings)
    qtbot.addWidget(again)
    assert again.format() == FORMAT_TXT
    assert again.parts() == 3


def _drop(window: MainWindow, paths: list[Path]) -> bool:
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    event = QDropEvent(
        QPointF(QPoint(10, 10)),
        Qt.DropAction.CopyAction,
        data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    window.dropEvent(event)
    return event.isAccepted()


def test_dropping_revision_file_opens_matching_import(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Dönen dosyayı pencereye bırakmak yeter: başlığa göre redaksiyon ya da dış çeviri içe aktarması açılır."""
    calls: list[tuple[bool, list[str]]] = []
    monkeypatch.setattr(
        window.exchange,
        "import_files",
        lambda paths, *, translation: calls.append((translation, [p.name for p in paths])),
    )
    rows = window.translate_page.model.rows
    redaction = export_xlsx(rows, tmp_path / "red.xlsx")[0]
    translation = export_translation_txt(rows, tmp_path / "cev.txt")[0]
    assert _drop(window, [redaction])
    assert _drop(window, [translation])
    assert calls == [(False, [redaction.name]), (True, [translation.name])]
    other = tmp_path / "resim.png"
    other.write_bytes(b"x")
    assert not _drop(window, [other])  # başka dosya: içe aktarma açılmaz
    assert len(calls) == 2
