"""Metin aktarma (oyun → proje), çeviri düzenleme ve proje şeması v2."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nxceviri.core.archives import nested
from nxceviri.core.errors import ContainerError, ProjectError
from nxceviri.core.formats.base import TextEntry
from nxceviri.core.formats.msbt import MsbtPlugin
from nxceviri.core.formats.scanner import EngineGuess, ScanEntry, ScanReport
from nxceviri.core.keys import KeySet, load_keys
from nxceviri.core.pipeline import Inputs, extract_texts, scan_sources, unsupported_text_kinds
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.project import store as store_module
from nxceviri.core.translate.status import SOURCE_CHANGED_NOTE, Status
from tests.conftest import UPDATE_FILES, GameFiles

NESTED_COMMON = "Mals/TRtr.Product.sarc.zs>TRtr.Product.sarc>Msg/Ortak.msbt"


@pytest.fixture
def extracted(game: GameFiles) -> list[ImportedFile]:
    inputs = Inputs((game.base_nsp, game.update_nsp), load_keys(game.keys_path))
    report = scan_sources(inputs, TaskContext())
    result = extract_texts(inputs, report, TaskContext())
    assert any("Bozuk.msbt" in w for w in result.warnings)  # bozuk dosya işlemi durdurmaz
    return result.files


def test_extract_texts_from_game(extracted: list[ImportedFile]) -> None:
    by_path = {f.path: f for f in extracted}
    assert set(by_path) == {"Message/Ana_Menü.msbt", NESTED_COMMON}
    menu = by_path["Message/Ana_Menü.msbt"]
    assert menu.format == "msbt"
    assert menu.origin == "update"
    assert [(e.key, e.source) for e in menu.entries] == [
        ("Menu_Start", "Start Adventure"),  # güncellemedeki metin
        ("Menu_Hello", "Hello ⟦1⟧Link⟦2⟧!"),
        ("Menu_New", "New option"),
    ]
    assert by_path[NESTED_COMMON].entries[2].source == "Please wait⟦1⟧"


def test_no_supported_format_is_explained() -> None:
    report = ScanReport(
        "Oyun",
        "0100",
        0,
        None,
        EngineGuess("unknown", "Bilinmiyor", "none", ()),
        [ScanEntry("0100", "Data/dialogue.json", 1, "text", "JSON", "high", "base")],
    )
    assert unsupported_text_kinds(report) == ["Düz metin / JSON / CSV"]
    with pytest.raises(ContainerError) as exc:
        # Desteklenen dosya yoksa paketler hiç açılmaz; boş anahtar kümesi yeterli.
        extract_texts(Inputs((), KeySet({})), report, TaskContext())
    assert "MSBT" in exc.value.hint
    assert "Unity" in exc.value.hint  # desteklenen biçimler listelenir
    assert "Unreal" in exc.value.hint
    assert "JSON" in exc.value.hint  # oyunda bulunan tür söylenir


def test_no_text_in_supported_files_is_an_error(game: GameFiles, monkeypatch: pytest.MonkeyPatch) -> None:
    """Dosyalar açılır ama hiç metin çıkmazsa "0 satır aktarıldı" başarısı yerine açık bir hata verilir.

    Gerçek örnek: Unity oyunu metnini tanınmayan kendi yapısında saklar (DKCR HD, Danganronpa).
    """
    monkeypatch.setattr(MsbtPlugin, "extract", lambda self, data, context=None: [])
    inputs = Inputs((game.base_nsp, game.update_nsp), load_keys(game.keys_path))
    report = scan_sources(inputs, TaskContext())
    with pytest.raises(ContainerError) as exc:
        extract_texts(inputs, report, TaskContext())
    assert "çevrilebilir metin bulunamadı" in exc.value.message
    assert "Nintendo LMS" in exc.value.hint  # tahmin edilen motor söylenir


def test_no_text_in_source_language_is_an_error(game: GameFiles, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MsbtPlugin, "language", lambda self, data: "en")
    inputs = Inputs((game.base_nsp, game.update_nsp), load_keys(game.keys_path))
    report = scan_sources(inputs, TaskContext())
    with pytest.raises(ContainerError) as exc:
        extract_texts(inputs, report, TaskContext(), source_language="ja")
    assert "Japonca" in exc.value.message
    assert "İngilizce (en)" in exc.value.hint  # dosyalarda bulunan dil önerilir


def test_import_and_edit(extracted: list[ImportedFile], tmp_path: Path) -> None:
    project = Project.new()
    stats = project.import_texts(extracted)
    assert (stats.files, stats.added, stats.changed, stats.removed) == (2, 6, 0, 0)
    rows = {r.key: r for r in project.translation_rows()}
    assert rows["Menu_Hello"].code_labels == ("Renk", "Etiket sonu (0:3)")
    assert all(r.status == Status.UNTRANSLATED for r in rows.values())

    ok, bad, empty = project.set_translations(
        [
            (rows["Menu_Hello"].id, "Merhaba ⟦1⟧Link⟦2⟧!"),
            (rows["Wait"].id, "Lütfen bekleyin"),  # ⟦1⟧ eksik
            (rows["Menu_Start"].id, ""),
        ]
    )
    assert (ok.status, ok.note) == (Status.APPROVED, "")
    assert bad.status == Status.ERROR
    assert "Eksik kontrol kodu" in bad.note
    assert empty.status == Status.UNTRANSLATED
    assert project.translation_counts() == {
        "untranslated": 4,
        "machine": 0,
        "redacted": 0,
        "approved": 1,
        "error": 1,
    }

    project.save_as(tmp_path / "Çeviri ğüş.nxproj")
    project.close()
    reopened = Project.open(tmp_path / "Çeviri ğüş.nxproj")
    again = {r.key: r for r in reopened.translation_rows()}
    assert again["Menu_Hello"].translation == "Merhaba ⟦1⟧Link⟦2⟧!"
    assert again["Wait"].status == Status.ERROR
    reopened.close()


def test_reimport_keeps_translations(extracted: list[ImportedFile]) -> None:
    project = Project.new()
    project.import_texts(extracted)
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations([(rows["Menu_Start"].id, "Maceraya Başla"), (rows["Yes"].id, "Evet")])

    # Oyun güncellendi: Menu_Start'ın orijinali değişti, Menu_New kaldırıldı, Yes aynı kaldı.
    menu = next(f for f in extracted if f.path == "Message/Ana_Menü.msbt")
    changed = ImportedFile(
        menu.path,
        menu.title_id,
        menu.format,
        menu.origin,
        (TextEntry("Menu_Start", 0, "Begin the Adventure", ()), menu.entries[1]),
    )
    common = next(f for f in extracted if f.path == NESTED_COMMON)
    stats = project.import_texts([changed, common])
    assert (stats.added, stats.changed, stats.removed) == (0, 1, 1)
    after = {r.key: r for r in project.translation_rows()}
    assert "Menu_New" not in after
    assert after["Menu_Start"].source == "Begin the Adventure"
    assert after["Menu_Start"].translation == "Maceraya Başla"  # çeviri silinmez
    assert (after["Menu_Start"].status, after["Menu_Start"].note) == (Status.ERROR, SOURCE_CHANGED_NOTE)
    assert (after["Yes"].translation, after["Yes"].status) == ("Evet", Status.APPROVED)

    # Dosya tamamen kaybolursa satırları da kalkar.
    assert project.import_texts([common]).removed == 2
    assert {r.file for r in project.translation_rows()} == {NESTED_COMMON}
    project.close()


def test_unknown_row_is_reported() -> None:
    project = Project.new()
    with pytest.raises(ProjectError, match="bulunamadı"):
        project.set_translations([(12345, "x")])
    project.close()


def test_v1_project_migrates_to_latest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    v1 = store_module.MIGRATIONS[:1]
    with monkeypatch.context() as m:
        m.setattr(store_module, "MIGRATIONS", v1)
        m.setattr(store_module, "SCHEMA_VERSION", 1)
        old = Project.new()
        old.set_game("Eski Proje", "0100")
        old.save_as(tmp_path / "eski.nxproj")
        old.close()
    project = Project.open(tmp_path / "eski.nxproj")
    assert project.game_name == "Eski Proje"
    assert project.translation_rows() == []
    project.close()
    assert (tmp_path / "eski.nxproj.bak").exists()
    conn = sqlite3.connect(tmp_path / "eski.nxproj")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == store_module.SCHEMA_VERSION == 6
    assert "context" in [c[1] for c in conn.execute("PRAGMA table_info(text_entries)")]
    conn.close()


def test_edited_translation_writes_back_through_nested_archive(extracted: list[ImportedFile]) -> None:
    """Uçtan uca zincir: tablodaki çeviri → MSBT inject → SARC → ZSTD → tekrar okuma."""
    project = Project.new()
    project.import_texts(extracted)
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations([(rows["Wait"].id, "Lütfen bekleyin⟦1⟧"), (rows["No"].id, "Hayır")])
    translations = {
        r.key: r.translation for r in project.translation_rows() if r.file == NESTED_COMMON and r.translation
    }

    plugin = MsbtPlugin()
    outer_name, *inner = nested.split(NESTED_COMMON)
    original = UPDATE_FILES[outer_name]
    patched = nested.replace_inner(original, inner, lambda data: plugin.inject(data, translations))
    assert patched != original
    entries = {e.key: e.source for e in plugin.extract(nested.open_inner(patched, inner))}
    assert entries == {"Yes": "Yes", "No": "Hayır", "Wait": "Lütfen bekleyin⟦1⟧"}
    # Aynı arşivdeki diğer dosya bayt bayt aynı kalır.
    bozuk = ["TRtr.Product.sarc", "Msg/Bozuk.msbt"]
    assert nested.open_inner(patched, bozuk) == nested.open_inner(original, bozuk)
    project.close()
