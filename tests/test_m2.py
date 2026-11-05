"""M2 arşivleri: PSB okuma/dizge yeniden yazma, mdf, anahtar bulma, `.psb.m` + `.bin`, NSO."""

from __future__ import annotations

import random
import struct
import zlib

import pytest

from nxceviri.core.archives import m2, psb
from nxceviri.core.archives.psb import Chunk, IntArray, PsbValue
from nxceviri.core.container import nso
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.errors import ArchiveError, ContainerError, UnsupportedFormatError
from tests.m2build import build_m2_archive, build_nso, build_psb

KEY = b"TestAnahtar01"  # testlere özgü uydurma anahtar; hiçbir oyuna ait değildir

TREE: dict[str, PsbValue] = {
    "data": [
        {"pageNo": 1, "pageTitle": "TOP", "text": "<b>Briefing</b><br>Snake"},
        {"pageNo": 2, "pageTitle": "Section 1", "text": "Çok uzun bir Türkçe metin: ğüşıöç İ"},
    ],
    "flags": [True, False, None],
    "numbers": [0, -1, 127, 128, -129, 1 << 40],
    "ratio": 0.5,
    "blob": Chunk(0),
    "empty": "",
}


@pytest.mark.parametrize("version", [2, 3, 4])
def test_psb_reads_hand_built_tree(version: int) -> None:
    data = build_psb(TREE, [b"\x01\x02\x03"], version)
    doc = psb.Psb(data)
    assert doc.version == version
    assert doc.root() == TREE
    assert doc.chunk(0) == b"\x01\x02\x03"
    if version >= 3:
        assert struct.unpack_from("<I", data, 0x28)[0] == psb.checksum(data)


@pytest.mark.parametrize("version", [2, 3, 4])
def test_psb_unchanged_round_trip_is_identical(version: int) -> None:
    data = build_psb(TREE, [b"chunk"], version)
    assert psb.replace_strings(data, {}) is data
    same = dict(enumerate(psb.Psb(data).strings))
    assert psb.replace_strings(data, same) is data


@pytest.mark.parametrize("version", [2, 3, 4])
def test_psb_replace_strings_keeps_everything_else(version: int) -> None:
    data = build_psb(TREE, [b"\xaa" * 300], version, chunk_align=0x80)
    doc = psb.Psb(data)
    i = doc.strings.index("<b>Briefing</b><br>Snake")
    new_text = "<b>Brifing</b><br>Yılan " + "ğ" * 400  # dizge tablosunu büyütür, ofset genişliğini değiştirir
    out = psb.replace_strings(data, {i: new_text})
    again = psb.Psb(out)
    root = again.root()
    assert isinstance(root, dict)
    assert isinstance(root["data"], list)
    assert root["data"][0] == {"pageNo": 1, "pageTitle": "TOP", "text": new_text}
    assert {**root, "data": None} == {**TREE, "data": None}
    assert root["data"][1] == TREE["data"][1]  # type: ignore[index]
    assert again.chunk(0) == b"\xaa" * 300
    assert struct.unpack_from("<I", out, 0x20)[0] % 0x80 == 0  # parça verisinin hizalaması korunur
    header_end, o_strings = struct.unpack_from("<II", data, 0x0C)
    assert out[header_end:o_strings] == data[header_end:o_strings]  # adlar ve kök ağaç aynen kalır
    if version >= 3:
        assert struct.unpack_from("<I", out, 0x28)[0] == psb.checksum(out)
    back = psb.replace_strings(out, {i: "<b>Briefing</b><br>Snake"})
    assert psb.Psb(back).root() == TREE


def test_psb_replace_strings_rejects_bad_input() -> None:
    data = build_psb(TREE)
    with pytest.raises(ArchiveError, match="dizini geçersiz"):
        psb.replace_strings(data, {999: "x"})
    with pytest.raises(ArchiveError, match="NUL"):
        psb.replace_strings(data, {0: "a\0b"})


def test_psb_rejects_corrupt_and_unsupported() -> None:
    data = build_psb(TREE)
    with pytest.raises(ArchiveError, match="imza"):
        psb.Psb(b"XXXX" + data[4:])
    with pytest.raises(UnsupportedFormatError, match="sürüm 5"):
        psb.Psb(data[:4] + struct.pack("<H", 5) + data[6:])
    with pytest.raises(UnsupportedFormatError, match="Şifreli"):
        psb.Psb(data[:6] + struct.pack("<H", 1) + data[8:])
    with pytest.raises(ArchiveError):
        psb.Psb(data[:60])


