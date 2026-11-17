"""Eklenti arşiv kancası (`archive_formats`): tarama üyeleri listeler, okuma `arşiv>üye` yolunu çözer, dışa aktarma
değişen üyelerle arşivi eklentinin `rebuild`'iyle yeniden kurar.

Örnek arşiv biçimi ("KUTU") ve metin biçimi ("SATIR") bu test için uydurulmuştur; gerçek bir oyunla ilgisi yoktur.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from pathlib import Path

import pytest

from nxceviri.arac import dogrula as dogrula_araci
from nxceviri.arac.ortak import kaynak_ac
from nxceviri.core.archives import access
from nxceviri.core.container.romfs import RomFs
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.container.view import ContentTree, LayeredRomFs, RomFsLayer
from nxceviri.core.errors import ArchiveError, NxError
from nxceviri.core.export.layeredfs import (
    LAYOUT_ATMOSPHERE,
    ExportError,
    ExportInfo,
    ExportOptions,
    TextFileRef,
    export_mod,
)
from nxceviri.core.formats import registry
from nxceviri.core.keys import load_keys
from nxceviri.core.pipeline import Inputs, extract_texts, scan_sources
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import Project
from tests import nxbuild

TITLE = "0100ABAB00000000"
OTHER_TITLE = "0100CDCD00000000"

#: Test eklentisi: `.satir` metin biçimi ("anahtar=metin" satırları) ve `.kutu` arşiv biçimi.
ARCHIVE_PLUGIN = """
import struct

from nxceviri.core.formats.base import FormatError, TextEntry
from nxceviri.core.formats.derived import Derived
from nxceviri.core.plugins import FormatPluginBase

MAGIC = b"KUTU"


def kutu_oku(veri):
    if not veri.startswith(MAGIC):
        raise FormatError("KUTU değil.")
    (sayi,) = struct.unpack_from("<I", veri, 4)
    pos = 8
    dizin = []
    for _ in range(sayi):
        (uzunluk,) = struct.unpack_from("<H", veri, pos)
        ad = veri[pos + 2 : pos + 2 + uzunluk].decode("utf-8")
        (boyut,) = struct.unpack_from("<I", veri, pos + 2 + uzunluk)
        dizin.append((ad, boyut))
        pos += 6 + uzunluk
    uyeler = {}
    for ad, boyut in dizin:
        uyeler[ad] = veri[pos : pos + boyut]
        pos += boyut
    return uyeler


def kutu_yaz(uyeler):
    out = bytearray(MAGIC + struct.pack("<I", len(uyeler)))
    for ad, veri in uyeler.items():
        a = ad.encode("utf-8")
        out += struct.pack("<H", len(a)) + a + struct.pack("<I", len(veri))
    for veri in uyeler.values():
        out += veri
    return bytes(out)


class KutuArsivi:
    def __init__(self, veri):
        self._uyeler = kutu_oku(veri)

    def members(self):
        return {ad: len(v) for ad, v in self._uyeler.items()}

    def read(self, uye):
        if uye not in self._uyeler:
            raise FormatError(f"KUTU üyesi yok: {uye}")
        return self._uyeler[uye]


class KutuBicimi:
    name = "kutu"
    label = "KUTU arşivi"
    suffixes = (".kutu",)

    def detect(self, path, head):
        return head.startswith(MAGIC)

    def open(self, game, path):
        return KutuArsivi(game.open(path).read_all())

    def rebuild(self, changes, game):
        out = {}
        for top, degisen in changes.items():
            uyeler = kutu_oku(game.open(top).read_all())
            uyeler.update(degisen)
            out[top] = kutu_yaz(uyeler)
        return out
__BOZUK__

