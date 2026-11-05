"""Devil May Cry program kodundaki düşman açıklamaları: işaretçi kayıtlarını bulma, Türkçe yama ve IPS (sahte kod)."""

from __future__ import annotations

import json
import struct
from importlib import resources

import pytest

from nxceviri.core.formats.base import FormatError
from nxceviri.core.formats.dmc1 import codec, exe

RO_FILE, RO_MEM = 0x57F700, 0x580000
TEXTS = ["They are evil\nspirits.", "Wiggle the Left Stick.", "Shoot them."]


def _mem(offset: int) -> int:
    return RO_MEM + offset - RO_FILE


def _code() -> tuple[bytes, list[int]]:
    """`ro` bölümünde art arda üç metin ve onları gösteren üç ardışık RELATIVE kaydı olan sahte kod."""
    code = bytearray(RO_FILE + 0x4000)
    pos = RO_FILE + 0x1003  # metinler hizasız başlayabilir
    code[pos - 4 : pos] = b"\x7e\x0e\x00\x00"  # önceki dilin son metninin bitişi
    starts = []
    for text in TEXTS:
        data = codec.encode(codec.Message("", (), b"\x7e\x0e\x00\x00"), text)
        code[pos : pos + len(data)] = data
        starts.append(pos)
        pos += len(data)
    code[pos : pos + 4] = b"\x7e\x0e\x00\x00"  # sonraki dilin metni (dokunulmamalı)
    rela = RO_FILE + 0x200
    for k, start in enumerate([RO_FILE + 0x3000, *starts, pos]):
        info = 0x403 if k < 4 else 0x101  # dizinin sonundaki kayıt başka tür
        struct.pack_into("<QQQ", code, rela + 24 * k, 0x8AD000 + 8 * k, info, _mem(start))
    return bytes(code), starts


def _apply(code: bytes, records: list[tuple[int, bytes]]) -> bytes:
    out = bytearray(code)
    for offset, data in records:
        at = offset - 0x100 - RO_MEM + RO_FILE
        out[at : at + len(data)] = data
    return bytes(out)


def test_find_entries_and_patch_round_trip() -> None:
    code, starts = _code()
    entries = exe.find_entries(code, exe.digest(TEXTS[0]))
    assert [e.english for e in entries[:3]] == TEXTS
    turkish = ["Kötü\nruhlardır.", "Sol Çubuğu salla.", "Vur."]
    pairs = [(exe.digest(en), tr) for en, tr in zip(TEXTS, turkish, strict=True)]
    records = exe.build_patch(code, pairs)
    patched = _apply(code, records)
    found = [codec.decode(patched[s : patched.find(b"\x7e\x0e", s) + 4]).text for s in starts[:1]]
    assert found == ["Kötü\nruhlardır."]
    # her kaydın yeni adresi Türkçe metne gider
    texts = []
    for k in range(3):
        addend = struct.unpack_from("<Q", patched, RO_FILE + 0x200 + 24 * (k + 1) + 16)[0]
        at = addend - RO_MEM + RO_FILE
        texts.append(codec.decode(patched[at : patched.find(b"\x7e\x0e", at) + 4]).text)
    assert texts == [tr for _en, tr in pairs]
    region_end = starts[-1] + len(codec.encode(codec.Message("", (), b"\x7e\x0e\x00\x00"), TEXTS[2]))
    assert patched[region_end:] == code[region_end:]  # bölge dışı aynen kalır


def test_too_long_or_wrong_version_is_refused() -> None:
    code, _starts = _code()
    with pytest.raises(FormatError):
        exe.build_patch(
            code, [(exe.digest(TEXTS[0]), "çok " * 40), (exe.digest(TEXTS[1]), "a"), (exe.digest(TEXTS[2]), "b")]
        )
    with pytest.raises(FormatError):
        exe.build_patch(code, [(exe.digest(TEXTS[0]), "a"), (exe.digest("Different text"), "b")])
    with pytest.raises(FormatError):
        exe.find_entries(code, exe.digest("Not in the code"))


def test_ips_format_and_bundled_translations() -> None:
    blob = exe.ips([(0x100, b"ab"), (0x200, b"x" * 0x10000)])
    assert blob.startswith(b"IPS32")
    assert blob.endswith(b"EEOF")
    assert struct.unpack_from(">IH", blob, 5) == (0x100, 2)
    assert len(blob) == 5 + 6 + 2 + 6 + 0xFFFF + 6 + 1 + 4  # 64 KB'tan uzun kayıt bölünür
    pairs = exe.translations()
    assert len(pairs) == 147
    assert all(len(digest) == 64 and tr for digest, tr in pairs)


def test_bundled_translations_hold_no_original_text() -> None:
    raw = (resources.files("nxceviri") / "assets" / "dmc1" / "dusman_aciklamalari.json").read_text(encoding="utf-8")
    assert all(set(row) == {"sha256", "tr"} for row in json.loads(raw))


def test_digest_normalizes_line_endings_and_trailing_spaces() -> None:
    base = exe.digest("They are evil\nspirits.")
    assert exe.digest("They are evil\r\nspirits.") == base
    assert exe.digest("They are evil \nspirits.  \n") == base
    assert exe.digest("They are evil\nspirit.") != base
    assert len(base) == 64


def test_find_entries_matches_by_digest_only_when_text_equal() -> None:
    code, starts = _code()
    entries = exe.find_entries(code, exe.digest("They are evil \r\nspirits."))
    assert entries[0].start == starts[0]
    with pytest.raises(FormatError):
        exe.find_entries(code, exe.digest("They are evil spirits."))