def test_key_stream_matches_reference_mt19937() -> None:
    # Python'un random modülü de MT19937 init_by_array kullanır: tohumun 32 bitlik parçaları.
    digest_words = [0x11111111, 0x22222222, 0x33333333, 0x44444444]
    seed_words = m2._mt19937_init_by_array(digest_words)
    ours = m2._mt19937_words(seed_words, 16)
    ref = random.Random(sum(w << (32 * i) for i, w in enumerate(digest_words)))
    assert ours == [ref.getrandbits(32) for _ in range(16)]


def test_mdf_round_trip_and_name_rule() -> None:
    payload = build_psb({"x": "Türkçe"}) * 50
    blob = m2.encode(payload, "087/config/Output_TextData_EN.psb.m", KEY)
    assert blob[:4] == m2.MAGIC
    assert struct.unpack_from("<I", blob, 4)[0] == len(payload)
    # yalnızca dosya adı (klasörsüz, küçük harfle) anahtar akışına girer
    assert m2.decode(blob, "output_textdata_en.psb.m", KEY) == payload
    assert m2.decode(blob, "başka/klasör/OUTPUT_TEXTDATA_EN.PSB.M", KEY) == payload
    with pytest.raises(ArchiveError, match="anahtar bu oyuna ait değil"):
        m2.decode(blob, "baska_ad.psb.m", KEY)


def test_mdf_replace_keeps_original_bytes_when_unchanged() -> None:
    payload = b"veri" * 100
    # Oyunun kendi sıkıştırıcısı bizimkinden farklı bayt üretebilir; değişmeyen dosya aynen kalmalı.
    packed = zlib.compress(payload, 1)
    blob = m2.MAGIC + struct.pack("<I", len(payload)) + m2._xor(packed, m2.key_stream(KEY, "a.bin.m"))
    assert m2.replace(blob, "a.bin.m", KEY, lambda b: b) is blob
    changed = m2.replace(blob, "a.bin.m", KEY, lambda b: b + b"!")
    assert m2.decode(changed, "a.bin.m", KEY) == payload + b"!"


def test_mdf_rejects_corrupt() -> None:
    with pytest.raises(ArchiveError, match="imzası yok"):
        m2.decode(b"mdx\0" + b"\0" * 8, "a.m", KEY)
    blob = m2.encode(b"abc", "a.m", KEY)
    with pytest.raises(ArchiveError, match="uyuşmuyor"):
        m2.decode(blob[:4] + struct.pack("<I", 2) + blob[8:], "a.m", KEY)
    with pytest.raises(ArchiveError, match="çok büyük"):
        m2.decode(blob[:4] + struct.pack("<I", 1 << 31) + blob[8:], "a.m", KEY)


def test_find_key_from_game_code() -> None:
    index, _ = build_m2_archive(KEY, "alldata.psb.m", {"a.txt": b"x"})
    code = b"\0".join([b"nn::fs::MountRom", b"%s/%s.psb.m", KEY, b"archive", b"\x90" * 64])
    assert m2.find_key(code, "alldata.psb.m", index) == KEY
    assert m2.find_key(code.replace(KEY, b"BaskaDizge99"), "alldata.psb.m", index) is None
    assert m2.find_key(code, "alldata.psb.m", b"PSB\0") is None


def test_m2_archive_reads_members() -> None:
    text_psb = build_psb({"data": ["Merhaba", "Snake"]})
    members = {
        "087/config/title_menu_string.psb.m": text_psb,
        "system/roms/disc.BIN": b"\x00\xff" * 3000,
        "system/font/a.ttf.m": b"font",
    }
    index, data = build_m2_archive(KEY, "alldata.psb.m", members)
    arc = m2.M2Archive("alldata.psb.m", index, MemoryStorage(data), KEY)
    assert set(arc.entries) == set(members)
    assert all(e.offset % 2048 == 0 for e in arc.entries.values())
    for path, content in members.items():
        assert arc.read(path) == content
    assert arc.open("system/roms/disc.BIN").read_all() == members["system/roms/disc.BIN"]
    assert m2.is_mdf(arc.open("system/font/a.ttf.m").read(0, 4))
    assert psb.Psb(arc.read("087/config/title_menu_string.psb.m")).root() == {"data": ["Merhaba", "Snake"]}
    assert m2.M2Archive.data_name("dlc/dlc_usa.psb.m") == "dlc/dlc_usa.bin"
    with pytest.raises(ArchiveError, match="bulunamadı"):
        arc.read("yok.psb.m")
    with pytest.raises(ArchiveError, match="kadar büyük"):
        arc.read("system/roms/disc.BIN", max_size=10)