class Satir(FormatPluginBase):
    name = "satir"
    label = "SATIR metni"
    path_suffixes = (".satir",)

    def detect(self, path, head):
        return path.lower().endswith(".satir") and head.startswith(b"SATIR\\n")

    def _satirlar(self, data):
        return data.decode("utf-8").split("\\n")[1:-1]

    def extract(self, data, context=None):
        out = []
        for i, satir in enumerate(self._satirlar(data)):
            anahtar, _, metin = satir.partition("=")
            out.append(TextEntry(key=anahtar, index=i, source=metin, codes=()))
        return out

    def inject(self, data, translations):
        satirlar = []
        for satir in self._satirlar(data):
            anahtar, _, metin = satir.partition("=")
            satirlar.append(f"{anahtar}={translations.get(anahtar, metin)}")
        return ("SATIR\\n" + "".join(s + "\\n" for s in satirlar)).encode("utf-8")
__KANCA__

PLUGIN = Satir()
"""

HOOK = """
    def archive_formats(self):
        return (KutuBicimi(),)
"""

DERIVED_HOOK = """
    def archive_formats(self):
        return (KutuBicimi(),)

    def derived_files(self, read, files, game_dir=None):
        out = Derived()
        out.members["veri/paket.kutu>yeni.bin"] = b"YENI-UYE"
        return out
