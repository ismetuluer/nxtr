"""Arayüz: Kontrol Et → bulguları satırlarıyla dışa aktarma (dış redaksiyon dosyası + bulgu sütunu)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QItemSelectionModel, QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.secrets import MemoryStore
from nxceviri.core.translate.csvio import parse_txt, plan_import, read_revision_file, xlsx_table
from nxceviri.gui import main_window as main_window_module
from nxceviri.gui.csv_dialog import CsvExportDialog
from nxceviri.gui.main_window import STEP_QA, MainWindow

pytestmark = pytest.mark.gui

LINES = [
    ("a", "Start Game"),
    ("b", "Hello "),
    ("c", "Go on and on"),
    ("d", "Clean line"),
]


def _project() -> Project:
    p = Project.new()
    entries = tuple(TextEntry(k, i, s, ()) for i, (k, s) in enumerate(LINES))
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations(
        [
            (rows["a"].id, "Oyunu  Başlat."),  # çift boşluk
            (rows["b"].id, "Merhaba"),  # sondaki boşluk eksik
            (rows["c"].id, "Devam et ve ve bitir"),  # tekrarlı sözcük
            (rows["d"].id, "Temiz satır"),
        ],
        machine=True,
    )
    return p


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    settings = QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat)
    w = MainWindow(settings)
    w.secrets = MemoryStore()
    w._replace_project(_project())
    w.show()
    w.nav.setCurrentRow(STEP_QA)
    w.qa_page.check_button.click()
    qtbot.waitUntil(lambda: not w.busy, timeout=10000)
    yield w
    w.dirty = False
    w.close()
    w.deleteLater()


@pytest.fixture
def notices(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    seen: list[tuple[str, str]] = []
    monkeypatch.setattr(window, "notify", lambda level, title, text="", actions=(): seen.append((title, text)))
    return seen


def _accept(monkeypatch: pytest.MonkeyPatch, target: Path, *, xlsx: bool = False, scope: int | None = None) -> None:
    def exec_(self: CsvExportDialog) -> int:
        if xlsx:
            self.xlsx_radio.setChecked(True)
        if scope is not None:
            button = self.scope_group.button(scope)
            assert button is not None
            button.setChecked(True)
        self.split_box.setChecked(False)
        return CsvExportDialog.DialogCode.Accepted

    monkeypatch.setattr(main_window_module.CsvExportDialog, "exec", exec_)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))


def _by_key(window: MainWindow) -> dict[str, int]:
    return {r.key: r.id for r in window.project.translation_rows()}


def test_exports_visible_findings_once_per_row(
    window: MainWindow, notices: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "bulgular.txt"
    _accept(monkeypatch, target)
    window.export_findings()
    lines = target.read_text(encoding="utf-8-sig").splitlines()
    assert lines[0].split("\t") == ["orijinal", "çeviri", "düzeltme", "grup", "bulgu"]
    sources = [line.split("\t")[0] for line in lines[1:]]
    assert sorted(sources) == ["Go on and on", "Hello ", "Start Game"]  # temiz satır yok, her satır bir kez
    assert all(line.split("\t")[4] for line in lines[1:])
    assert "Dış Redaksiyondan İçe Aktar" in notices[-1][1]
    assert "3 satır" in notices[-1][1]
    assert "bulgu" in QGuiApplication.clipboard().text()


def test_exported_findings_file_imports_back(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    target = tmp_path / "bulgular.txt"
    _accept(monkeypatch, target)
    window.export_findings()
    text = target.read_text(encoding="utf-8-sig").replace("Oyunu  Başlat.\t\t", "Oyunu  Başlat.\tOyunu Başlat.\t")
    target.write_text(text, encoding="utf-8")
    plan = plan_import(window.project.translation_rows(), read_revision_file(target))
    assert plan.changes == [(_by_key(window)["a"], "Oyunu Başlat.")]


def test_exports_xlsx(window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "bulgular.xlsx"
    _accept(monkeypatch, target, xlsx=True)
    window.export_findings()
    table = xlsx_table(target.read_bytes())
    assert table[0] == ["orijinal", "çeviri", "düzeltme", "grup", "bulgu"]
    assert len(table) == 4


def test_respects_kind_filter(window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    window.qa_page.kind_list.select_kinds(("repeated_word",))
    target = tmp_path / "bulgular.txt"
    _accept(monkeypatch, target)
    window.export_findings()
    rows = parse_txt(target.read_text(encoding="utf-8-sig"))
    assert [r.source for r in rows] == ["Go on and on"]


def test_selected_scope_exports_selected_rows(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    page = window.qa_page
    page.table.clearSelection()
    target_id = _by_key(window)["b"]
    for r in range(page.proxy.rowCount()):
        if page.model.issues[page.proxy.mapToSource(page.proxy.index(r, 0)).row()].row_id == target_id:
            page.table.selectRow(r)
            break
    page.table.selectRow(0)
    page.table.selectionModel().select(
        page.proxy.index(1, 0),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
    )
    target = tmp_path / "bulgular.txt"
    _accept(monkeypatch, target, scope=0)
    window.export_findings()
    assert len(parse_txt(target.read_text(encoding="utf-8-sig"))) == 2  # üç bulgulu satırdan yalnızca seçili ikisi


def test_no_findings_shows_message_and_writes_nothing(
    window: MainWindow, notices: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    window.qa_page.show_issues([], window.project.translation_rows())
    target = tmp_path / "bos.txt"
    _accept(monkeypatch, target)
    window.export_findings()
    assert not target.exists()
    assert "bulgu yok" in notices[-1][1]


def test_context_menu_and_tools_menu_have_the_action(window: MainWindow) -> None:
    window.qa_page.table.selectRow(0)
    assert "Bulguları dışa aktar…" in [a.text() for a in window.qa_page.context_menu().actions()]
    assert "qa.export_findings" in window.menus.actions
