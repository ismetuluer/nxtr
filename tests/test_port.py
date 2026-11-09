"""Hazır çeviriyi (topluluk Türkçe yaması) projeye aktarma."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog, QMessageBox
from pytestqt.qtbot import QtBot

from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.progress import CancelToken, TaskContext
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.translate.port import PortError, port_translations, read_unity_translations
from nxceviri.core.translate.status import Status
from nxceviri.gui.main_window import MainWindow
from tests.unitybuild import build_bundle, other_behaviour, string_table

BOLD = (ControlCode(b"<b>", "Kalın başı"), ControlCode(b"</b>", "Kalın sonu"))


def _entry(key: str, source: str, codes: tuple[ControlCode, ...] = ()) -> TextEntry:
    return TextEntry(key, 0, source, codes)


def _project() -> Project:
    entries = (
        _entry("Dialogue_en/1", "Hello"),
        _entry("Dialogue_en/2", "Press <b>A</b>", ()),  # kaynakta kod yok: kod gelirse uyuşmaz
        _entry("Dialogue_en/3", "Use ⟦1⟧Key⟦2⟧", BOLD),
        _entry("Dialogue_en/4", "Velvet"),  # özel ad: yamada aynı
        _entry("Dialogue_en/5", "Approved line"),
        _entry("Dialogue_en/6", "Empty in patch"),
        _entry("Dialogue_en/7", "Not in patch"),
        _entry("UI_en/1", "Start"),
        _entry("Dialogue_en/8", "Machine line"),
    )
    p = Project.new()
    p.import_texts([ImportedFile("Data/x.bundle", "0100AAAA00000000", "unity", "base", entries)])
    rows = {r.key: r for r in p.translation_rows()}
    p.set_translations([(rows["Dialogue_en/5"].id, "Benim onayladığım")])  # onaylı
    p.set_translations([(rows["Dialogue_en/8"].id, "Makine eski")], machine=True)
    return p


def _patch(tmp_path: Path) -> Path:
    """Topluluk yaması gibi: tablolar "_tr" adlı, bir font paketi ve metin dışı bir paket de var."""
    folder = tmp_path / "tr yama" / "Data" / "StreamingAssets" / "aa" / "Windows"
    folder.mkdir(parents=True)
    tables = [
        string_table(
            "Dialogue_tr",
            "tr",
            1,
            [
                (1, "Merhaba"),
                (2, "<b>A</b> tuşuna basın"),
                (3, "<b>Anahtar</b> kullan"),  # özgün koda uyar: "Use ⟦1⟧Key⟦2⟧"
                (4, "Velvet"),
                (5, "Yamadaki çeviri"),
                (6, ""),
                (8, "Yeni makine"),
                (99, "Projede olmayan"),
            ],
        ),
        string_table("UI_tr", "tr", 2, [(1, "Başla")]),
    ]
    (folder / "localization-string-tables-turkish(tr)_assets_all.bundle").write_bytes(build_bundle(tables))
    (folder / "fonts_assets_all.bundle").write_bytes(build_bundle([other_behaviour("font")]))
    (folder / "readme.txt").write_text("not a bundle", encoding="utf-8")
    return tmp_path / "tr yama"


def test_read_unity_translations(tmp_path: Path) -> None:
    got = read_unity_translations(_patch(tmp_path))
    assert got["Dialogue_tr/1"] == "Merhaba"
    assert got["Dialogue_tr/2"] == "⟦1⟧A⟦2⟧ tuşuna basın"
    assert len(got) == 9  # font paketi ve metin dosyası atlandı


def test_read_translations_errors(tmp_path: Path) -> None:
    with pytest.raises(PortError, match="Klasör bulunamadı"):
        read_unity_translations(tmp_path / "yok")
    empty = tmp_path / "boş"
    empty.mkdir()
    (empty / "x.bundle").write_bytes(build_bundle([other_behaviour("a")]))
    with pytest.raises(PortError, match="metin tablosu bulunamadı"):
        read_unity_translations(empty)
    token = CancelToken()
    token.cancel()
    with pytest.raises(Exception, match="iptal"):
        read_unity_translations(_patch(tmp_path / "iptal"), TaskContext(token=token))


def test_port_matches_by_normalized_key_and_protects_approved(tmp_path: Path) -> None:
    p = _project()
    translations = read_unity_translations(_patch(tmp_path))
    preview = port_translations(p, translations, apply=False)
    assert preview.applied == 6 - 1  # kodu uyuşmayan satır hariç
    assert {r.translation for r in p.translation_rows()} >= {"Benim onayladığım", "Makine eski"}  # önizleme yazmaz

    report = port_translations(p, translations)
    rows = {r.key: r for r in p.translation_rows()}
    assert report.found == 9
    assert report.matched == 8
    assert report.unmatched_rows == 1  # "Not in patch"
    assert report.empty == 1
    assert report.protected == 1
    assert report.identical_to_source == 1  # Velvet
    assert [k for k, _s, _why in report.code_problems] == ["Dialogue_en/2"]
    assert rows["Dialogue_en/1"].translation == "Merhaba"
    assert rows["Dialogue_en/1"].status == Status.MACHINE
    assert rows["Dialogue_en/3"].translation == "⟦1⟧Anahtar⟦2⟧ kullan"  # özgün kod yer tutucuları
    assert rows["Dialogue_en/4"].translation == "Velvet"
    assert rows["Dialogue_en/5"].translation == "Benim onayladığım"  # onaylıya dokunulmadı
    assert rows["Dialogue_en/5"].status == Status.APPROVED
    assert rows["Dialogue_en/8"].translation == "Yeni makine"  # makine çevirisinin üzerine yazar
    assert rows["Dialogue_en/2"].translation == ""  # kodu uyuşmayan yazılmaz
    assert rows["Dialogue_en/7"].translation == ""
    assert rows["UI_en/1"].translation == "Başla"

    again = port_translations(p, translations)  # ikinci kez: değişecek bir şey yok
    assert again.applied == 0
    assert again.unchanged == 5


@pytest.fixture
def window(qtbot: QtBot, tmp_path: Path) -> Iterator[MainWindow]:
    w = MainWindow(QSettings(str(tmp_path / "a.ini"), QSettings.Format.IniFormat))
    qtbot.addWidget(w)
    w.show()
    yield w
    w.dirty = False
    w.close()


@pytest.mark.gui
def test_gui_import_flow(qtbot: QtBot, window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    window.import_ready_translation()  # proje boş
    assert "Metinleri Tara" in window.notifier.history[0].text  # bilgi penceresi değil, bildirim

    window.project = _project()
    window.translate_page.set_rows(window.project.translation_rows())
    folder = _patch(tmp_path)
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_a, **_k: str(folder))
    questions: list[str] = []

    def no(*a: object, **_k: object) -> QMessageBox.StandardButton:
        questions.append(str(a[2]))
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", no)
    window.import_ready_translation()
    qtbot.waitUntil(lambda: window.task is None and bool(questions), timeout=20_000)
    assert "Yazılacak: 5 satır" in questions[0]
    assert "kontrol kodları uyuşmuyor" in questions[0]
    assert {r.key: r.translation for r in window.project.translation_rows()}["Dialogue_en/1"] == ""  # vazgeçildi

    monkeypatch.setattr(QMessageBox, "question", lambda *_a, **_k: QMessageBox.StandardButton.Yes)
    window.import_ready_translation()
    qtbot.waitUntil(lambda: window.dirty and window.task is None, timeout=20_000)
    assert {r.key: r.translation for r in window.project.translation_rows()}["Dialogue_en/1"] == "Merhaba"
    assert window.translate_page.model.rows[0].translation == "Merhaba"
    assert "aktarıldı" in window.translate_page.notice_text

    empty = tmp_path / "bos"
    empty.mkdir()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *_a, **_k: str(empty))
    window.import_ready_translation()
    qtbot.waitUntil(lambda: window.task is None, timeout=20_000)
    assert "metin tablosu bulunamadı" in window.notifier.history[0].text  # uyarı penceresi değil, bildirim
