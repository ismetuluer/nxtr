"""Unreal: .locres eklentisi, .pak okuma, tarama/aktarma ve yama pak'ı ile dışa aktarma."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from nxceviri.core.archives.pak import PakFile, build_patch_pak, is_pak, relative_to_mount
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.errors import ArchiveError, UnsupportedFormatError
from nxceviri.core.export.layeredfs import (
    LAYOUT_ATMOSPHERE,
    ExportInfo,
    ExportOptions,
    TextFileRef,
    export_mod,
    patch_pak_name,
)
from nxceviri.core.formats.base import FormatError
from nxceviri.core.formats.unreal import LocresPlugin
from nxceviri.core.formats.unreal.locres import read as read_locres
from nxceviri.core.keys import load_keys
from nxceviri.core.pipeline import Inputs, extract_texts, scan_sources
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import Project
from tests import nxbuild
from tests.unrealbuild import build_locres, build_pak

PLUGIN = LocresPlugin()

ENTRIES = [
    ("Menu", "Start", "Start Game"),
    ("Menu", "Options", "Options"),
    ("Dialog", "Hello", "Hello {PlayerName}, <Bold>welcome</>!"),
    ("Dialog", "Icon", 'Press <img id="Confirm"/> to continue'),
    ("", "NoNamespace", "Options"),  # metin paylaşımı (aynı metin dizide bir kez)
    ("Dialog", "Unicode", "Café — ✓"),
]


@pytest.mark.parametrize("version", [0, 1, 2, 3])
def test_extract(version: int) -> None:
    data = build_locres(ENTRIES, version)
    entries = {e.key: e for e in PLUGIN.extract(data)}
    assert list(entries) == [
        "Menu/Start",
        "Menu/Options",
        "Dialog/Hello",
        "Dialog/Icon",
        "Dialog/Unicode",
        "NoNamespace",
    ]
    hello = entries["Dialog/Hello"]
    assert hello.source == "Hello ⟦1⟧, ⟦2⟧welcome⟦3⟧!"
    assert [c.label for c in hello.codes] == ["Değişken {PlayerName}", "Biçim etiketi <Bold>", "Biçim sonu"]
    assert entries["Dialog/Icon"].codes[0].label == "Simge (img)"
    assert entries["Dialog/Unicode"].source == "Café — ✓"
    assert entries["NoNamespace"].context == "NoNamespace"
    assert PLUGIN.detect("Game.locres", data[:64])


@pytest.mark.parametrize("version", [0, 1, 2, 3])
def test_round_trip_is_byte_identical(version: int) -> None:
    data = build_locres(ENTRIES, version)
    entries = PLUGIN.extract(data)
    assert PLUGIN.inject(data, {e.key: e.source for e in entries}) == data
    assert PLUGIN.inject(data, {}) == data


@pytest.mark.parametrize("version", [0, 1, 2, 3])
def test_inject(version: int) -> None:
    data = build_locres(ENTRIES, version)
    out = PLUGIN.inject(
        data,
        {"Menu/Options": "Seçenekler", "Dialog/Hello": "Merhaba ⟦1⟧, ⟦2⟧hoş geldin⟦3⟧!", "Menu/Start": "Başla"},
    )
    got = {e.key: e.source for e in PLUGIN.extract(out)}
    assert got["Menu/Options"] == "Seçenekler"
    assert got["NoNamespace"] == "Options"  # paylaşılan metnin diğer kullanıcısı etkilenmez
    assert got["Dialog/Hello"] == "Merhaba ⟦1⟧, ⟦2⟧hoş geldin⟦3⟧!"
    assert got["Menu/Start"] == "Başla"
    before, after = read_locres(data), read_locres(out)
    # Ad alanları, anahtarlar ve kaynak özetleri aynı kalır.
    assert [(e.namespace, e.key, e.source_hash) for e in before.entries] == [
        (e.namespace, e.key, e.source_hash) for e in after.entries
    ]
    if version >= 2:
        idx = {f"{e.namespace}/{e.key}" if e.namespace else e.key: e.string_index for e in after.entries}
        assert after.refcounts[idx["NoNamespace"]] == 1
        assert sum(after.refcounts) == len(after.entries)


def test_inject_rejects_broken_codes_and_unknown_keys() -> None:
    data = build_locres(ENTRIES, 2)
    with pytest.raises(FormatError, match="Eksik kontrol kodu"):
        PLUGIN.inject(data, {"Dialog/Hello": "Merhaba!"})
    with pytest.raises(FormatError, match="olmayan girdiler"):
        PLUGIN.inject(data, {"Yok/Anahtar": "x"})


def test_corrupt_locres() -> None:
    data = build_locres(ENTRIES, 2)
    with pytest.raises(FormatError):
        PLUGIN.extract(data[: len(data) // 2])
    with pytest.raises(FormatError, match="sürümü"):
        PLUGIN.extract(data[:16] + b"\x09" + data[17:])
    with pytest.raises(FormatError):
        PLUGIN.extract(data + b"\x00\x01")


# --- pak ---------------------------------------------------------------------------------

FILES = {
    "Game/Content/Localization/Game/en/Game.locres": build_locres(ENTRIES, 2),
    "Game/Content/Localization/Game/ja/Game.locres": build_locres([("Menu", "Start", "スタート")], 2),
    "Game/Content/Maps/Level.umap": b"\xc1\x83\x2a\x9e" + bytes(5000),
    "Game/Config/DefaultGame.ini": b"[/Script]\nKey=Value\n",
}


@pytest.mark.parametrize(
    ("version", "compress"), [(3, False), (7, True), (8, True), (9, False), (11, True), (11, False)]
)
def test_pak_read(version: int, compress: bool) -> None:
    data = build_pak(FILES, version=version, compress=compress, block_size=512)
    pak = PakFile(MemoryStorage(data), "pakchunk0-Switch.pak")
    assert pak.version == version
    assert set(pak.entries) == set(FILES)
    for name, content in FILES.items():
        assert pak.read(name) == content
    if compress:
        assert pak.entries["Game/Content/Maps/Level.umap"].compression == "Zlib"
    assert is_pak(MemoryStorage(data))


def test_pak_errors() -> None:
    with pytest.raises(UnsupportedFormatError, match="şifreli"):
        PakFile(MemoryStorage(build_pak(FILES, version=8, encrypted_index=True)), "x.pak")
    with pytest.raises(ArchiveError, match="pak bilgisi"):
        PakFile(MemoryStorage(b"\0" * 1000), "x.pak")
    pak = PakFile(MemoryStorage(build_pak(FILES, version=8)), "x.pak")
    with pytest.raises(ArchiveError, match="bulunamadı"):
        pak.read("yok")


def test_patch_pak_round_trip() -> None:
    files = {"Game/Content/Localization/Game/en/Game.locres": b"yeni", "Game/Config/A.ini": b"x"}
    built = build_patch_pak("../../../", files, version=11)
    pak = PakFile(MemoryStorage(built), "yama.pak")
    assert pak.version == 7  # en çok v7 (eski dizin biçimi) yazılır
    assert {n: pak.read(n) for n in pak.entries} == files
    assert relative_to_mount("../../../Game/", "Game/Content/x") == "Content/x"
    with pytest.raises(ArchiveError):
        relative_to_mount("../../../Other/", "Game/Content/x")
    assert (
        patch_pak_name("Game/Content/Paks/pakchunk0-Switch.pak") == "Game/Content/Paks/pakchunk0-Switch_NXCeviri_P.pak"
    )
    assert patch_pak_name("Game/Content/Paks/x_P.pak") == "Game/Content/Paks/x_NXCeviri_P.pak"


# --- oyundan moda ------------------------------------------------------------------------

PAK_PATH = "Game/Content/Paks/pakchunk0-Switch.pak"


@pytest.fixture
def unreal_game(tmp_path: Path) -> tuple[Inputs, Path]:
    keys = nxbuild.TestKeys.random()
    romfs = {
        PAK_PATH: build_pak(FILES, version=11, compress=True, block_size=512),
        "Game/Content/Paks/pakchunk0-Switch.sig": b"imza",
        "Game/Binaries/x.bin": b"\0" * 64,
    }
    pkg = nxbuild.build_package(
        keys,
        kind="base",
        title_id=0x0100BBBB00000000,
        application_id=0x0100BBBB00000000,
        version=0,
        romfs_files=romfs,
        name="Unreal Oyunu",
    )
    nsp = tmp_path / "unreal ğüş.nsp"
    nsp.write_bytes(pkg.nsp)
    return Inputs((nsp,), load_keys(keys.write(tmp_path / "prod.keys"))), tmp_path


def test_unreal_game_scan_import_export(unreal_game: tuple[Inputs, Path]) -> None:
    inputs, tmp_path = unreal_game
    report = scan_sources(inputs, TaskContext())
    assert report.engine.engine == "unreal"
    inner = {e.path: e for e in report.entries if ">" in e.path}
    en_path = f"{PAK_PATH}>Game/Content/Localization/Game/en/Game.locres"
    assert inner[en_path].likelihood == "high"
    assert f"{PAK_PATH}>Game/Content/Maps/Level.umap" not in inner  # metin adayı olmayanlar listelenmez

    result = extract_texts(inputs, report, TaskContext())
    assert sorted(f.path for f in result.files) == sorted(
        [en_path, f"{PAK_PATH}>Game/Content/Localization/Game/ja/Game.locres"]
    )
    project = Project.new()
    project.import_texts([f for f in result.files if f.path == en_path])
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations(
        [(rows["Menu/Start"].id, "Oyuna Başla"), (rows["Dialog/Hello"].id, "Selam ⟦1⟧, ⟦2⟧hoş geldin⟦3⟧!")]
    )

    dest = tmp_path / "mod"
    out = export_mod(
        inputs,
        [TextFileRef(*f) for f in project.text_files()],
        project.translation_rows(),
        options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "x"),
        info=ExportInfo("Unreal Oyunu", "0100BBBB00000000", 0, None),
    )
    patch = "atmosphere/contents/0100BBBB00000000/romfs/Game/Content/Paks/pakchunk0-Switch_NXCeviri_P.pak"
    assert out.files == [patch]
    assert any("imzalı" in w for w in out.warnings)
    pak = PakFile(MemoryStorage((dest / patch).read_bytes()), "yama")
    assert list(pak.entries) == ["Game/Content/Localization/Game/en/Game.locres"]  # yalnızca değişen dosya
    texts = {e.key: e.source for e in PLUGIN.extract(pak.read("Game/Content/Localization/Game/en/Game.locres"))}
    assert texts["Menu/Start"] == "Oyuna Başla"
    assert texts["Dialog/Hello"] == "Selam ⟦1⟧, ⟦2⟧hoş geldin⟦3⟧!"
    assert texts["Menu/Options"] == "Options"


def test_locres_fstring_encoding() -> None:
    from nxceviri.core.formats.unreal.locres import encode_fstring

    assert encode_fstring("") == struct.pack("<i", 0)
    assert encode_fstring("Hi") == struct.pack("<i", 3) + b"Hi\0"
    assert encode_fstring("Şi") == struct.pack("<i", -3) + "Şi".encode("utf-16-le") + b"\0\0"
