"""Yardım → Eklentiler penceresi ve projenin eklenti uyarısı."""

from __future__ import annotations

import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog, QMenu, QMessageBox
from pytestqt.qtbot import QtBot

from nxceviri import __version__
from nxceviri.core.formats import registry
from nxceviri.core.plugins.record import record_extraction
from nxceviri.core.project import Project
from nxceviri.gui.main_window import MainWindow
from nxceviri.gui.plugins_dialog import SOURCE_BUILTIN, SOURCE_USER, STATUS_OK, PluginsDialog
from tests.test_plugins import PLUGIN_BODY, make_plugin

pytestmark = pytest.mark.gui


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    registry.reset_user_plugins()
    yield
    registry.reset_user_plugins()


def _rows(dialog: PluginsDialog) -> list[list[str]]:
    table = dialog.table
    return [
        [table.item(r, c).text() for c in range(table.columnCount())]  # type: ignore[union-attr]
        for r in range(table.rowCount())
    ]


def _dialog(qtbot: QtBot, tmp_path: Path, opened: list[Path] | None = None) -> PluginsDialog:
    make_plugin(tmp_path / "ek", "iyi", ad="iyi", kind="iyi_kind", oyunlar=("0100ABCD12340000",))
    make_plugin(tmp_path / "ek", "kotu", toml="ad = [\n")
    report = registry.load_user_plugins([tmp_path / "ek"])
    log = opened if opened is not None else []
    dialog = PluginsDialog(
        None,
        report=report,
        builtin=registry.BUILTIN_PLUGINS,
        install_dir=tmp_path / "kurulum",
        opener=log.append,
    )
    qtbot.addWidget(dialog)
    return dialog


def test_lists_user_and_builtin_plugins_with_errors(qtbot: QtBot, tmp_path: Path) -> None:
    dialog = _dialog(qtbot, tmp_path)
    rows = _rows(dialog)
    user = [r for r in rows if r[3] == SOURCE_USER]
    assert user[0] == ["iyi", "1.0.0", "Deneme", SOURCE_USER, STATUS_OK]
    assert user[1][0] == "kotu"
    assert "bozuk" in user[1][4]
    builtin = [r for r in rows if r[3] == SOURCE_BUILTIN]
    assert len(builtin) == len(registry.BUILTIN_PLUGINS)
    assert builtin[0][1] == __version__
    dialog.table.selectRow(1)
    assert "Konum:" in dialog.detail.text()
    assert "bozuk" in dialog.detail.text()
    dialog.table.selectRow(0)
    assert "0100ABCD12340000" in dialog.detail.text()


def test_open_folder_opens_selected_plugin_or_install_dir(qtbot: QtBot, tmp_path: Path) -> None:
    opened: list[Path] = []
    dialog = _dialog(qtbot, tmp_path, opened)
    dialog.table.selectRow(0)
    dialog.open_selected_folder()
    dialog.table.clearSelection()
    dialog.open_selected_folder()
    last = len(registry.user_plugin_report().infos) + len(registry.BUILTIN_PLUGINS) - 1
    dialog.table.selectRow(last)  # yerleşik: klasörü yok, kurulum klasörü açılır
    dialog.open_selected_folder()
    assert opened == [tmp_path / "ek" / "iyi", tmp_path / "kurulum", tmp_path / "kurulum"]
    assert (tmp_path / "kurulum").is_dir()


def test_install_from_zip_and_folder_and_errors(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = _dialog(qtbot, tmp_path)
    archive = tmp_path / "e.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("eklenti.toml", 'ad = "yeni"\nsurum = "1"\nyazar = "y"\napi = 1\n')
        zf.writestr("plugin.py", PLUGIN_BODY.format(kind="yeni_kind"))
    assert dialog.install(archive)
    assert (tmp_path / "kurulum" / "yeni" / "plugin.py").is_file()
    assert "yeniden başlatın" in dialog.banner.text.text()
    assert dialog.banner.property("state") == "success"

    asked: list[str] = []

    def decline(*_a: object, **_k: object) -> QMessageBox.StandardButton:
        asked.append("soru")
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", decline)
    assert not dialog.install(archive)  # zaten kurulu, kullanıcı vazgeçti
    assert asked == ["soru"]
    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    assert dialog.install(archive)  # değiştirmeyi onayladı

    evil = tmp_path / "kotu.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../kacak.py", "x")
    assert not dialog.install(evil)
    assert dialog.banner.property("state") == "danger"
    assert "güvensiz" in dialog.banner.text.text()
    assert not (tmp_path / "kacak.py").exists()


def test_add_buttons_use_file_dialogs(qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dialog = _dialog(qtbot, tmp_path)
    seen: list[Path] = []

    def fake_install(source: Path) -> bool:
        seen.append(source)
        return True

    monkeypatch.setattr(dialog, "install", fake_install)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a, **_k: ("a.zip", ""))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_a, **_k: "klasor")
    dialog.add_from_zip()
    dialog.add_from_folder()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_a, **_k: ("", ""))
    dialog.add_from_zip()  # iptal: bir şey yapılmaz
    assert seen == [Path("a.zip"), Path("klasor")]
    assert dialog.add_button.menu() is not None
    assert dialog.add_button.text() == "Eklenti Ekle…"


@pytest.fixture
def window(tmp_path: Path) -> Iterator[MainWindow]:
    w = MainWindow(QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat))
    w.show()
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


def test_help_menu_has_plugins_entry(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    help_menu = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Yardım")
    assert isinstance(help_menu, QMenu)
    action = next(a for a in help_menu.actions() if a.text() == "Eklentiler…")
    shown: list[str] = []

    def fake_exec(self: PluginsDialog) -> int:
        shown.append(self.windowTitle())
        return 0

    monkeypatch.setattr(PluginsDialog, "exec", fake_exec)
    action.trigger()
    assert shown == ["Eklentiler"]


def test_opening_project_warns_about_missing_plugin(window: MainWindow, tmp_path: Path) -> None:
    make_plugin(tmp_path / "ek", "demo", surum="1.0.0")
    registry.load_user_plugins([tmp_path / "ek"])
    project = Project.new()
    record_extraction(project, ["demo_kind", "msbt"])
    path = tmp_path / "deneme.nxproj"
    project.save_as(path)
    project.close()

    window.open_project(path)  # eklenti yüklü ve aynı sürüm: uyarı yok
    assert window.add_page.files_banner.isHidden()

    registry.reset_user_plugins()
    window.open_project(path)
    text = window.add_page.files_banner.text.text()
    assert "“demo”" in text
    assert "yüklü değil" in text
    assert not window.add_page.files_banner.isHidden()


def test_importing_texts_records_the_extracting_plugins(window: MainWindow, tmp_path: Path) -> None:
    from nxceviri.core.formats.base import TextEntry
    from nxceviri.core.pipeline import TextExtraction
    from nxceviri.core.plugins.record import SETTING_KEY, plugin_warnings
    from nxceviri.core.project import ImportedFile

    make_plugin(tmp_path / "ek", "demo", surum="1.0.0")
    registry.load_user_plugins([tmp_path / "ek"])
    entry = TextEntry(key="k0", index=0, source="Merhaba", codes=())
    files = [ImportedFile("Data/level1.bin", "0100ABCD12340000", "demo_kind", "base", (entry,))]
    window._import_language = "en"
    window._texts_extracted(TextExtraction(files, []))
    assert '"demo_kind"' in window.project.setting(SETTING_KEY)
    assert plugin_warnings(window.project) == []
