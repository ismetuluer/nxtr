"""Eklentinin `font_support` bildirimi: etkin eklentilerin font cümleleri, Font sekmesi ve öneri metni."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from pytestqt.qtbot import QtBot

from nxceviri.core.formats import registry
from nxceviri.core.plugins.loader import PluginInfo, PluginReport
from nxceviri.core.qa.fonts import DURUM_DONUSTURME, FontReport, font_verdict

CUMLE = "Arşivdeki Latin fontlara eksik Türkçe harfleri dışa aktarmada ekler."


class _Eklenti:
    name = "demoyazi"
    label = "Demo"
    candidates_only = False
    path_suffixes: tuple[str, ...] = ()

    def __init__(self, font_support: str | None) -> None:
        if font_support is not None:
            self.font_support = font_support


def _kaydet(monkeypatch: pytest.MonkeyPatch, font_support: str | None, oyunlar: tuple[str, ...] = ()) -> None:
    info = PluginInfo("Demo Eklenti", "1", "t", None, 1, oyunlar, tur="demoyazi", plugin=_Eklenti(font_support))  # type: ignore[arg-type]
    monkeypatch.setattr(registry, "_user_report", PluginReport((info,)))


def test_font_support_notes_lists_active_plugin(monkeypatch: pytest.MonkeyPatch) -> None:
    _kaydet(monkeypatch, CUMLE)
    notes = registry.font_support_notes([("0100AAAA", "demoyazi"), ("0100AAAA", "demoyazi"), ("0100AAAA", "msbt")])
    assert notes == [("Demo Eklenti", CUMLE)]


def test_font_support_notes_empty_without_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    _kaydet(monkeypatch, None)
    assert registry.font_support_notes([("0100AAAA", "demoyazi")]) == []
    _kaydet(monkeypatch, "  ")
    assert registry.font_support_notes([("0100AAAA", "demoyazi")]) == []


def test_font_support_notes_ignores_plugin_for_other_game(monkeypatch: pytest.MonkeyPatch) -> None:
    _kaydet(monkeypatch, CUMLE, oyunlar=("0100BBBB",))
    assert registry.font_support_notes([("0100AAAA", "demoyazi")]) == []


def test_verdict_does_not_recommend_transliteration_when_plugin_handles_fonts() -> None:
    v = font_verdict(FontReport([]), [("Demo Eklenti", CUMLE)])
    assert v.durum != DURUM_DONUSTURME
    assert "Demo Eklenti" in v.oneri
    assert "harf dönüştürme gerekir" not in v.oneri
    assert font_verdict(FontReport([])).durum == DURUM_DONUSTURME


def test_font_tab_shows_plugin_info_banner(qtbot: QtBot) -> None:
    from nxceviri.gui.qa_page import QaPage

    page = QaPage()
    qtbot.addWidget(page)
    page.show_font_report(FontReport([]), "", [("Demo Eklenti", CUMLE)])
    text = page.font_banner.text.text()
    assert "Demo Eklenti" in text
    assert CUMLE in text
    assert "bilgi dosyasında" not in text  # kısa tutulur: tek cümle
    assert "bulunamadı" not in text
    assert page.font_banner.property("state") == "success"


def _export_notes(qtbot: QtBot, tmp_path: Path) -> tuple[str, ...]:
    """Demo eklentili projede (font taranmadı) Dışa Aktar sayfasının üst bilgi notları."""
    from nxceviri.core.formats.base import TextEntry
    from nxceviri.core.project import ImportedFile, Project
    from nxceviri.core.secrets import MemoryStore
    from nxceviri.gui.main_window import STEP_EXPORT, MainWindow

    project = Project.new()
    project.import_texts([ImportedFile("a.bin", "0100AAAA", "demoyazi", "base", (TextEntry("k", 0, "Hi", ()),))])
    w = MainWindow(QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat))
    w.secrets = MemoryStore()
    w._replace_project(project)
    qtbot.addWidget(w)
    w.nav.setCurrentRow(STEP_EXPORT)
    details = w.export_page.header.chip.details()
    w.dirty = False
    w.close()
    return details


def test_export_does_not_ask_font_scan_when_plugin_handles_fonts(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _kaydet(monkeypatch, CUMLE)
    assert not any("Fontlar taranmadı" in n for n in _export_notes(qtbot, tmp_path))


def test_export_asks_font_scan_without_plugin_claim(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _kaydet(monkeypatch, None)
    assert any("Fontlar taranmadı" in n for n in _export_notes(qtbot, tmp_path))


def test_font_tab_keeps_warning_without_plugin_claim(qtbot: QtBot) -> None:
    from nxceviri.gui.qa_page import QaPage

    page = QaPage()
    qtbot.addWidget(page)
    page.show_font_report(FontReport([]), "")
    assert "okunabilen font bulunamadı" in page.font_banner.text.text()
    assert page.font_banner.property("state") == "warning"
