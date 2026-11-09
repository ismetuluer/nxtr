"""Dışa Aktar sayfası: "Hatalı satırları da aktar" kutusu (varsayılan kapalı, proje başına hatırlanır)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.translate.status import Status
from nxceviri.gui.main_window import STEP_EXPORT, MainWindow
from tests.conftest import GameFiles

pytestmark = pytest.mark.gui


def _project(*, with_error: bool = True) -> Project:
    p = Project.new()
    p.import_texts(
        [
            ImportedFile(
                "Dialogue.tsv",
                "0100",
                "unity",
                "base",
                (
                    TextEntry("d01", 0, "Hello", ()),
                    TextEntry("d02", 1, "Press ⟦1⟧ now.", (ControlCode(b"\x0e\x05", "Kod"),)),
                ),
            )
        ]
    )
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations([(rows["d01"].id, "Merhaba")])
    p.set_translations([(rows["d02"].id, "Şimdi bas." if with_error else "Şimdi ⟦1⟧ bas.")], machine=True)
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.show()
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def test_box_starts_unchecked_and_shows_when_errors_exist(window: MainWindow) -> None:
    assert [r.status for r in window.project.translation_rows()].count(Status.ERROR) == 1
    window.nav.setCurrentRow(STEP_EXPORT)
    page = window.export_page
    assert not page.include_errors_box.isHidden()
    assert not page.include_errors_box.isChecked()
    assert page.include_errors_box.text() == "Hatalı satırları da aktar"
    assert "çökebilir" in page.include_errors_box.toolTip()
    assert page.summary.text().startswith("1 yazılacak · 1 hatalı")
    assert "denenecek" not in page.summary.text()


def test_box_hidden_without_error_rows(window: MainWindow) -> None:
    window._replace_project(_project(with_error=False))
    window.nav.setCurrentRow(STEP_EXPORT)
    assert window.export_page.include_errors_box.isHidden()


def test_choice_is_remembered_per_project(window: MainWindow) -> None:
    window.nav.setCurrentRow(STEP_EXPORT)
    page = window.export_page
    page.include_errors_box.setChecked(True)
    assert window.project.setting("export_include_errors") == "1"
    assert "uygun olanlar denenecek" in page.summary.text()
    page.include_errors_box.setChecked(False)
    assert window.project.setting("export_include_errors") == ""
    page.include_errors_box.setChecked(True)
    # Başka bir proje açılınca kutu o projenin değerini (varsayılan: kapalı) gösterir.
    window._replace_project(_project())
    window.nav.setCurrentRow(STEP_EXPORT)
    assert not page.include_errors_box.isChecked()
    assert window.project.setting("export_include_errors") == ""


def test_export_with_box_reports_error_rows(
    qtbot: QtBot, window: MainWindow, game: GameFiles, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window.load_keys_file(game.keys_path)
    window.add_files([game.base_nsp, game.update_nsp])
    qtbot.waitUntil(lambda: window.task is None, timeout=20_000)
    window.start_scan()
    qtbot.waitUntil(lambda: window.task is None, timeout=20_000)
    window.import_texts()
    qtbot.waitUntil(lambda: window.task is None, timeout=20_000)
    rows = {r.key: r for r in window.translate_page.model.rows}
    # "Wait" ⟦1⟧ içermeden çevrilir → hatalı; "Menu_Start" geçerli.
    window.translate_page.model.apply([(rows["Menu_Start"].id, "Maceraya Başla"), (rows["Wait"].id, "Bekleyin")])
    window.nav.setCurrentRow(STEP_EXPORT)
    export = window.export_page
    export.folder.setText(str(tmp_path / "Çıktılar"))
    export.mod_name.setText("Kapalı")
    export.export_button.click()
    qtbot.waitUntil(lambda: window.task is None, timeout=20_000)
    assert "Hatalı satırlar:" not in window.notifier.history[0].text  # kapalıyken eski mesaj
    export.mod_name.setText("Açık")
    export.include_errors_box.setChecked(True)
    export.export_button.click()
    qtbot.waitUntil(lambda: window.task is None, timeout=20_000)
    assert "Mod oluşturuldu" in export.result.text.text()  # sayfada kısa durum
    assert window.notifier.history[0].title == "Mod oluşturuldu"
    text = window.notifier.history[0].text  # ayrıntılar bildirimde
    assert "Hatalı satırlar: 0 tanesi çevirisiyle yazıldı, 1 tanesi orijinal bırakıldı" in text
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices

    opened: list[str] = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(QUrl(url).toLocalFile()) or True)
    open_action = next(a for a in window.notifier.history[0].actions if a.label == "Klasörü Aç")
    open_action.callback()  # bildirimdeki düğme gerçekten klasörü açar
    assert opened