"""


def kutu(uyeler: dict[str, bytes]) -> bytes:
    """Test eklentisindeki `kutu_yaz`ın eşi (beklenen çıktıyı bağımsız kurmak için)."""
    out = bytearray(b"KUTU" + struct.pack("<I", len(uyeler)))
    for ad, veri in uyeler.items():
        a = ad.encode("utf-8")
        out += struct.pack("<H", len(a)) + a + struct.pack("<I", len(veri))
    for veri in uyeler.values():
        out += veri
    return bytes(out)


def kutu_oku(veri: bytes) -> dict[str, bytes]:
    (sayi,) = struct.unpack_from("<I", veri, 4)
    pos = 8
    dizin = []
    for _ in range(sayi):
        (uzunluk,) = struct.unpack_from("<H", veri, pos)
        ad = veri[pos + 2 : pos + 2 + uzunluk].decode("utf-8")
        (boyut,) = struct.unpack_from("<I", veri, pos + 2 + uzunluk)
        dizin.append((ad, boyut))
        pos += 6 + uzunluk
    uyeler = {}
    for ad, boyut in dizin:
        uyeler[ad] = veri[pos : pos + boyut]
        pos += boyut
    return uyeler


A_SATIR = b"SATIR\nselam=Hello\nveda=Goodbye\n"
C_SATIR = b"SATIR\nsoru=Ready?\n"
B_BIN = bytes(range(256)) * 3
PAKET = kutu({"a.satir": A_SATIR, "resim/b.bin": B_BIN, "metin/c.satir": C_SATIR})
GAME_FILES = {"veri/paket.kutu": PAKET, "diger.bin": b"\x00" * 64}


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    registry.reset_user_plugins()
    yield
    registry.reset_user_plugins()


def install(root: Path, *, oyunlar: tuple[str, ...] = (TITLE,), hook: str = HOOK, broken: str = "") -> None:
    folder = root / "ek" / "kutu_eklentisi"
    folder.mkdir(parents=True)
    games = ", ".join(f'"{g}"' for g in oyunlar)
    (folder / "eklenti.toml").write_text(
        f'ad = "kutu_eklentisi"\nsurum = "1.0.0"\nyazar = "Deneme"\napi = 1\noyunlar = [{games}]\n', encoding="utf-8"
    )
    body = ARCHIVE_PLUGIN.replace("__KANCA__", hook).replace("__BOZUK__", broken)
    (folder / "plugin.py").write_text(body, encoding="utf-8")
    report = registry.load_user_plugins([root / "ek"])
    assert not report.errors or broken, report.errors


def game(tmp_path: Path, files: dict[str, bytes] = GAME_FILES) -> Inputs:
    keys = nxbuild.TestKeys.random()
    pkg = nxbuild.build_package(
        keys,
        kind="base",
        title_id=int(TITLE, 16),
        application_id=int(TITLE, 16),
        version=0,
        romfs_files=files,
        name="Kutu Deneme",
    )
    nsp = tmp_path / "Kutu Deneme.nsp"
    nsp.write_bytes(pkg.nsp)
    return Inputs((nsp,), load_keys(keys.write(tmp_path / "prod.keys")))


def tree(files: dict[str, bytes] = GAME_FILES, title: str = TITLE) -> ContentTree:
    romfs = RomFs(MemoryStorage(nxbuild.build_romfs(files)), "test")
    return ContentTree(title, "Deneme", LayeredRomFs([RomFsLayer("base", romfs)]))


def test_scan_import_and_export_rebuild_the_plugin_archive(tmp_path: Path) -> None:
    install(tmp_path)
    inputs = game(tmp_path)
    report = scan_sources(inputs, TaskContext())
    by_path = {e.path: e for e in report.entries}
    assert by_path["veri/paket.kutu"].detail == "KUTU arşivi"
    assert by_path["veri/paket.kutu>a.satir"].kind == "satir"
    assert by_path["veri/paket.kutu>metin/c.satir"].kind == "satir"
    assert "veri/paket.kutu>resim/b.bin" not in by_path  # eklentilerin tanımadığı üye listelenmez

    result = extract_texts(inputs, report, TaskContext())
    assert sorted(f.path for f in result.files) == ["veri/paket.kutu>a.satir", "veri/paket.kutu>metin/c.satir"]

    project = Project.new()
    project.import_texts(result.files)
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations([(rows["selam"].id, "Merhaba ğüşıöçİ")])
    dest = tmp_path / "mod"
    export = export_mod(
        inputs,
        [TextFileRef(*f) for f in project.text_files()],
        project.translation_rows(),
        options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "x", ""),
        info=ExportInfo("Kutu Deneme", TITLE, 0, None),
    )
    assert export.files == [f"atmosphere/contents/{TITLE}/romfs/veri/paket.kutu"]
    built = kutu_oku((dest / export.files[0]).read_bytes())
    assert list(built) == ["a.satir", "resim/b.bin", "metin/c.satir"]  # sıra korunur
    assert built["a.satir"] == "SATIR\nselam=Merhaba ğüşıöçİ\nveda=Goodbye\n".encode()
    assert built["resim/b.bin"] == B_BIN  # değişmeyen üyeler bayt bayt aynı
    assert built["metin/c.satir"] == C_SATIR


def test_title_limit_applies_to_the_archive_hook(tmp_path: Path) -> None:
    install(tmp_path, oyunlar=(OTHER_TITLE,))
    report = scan_sources(game(tmp_path), TaskContext())
    paths = {e.path for e in report.entries}
    assert "veri/paket.kutu" in paths
    assert not any(">" in p for p in paths)
    assert registry.archive_formats(TITLE) == ()
    assert [f.name for f in registry.archive_formats(OTHER_TITLE)] == ["kutu"]
    assert not access.is_member_path("veri/paket.kutu>a.satir", registry.archive_formats(TITLE))


def test_plugin_without_hook_changes_nothing(tmp_path: Path) -> None:
    install(tmp_path, hook="")
    report = scan_sources(game(tmp_path), TaskContext())
    assert not any(">" in e.path for e in report.entries)
    assert registry.archive_formats(TITLE) == ()


def test_member_path_needs_a_known_archive_format() -> None:
    assert not access.is_member_path("veri/paket.kutu>a.satir")
    assert registry.archive_formats(TITLE) == ()


def test_member_reader_resolves_member_paths(tmp_path: Path) -> None:
    install(tmp_path)
    formats = registry.archive_formats(TITLE)
    assert access.is_member_path("veri/paket.kutu>a.satir", formats)
    reader = registry.member_reader(tree())
    assert reader.read("veri/paket.kutu>metin/c.satir") == C_SATIR
    assert set(reader.plugin_archive("veri/paket.kutu").members()) == {"a.satir", "resim/b.bin", "metin/c.satir"}
    with pytest.raises(NxError, match="üyesi yok"):
        reader.read("veri/paket.kutu>yok.satir")
    other = registry.member_reader(tree(title=OTHER_TITLE))
    assert other.plugin_format("veri/paket.kutu") is None  # oyunlar sınırı


def test_derived_members_are_added_through_the_hook(tmp_path: Path) -> None:
    install(tmp_path, hook=DERIVED_HOOK)
    inputs = game(tmp_path)
    report = scan_sources(inputs, TaskContext())
    project = Project.new()
    project.import_texts(extract_texts(inputs, report, TaskContext()).files)
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations([(rows["soru"].id, "Hazır mı?")])
    dest = tmp_path / "mod"
    export = export_mod(
        inputs,
        [TextFileRef(*f) for f in project.text_files()],
        project.translation_rows(),
        options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "x", ""),
        info=ExportInfo("Kutu Deneme", TITLE, 0, None),
    )
    built = kutu_oku((dest / export.files[0]).read_bytes())
    assert built["yeni.bin"] == b"YENI-UYE"
    assert built["metin/c.satir"] == "SATIR\nsoru=Hazır mı?\n".encode()
    assert built["a.satir"] == A_SATIR


BAD_REBUILD = """
    def archive_formats(self):
        return (Unutkan(),)


