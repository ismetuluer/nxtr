"""Switch `.zs` font kapsayıcısı ve CID anahtarlı CFF yaması.

Kapsayıcı: zstd → 8 baytlık başlık → 4 baytlık XOR anahtarı → sfnt. Testlerdeki fontlar
FontBuilder ile üretilir; CID fontta glif adları `cidNNNNN`, `FDSelect` ve `vmtx` tabloları
gerçek oyun fontlarındaki gibi doldurulur.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
import zstandard as zstd
from fontTools.cffLib import FDArrayIndex, FDSelect, FontDict
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from nxceviri.core.fontpatch import switchfont, ttf

UPM = 1000
LETTERS = "\u0130\u015f\u015e\u011f\u011e"  # İ ş Ş ğ Ğ
ALL = ttf.PATCHABLE  # varsayılan yama kümesi: ı İ ş Ş ğ Ğ
HEADER = bytes.fromhex("d99b871a11223344")
KEY = bytes.fromhex("a6018502")

#: harf → (genişlik, dikdörtgenler); i'nin noktası ayrı bir dikdörtgendir
RECTS: dict[str, tuple[int, list[tuple[int, int, int, int]]]] = {
    "I": (260, [(50, 0, 150, 700)]),
    "i": (200, [(50, 0, 130, 500), (40, 560, 140, 660)]),
    "s": (480, [(30, 0, 430, 500)]),
    "S": (560, [(30, 0, 500, 700)]),
    "g": (480, [(30, -200, 430, 500)]),
    "G": (600, [(30, 0, 550, 700)]),
    "x": (500, [(20, 0, 450, 500)]),
    ".": (140, [(20, 0, 120, 100)]),
    ",": (140, [(20, -150, 120, 100)]),
}


def _draw(pen: object, rects: list[tuple[int, int, int, int]]) -> None:
    for x0, y0, x1, y1 in rects:
        pen.moveTo((x0, y0))  # type: ignore[attr-defined]
        pen.lineTo((x0, y1))  # type: ignore[attr-defined]
        pen.lineTo((x1, y1))  # type: ignore[attr-defined]
        pen.lineTo((x1, y0))  # type: ignore[attr-defined]
        pen.closePath()  # type: ignore[attr-defined]


def make_font(glyf: bool = True) -> bytes:
    """Türkçe harfleri içermeyen küçük bir font (glyf ya da CFF)."""
    order = [".notdef", "space", *RECTS]
    cmap = {32: "space", **{ord(ch): ch for ch in RECTS}}
    metrics = {".notdef": (500, 0), "space": (250, 0)}
    for ch, (width, rects) in RECTS.items():
        metrics[ch] = (width, rects[0][0] if rects else 0)

    fb = FontBuilder(UPM, isTTF=glyf)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    if glyf:
        glyphs = {}
        for name in order:
            pen = TTGlyphPen(None)
            _draw(pen, RECTS.get(name, (250, []))[1])
            glyphs[name] = pen.glyph()
        fb.setupGlyf(glyphs)
    else:
        charstrings = {}
        for name in order:
            pen = T2CharStringPen(metrics[name][0], None)
            _draw(pen, RECTS.get(name, (250, []))[1])
            charstrings[name] = pen.getCharString()
        fb.setupCFF("TestFont", {"FullName": "TestFont"}, charstrings, {"defaultWidthX": 0, "nominalWidthX": 0})
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "TestFont", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    out = io.BytesIO()
    fb.font.save(out)
    return out.getvalue()


def make_cid_font() -> bytes:
    """Aynı fontun CID anahtarlı CFF sürümü: charset `cidNNNNN`, FDArray/FDSelect dolu."""
    font = TTFont(io.BytesIO(make_font(glyf=False)))
    # Tembel açılan tablolar glif sırasından ad üretir: yeniden adlandırmadan ÖNCE yüklenmeli.
    hmtx = font["hmtx"]
    metrics = dict(hmtx.metrics)
    cmap_tables = list(font["cmap"].tables)
    for table in cmap_tables:
        table.cmap = dict(table.cmap)
    cff = font["CFF "].cff
    top = cff.topDictIndex[0]
    fd = FontDict()
    fd.Private = top.Private
    fdarray = FDArrayIndex()
    fdarray.append(fd)
    top.FDArray = fdarray
    select = FDSelect()
    select.format = 0
    select.gidArray = [0] * len(top.charset)
    top.FDSelect = select
    top.ROS = ("Adobe", "Identity", 0)
    top.CIDCount = len(top.charset)
    if hasattr(top, "Private"):
        del top.Private
    top.rawDict.pop("Private", None)
    # CharStrings tembel açılır: yeniden adlandırmadan ÖNCE yüklenmeli, yoksa anahtarlar yeni adlarla gelir.
    chars = top.CharStrings
    charstrings = list(chars.charStrings.items())
    mapping = {name: (".notdef" if i == 0 else f"cid{i:05d}") for i, name in enumerate(top.charset)}
    top.charset = [mapping[name] for name in top.charset]
    chars.charStrings = {mapping[k]: v for k, v in charstrings}
    font.setGlyphOrder(list(top.charset))
    hmtx.metrics = {mapping[k]: v for k, v in metrics.items()}
    for table in cmap_tables:
        table.cmap = {cp: mapping.get(name, name) for cp, name in table.cmap.items()}
    if getattr(font["post"], "glyphOrder", None):
        font["post"].glyphOrder = [mapping.get(name, name) for name in font["post"].glyphOrder]
    out = io.BytesIO()
    font.save(out)
    font.close()
    return out.getvalue()


def wrap(sfnt: bytes, header: bytes = HEADER, key: bytes = KEY) -> bytes:
    payload = bytes(b ^ key[i % 4] for i, b in enumerate(sfnt))
    return zstd.ZstdCompressor().compress(header + payload)


def outlines(data: bytes) -> dict[str, tuple[float, float, float, float] | None]:
    font = TTFont(io.BytesIO(data))
    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()
    result: dict[str, tuple[float, float, float, float] | None] = {}
    for letter in ALL:
        name = cmap.get(ord(letter))
        if name is None:
            result[letter] = None
            continue
        pen = BoundsPen(glyph_set)
        glyph_set[name].draw(pen)
        result[letter] = pen.bounds
    font.close()
    return result


def test_unwrap_roundtrip() -> None:
    sfnt = make_font()
    header, unpacked, key = switchfont.unwrap(wrap(sfnt))
    assert header == HEADER
    assert key == KEY
    assert unpacked == sfnt
    assert switchfont.unwrap(switchfont.wrap(header, unpacked, key))[1] == sfnt


def test_glyf_font_gets_turkish_letters() -> None:
    sfnt = make_font()
    result = switchfont.patch_font(wrap(sfnt))

    assert result.added == ALL
    assert result.skipped == {}
    assert result.data != wrap(sfnt)

    header, patched, key = switchfont.unwrap(result.data)
    assert (header, key) == (HEADER, KEY)
    bounds = outlines(patched)
    assert all(bounds[letter] is not None for letter in ALL), bounds


def test_cid_cff_font_gets_turkish_letters() -> None:
    sfnt = make_cid_font()
    result = switchfont.patch_font(wrap(sfnt))

    assert result.added == ALL
    _header, patched, _key = switchfont.unwrap(result.data)
    font = TTFont(io.BytesIO(patched))
    top = font["CFF "].cff.topDictIndex[0]

    cmap = font.getBestCmap()
    new_cids = [cmap[ord(letter)] for letter in ALL]
    assert all(name.startswith("cid") for name in new_cids), new_cids
    assert len(set(new_cids)) == len(ALL)
    # charset, FDSelect ve metrik tabloları yeni glifleri kapsar
    assert all(name in top.charset for name in new_cids)
    assert len(top.FDSelect.gidArray) == len(top.charset)
    assert all(name in font["hmtx"].metrics for name in new_cids)
    assert "vmtx" not in font or all(name in font["vmtx"].metrics for name in new_cids)
    bounds = outlines(patched)
    assert all(bounds[letter] is not None for letter in ALL), bounds
    font.close()


def test_second_patch_returns_original_bytes() -> None:
    once = switchfont.patch_font(wrap(make_font()))
    twice = switchfont.patch_font(once.data)

    assert twice.added == ""
    assert twice.data == once.data


def test_broken_container_raises() -> None:
    with pytest.raises(ValueError, match="zstd"):
        switchfont.unwrap(b"bu bir font degil")


def test_patch_file_writes_destination(tmp_path: Path) -> None:
    src = tmp_path / "font.bfotf.zs"
    src.write_bytes(wrap(make_cid_font()))
    dest = tmp_path / "out" / "font.bfotf.zs"

    result = switchfont.patch_file(src, dest)

    assert result.added == ALL
    assert dest.read_bytes() == result.data
    assert switchfont.unwrap(dest.read_bytes())[1] != switchfont.unwrap(src.read_bytes())[1]


def test_new_glyph_order_does_not_corrupt_charset() -> None:
    """CFF'te glif sırası charset listesiyle aynı nesne olabilir; yeni adlar karışmamalı."""
    sfnt = make_cid_font()
    _header, patched, _key = switchfont.unwrap(switchfont.patch_font(wrap(sfnt)).data)
    font = TTFont(io.BytesIO(patched))
    top = font["CFF "].cff.topDictIndex[0]
    assert all(name.startswith("cid") or name == ".notdef" for name in top.charset)
    assert font.getGlyphOrder() == list(top.charset)
    font.close()


def test_plan_skips_cjk_fonts_unless_allowed() -> None:
    """Varsayılan davranış korunur: CJK yoğun fonta Latin harfleri eklenmez."""
    font = TTFont(io.BytesIO(make_cid_font()))
    cmap = font["cmap"].tables[0].cmap
    placeholder = font.getBestCmap()[ord("x")]
    for cp in range(0x4E00, 0x4E00 + 250):
        cmap[cp] = placeholder
    data = _serialize(font)
    font.close()

    assert ttf.plan(data, LETTERS) == ("", {})
    assert ttf.plan(data, ALL, allow_cjk=True)[0] == ALL


def _serialize(font: TTFont) -> bytes:
    out = io.BytesIO()
    font.save(out)
    return out.getvalue()
