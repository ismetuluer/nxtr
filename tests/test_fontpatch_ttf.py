"""Vektör (TrueType / CFF) font yaması: elle üretilmiş fontlarda ı İ ş Ş ğ Ğ eklenir."""

from __future__ import annotations

import io
from collections.abc import Callable

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._k_e_r_n import KernTable_format_0

from nxceviri.core.fontpatch import sources, ttf

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


Shape = tuple[int, int, int, int] | list[tuple[int, int]]  # dikdörtgen ya da çokgen


def _draw_shapes(pen: object, shapes: list[Shape]) -> None:
    for shape in shapes:
        if isinstance(shape, tuple):
            _draw(pen, [shape])
            continue
        pen.moveTo(shape[0])  # type: ignore[attr-defined]
        for point in shape[1:]:
            pen.lineTo(point)  # type: ignore[attr-defined]
        pen.closePath()  # type: ignore[attr-defined]


def glyph_name(ch: str) -> str:
    return {".": "period", ",": "comma"}.get(ch, ch if ch.isascii() else f"uni{ord(ch):04X}")


def make_font(
    glyf: bool = True,
    drop: str = "",
    merged_dot: bool = False,
    extra: dict[str, tuple[int, list[Shape]]] | None = None,
    ascent: int = 800,
    win_ascent: int | None = None,
    features: str = "",
    kern: dict[tuple[str, str], int] | None = None,
) -> bytes:
    """`drop`: fontta olmayacak harfler. `merged_dot`: i'nin noktası gövdeyle tek konturda.

    `extra`: eklenecek harfler (dikdörtgen ya da çokgen); `features`: feaLib ile derlenecek OpenType özellikleri;
    `kern`: eski `kern` tablosu (biçim 0) çiftleri (harflerle).
    """
    specs: dict[str, tuple[int, list[Shape]]] = {k: (v[0], list(v[1])) for k, v in RECTS.items() if k not in drop}
    if merged_dot and "i" in specs:
        specs["i"] = (200, [(50, 0, 130, 660)])
    specs.update(extra or {})
    order = [".notdef", "space", *[glyph_name(ch) for ch in specs]]
    cmap = {32: "space", **{ord(ch): glyph_name(ch) for ch in specs}}
    metrics = {".notdef": (500, 0), "space": (250, 0)}
    drawn: dict[str, list[Shape]] = {".notdef": [], "space": []}
    for ch, (width, shapes) in specs.items():
        name = glyph_name(ch)
        metrics[name] = (width, min(s[0] if isinstance(s, tuple) else min(p[0] for p in s) for s in shapes))
        drawn[name] = shapes
    fb = FontBuilder(UPM, isTTF=glyf)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    if glyf:
        glyphs = {}
        for name in order:
            pen = TTGlyphPen(None)
            _draw_shapes(pen, drawn[name])
            glyphs[name] = pen.glyph()
        fb.setupGlyf(glyphs)
    else:
        charstrings = {}
        for name in order:
            pen = T2CharStringPen(metrics[name][0], None)
            _draw_shapes(pen, drawn[name])
            charstrings[name] = pen.getCharString()
        fb.setupCFF("Test", {"FullName": "Test"}, charstrings, {})
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ascent, descent=-200)
    fb.setupNameTable({"familyName": "Test", "styleName": "Regular"})
    fb.setupOS2(**({"usWinAscent": win_ascent} if win_ascent is not None else {}))
    fb.setupPost()
    if features:
        fb.addOpenTypeFeatures(features)
    if kern:
        table = newTable("kern")
        table.version = 0
        sub = KernTable_format_0()
        sub.version, sub.format, sub.coverage, sub.tupleIndex = 0, 0, 1, None
        sub.kernTable = {(glyph_name(a), glyph_name(b)): v for (a, b), v in kern.items()}
        table.kernTables = [sub]
        fb.font["kern"] = table
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
    # i'nin noktası gövdeye kaynamış: İ için de nokta kaynağı kalmaz.
    result = ttf.patch_font(make_font(is_glyf, drop=".,", merged_dot=True))
    out = result.data
    for ch in "İşğ":
        assert bounds_of(out, ch) is not None
    cedilla = bounds_of(out, "ş")
    assert cedilla is not None
    assert cedilla[1] < 0
    assert {c: result.sources[c] for c in "İşŞğĞ"} == dict.fromkeys("İşŞğĞ", sources.DRAWN)
    assert result.sources["ı"] == sources.DOTLESS_FROM_CAPITAL


