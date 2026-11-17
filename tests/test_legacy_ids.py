"""Kalıcı kimliklerin yeni adları ve 0.59.0 ile yazılmış (eski kimlikli) projelerin açılması.

Eski değerler burada bilerek elle yazılır: eşleme tablosu kendi kendini doğrulamasın diye.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from nxceviri.core.container.view import GameView
from nxceviri.core.export.layeredfs import ExportError, ExportResult, TextFileRef, _apply_group, _verify_group
from nxceviri.core.fontpatch import fsdmsg_graphics, nni_graphics
from nxceviri.core.formats import legacy
from nxceviri.core.formats.detection import (
    CPK_ARCHIVE_DETAIL,
    NNI_ARCHIVE_DETAIL,
    PSB_ARCHIVE_DETAIL,
    WAD_ARCHIVE_DETAIL,
    FileKind,
    detect,
)
from nxceviri.core.formats.registry import BUILTIN_PLUGINS, kind_label, plugin_for_kind
from nxceviri.core.formats.scanner import ENGINE_LABELS, EngineGuess, ScanEntry, ScanReport, scan_view
from nxceviri.core.project import ImportedFile, Project, in_collection, row_group
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import FitConfig, separate_groups
from tests.fsdmsgbuild import fsd, message, table
from tests.nnicpkbuild import build_xso
from tests.psbbuild import build_psb
from tests.test_nnitext import TID as NNI_TID
from tests.test_nnitext import _tree as nni_tree
from tests.test_pakyc import _game
from tests.test_psbtext import MENU
from tests.test_wadlin import LINES, build_lin

TID = "0100000000000000"

#: 0.59.0'ın yazdığı biçim kimlikleri → bugünkü kimlikler.
OLD_FORMATS = {"danganronpa": "wadlin", "dmc1": "fsdmsg", "mina": "pakyc", "ysorigin": "nnitext", "m2text": "psbtext"}
#: 0.59.0'ın yazdığı motor anahtarları → bugünkü anahtarlar.
OLD_ENGINES = {
    "m2": "psb",
    "falcom": "nni",
    "vanillaware": "cpk",
    "spike": "wad",
    "nintendo": "lms",
    "gamefreak": "gfmsg",
}
#: 0.59.0'ın yazdığı arşiv ayrıntıları → bugünkü ayrıntılar.
OLD_ARCHIVE_DETAILS = {
    "M2 arşivi (mdf)": PSB_ARCHIVE_DETAIL,
    "Falcom NNI arşivi": NNI_ARCHIVE_DETAIL,
    "CRI CPK arşivi": CPK_ARCHIVE_DETAIL,
    "Spike Chunsoft WAD arşivi": WAD_ARCHIVE_DETAIL,
}


def _samples() -> list[tuple[str, str, bytes]]:
    """(yol, 0.59.0 kimliği, dosya) — beş yeniden adlandırılan biçimin her biri için elle üretilmiş örnek."""
    return [
        ("romfs/script/e00.lin", "danganronpa", build_lin(LINES)),
        ("romfs/data/fsd/r100.fsd", "dmc1", fsd(table([message(s) for s in ["Hello there.", "Go on."]]))),
        ("romfs/global.pak.yc", "mina", _game()),
        ("romfs/LOC/EN/X.XSO", "ysorigin", build_xso(["S_0003", "Who goes there?", "Hugo"])),
        ("romfs/menu_item.psb", "m2text", build_psb(MENU)),
    ]


def _old_project(path: Path) -> tuple[int, int]:
    """0.59.0 biçimli proje: eski biçim kimlikleri, eski motor anahtarı ve eski arşiv ayrıntısıyla saklı tarama."""
    project = Project.new()
    files = []
    for file_path, old, data in _samples():
        entries = tuple(plugin_for_kind(OLD_FORMATS[old]).extract(data))  # type: ignore[union-attr]
        files.append(ImportedFile(file_path, TID, old, "base", entries))
    project.import_texts(files)
    rows = project.translation_rows()
    # kodlar ve uzunluk korunur (sığmayan çeviri bu testin konusu değil)
    project.set_translations([(r.id, r.source.swapcase()) for r in rows[::2]])
    project.save_scan(
        ScanReport(
            "Oyun",
            TID,
            0,
            None,
            EngineGuess(
                "falcom",
                "Falcom (Ys Origin)",
                "medium",
                ("Falcom NNI arşivleri: 1", "Ys Origin betik/arayüz metinleri: 1"),
            ),
            [
                ScanEntry(TID, "data-en.ni", 10, "archive", "Falcom NNI arşivi", "none", "base"),
                ScanEntry(
                    TID, "data-en.ni>LOC/EN/X.XSO", 10, "ysorigin", "Ys Origin betik metni (XSO)", "high", "base"
                ),
                ScanEntry(TID, "x.msbt", 10, "msbt", "MSBT (Nintendo LMS metni)", "high", "base"),
            ],
        )
    )
    project.save_as(path)
    project.close()
    return len(rows), len(rows[::2])


def _stored(path: Path) -> tuple[set[str], tuple[str, str, str], set[str]]:
    with sqlite3.connect(path) as conn:
        formats = {r[0] for r in conn.execute("SELECT format FROM text_files")}
        engine = conn.execute("SELECT engine, engine_label, engine_evidence FROM scans").fetchone()
        details = {r[0] for r in conn.execute("SELECT detail FROM scan_files")}
    conn.close()
    return formats, engine, details


# --- kimlikler ve kayıt defteri ------------------------------------------------------------


def test_registry_offers_exactly_the_eleven_builtin_plugins() -> None:
    assert sorted(p.name for p in BUILTIN_PLUGINS) == sorted(
        ["wadlin", "fsdmsg", "fmsb", "gfmsg", "psbtext", "pakyc", "msbt", "srt", "unity", "unreal", "nnitext"]
    )


def test_new_ids_are_file_kinds_and_the_legacy_table_matches() -> None:
    for new in OLD_FORMATS.values():
        assert FileKind(new).value == new
    assert legacy.FORMAT_IDS == OLD_FORMATS
    assert legacy.ENGINE_IDS == OLD_ENGINES
    for old, new in OLD_ARCHIVE_DETAILS.items():
        assert legacy.detail(old) == new


def test_every_legacy_format_id_resolves_to_its_plugin() -> None:
    for old, new in OLD_FORMATS.items():
        plugin = plugin_for_kind(old, TID)
        assert plugin is not None
        assert plugin.name == new
        assert legacy.format_id(old) == new
        assert kind_label(old) == kind_label(new)


def test_every_legacy_engine_resolves_to_a_label() -> None:
    for old, new in OLD_ENGINES.items():
        assert legacy.engine_id(old) == new
        assert new in ENGINE_LABELS


def test_unknown_id_keeps_todays_behaviour() -> None:
    assert legacy.format_id("bilinmeyen") == "bilinmeyen"
    assert legacy.engine_id("bilinmeyen") == "bilinmeyen"
    assert legacy.detail("Bilinmeyen") == "Bilinmeyen"
    assert plugin_for_kind("bilinmeyen") is None
    assert kind_label("bilinmeyen") == "bilinmeyen"
    ref = TextFileRef("romfs/x.bin", TID, "bilinmeyen")
    with pytest.raises(ExportError) as exc:
        _apply_group(b"x", [ref], {ref.path: {}}, skip=1, result=ExportResult(Path(".")))
    assert exc.value.message == "'romfs/x.bin' için format eklentisi yok (bilinmeyen)."


def test_new_scan_writes_new_ids(tmp_path: Path) -> None:
    assert detect("romfs/global.pak.yc", _game()[:64]).kind == "pakyc"
    assert detect("data/dmc1/fsd/r100.fsd", b"\0" * 64).kind == "fsdmsg"
    report = scan_view(GameView(NNI_TID, "Oyun", 0, None, [nni_tree()]))
    project = Project.new()
    project.save_scan(report)
    texts = [e for e in report.entries if plugin_for_kind(e.kind) is not None]
    project.import_texts(
        [ImportedFile(e.path, e.title_id, plugin_for_kind(e.kind).name, e.origin, ()) for e in texts]  # type: ignore[union-attr]
    )
    path = tmp_path / "yeni.nxproj"
    project.save_as(path)
    project.close()
    with sqlite3.connect(path) as conn:
        engine = conn.execute("SELECT engine, engine_label, engine_evidence FROM scans").fetchone()
        kinds = {r[0] for r in conn.execute("SELECT kind FROM scan_files")}
        details = {r[0] for r in conn.execute("SELECT detail FROM scan_files")}
        formats = {r[0] for r in conn.execute("SELECT format FROM text_files")}
    conn.close()
    assert engine[0] == "nni"
    assert engine[1] == ENGINE_LABELS["nni"]
    assert json.loads(engine[2]) == ["NNI arşivleri: 2", "NNI betik/arayüz metinleri: 4"]
    assert "nnitext" in kinds
    assert not kinds & set(OLD_FORMATS)
    assert NNI_ARCHIVE_DETAIL in details
    assert not details & set(legacy.DETAILS)
    assert formats == {"nnitext"}


# --- 0.59.0 projesi ------------------------------------------------------------------------


def test_old_project_opens_with_every_row_translation_and_plugin(tmp_path: Path) -> None:
    path = tmp_path / "eski.nxproj"
    n_rows, n_translated = _old_project(path)

    project = Project.open(path)
    rows = project.translation_rows()
    assert len(rows) == n_rows
    assert sum(1 for r in rows if r.translation) == n_translated
    assert {r.format for r in rows} == set(OLD_FORMATS.values())
    assert {f for _p, _t, f in project.text_files()} == set(OLD_FORMATS.values())
    for r in rows:
        plugin = plugin_for_kind(r.format, TID)
        assert plugin is not None
        assert plugin.name == r.format

    scan = project.latest_scan()
    assert scan is not None
    assert scan.engine == EngineGuess(
        "nni", ENGINE_LABELS["nni"], "medium", ("NNI arşivleri: 1", "NNI betik/arayüz metinleri: 1")
    )
    assert [(e.kind, e.detail) for e in scan.entries] == [
        ("archive", NNI_ARCHIVE_DETAIL),
        ("nnitext", legacy.detail("Ys Origin betik metni (XSO)")),
        ("msbt", legacy.detail("MSBT (Nintendo LMS metni)")),
    ]
    project.close()


def test_old_project_round_trips_and_exports_with_old_ids(tmp_path: Path) -> None:
    path = tmp_path / "eski.nxproj"
    _old_project(path)
    project = Project.open(path)
    by_file: dict[str, dict[str, str]] = {}
    for r in project.translation_rows():
        if r.translation:
            by_file.setdefault(r.file, {})[r.key] = r.translation
    project.close()

    for file_path, old, data in _samples():
        plugin = plugin_for_kind(old, TID)
        assert plugin is not None
        assert plugin.extract(data)
        assert plugin.inject(data, {}) == data  # round-trip: değişiklik yoksa bayt bayt aynı
        ref = TextFileRef(file_path, TID, old)
        translations = {file_path: by_file.get(file_path, {})}
        result = ExportResult(tmp_path)
        out = _apply_group(data, [ref], translations, skip=1, result=result)
        _verify_group(out, [ref], translations, skip=1, result=result, original=data)
        if translations[file_path]:
            assert out != data


def test_old_ids_stay_in_the_file_after_use_and_save(tmp_path: Path) -> None:
    path = tmp_path / "eski.nxproj"
    _old_project(path)
    before = _stored(path)
    assert before[0] == set(OLD_FORMATS)
    assert before[1][0] == "falcom"
    assert "Falcom NNI arşivi" in before[2]

    project = Project.open(path)
    rows = project.translation_rows()
    project.set_translations([(rows[1].id, "Yeni çeviri")])
    project.unapprove([rows[0].id])
    project.set_setting("deneme", "1")
    project.save_as(tmp_path / "kopya.nxproj")
    project.close()

    assert _stored(path) == before
    assert _stored(tmp_path / "kopya.nxproj") == before


def test_reimport_keeps_the_stored_old_id_of_the_same_format(tmp_path: Path) -> None:
    """Yeniden taramada aynı biçimin eski kimliği dosyada kalır (eski sürüm projeyi açmaya devam eder);
    projeye yeni giren dosya yeni kimlikle yazılır."""
    path = tmp_path / "eski.nxproj"
    _old_project(path)
    project = Project.open(path)
    files = [
        ImportedFile(p, TID, OLD_FORMATS[old], "base", tuple(plugin_for_kind(old).extract(d)))  # type: ignore[union-attr]
        for p, old, d in _samples()
    ]
    files.append(ImportedFile("romfs/yeni.pak.yc", TID, "pakyc", "base", ()))
    project.import_texts(files)
    project.close()
    with sqlite3.connect(path) as conn:
        stored = dict(conn.execute("SELECT path, format FROM text_files").fetchall())
    conn.close()
    assert stored == {p: old for p, old, _d in _samples()} | {"romfs/yeni.pak.yc": "pakyc"}


def test_mixed_old_and_new_rows_behave_as_one_format() -> None:
    project = Project.new()
    entries = tuple(plugin_for_kind("pakyc").extract(_game()))  # type: ignore[union-attr]
    project.import_texts(
        [
            ImportedFile("romfs/a/global.pak.yc", TID, "mina", "base", entries),
            ImportedFile("romfs/b/global.pak.yc", TID, "pakyc", "base", entries),
        ]
    )
    rows = project.translation_rows()
    assert {r.format for r in rows} == {"pakyc"}
    assert {row_group(r) for r in rows} == {"global.pak.yc"}
    assert not any(in_collection(r) for r in rows)
    refs = [TextFileRef(p, t, f) for p, t, f in project.text_files()]
    refs += [TextFileRef("romfs/c.pak.yc", TID, "mina")]
    assert {(r.title_id, r.format) for r in refs} == {(TID, "pakyc")}
    # sığdırma: iki dosyadaki aynı grup tek grup olarak öğrenilir ve aynı kuralı alır
    assert separate_groups(rows) == ["global.pak.yc"]
    config = FitConfig(per_group={"global.pak.yc": FitRules(20, 2)})
    assert {config.rules_for_row(r) for r in rows} == {FitRules(20, 2)}


# --- ortam değişkenleri --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("module", "new", "old"),
    [
        (fsdmsg_graphics, "NXCEVIRI_FSD_GRAFIK", "NXCEVIRI_DMC1_GRAFIK"),
        (nni_graphics, "NXCEVIRI_NNI_GRAFIK", "NXCEVIRI_YS_GRAFIK"),
    ],
)
def test_graphics_folder_variable_new_name_wins_old_name_still_works(
    module: object, new: str, old: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert new == module.ENV  # type: ignore[attr-defined]
    monkeypatch.delenv(new, raising=False)
    monkeypatch.setenv(old, "eski")
    assert legacy.environ(new) == "eski"
    monkeypatch.setenv(new, "yeni")
    assert legacy.environ(new) == "yeni"
    monkeypatch.delenv(old)
    monkeypatch.delenv(new)
    assert legacy.environ(new) is None


def test_graphics_folder_lookup_uses_the_old_variable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "grafik"
    (folder / "turkce").mkdir(parents=True)
    monkeypatch.delenv("NXCEVIRI_NNI_GRAFIK", raising=False)
    monkeypatch.setenv("NXCEVIRI_YS_GRAFIK", str(folder))
    assert nni_graphics.folder_for(None) == folder
    other = tmp_path / "diger"
    (other / "turkce").mkdir(parents=True)
    monkeypatch.setenv("NXCEVIRI_NNI_GRAFIK", str(other))
    assert nni_graphics.folder_for(None) == other


def test_check_tool_finds_plugin_by_old_id() -> None:
    from nxceviri.arac.dogrula import eklenti_bul

    for old, new in OLD_FORMATS.items():
        assert eklenti_bul(old).name == new