class Unutkan(KutuBicimi):
    def rebuild(self, changes, game):
        return {top: game.open(top).read_all() for top in changes}
"""


def test_export_refuses_a_rebuild_that_loses_the_change(tmp_path: Path) -> None:
    install(tmp_path, hook=BAD_REBUILD)
    inputs = game(tmp_path)
    report = scan_sources(inputs, TaskContext())
    project = Project.new()
    project.import_texts(extract_texts(inputs, report, TaskContext()).files)
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations([(rows["selam"].id, "Merhaba")])
    dest = tmp_path / "mod"
    with pytest.raises(ExportError, match="doğrulanamadı"):
        export_mod(
            inputs,
            [TextFileRef(*f) for f in project.text_files()],
            project.translation_rows(),
            options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "x", ""),
            info=ExportInfo("Kutu Deneme", TITLE, 0, None),
        )
    assert not dest.exists()


def test_invalid_archive_format_fails_to_load(tmp_path: Path) -> None:
    hook = """
    def archive_formats(self):
        return (Eksik(),)


class Eksik:
    name = "eksik"
    label = "Eksik"
    suffixes = (".eksik",)
"""
    install(tmp_path, hook=hook, broken=" ")
    (info,) = registry.user_plugin_report().infos
    assert info.hata
    assert "archive_formats" in info.hata
    assert "rebuild" in info.hata


def test_unexpected_errors_in_archive_code_become_archive_errors(tmp_path: Path) -> None:
    hook = """
    def archive_formats(self):
        return (Patlayan(),)


class Patlayan(KutuBicimi):
    def open(self, game, path):
        raise ValueError("bozuk")
"""
    install(tmp_path, hook=hook)
    reader = registry.member_reader(tree())
    with pytest.raises(ArchiveError, match="kutu_eklentisi"):
        reader.read("veri/paket.kutu>a.satir")


def test_scan_survives_an_archive_detect_error(tmp_path: Path) -> None:
    hook = """
    def archive_formats(self):
        return (Bozuk(),)


class Bozuk(KutuBicimi):
    def detect(self, path, head):
        raise ValueError("bozuk")
"""
    install(tmp_path, hook=hook)
    report = scan_sources(game(tmp_path), TaskContext())
    assert "veri/paket.kutu" in {e.path for e in report.entries}  # yerleşik tespitle taranır
    assert any("kutu_eklentisi" in w for w in report.warnings)


def test_dogrula_walks_plugin_archive_members(tmp_path: Path) -> None:
    install(tmp_path)
    folder = tmp_path / "romfs"
    (folder / "veri").mkdir(parents=True)
    (folder / "veri" / "paket.kutu").write_bytes(PAKET)
    plugin = registry.plugin_for_kind("satir", TITLE)
    assert plugin is not None
    with kaynak_ac([folder], None) as kaynak:
        sonuclar, _uyarilar = dogrula_araci.dogrula(plugin, kaynak.dosyalar)
    assert [(s.yol, s.gecti, s.girdi_sayisi) for s in sonuclar] == [
        ("veri/paket.kutu>a.satir", True, 2),
        ("veri/paket.kutu>metin/c.satir", True, 1),
    ]