def contours_of(data: bytes, ch: str) -> list[list[tuple[float, float]]]:
    """Harfin konturları; her kontur noktalarının sıralı listesi (başlangıç noktası ve yönden bağımsız)."""
    font = TTFont(io.BytesIO(data))
    pen = DecomposingRecordingPen(font.getGlyphSet())
    font.getGlyphSet()[font.getBestCmap()[ord(ch)]].draw(pen)
    out: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for op, args in pen.value:
        if op in ("closePath", "endPath"):
            out.append(sorted(current))
            current = []
        else:
            current += [(float(x), float(y)) for x, y in args]
    return sorted(out)


def added_contours(data: bytes, letter: str, base: str) -> list[list[tuple[float, float]]]:
    base_contours = contours_of(data, base)
    return [c for c in contours_of(data, letter) if c not in base_contours]


def moved(shape: list[tuple[int, int]], dx: float, dy: float) -> list[list[tuple[float, float]]]:
    return [sorted((x + dx, y + dy) for x, y in shape)]


#: ç'nin ayırt edici, taban çizgisinin altına inen çengeli (gövdeye 20 birim girer).
HOOK = [(200, 20), (260, 20), (300, -120), (180, -210), (160, -180), (240, -110)]
#: ă'nın kavisi: x-yüksekliğinin üstünde, kendine özgü bir çokgen.
ARC = [(120, 560), (340, 560), (380, 700), (330, 640), (230, 600), (130, 650), (90, 700)]


def test_cedilla_is_the_hook_of_c_cedilla(is_glyf: bool) -> None:
    extra: dict[str, tuple[int, list[Shape]]] = {
        "ç": (480, [(30, 0, 430, 500), HOOK]),
        "s": (380, [(30, 0, 330, 500)]),
    }
    result = ttf.patch_font(make_font(is_glyf, extra=extra))
    assert result.sources["ş"] == "ç'nin çengeli"
    assert result.sources["Ş"] == "ç'nin çengeli"  # Ç yok: küçük harfin çengeli, ölçeklenmeden
    # Çengel kopyalanır, yalnızca yatayda taban harfe ortalanır (ç gövdesi 230, s 180, S 265).
    assert added_contours(result.data, "ş", "s") == moved(HOOK, -50, 0)
    assert added_contours(result.data, "Ş", "S") == moved(HOOK, 35, 0)


def test_capital_cedilla_prefers_capital_c_cedilla(is_glyf: bool) -> None:
    big_hook = [(x, y - 20) for x, y in HOOK]
    extra: dict[str, tuple[int, list[Shape]]] = {
        "ç": (480, [(30, 0, 430, 500), HOOK]),
        "Ç": (560, [(30, 0, 500, 700), big_hook]),
    }
    result = ttf.patch_font(make_font(is_glyf, extra=extra))
    assert result.sources["Ş"] == "Ç'nin çengeli"
    assert added_contours(result.data, "Ş", "S") == moved(big_hook, 0, 0)


def test_breve_comes_from_a_breve(is_glyf: bool) -> None:
    extra: dict[str, tuple[int, list[Shape]]] = {"ă": (480, [(30, 0, 430, 500), ARC])}
    result = ttf.patch_font(make_font(is_glyf, extra=extra))
    assert result.sources["ğ"] == "ă'nın kavisi"
    assert result.sources["Ğ"] == "ă'nın kavisi"
    # Kavis taban harfe ortalanır (kavis 235); ğ: aynı yükseklik (g ve a 500), Ğ: G'ye göre 200 yukarı.
    assert added_contours(result.data, "ğ", "g") == moved(ARC, -5, 0)
    assert added_contours(result.data, "Ğ", "G") == moved(ARC, 55, 200)


