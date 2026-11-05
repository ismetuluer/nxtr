"""SARC / Yaz0 / ZSTD okuyucuları."""

from __future__ import annotations

import struct

import pytest
import zstandard

from nxceviri.core.archives import sarc, yaz0, zstd
from nxceviri.core.errors import ArchiveError
from tests.nxbuild import build_sarc, yaz0_literal


def test_yaz0_literal() -> None:
    payload = "Türkçe metin ğüşıöç".encode() * 3
    assert yaz0.decompress(yaz0_literal(payload), 1 << 20) == payload


def test_yaz0_backreference() -> None:
    # "abc" düz, ardından mesafe 3 uzunluk 6 geri başvuru → "abcabcabc"; sonra uzun başvuru (0x12+).
    body = bytes([0b11100000]) + b"abc" + bytes([0x40, 0x02]) + bytes([0x00, 0x08, 0x00])
    data = b"Yaz0" + struct.pack(">I", 9 + 0x12) + b"\0" * 8 + body
    out = yaz0.decompress(data, 1 << 20)
    assert out[:9] == b"abcabcabc"
    assert out[9:] == (b"abcabcabc" * 3)[:0x12]


@pytest.mark.parametrize(
    "data",
    [b"Yaz1" + b"\0" * 12, b"Yaz0" + struct.pack(">I", 100) + b"\0" * 8 + b"\xff" + b"ab"],
)
def test_yaz0_corrupt(data: bytes) -> None:
    with pytest.raises(ArchiveError):
        yaz0.decompress(data, 1 << 20)


def test_yaz0_invalid_backreference() -> None:
    data = b"Yaz0" + struct.pack(">I", 10) + b"\0" * 8 + b"\x00" + b"\x40\x10"
    with pytest.raises(ArchiveError, match="geri başvuru"):
        yaz0.decompress(data, 1 << 20)


def test_yaz0_size_limit() -> None:
    with pytest.raises(ArchiveError, match="büyük"):
        yaz0.decompress(yaz0_literal(b"x" * 100), 50)


@pytest.mark.parametrize("big_endian", [False, True])
def test_sarc_parse(big_endian: bool) -> None:
    files = {"Msg/ana.msbt": b"MsgStdBn" + b"\0" * 8, "Msg/ğ.txt": "çğı".encode(), "z": b""}
    entries = sarc.parse(build_sarc(files, big_endian))
    assert {e.name: e.data for e in entries} == files


def test_sarc_corrupt() -> None:
    good = build_sarc({"a": b"1"})
    with pytest.raises(ArchiveError):
        sarc.parse(b"SARC" + b"\0" * 4)
    with pytest.raises(ArchiveError, match="SFAT"):
        sarc.parse(good[:0x14] + b"XXXX" + good[0x18:])
    with pytest.raises(ArchiveError, match="dışına"):
        sarc.parse(good[:-8])


def test_zstd() -> None:
    payload = b"metin " * 1000
    assert zstd.decompress(zstandard.ZstdCompressor().compress(payload), 1 << 20) == payload
    with pytest.raises(ArchiveError, match="büyük"):
        zstd.decompress(zstandard.ZstdCompressor().compress(payload), 100)
    with pytest.raises(ArchiveError):
        zstd.decompress(zstd.MAGIC + b"\x00\x00bozuk veri", 1 << 20)


def test_sarc_build_is_byte_identical() -> None:
    for big_endian in (False, True):
        data = build_sarc({"a.msbt": b"MsgStdBn" + b"\0" * 30, "b/c.bin": b"\x01" * 13, "d": b""}, big_endian)
        assert sarc.build(sarc.read(data)) == data


def test_sarc_replace_keeps_alignment_and_other_files() -> None:
    files = {"Msg/a.msbt": b"A" * 10, "Msg/b.msbt": b"B" * 20, "z.bin": b"Z" * 7}
    arc = sarc.read(build_sarc(files))
    arc.replace("Msg/a.msbt", b"yeni ve daha uzun veri " * 3)
    out = sarc.build(arc)
    again = {e.name: e.data for e in sarc.parse(out)}
    assert again == {**files, "Msg/a.msbt": b"yeni ve daha uzun veri " * 3}
    rearc = sarc.read(out)
    assert all(n.alignment >= 8 for n in rearc.nodes)
    with pytest.raises(ArchiveError, match="bulunamadı"):
        arc.replace("yok", b"")


@pytest.mark.parametrize(
    "payload",
    [b"", b"a", b"abcabcabc" * 200, bytes(range(256)) * 40, "Türkçe metin ğüşıöç ".encode() * 300],
)
def test_yaz0_compress_round_trip(payload: bytes) -> None:
    packed = yaz0.compress(payload, alignment=0x80)
    assert yaz0.header_alignment(packed) == 0x80
    assert yaz0.decompress(packed, 1 << 24) == payload


def test_zstd_compress_round_trip() -> None:
    payload = b"metin " * 5000
    assert zstd.decompress(zstd.compress(payload), 1 << 24) == payload


def test_nested_open_and_replace() -> None:
    from nxceviri.core.archives import nested

    inner = build_sarc({"Msg/a.msbt": b"eski", "Msg/b.msbt": b"dokunulmaz"})
    outer_zs = zstd.compress(inner)
    outer_yaz = yaz0_literal(build_sarc({"pack.sarc": inner}))
    assert nested.open_inner(outer_zs, ["pack.sarc", "Msg/a.msbt"]) == b"eski"
    assert nested.open_inner(outer_yaz, ["pack", "pack.sarc", "Msg/b.msbt"]) == b"dokunulmaz"

    new_zs = nested.replace_inner(outer_zs, ["pack.sarc", "Msg/a.msbt"], lambda _old: b"yeni")
    assert nested.open_inner(new_zs, ["pack.sarc", "Msg/a.msbt"]) == b"yeni"
    assert nested.open_inner(new_zs, ["pack.sarc", "Msg/b.msbt"]) == b"dokunulmaz"
    new_yaz = nested.replace_inner(outer_yaz, ["pack", "pack.sarc", "Msg/a.msbt"], lambda _old: b"yeni")
    assert new_yaz.startswith(b"Yaz0")
    assert nested.open_inner(new_yaz, ["pack", "pack.sarc", "Msg/a.msbt"]) == b"yeni"
    # Değişiklik yoksa arşivler yeniden sıkıştırılmaz: bayt bayt aynı.
    assert nested.replace_inner(outer_yaz, ["pack", "pack.sarc", "Msg/a.msbt"], lambda old: old) == outer_yaz
    with pytest.raises(ArchiveError):
        nested.open_inner(b"duz veri", ["x"])
