"""Dışa aktarmada biçim eklentisinin reddettiği satır yalnızca kendisi orijinal kalır (AGENTS.md "Kontrol kodları").

Eklenti bir satırı yazmayı reddederse (ör. eski sürümde taranmış, kaynağı eski kod düzeniyle saklanmış çoğul satırı ya
da çoğul seçeneğine boşluk/virgül yazılmış satır) dosyanın geri kalanı yazılır; reddedilen satır orijinal kalır ve
bilgi dosyasında dosya + anahtarıyla listelenir. Satır "Hatalı" işaretli olmasa da böyledir (TECH_DEBT 97).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from pathlib import Path

import pytest

from nxceviri.core.archives.pak import PakFile
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.export.layeredfs import (
    INFO_FILE,
    LAYOUT_ATMOSPHERE,
    ExportError,
    ExportInfo,
    ExportOptions,
    ExportResult,
    TextFileRef,
    collect_translations,
    export_mod,
)
from nxceviri.core.formats.base import ControlCode, FormatError
from nxceviri.core.formats.unity import UnityPlugin
from nxceviri.core.formats.unreal import LocresPlugin
from nxceviri.core.keys import load_keys
from nxceviri.core.pipeline import Inputs, extract_texts, scan_sources
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.translate.status import Status
from tests import nxbuild
from tests.unitybuild import build_bundle, string_table
from tests.unrealbuild import build_locres, build_pak

PAK_PATH = "Game/Content/Paks/pakchunk0-Switch.pak"
LOCRES = "Game/Content/Localization/Game/en/Game.locres"
AA = "Data/StreamingAssets/aa/Switch/"
UNREAL_TID = "0100BBBB00000000"
UNITY_TID = "0100AAAA00000000"

#: Unreal: bu sürümden önce `{N}` serbest değişkendi, `|plural(…)` düz metindi (0.63.0'ın `tokenize` çıktısı, elle).
OLD_PLURAL = "{N}|plural(one=cat,other=cats) left"
OLD_PLURAL_ENTRY = ("⟦1⟧|plural(one=cat,other=cats) left", (ControlCode(b"{N}", "Değişken {N}"),))
#: Unity: bu sürümden önce çoğul ifadesinin bütünü tek koddu (TECH_DEBT 21'den önceki `tokenize` çıktısı, elle).
OLD_SMART = "Smart {0:plural:one item|{} items} left"
OLD_SMART_ENTRY = (
    "Smart ⟦1⟧ left",
    (ControlCode(b"{0:plural:one item|{} items}", "Değişken {0:plural:one item|{} items}"),),
)


def _package(tmp_path: Path, title_id: int, files: dict[str, bytes], name: str) -> Inputs:
    keys = nxbuild.TestKeys.random()
    pkg = nxbuild.build_package(
        keys, kind="base", title_id=title_id, application_id=title_id, version=0, romfs_files=files, name=name
    )
    nsp = tmp_path / f"{name}.nsp"
    nsp.write_bytes(pkg.nsp)
    return Inputs((nsp,), load_keys(keys.write(tmp_path / "prod.keys")))


def _import_with_old_layout(
    inputs: Inputs, old: dict[str, tuple[str, tuple[ControlCode, ...]]], language: str | None = None
) -> Project:
    """Oyunu tarar ve projeye aktarır; `old` içindeki anahtarların kaynağını eski kod düzeniyle saklar."""
    report = scan_sources(inputs, TaskContext())
    imported = []
    for f in extract_texts(inputs, report, TaskContext(), language).files:
        entries = tuple(
            dataclasses.replace(e, source=old[e.key][0], codes=old[e.key][1]) if e.key in old else e for e in f.entries
        )
        imported.append(ImportedFile(f.path, f.title_id, f.format, f.origin, entries))
    project = Project.new()
    project.import_texts(imported)
    return project


def _translate(project: Project, texts: dict[str, str]) -> None:
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations([(rows[k].id, t) for k, t in texts.items()], machine=True)


def _export(project: Project, inputs: Inputs, dest: Path, tid: str, *, include_errors: bool = False) -> ExportResult:
    return export_mod(
        inputs,
        [TextFileRef(*f) for f in project.text_files()],
        project.translation_rows(),
        options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "Deneme", include_errors=include_errors),
        info=ExportInfo("Deneme Oyunu", tid, 0, None),
    )


def _assert_not_error_and_not_soft(project: Project, keys: tuple[str, ...]) -> None:
    """Ön koşul: satırlar "Hatalı" değil ve eski serbest kod/hatalı satır yolundan (soft) geçmiyor."""
    rows = project.translation_rows()
    for r in rows:
        if r.key in keys:
            assert r.status != Status.ERROR, r.key
    soft: dict[str, set[str]] = {}
    collect_translations(rows, "", soft=soft)
    assert not any(k in keys for found in soft.values() for k in found)


# --- Unreal ------------------------------------------------------------------------------------


def _unreal(tmp_path: Path) -> tuple[Inputs, Project]:
    locres = build_locres(
        [
            ("Game", "Old", OLD_PLURAL),
            ("Game", "Bad", "There {N}|plural(one=is,other=are) here"),
            ("Game", "Plain", "Hello"),
            ("Game", "Start", "Start"),
        ]
    )
    inputs = _package(tmp_path, 0x0100BBBB00000000, {PAK_PATH: build_pak({LOCRES: locres}, version=11)}, "unreal")
    project = _import_with_old_layout(inputs, {"Game/Old": OLD_PLURAL_ENTRY})
    _translate(
        project,
        {
            "Game/Old": "⟦1⟧|plural(one=kedi,other=kedi) kaldı",  # eski düzende geçerli çeviri
            "Game/Bad": "Orada ⟦1⟧var, yok⟦2⟧var⟦3⟧",  # kodları doğru, seçeneğe virgül ve boşluk yazılmış
            "Game/Plain": "Merhaba",
            "Game/Start": "Başla",
        },
    )
    return inputs, project


def _written_locres(dest: Path) -> dict[str, str]:
    patch = dest / "atmosphere/contents" / UNREAL_TID / "romfs/Game/Content/Paks/pakchunk0-Switch_NXCeviri_P.pak"
    pak = PakFile(MemoryStorage(patch.read_bytes()), "yama")
    return {e.key: e.source for e in LocresPlugin().extract(pak.read(LOCRES))}


def test_unreal_rejected_rows_stay_original_and_rest_of_file_is_written(tmp_path: Path) -> None:
    inputs, project = _unreal(tmp_path)
    _assert_not_error_and_not_soft(project, ("Game/Old", "Game/Bad"))
    dest = tmp_path / "mod"
    result = _export(project, inputs, dest, UNREAL_TID)
    texts = _written_locres(dest)
    assert texts["Game/Plain"] == "Merhaba"
    assert texts["Game/Start"] == "Başla"
    assert texts["Game/Old"] == "⟦1⟧cat⟦2⟧cats⟦3⟧ left"  # orijinal kaldı (bugünkü düzenle okunur)
    assert texts["Game/Bad"] == "There ⟦1⟧is⟦2⟧are⟦3⟧ here"
    ids = {r.key: r.id for r in project.translation_rows()}
    assert sorted(result.rejected_ids) == sorted([ids["Game/Old"], ids["Game/Bad"]])
    assert result.reorder_dropped_ids == []
    assert result.rows_written == 2
    assert any("yazılamadı" in w and "2 satır" in w for w in result.warnings)
    info = (dest / INFO_FILE).read_text(encoding="utf-8")
    assert "Biçim eklentisi reddettiği için orijinal bırakılan satır: 2" in info
    assert "Game/Old" in info
    assert "Game/Bad" in info
    assert "kaldı" not in info  # oyun metni değil yalnızca anahtar yazılır
    assert "Orada" not in info
    assert "Yazılan çeviri satırı: 2" in info


def test_unreal_rejected_rows_with_include_errors_too(tmp_path: Path) -> None:
    """ "Hatalı satırları da aktar" açıkken de hatalı olmayan reddedilen satır dosyayı düşürmez."""
    inputs, project = _unreal(tmp_path)
    dest = tmp_path / "mod"
    result = _export(project, inputs, dest, UNREAL_TID, include_errors=True)
    texts = _written_locres(dest)
    assert (texts["Game/Plain"], texts["Game/Start"]) == ("Merhaba", "Başla")
    assert len(result.rejected_ids) == 2
    assert (result.rows_error_written, result.rows_error_kept) == (0, 0)


# --- Unity -------------------------------------------------------------------------------------


def test_unity_old_smart_string_row_stays_original(tmp_path: Path) -> None:
    bundle = build_bundle([string_table("UI_en", "en", 0, [(1, "Yes"), (2, OLD_SMART), (3, "No")])])
    files = {
        "Data/globalgamemanagers": b"\0" * 8 + (22).to_bytes(4, "big") + b"\0" * 20,
        AA + "localization-string-tables-english(en)_assets_all.bundle": bundle,
    }
    inputs = _package(tmp_path, 0x0100AAAA00000000, files, "unity")
    project = _import_with_old_layout(inputs, {"UI_en/2": OLD_SMART_ENTRY}, "en")
    _translate(project, {"UI_en/1": "Evet", "UI_en/2": "Kalan ⟦1⟧", "UI_en/3": "Hayır"})
    _assert_not_error_and_not_soft(project, ("UI_en/2",))
    dest = tmp_path / "mod"
    result = _export(project, inputs, dest, UNITY_TID)
    written = (dest / result.files[0]).read_bytes()
    texts = {e.key: e.source for e in UnityPlugin().extract(written)}
    assert texts["UI_en/1"] == "Evet"
    assert texts["UI_en/3"] == "Hayır"
    assert texts["UI_en/2"] == "Smart ⟦1⟧one item⟦2⟧⟦3⟧ items⟦4⟧ left"  # orijinal kaldı
    assert result.rejected_ids == [next(r.id for r in project.translation_rows() if r.key == "UI_en/2")]
    info = (dest / INFO_FILE).read_text(encoding="utf-8")
    assert "UI_en/2" in info


def test_unattributable_failure_still_fails_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Çevirisiz (boş) yazım bile başarısızsa sorun satırlarda değildir: hata yutulmaz, mod üretilmez."""
    inputs, project = _unreal(tmp_path)

    def broken(self: LocresPlugin, data: bytes, translations: Mapping[str, str]) -> bytes:
        raise FormatError("dosya bozuk")

    monkeypatch.setattr(LocresPlugin, "inject", broken)
    with pytest.raises(ExportError):
        _export(project, inputs, tmp_path / "bozuk", UNREAL_TID)
    assert not (tmp_path / "bozuk").exists()


@pytest.mark.parametrize(
    ("text", "translation"),
    [
        (OLD_PLURAL, "⟦1⟧|plural(one=kedi,other=kedi) kaldı"),  # eski düzen: eksik kod
        ("{N}|plural(one=cat,other=cats)", "⟦1⟧var, yok⟦2⟧var⟦3⟧"),  # geçersiz çoğul seçeneği
    ],
)
def test_row_rejection_names_the_row(text: str, translation: str) -> None:
    """Satır reddi hangi satır olduğunu söyler (`FormatError.key`); dışa aktarma onu bölmeden doğrudan ayıklar."""
    data = build_locres([("Game", "K", text), ("Game", "Plain", "Hello")])
    with pytest.raises(FormatError) as caught:
        LocresPlugin().inject(data, {"Game/K": translation, "Game/Plain": "Merhaba"})
    assert caught.value.key == "Game/K"