def test_spacing_breve_is_used_when_there_is_no_a_breve(is_glyf: bool) -> None:
    result = ttf.patch_font(make_font(is_glyf, extra={"˘": (300, [ARC])}))
    assert result.sources["ğ"] == "˘ işareti"
    assert added_contours(result.data, "ğ", "g") == moved(ARC, -5, 0)


def test_breve_without_any_source_is_drawn(is_glyf: bool) -> None:
    result = ttf.patch_font(make_font(is_glyf))
    assert result.sources == {
        "ı": "i'den nokta silindi",
        "İ": "i'nin noktası",
        "ş": "virgül",
        "Ş": "virgül",
        "ğ": sources.DRAWN,
        "Ğ": sources.DRAWN,
    }


def test_dot_of_z_dot_is_used_when_i_has_no_separate_dot(is_glyf: bool) -> None:
    dot = [(180, 560), (280, 560), (230, 680)]  # üçgen nokta
    result = ttf.patch_font(make_font(is_glyf, merged_dot=True, extra={"ż": (460, [(30, 0, 430, 500), dot])}))
    assert result.sources["İ"] == "ż'nin noktası"
    # Yatayda I'ya (orta 100) ortalanır; z'nin gövdesine uzaklığı I'nın üstünde korunur (700 - 500).
    assert added_contours(result.data, "İ", "I") == moved(dot, -130, 200)


def test_period_is_the_last_dot_source(is_glyf: bool) -> None:
    result = ttf.patch_font(make_font(is_glyf, merged_dot=True))
    assert result.sources["İ"] == "nokta işareti"


def test_new_glyphs_inherit_legacy_kern_pairs(is_glyf: bool) -> None:
    kern = {("s", "x"): -40, ("x", "s"): -30, ("I", "I"): 15, ("g", "s"): -10}
    font = TTFont(io.BytesIO(ttf.patch_font(make_font(is_glyf, kern=kern)).data))
    pairs = font["kern"].kernTables[0].kernTable
    cmap = font.getBestCmap()
    s, x, ii, g = (cmap[ord(c)] for c in "sxIg")
    sc, dotted_i, gb = (cmap[ord(c)] for c in "şİğ")
    assert pairs[(sc, x)] == -40
    assert pairs[(x, sc)] == -30
    assert pairs[(dotted_i, ii)] == pairs[(ii, dotted_i)] == pairs[(dotted_i, dotted_i)] == 15
    assert pairs[(gb, sc)] == pairs[(g, sc)] == pairs[(gb, s)] == -10  # yeni–yeni çiftleri de
    assert len(pairs) == 4 + 2 + 3 + 3


def _pair_value(font: TTFont, left: str, right: str) -> int | None:
    """GPOS'tan iki glif arasındaki XAdvance değeri (biçim 1 ve 2, Extension sarmalı dahil)."""
    cmap = font.getBestCmap()
    a, b = cmap[ord(left)], cmap[ord(right)]
    for lookup in font["GPOS"].table.LookupList.Lookup:
        for entry in lookup.SubTable:
            sub = entry.ExtSubTable if lookup.LookupType == 9 else entry
            if a not in sub.Coverage.glyphs:
                continue
            if sub.Format == 1:
                pair_set = sub.PairSet[sub.Coverage.glyphs.index(a)]
                for record in pair_set.PairValueRecord:
                    if record.SecondGlyph == b:
                        return int(record.Value1.XAdvance)
            else:
                c1, c2 = sub.ClassDef1.classDefs.get(a, 0), sub.ClassDef2.classDefs.get(b, 0)
                return int(sub.Class1Record[c1].Class2Record[c2].Value1.XAdvance)
    return None


