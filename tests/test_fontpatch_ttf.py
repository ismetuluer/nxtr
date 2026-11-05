"""Vektör (TrueType / CFF) font yaması: elle üretilmiş fontlarda ı İ ş Ş ğ Ğ eklenir."""

from __future__ import annotations

import io
from collections.abc import Callable

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

from nxceviri.core.fontpatch import ttf

UPM = 1000
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


def make_font(glyf: bool = True, drop: str = "", merged_dot: bool = False) -> bytes:
    """`drop`: fontta olmayacak harfler. `merged_dot`: i'nin noktası gövdeyle tek konturda."""
    specs = {k: v for k, v in RECTS.items() if k not in drop}
    if merged_dot and "i" in specs:
        specs["i"] = (200, [(50, 0, 130, 660)])
    order = [".notdef", "space", *[{".": "period", ",": "comma"}.get(ch, ch) for ch in specs]]
    cmap = {32: "space", **{ord(ch): {".": "period", ",": "comma"}.get(ch, ch) for ch in specs}}
    metrics = {".notdef": (500, 0), "space": (250, 0)}
    drawn: dict[str, list[tuple[int, int, int, int]]] = {".notdef": [], "space": []}
    for ch, (width, rects) in specs.items():
        name = {".": "period", ",": "comma"}.get(ch, ch)
        metrics[name] = (width, min(r[0] for r in rects))
        drawn[name] = rects
    fb = FontBuilder(UPM, isTTF=glyf)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    if glyf:
        glyphs = {}
        for name in order:
            pen = TTGlyphPen(None)
            _draw(pen, drawn[name])
            glyphs[name] = pen.glyph()
        fb.setupGlyf(glyphs)
    else:
        charstrings = {}
        for name in order:
            pen = T2CharStringPen(metrics[name][0], None)
            _draw(pen, drawn[name])
            charstrings[name] = pen.getCharString()
        fb.setupCFF("Test", {"FullName": "Test"}, charstrings, {})
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    out = io.BytesIO()
    fb.save(out)
    return out.getvalue()


def bounds_of(data: bytes, ch: str) -> tuple[float, float, float, float] | None:
    font = TTFont(io.BytesIO(data))
    name = font.getBestCmap()[ord(ch)]
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[name].draw(pen)
    bounds: tuple[float, float, float, float] | None = pen.bounds
    return bounds


def advance_of(data: bytes, ch: str) -> int:
    font = TTFont(io.BytesIO(data))
    return int(font["hmtx"][font.getBestCmap()[ord(ch)]][0])


@pytest.fixture(params=[True, False], ids=["glyf", "cff"])
def is_glyf(request: pytest.FixtureRequest) -> bool:
    return bool(request.param)


def test_plan_lists_every_derivable_letter(is_glyf: bool) -> None:
    addable, skipped = ttf.plan(make_font(is_glyf))
    assert (addable, skipped) == (ttf.PATCHABLE, {})


def test_adds_all_six_letters_with_expected_shapes(is_glyf: bool) -> None:
    data = make_font(is_glyf)
    result = ttf.patch_font(data)
    assert result.added == ttf.PATCHABLE
    out = result.data
    cmap = TTFont(io.BytesIO(out)).getBestCmap()
    assert all(ord(c) in cmap for c in ttf.PATCHABLE)
    # ı: i'nin gövdesi, nokta yok
    assert bounds_of(out, "ı") == (50, 0, 130, 500)
    assert advance_of(out, "ı") == 200
    # İ: I + üstte nokta (büyük harf yüksekliğinin üstünde, ortada)
    dotted = bounds_of(out, "İ")
    assert dotted is not None
    assert dotted[3] > 700 + 50
    assert dotted[0] == 50
    assert advance_of(out, "İ") == 260
    # ş / Ş: taban çizgisinin altına inen cedilla; üst kenar aynı
    for plain, cedilla in (("s", "ş"), ("S", "Ş")):
        base, patched = bounds_of(out, plain), bounds_of(out, cedilla)
        assert base is not None
        assert patched is not None
        assert patched[1] < base[1] - 100
        assert patched[3] == base[3]
        assert advance_of(out, cedilla) == advance_of(out, plain)
    # ğ / Ğ: üstte breve; alt kenar aynı
    for plain, breve in (("g", "ğ"), ("G", "Ğ")):
        base, patched = bounds_of(out, plain), bounds_of(out, breve)
        assert base is not None
        assert patched is not None
        assert patched[3] > base[3] + 50
        assert patched[1] == base[1]
        assert advance_of(out, breve) == advance_of(out, plain)


