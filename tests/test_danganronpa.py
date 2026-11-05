"""Danganronpa: Spike Chunsoft WAD arşivi, .lin betikleri, .pak metin tabloları (elle üretilmiş örneklerle)."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from nxceviri.core.archives import wad
from nxceviri.core.archives.access import MemberReader, is_member_path, is_wad_path
from nxceviri.core.container.romfs import RomFs
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.container.view import ContentTree, GameView, LayeredRomFs, RomFsLayer
from nxceviri.core.errors import ArchiveError, UnsupportedFormatError
from nxceviri.core.export.layeredfs import ExportResult, TextFileRef, _export_member_archive
from nxceviri.core.formats.base import FormatError
from nxceviri.core.formats.danganronpa import DanganronpaPlugin
from nxceviri.core.formats.danganronpa.plugin import BOM, encode
from nxceviri.core.formats.detection import WAD_ARCHIVE_DETAIL, detect
from nxceviri.core.formats.scanner import scan_view
from nxceviri.core.pipeline import path_language
from tests.nxbuild import build_romfs

TID = "0100A3301618E000"
PLUGIN = DanganronpaPlugin()
WAD_PATH = "Data/StreamingAssets/Initialpack/dr1_data.wad"

LINES = [
    "<CLT 4>Hope's Peak Academy...\n<CLT>",
    "",
    "<CLT 4>It was built to raise <CLT><CLT 3>hope<CLT><CLT 4> in the nation's future.\n<CLT>",
    "？？？",  # harf içermeyen satır alınmaz
    "Makoto Naegi",
]
ITEMS = ["？？？", "Cola Cola", "Contains a highly stimulating,\nalmost addictive sweetness.", ""]


def build_lin(strings: list[str], script: bytes = b"p\x00\x05\x00p\x02\x00\x00p\x02\x00\x02") -> bytes:
    """Metinli LIN: başlık, betik komutları, 4 bayta hizalanmış metin bloğu."""
    raw = [encode(s) for s in strings]
    offsets = [8 + 4 * len(raw)]
    for r in raw:
        offsets.append(offsets[-1] + len(r))
    block = struct.pack(f"<I{len(offsets)}I", len(raw), *offsets) + b"".join(raw)
    text_offset = 16 + len(script)
    body = bytearray(struct.pack("<IIII", 2, 16, text_offset, 0) + script + block)
    body += bytes(-len(body) % 4)
    struct.pack_into("<I", body, 12, len(body))
    return bytes(body)


def build_plain_lin() -> bytes:
    script = b"p\x00\x00\x00p\x1a"
    return struct.pack("<III", 1, 12, 12 + len(script)) + script


def build_pak(items: list[bytes]) -> bytes:
    offsets = [4 + 4 * len(items)]
    for item in items[:-1]:
        offsets.append(offsets[-1] + len(item))
    return struct.pack(f"<I{len(offsets)}I", len(items), *offsets) + b"".join(items)


def build_wad(files: dict[str, bytes], gap: bytes = b"") -> bytes:
    """AGAR arşivi; `gap` her üyeden sonra konan dolgu (gerçek oyunda yok, korunduğunu sınamak için)."""
    table = bytearray(struct.pack("<I", len(files)))
    data = bytearray()
    for name, content in files.items():
        raw = name.encode()
        table += struct.pack("<I", len(raw)) + raw + struct.pack("<QQ", len(content), len(data))
        data += content + gap
    dirs = {"": ["Dr1"], "Dr1": ["data"]}
    table += struct.pack("<I", len(dirs))
    for parent, children in dirs.items():
        table += struct.pack("<I", len(parent)) + parent.encode() + struct.pack("<I", len(children))
        for child in children:
            table += struct.pack("<I", len(child)) + child.encode() + b"\x01"
    return struct.pack("<4sIII", b"AGAR", 1, 1, 0) + bytes(table) + bytes(data)


SCRIPT = "Dr1/data/us/script/e00_001_000.lin"
ITEM_PAK = "Dr1/data/us/script/04_ItemName.pak"
SCRIPT_PAK = "Dr1/data/us/script/script_pak_e00.pak"
MEMBERS = {
    SCRIPT: build_lin(LINES),
    ITEM_PAK: build_pak([encode(s) for s in ITEMS]),
    SCRIPT_PAK: build_pak([build_lin(["First script line."]), build_plain_lin(), build_lin(["Third", "Fourth one"])]),
    "Dr1/data/us/script/e00_000_000.lin": build_plain_lin(),
    "Dr1/data/jp/script/04_ItemName.pak": build_pak([encode("コーラ")]),
    "Dr1/data/us/bin/nonstop_01_001.dat": b"\x01\x02\x03",
}


def _tree() -> ContentTree:
    romfs = RomFs(MemoryStorage(build_romfs({WAD_PATH: build_wad(MEMBERS), "Data/level0": b"x"})))
    return ContentTree(TID, "Ana oyun", LayeredRomFs([RomFsLayer("base", romfs)]), lambda: None)


# --- WAD ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("gap", [b"", b"\0\0\0\0"])
def test_wad_reads_members_and_rebuilds_identically(gap: bytes) -> None:
    data = build_wad(MEMBERS, gap)
    arc = wad.WadArchive(MemoryStorage(data), "dr1_data.wad")
    assert set(arc.entries) == set(MEMBERS)
    assert all(arc.read(m) == content for m, content in MEMBERS.items())
    assert arc.rebuild({}) == data


def test_wad_rebuild_with_bigger_member() -> None:
    data = build_wad(MEMBERS, b"\xaa\xbb")
    arc = wad.WadArchive(MemoryStorage(data), "dr1_data.wad")
    bigger = build_lin([*LINES, "Türkçe: çğıİöşü " * 50])
    rebuilt = wad.WadArchive(MemoryStorage(arc.rebuild({SCRIPT: bigger})), "dr1_data.wad")
    assert rebuilt.read(SCRIPT) == bigger
    assert all(rebuilt.read(m) == c for m, c in MEMBERS.items() if m != SCRIPT)
    assert rebuilt.index[: arc.data_start - 16 * len(MEMBERS)] != b""  # dizin korunur
    assert rebuilt.data_start == arc.data_start


def test_wad_reads_index_larger_than_first_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wad, "_FIRST_READ", 16)
    arc = wad.WadArchive(MemoryStorage(build_wad(MEMBERS)), "dr1_data.wad")
    assert arc.read(ITEM_PAK) == MEMBERS[ITEM_PAK]


def test_wad_rejects_corrupt_and_unknown() -> None:
    data = build_wad(MEMBERS)
    with pytest.raises(ArchiveError, match="değil"):
        wad.WadArchive(MemoryStorage(b"XXXX" + data[4:]), "a.wad")
    with pytest.raises(ArchiveError, match="bozuk"):
        wad.WadArchive(MemoryStorage(data[:200]), "a.wad")
    with pytest.raises(ArchiveError, match="bozuk"):
        wad.WadArchive(MemoryStorage(data[:-10]), "a.wad")  # son üye dışarı taşar
    arc = wad.WadArchive(MemoryStorage(data), "a.wad")
    with pytest.raises(ArchiveError, match="yok"):
        arc.read("Dr1/yok.lin")
    with pytest.raises(ArchiveError, match="olmayan"):
        arc.rebuild({"Dr1/yok.lin": b""})


def test_wad_refuses_to_rebuild_huge_archive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wad, "MAX_REBUILD", 100)
    arc = wad.WadArchive(MemoryStorage(build_wad(MEMBERS)), "a.wad")
    with pytest.raises(UnsupportedFormatError, match="çok büyük"):
        arc.rebuild({SCRIPT: b""})


# --- .lin / .pak -----------------------------------------------------------------------------------


def test_lin_round_trip_and_tokens() -> None:
    data = build_lin(LINES)
    entries = {e.key: e for e in PLUGIN.extract(data)}
    assert set(entries) == {"0", "2", "4"}  # boş ve harfsiz satırlar alınmaz
    assert entries["0"].source == "⟦1⟧Hope's Peak Academy...\n⟦2⟧"
    assert entries["2"].source == "⟦1⟧It was built to raise ⟦2⟧⟦3⟧hope⟦4⟧⟦5⟧ in the nation's future.\n⟦6⟧"
    assert [c.raw for c in entries["2"].codes][:3] == [b"<CLT 4>", b"<CLT>", b"<CLT 3>"]
    assert entries["4"].codes == ()
    assert PLUGIN.inject(data, {k: e.source for k, e in entries.items()}) == data


def test_lin_inject_changes_length_and_keeps_script() -> None:
    data = build_lin(LINES)
    out = PLUGIN.inject(data, {"0": "⟦1⟧Umudun Zirvesi Akademisi... çğıİöşü ÇĞÖŞÜ\n⟦2⟧", "4": "Makoto"})
    got = {e.key: e.source for e in PLUGIN.extract(out)}
    assert got["0"] == "⟦1⟧Umudun Zirvesi Akademisi... çğıİöşü ÇĞÖŞÜ\n⟦2⟧"
    assert got["4"] == "Makoto"
    assert got["2"].startswith("⟦1⟧It was built")
    assert out[:12] == data[:12]  # tür, başlık ve metin bloğu ofseti aynı: betik değişmez
    assert out[16:28] == data[16:28]
    assert struct.unpack_from("<I", out, 12)[0] == len(out)
    assert len(out) % 4 == 0


def test_text_pak_round_trip_and_inject() -> None:
    data = MEMBERS[ITEM_PAK]
    entries = {e.key: e for e in PLUGIN.extract(data)}
    assert {k: e.source for k, e in entries.items()} == {"1": ITEMS[1], "2": ITEMS[2]}
    assert PLUGIN.inject(data, {"1": ITEMS[1]}) == data
    out = PLUGIN.inject(data, {"1": "Kola Kola", "2": "Son derece uyarıcı,\nneredeyse bağımlılık yapan bir tatlılık."})
    got = {e.key: e.source for e in PLUGIN.extract(out)}
    assert got == {"1": "Kola Kola", "2": "Son derece uyarıcı,\nneredeyse bağımlılık yapan bir tatlılık."}
    assert out.count(BOM) == len(ITEMS)  # boş ve harfsiz öğeler de yerinde kalır


def test_script_pak_keys_and_round_trip() -> None:
    data = MEMBERS[SCRIPT_PAK]
    entries = {e.key: e for e in PLUGIN.extract(data)}
    assert {k: e.source for k, e in entries.items()} == {
        "0.0": "First script line.",
        "2.0": "Third",
        "2.1": "Fourth one",
    }
    assert entries["2.1"].context == "Betik 2"
    assert PLUGIN.inject(data, {k: e.source for k, e in entries.items()}) == data
    out = PLUGIN.inject(data, {"2.1": "Dördüncü satır, daha uzun bir çeviri"})
    assert {e.key: e.source for e in PLUGIN.extract(out)}["2.1"] == "Dördüncü satır, daha uzun bir çeviri"
    assert PLUGIN.extract(out)[0].source == "First script line."


def test_plain_lin_has_no_text() -> None:
    assert PLUGIN.extract(build_plain_lin()) == []
    assert PLUGIN.inject(build_plain_lin(), {}) == build_plain_lin()


def test_inject_rejects_bad_tokens_and_unknown_keys() -> None:
    data = build_lin(LINES)
    with pytest.raises(FormatError, match="yazılamadı"):
        PLUGIN.inject(data, {"0": "kodlar silinmiş"})
    for key in ("1", "3", "9", "x", "0.0"):  # boş, harfsiz, olmayan, geçersiz, betik paketine ait
        with pytest.raises(FormatError, match="olmayan"):
            PLUGIN.inject(data, {key: "x"})
    with pytest.raises(FormatError, match="NUL"):
        PLUGIN.inject(MEMBERS[ITEM_PAK], {"1": "a\0b"})


def test_corrupt_files() -> None:
    data = build_lin(LINES)
    with pytest.raises(FormatError):
        PLUGIN.extract(data[:-4])  # kesik dosya: boyut alanı tutmuyor → PAK sanılır, ofset tablosu bozuk
    broken = bytearray(data)
    struct.pack_into("<I", broken, struct.unpack_from("<I", data, 8)[0] + 8, 0xFFFF)  # ofset dışarıda
    with pytest.raises(FormatError):
        PLUGIN.extract(bytes(broken))
    with pytest.raises(FormatError, match="metin tablosu veya betik"):
        PLUGIN.extract(build_pak([b"GIM\0" + b"\0" * 12, b"\x01\x02"]))
    with pytest.raises(FormatError):
        PLUGIN.extract(b"\x05\0\0\0")


def test_detection_and_paths() -> None:
    data = build_wad(MEMBERS)
    assert detect(WAD_PATH, data[:64]).detail == WAD_ARCHIVE_DETAIL
    assert detect("x.dat", data[:64]).detail != WAD_ARCHIVE_DETAIL
    assert PLUGIN.detect(SCRIPT, MEMBERS[SCRIPT][:64])
    assert PLUGIN.detect(ITEM_PAK, MEMBERS[ITEM_PAK][:64])
    assert not PLUGIN.detect("x.pak", b"\0" * 64)
    member = f"{WAD_PATH}>{SCRIPT}"
    assert is_wad_path(member)
    assert is_member_path(member)
    assert path_language(member) == "en"
    assert path_language(f"{WAD_PATH}>Dr1/data/jp/script/a.lin") == "ja"
    assert path_language(f"{WAD_PATH}>Dr1/data/ch/script/a.lin") == "zh-hant"


def test_scan_lists_scripts_and_tables() -> None:
    report = scan_view(GameView(TID, "Danganronpa", 0, None, [_tree()]))
    found = sorted(e.path.split(">", 1)[1] for e in report.entries if e.kind == "danganronpa")
    assert found == sorted(m for m in MEMBERS if "/script/" in m)
    reader = MemberReader(_tree().view)
    assert reader.read(f"{WAD_PATH}>{ITEM_PAK}") == MEMBERS[ITEM_PAK]


def test_export_rebuilds_wad() -> None:
    tree = _tree()
    script, items = f"{WAD_PATH}>{SCRIPT}", f"{WAD_PATH}>{ITEM_PAK}"
    translations = {script: {"4": "Makoto Naegi (çeviri)"}, items: {"1": "Kola Kola"}}
    outputs = _export_member_archive(
        tree,
        WAD_PATH,
        [TextFileRef(script, TID, "danganronpa"), TextFileRef(items, TID, "danganronpa")],
        translations=translations,
        root=Path("romfs"),
        result=ExportResult(Path("x")),
    )
    assert [rel.as_posix() for rel, _ in outputs] == [f"romfs/{WAD_PATH}"]
    arc = wad.WadArchive(MemoryStorage(outputs[0][1]), WAD_PATH)
    assert {e.key: e.source for e in PLUGIN.extract(arc.read(SCRIPT))}["4"] == "Makoto Naegi (çeviri)"
    assert {e.key: e.source for e in PLUGIN.extract(arc.read(ITEM_PAK))}["1"] == "Kola Kola"
    assert arc.read(SCRIPT_PAK) == MEMBERS[SCRIPT_PAK]
    assert arc.read("Dr1/data/us/bin/nonstop_01_001.dat") == b"\x01\x02\x03"