@pytest.mark.parametrize("extension", [False, True], ids=["dogrudan", "extension"])
def test_new_glyphs_inherit_gpos_pair_kerning(is_glyf: bool, extension: bool) -> None:
    ext = " useExtension" if extension else ""
    features = f"""
        @L = [s g];
        @R = [I x];
        lookup glyph_pairs{ext} {{ pos s x -40; pos x s -30; pos I I 15; pos g s -10; }} glyph_pairs;
        lookup class_pairs{ext} {{ pos @L @R -25; }} class_pairs;
        feature kern {{ lookup glyph_pairs; lookup class_pairs; }} kern;
    """
    data = ttf.patch_font(make_font(is_glyf, features=features)).data
    font = TTFont(io.BytesIO(data))
    # Biçim 1 (tek glif çiftleri)
    assert _pair_value(font, "ş", "x") == -40
    assert _pair_value(font, "x", "ş") == -30
    assert _pair_value(font, "İ", "I") == _pair_value(font, "I", "İ") == _pair_value(font, "İ", "İ") == 15
    assert _pair_value(font, "ğ", "ş") == -10
    # Biçim 2 (sınıf çiftleri): ş, ğ sol sınıfa; İ sağ sınıfa girer.
    font = TTFont(io.BytesIO(data))
    lookups = font["GPOS"].table.LookupList.Lookup
    class_sub = lookups[1].SubTable[0]
    class_sub = class_sub.ExtSubTable if extension else class_sub
    assert class_sub.Format == 2
    cmap = font.getBestCmap()
    assert {cmap[ord("ş")], cmap[ord("ğ")]} <= set(class_sub.Coverage.glyphs)
    assert class_sub.ClassDef1.classDefs.get(cmap[ord("ş")], 0) == class_sub.ClassDef1.classDefs.get("s", 0)
    assert class_sub.ClassDef2.classDefs[cmap[ord("İ")]] == class_sub.ClassDef2.classDefs["I"]
    glyph_ids = [font.getGlyphID(g) for g in class_sub.Coverage.glyphs]
    assert glyph_ids == sorted(glyph_ids)


def test_font_without_kerning_is_patched_as_before(is_glyf: bool) -> None:
    font = TTFont(io.BytesIO(ttf.patch_font(make_font(is_glyf)).data))
    assert "kern" not in font
    assert "GPOS" not in font


def test_accent_above_the_ascent_is_noted_not_fixed(is_glyf: bool) -> None:
    low = ttf.patch_font(make_font(is_glyf, ascent=800, win_ascent=1200))
    assert "İ: işaret fontun üst sınırını aşıyor; oyunda kesilebilir" in low.notes
    assert TTFont(io.BytesIO(low.data))["hhea"].ascent == 800  # metrikler değişmez
    win = ttf.patch_font(make_font(is_glyf, ascent=1200, win_ascent=800))
    assert "İ: işaret fontun üst sınırını aşıyor; oyunda kesilebilir" in win.notes
    tall = ttf.patch_font(make_font(is_glyf, ascent=1200, win_ascent=1200))
    assert tall.notes == ()


def test_sources_module_orders_and_labels() -> None:
    assert sources.donors("İ")[:2] == ("i", "ż")
    assert sources.donors("Ş") == ("Ç", "ç", ",")
    assert sources.donors("ğ")[:2] == ("ă", "˘")
    assert sources.label("ş", "ç") == "ç'nin çengeli"
    assert sources.label("İ", "ö") == "ö'nün noktası"
    assert sources.label("Ğ", "Ŭ") == "Ŭ'nun kavisi"
    assert sources.label("ğ", "") == "çizildi"
    assert sources.describe({"ş": "virgül", "ğ": "çizildi"}) == "ş: virgül, ğ: çizildi"


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


def test_kerning_that_does_not_compile_falls_back_to_no_kerning(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(font: TTFont, bases: dict[str, str]) -> list[str]:
        font["GPOS"].table.LookupList.Lookup[0].SubTable[0].Coverage.glyphs.append("yok-boyle-glif")
        return []

    monkeypatch.setattr("nxceviri.core.fontpatch.kerning.inherit", broken)
    result = ttf.patch_font(make_font(features="feature kern { pos s x -40; } kern;"))
    assert result.added == ttf.PATCHABLE
    assert any(note.startswith("kerning aktarılamadı") for note in result.notes)
    font = TTFont(io.BytesIO(result.data))
    assert font["GPOS"].table.LookupList.Lookup[0].SubTable[0].Coverage.glyphs == ["s"]  # özgün kerning aynen
