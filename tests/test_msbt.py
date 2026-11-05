"""MSBT eklentisi: çıkarma, geri yazma ve zorunlu round-trip testleri."""

from __future__ import annotations

import struct

import pytest

from nxceviri.core.formats.base import FormatError
from nxceviri.core.formats.msbt import MsbtPlugin
from nxceviri.core.formats.msbt.msbt import read
from tests.nxbuild import MsbtSegment, build_msbt

PLUGIN = MsbtPlugin()

COLOR_RED = ("tag", 0, 3, b"\x00\x00")
COLOR_END = ("end", 0, 3, b"")
PLAYER = ("tag", 2, 1, b"\x02\x00\x41\x00")
PAGE = ("tag", 0, 4, b"")

TEXTS: list[tuple[str, list[MsbtSegment]]] = [
    ("Menu_Start", ["Start Game"]),
    ("Talk_Hello", ["Hello, ", PLAYER, "!\nWelcome to ", COLOR_RED, "Hyrule", COLOR_END, "."]),
    ("Talk_Page", ["First page", PAGE, "Second page"]),
    ("Empty", []),
    ("Unicode", ["Çok güzel şey — ığİöü ✓"]),
]


def _variants() -> list[bytes]:
    return [
        build_msbt(TEXTS),
        build_msbt(TEXTS, endian=">"),
        build_msbt(TEXTS, encoding=0),
        build_msbt(TEXTS, labels=False),
        build_msbt(TEXTS, extra_sections=False, pad_last=False),
        build_msbt(TEXTS, tail=b"\x00\x00"),
    ]


def test_extract_entries_and_codes() -> None:
    entries = PLUGIN.extract(build_msbt(TEXTS))
    by_key = {e.key: e for e in entries}
    assert [e.key for e in entries] == [k for k, _ in TEXTS]
    talk = by_key["Talk_Hello"]
    assert talk.source == "Hello, ⟦1⟧!\nWelcome to ⟦2⟧Hyrule⟦3⟧."
    assert [c.label for c in talk.codes] == ["Oyun etiketi 2:1", "Renk", "Etiket sonu (0:3)"]
    assert by_key["Talk_Page"].codes[0].label == "Sayfa sonu"
    assert by_key["Empty"].source == ""
    assert by_key["Unicode"].source == "Çok güzel şey — ığİöü ✓"


def test_detect() -> None:
    assert PLUGIN.detect("a.msbt", build_msbt(TEXTS)[:64])
    assert not PLUGIN.detect("a.msbt", b"MsgPrjBn")


@pytest.mark.parametrize("data", _variants())
def test_round_trip_is_byte_identical(data: bytes) -> None:
    """Zorunlu test: değişiklik yapmadan extract → inject çıktısı orijinalle bayt bayt aynı."""
    entries = PLUGIN.extract(data)
    assert PLUGIN.inject(data, {e.key: e.source for e in entries}) == data
    assert PLUGIN.inject(data, {}) == data


@pytest.mark.parametrize("data", _variants())
def test_inject_translation(data: bytes) -> None:
    out = PLUGIN.inject(
        data,
        {
            "Talk_Hello": "Merhaba ⟦1⟧!\n⟦2⟧Hyrule⟦3⟧'a hoş geldin.",
            "Menu_Start": "Oyuna Başla",
            "Empty": "Artık boş değil: ğüşİöçı",
        }
        if read(data).labels
        else {"#1": "Merhaba ⟦1⟧!\n⟦2⟧Hyrule⟦3⟧'a hoş geldin.", "#0": "Oyuna Başla", "#3": "Artık boş değil: ğüşİöçı"},
    )
    entries = {e.index: e for e in PLUGIN.extract(out)}
    assert entries[0].source == "Oyuna Başla"
    assert entries[1].source == "Merhaba ⟦1⟧!\n⟦2⟧Hyrule⟦3⟧'a hoş geldin."
    assert entries[1].codes == PLUGIN.extract(data)[1].codes  # kodlar bayt bayt korunur
    assert entries[2].source == "First page⟦1⟧Second page"  # dokunulmayan girdi aynı
    assert entries[3].source == "Artık boş değil: ğüşİöçı"
    # Diğer bölümler değişmez, dosya boyutu alanı güncel.
    before, after = read(data), read(out)
    for a, b in zip(before.sections, after.sections, strict=True):
        if a.magic != b"TXT2":
            assert a.data == b.data
    e = before.endian
    assert struct.unpack_from(e + "I", out, 0x12)[0] == len(out)
    assert len(out) % 16 == 0 or not after.sections[-1].trailing


@pytest.mark.parametrize(
    ("translation", "message"),
    [
        ("Merhaba!", "Eksik kontrol kodu"),
        ("Merhaba ⟦1⟧⟦2⟧⟦3⟧⟦4⟧", "olmayan kontrol kodu"),
        ("⟦2⟧Merhaba ⟦1⟧ ⟦3⟧", "sırası"),
        ("⟦1⟧ ⟦1⟧ ⟦2⟧⟦3⟧", "sayısı"),
        ("Merhaba ⟦1⟧ ⟦2⟧ ⟦3⟧ ⟦", "Yarım kalmış"),
    ],
)
def test_inject_rejects_broken_placeholders(translation: str, message: str) -> None:
    with pytest.raises(FormatError, match=message):
        PLUGIN.inject(build_msbt(TEXTS), {"Talk_Hello": translation})


def test_inject_unknown_key() -> None:
    with pytest.raises(FormatError, match="olmayan girdiler"):
        PLUGIN.inject(build_msbt(TEXTS), {"Yok": "x"})


def test_utf8_file_accepts_any_unicode() -> None:
    data = build_msbt(TEXTS, encoding=0)
    out = PLUGIN.inject(data, {"Menu_Start": "Ğüzel 😀"})
    assert PLUGIN.extract(out)[0].source == "Ğüzel 😀"


def test_corrupt_files() -> None:
    good = build_msbt(TEXTS)
    with pytest.raises(FormatError, match="MsgStdBn"):
        PLUGIN.extract(b"MsgPrjBn" + good[8:])
    with pytest.raises(FormatError):
        PLUGIN.extract(good[: len(good) // 2])
    bad_bom = good[:8] + b"\x00\x00" + good[10:]
    with pytest.raises(FormatError, match="bayt sırası"):
        PLUGIN.extract(bad_bom)
    bad_enc = good[:0x0C] + b"\x07" + good[0x0D:]
    with pytest.raises(FormatError, match="kodlaması"):
        PLUGIN.extract(bad_enc)
    # Yarım kalmış etiket: metnin sonunu 0x0E ile bitir.
    half = build_msbt([("a", ["x"])], extra_sections=False, labels=False)
    txt = half.index(b"TXT2") + 0x10
    broken = bytearray(half)
    struct.pack_into("<H", broken, txt + 8, 0x0E)
    struct.pack_into("<H", broken, txt + 10, 0)
    with pytest.raises(FormatError):
        PLUGIN.extract(bytes(broken))


def test_large_file_round_trip() -> None:
    texts: list[tuple[str, list[MsbtSegment]]] = [
        (f"Line_{i:05d}", [f"Metin {i} ", COLOR_RED, "renkli", COLOR_END]) for i in range(5000)
    ]
    data = build_msbt(texts)
    entries = PLUGIN.extract(data)
    assert len(entries) == 5000
    assert PLUGIN.inject(data, {e.key: e.source for e in entries}) == data