def test_m2_archive_rejects_bad_index() -> None:
    index, data = build_m2_archive(KEY, "alldata.psb.m", {"a.bin": b"x" * 10})
    with pytest.raises(ArchiveError, match="dışını gösteriyor"):
        m2.M2Archive("alldata.psb.m", index, MemoryStorage(data[:5]), KEY)
    not_index = m2.encode(build_psb({"id": "archive"}), "alldata.psb.m", KEY)
    with pytest.raises(ArchiveError, match="file_info yok"):
        m2.M2Archive("alldata.psb.m", not_index, MemoryStorage(data), KEY)
    with pytest.raises(ArchiveError, match="ile bitmeli"):
        m2.M2Archive.data_name("alldata.bin")


def test_nso_decompress() -> None:
    segs = (b"text" * 100, b"ro: TestAnahtar01\0" * 10, b"data" * 7)
    image = build_nso(segs, (True, True, False))
    assert nso.decompress(image) == b"".join(segs)
    with pytest.raises(ContainerError, match="imza"):
        nso.decompress(b"NSO1" + image[4:])
    with pytest.raises(ContainerError, match="dışında"):
        nso.decompress(image[:0x120])


def test_psb_int_array_kept_apart_from_int_list() -> None:
    tree: dict[str, PsbValue] = {"arr": IntArray([1, 2, 300]), "lst": [1, 2, 300]}
    root = psb.Psb(build_psb(tree)).root()
    assert isinstance(root, dict)
    assert isinstance(root["arr"], IntArray)
    assert not isinstance(root["lst"], IntArray)


@pytest.mark.parametrize("version", [2, 3, 4])
def test_psb_replace_root_unchanged_and_reencoded(version: int) -> None:
    tree: dict[str, PsbValue] = {**TREE, "spans": {"a.bin": [0, 70000], "b.bin": [2048, 5]}, "ids": IntArray([7, 8])}
    data = build_psb(tree, [b"\xbb" * 40], version, chunk_align=0x80)
    assert psb.replace_root(data, psb.Psb(data).root()) is data
    # aynı ağacı kodlayıcıdan geçirince (builder ile aynı kurallar) bayt bayt aynı çıkar
    doc = psb.Psb(data)
    forced = psb._rebuild(data, doc._h, psb._Encoder(doc.names, doc.strings).encode(doc.root(), 0), doc.strings)
    assert forced == data


@pytest.mark.parametrize("version", [2, 3, 4])
def test_psb_replace_root_removes_entry(version: int) -> None:
    tree: dict[str, PsbValue] = {
        "file_info": {"a.bin": [0, 10], "b.bin": [2048, -3], "c.bin": [4096, 1 << 33]},
        "id": "archive",
    }
    data = build_psb(tree, [b"\xcc" * 300], version, chunk_align=0x80)
    out = psb.replace_root(data, {"file_info": {"a.bin": [0, 10], "c.bin": [4096, 1 << 33]}, "id": "archive"})
    again = psb.Psb(out)
    assert again.root() == {"file_info": {"a.bin": [0, 10], "c.bin": [4096, 1 << 33]}, "id": "archive"}
    assert again.names == psb.Psb(data).names
    assert again.strings == psb.Psb(data).strings
    assert again.chunk(0) == b"\xcc" * 300
    assert struct.unpack_from("<I", out, 0x20)[0] % 0x80 == 0
    if version >= 3:
        assert struct.unpack_from("<I", out, 0x28)[0] == psb.checksum(out)


def test_psb_replace_root_rejects_new_names_and_strings() -> None:
    data = build_psb({"id": "archive", "n": 1})
    with pytest.raises(ArchiveError, match="yeni dizge"):
        psb.replace_root(data, {"id": "başka", "n": 1})
    with pytest.raises(ArchiveError, match="yeni ad"):
        psb.replace_root(data, {"id": "archive", "yeni": 1})


def test_m2_index_without_member() -> None:
    members = {"a/x.psb.m": build_psb({"t": "Merhaba"}), "b/y.bin": b"y" * 3000, "c/z.bin.m": b"z"}
    index, data = build_m2_archive(KEY, "alldata.psb.m", members)
    arc = m2.M2Archive("alldata.psb.m", index, MemoryStorage(data), KEY)
    assert arc.index_without(set()) is index
    new_index = arc.index_without({"a/x.psb.m"})
    smaller = m2.M2Archive("alldata.psb.m", new_index, MemoryStorage(data), KEY)
    assert set(smaller.entries) == {"b/y.bin", "c/z.bin.m"}
    assert smaller.entries["b/y.bin"] == arc.entries["b/y.bin"]
    assert smaller.read("c/z.bin.m") == b"z"
    with pytest.raises(ArchiveError, match="bulunamadı"):
        arc.index_without({"yok.bin"})