def test_existing_glyphs_keep_their_numbers_and_outlines(is_glyf: bool) -> None:
    data = make_font(is_glyf)
    before = TTFont(io.BytesIO(data))
    after = TTFont(io.BytesIO(ttf.patch_font(data).data))
    old_order = before.getGlyphOrder()
    assert after.getGlyphOrder()[: len(old_order)] == old_order  # TextMeshPro'nun glif numaraları kayamaz
    assert len(after.getGlyphOrder()) == len(old_order) + 6
    assert after["maxp"].numGlyphs == len(old_order) + 6
    for ch in "iIsSgGx.,":
        assert bounds_of(ttf.patch_font(data).data, ch) == bounds_of(data, ch)


def test_dot_fused_into_the_stem_falls_back_to_a_shortened_capital_i(is_glyf: bool) -> None:
    out = ttf.patch_font(make_font(is_glyf, merged_dot=True)).data
    dotless = bounds_of(out, "ı")
    assert dotless is not None
    assert dotless[1] == 0
    assert dotless[3] == pytest.approx(500, abs=1)  # x-yüksekliği (x harfinin üstü)
    assert dotless[2] - dotless[0] <= 200


def test_letter_without_base_glyph_is_reported_not_invented(is_glyf: bool) -> None:
    data = make_font(is_glyf, drop="gG")
    result = ttf.patch_font(data)
    assert result.added == "ıİşŞ"
    assert result.skipped == {"ğ": f"{ttf.NO_BASE_LETTER} (g)", "Ğ": f"{ttf.NO_BASE_LETTER} (G)"}
    assert ord("ğ") not in TTFont(io.BytesIO(result.data)).getBestCmap()


def test_font_without_period_and_comma_gets_drawn_marks(is_glyf: bool) -> None:
    out = ttf.patch_font(make_font(is_glyf, drop=".,")).data
    for ch in "İşğ":
        assert bounds_of(out, ch) is not None
    cedilla = bounds_of(out, "ş")
    assert cedilla is not None
    assert cedilla[1] < 0


def test_only_missing_letters_are_added(is_glyf: bool) -> None:
    once = ttf.patch_font(make_font(is_glyf))
    again = ttf.patch_font(once.data)
    assert again.added == ""
    assert again.data == once.data  # değişmediyse özgün baytlar
    partial = ttf.patch_font(make_font(is_glyf), "ış")
    assert partial.added == "ış"
    assert ord("ğ") not in TTFont(io.BytesIO(partial.data)).getBestCmap()


@pytest.mark.parametrize("make", [lambda: b"", lambda: b"not a font" * 20, lambda: b"\x00\x01\x00\x00" + b"\xff" * 40])
def test_unreadable_fonts_are_left_alone(make: Callable[[], bytes]) -> None:
    data = make()
    result = ttf.patch_font(data)
    assert result.data == data
    assert result.added == ""
    assert set(result.skipped) == set(ttf.PATCHABLE)
    assert ttf.plan(data) == ("", result.skipped)


def test_patched_font_is_usable_by_a_real_text_renderer(is_glyf: bool) -> None:
    from PIL import Image, ImageDraw, ImageFont

    out = ttf.patch_font(make_font(is_glyf)).data

    def ink(ch: str) -> tuple[int, int, int, int] | None:
        img = Image.new("L", (400, 400), 0)
        ImageDraw.Draw(img).text((100, 300), ch, font=ImageFont.truetype(io.BytesIO(out), 100), fill=255, anchor="ls")
        return img.getbbox()

    for ch in ttf.PATCHABLE:
        assert ink(ch) is not None, ch
    plain, breve = ink("g"), ink("ğ")
    assert plain is not None
    assert breve is not None
    assert breve[1] < plain[1] - 5  # breve harfin üstüne çıkıyor


def test_cjk_fonts_are_language_specific_and_silently_skipped(is_glyf: bool) -> None:
    font = TTFont(io.BytesIO(make_font(is_glyf)))
    for table in font["cmap"].tables:
        table.cmap.update({0x4E00 + i: "x" for i in range(ttf._CJK_MIN_CHARS)})
    out = io.BytesIO()
    font.save(out)
    assert ttf.is_cjk_chars(range(0x4E00, 0x4E00 + ttf._CJK_MIN_CHARS))
    assert not ttf.is_cjk_chars(range(0x20, 0x250))
    assert ttf.plan(out.getvalue()) == ("", {})
    assert ttf.patch_font(out.getvalue()).data == out.getvalue()
