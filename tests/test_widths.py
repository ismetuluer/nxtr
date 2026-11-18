"""Piksel genişliği ölçümü (`core/translate/widths.py`): tablo, ölçüm, dışa/içe aktarma, genişlik sorunu."""

from __future__ import annotations

import io
import logging
import struct

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from PIL import Image

from nxceviri.core.fontpatch.bmfont import MAGIC, BmFont
from nxceviri.core.translate import widths
from nxceviri.core.translate.codekinds import KIND_LINE_BREAK, KIND_OTHER, KIND_SYMBOL, KIND_VARIABLE
from nxceviri.core.translate.fit import DEFAULT_VARIABLE_WIDTH

KINDS = {1: KIND_LINE_BREAK, 2: KIND_VARIABLE, 3: KIND_SYMBOL, 4: KIND_OTHER}


def kind_of(n: int) -> str:
    return KINDS.get(n, KIND_OTHER)


def simple(advances: dict[str, float]) -> widths.WidthTable:
    return widths.WidthTable(advances, name="deneme", approximate=False)


# --- yaklaşık tablo ---------------------------------------------------------------------------------------------


def test_approximate_table_orders_wide_and_narrow_letters() -> None:
    table = widths.approximate_table()
    assert table.approximate is True
    assert table.measure("MMMM") > table.measure("iiii") * 2
    assert table.measure("W") > table.measure("l")


def test_approximate_table_covers_printable_ascii_and_turkish() -> None:
    table = widths.approximate_table()
    for code in range(0x20, 0x7F):
        assert chr(code) in table.advances
    for ch in "çğıİöşüÇĞÖŞÜ":
        assert ch in table.advances
    assert table.measure("ı") < table.measure("ş")
    assert table.measure("İ") < table.measure("Ş")


# --- ölçüm ------------------------------------------------------------------------------------------------------


def test_measure_sums_advances() -> None:
    table = simple({"a": 10, "b": 20, " ": 4})
    assert table.measure("ab a") == 10 + 20 + 4 + 10


def test_missing_turkish_letter_falls_back_to_base_letter() -> None:
    table = simple({"s": 7, "g": 9, "i": 3, "I": 5, "c": 6, "o": 8, "u": 8, "S": 11})
    assert table.measure("ş") == 7
    assert table.measure("ğ") == 9
    assert table.measure("ı") == 3
    assert table.measure("İ") == 5
    assert table.measure("ç") == 6
    assert table.measure("ö") == 8
    assert table.measure("ü") == 8
    assert table.measure("Ş") == 11


def test_unknown_char_falls_back_to_average() -> None:
    table = simple({"a": 10, "b": 20})
    assert table.average == 15
    assert table.measure("a€") == 25


def test_space_defaults_to_half_average() -> None:
    table = simple({"a": 10, "b": 20})
    assert table.measure(" ") == 7.5


def test_measure_empty_table_is_zero() -> None:
    assert simple({}).measure("abc") == 0.0


def test_visible_matches_fit_semantics() -> None:
    table = simple({"a": 10, "b": 20, " ": 4})
    assert widths.visible_pixels("  ab  ", kind_of, table) == 30  # kenar boşlukları sayılmaz
    assert widths.visible_pixels("a⟦4⟧b", kind_of, table) == 30  # diğer kod görünmez
    assert widths.visible_pixels("a⟦3⟧", kind_of, table) == 10 + 15  # sembol = bir ortalama harf
    assert widths.visible_pixels("a⟦2⟧", kind_of, table) == 10 + DEFAULT_VARIABLE_WIDTH * 15
    assert widths.visible_pixels("a⟦2⟧", kind_of, table, variable_width=2) == 10 + 2 * 15
    assert widths.visible_pixels("", kind_of, table) == 0


# --- TTF --------------------------------------------------------------------------------------------------------


def make_ttf(upm: int, advances: dict[str, int]) -> bytes:
    order = [".notdef", "space", *advances]
    cmap = {32: "space", **{ord(ch): ch for ch in advances}}
    metrics = {".notdef": (upm // 2, 0), "space": (upm // 4, 0), **{ch: (w, 0) for ch, w in advances.items()}}
    fb = FontBuilder(upm, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf({name: TTGlyphPen(None).glyph() for name in order})
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "T", "styleName": "R"})
    fb.setupOS2()
    fb.setupPost()
    out = io.BytesIO()
    fb.font.save(out)
    return out.getvalue()


def test_table_from_ttf_normalises_to_em() -> None:
    table = widths.table_from_ttf(make_ttf(2000, {"a": 1000, "b": 500}), "Test")
    assert table is not None
    assert table.name == "Test"
    assert table.approximate is False
    assert table.advances["a"] == pytest.approx(0.5)
    assert table.advances["b"] == pytest.approx(0.25)
    assert table.advances[" "] == pytest.approx(0.25)
    assert table.measure("ab") == pytest.approx(0.75)


def test_table_from_ttf_garbage_is_none() -> None:
    assert widths.table_from_ttf(b"not a font", "x") is None


# --- TMP --------------------------------------------------------------------------------------------------------


def test_table_from_tmp_dicts() -> None:
    glyphs = [
        {"m_Index": 0, "m_Metrics": {"m_HorizontalAdvance": 30.0}},
        {"m_Index": 1, "m_Metrics": {"m_HorizontalAdvance": 12.5}},
        {"m_Index": 2, "m_Metrics": {"m_HorizontalAdvance": 8.0}},
    ]
    chars = [
        {"m_Unicode": 77, "m_GlyphIndex": 0},
        {"m_Unicode": 105, "m_GlyphIndex": 1},
        {"m_Unicode": 32, "m_GlyphIndex": 2},
        {"m_Unicode": 90, "m_GlyphIndex": 99},  # glifi olmayan karakter atlanır
    ]
    table = widths.table_from_tmp(glyphs, chars, "TMP")
    assert table is not None
    assert table.advances == {"M": 30.0, "i": 12.5, " ": 8.0}
    assert table.measure("Mi") == 42.5


def test_table_from_tmp_empty_or_malformed_is_none() -> None:
    assert widths.table_from_tmp([], [], "x") is None
    assert widths.table_from_tmp([{"foo": 1}], [{"m_Unicode": 65, "m_GlyphIndex": 0}], "x") is None


def test_table_from_tmp_legacy() -> None:
    table = widths.table_from_tmp_legacy([{"id": 65, "xAdvance": 14.0}, {"id": 66, "xAdvance": 11.0}], "Eski")
    assert table is not None
    assert table.advances == {"A": 14.0, "B": 11.0}
    assert widths.table_from_tmp_legacy([], "x") is None


# --- BMFont -----------------------------------------------------------------------------------------------------


def make_bmfont(advances: dict[int, int]) -> BmFont:
    common = struct.pack("<5H", 20, 16, 8, 8, 1) + bytes(10)
    chars = b"".join(struct.pack("<IHHHHhhhBB", cid, 0, 0, 1, 1, 0, 0, adv, 0, 15) for cid, adv in advances.items())
    fnt = MAGIC + bytes([2]) + struct.pack("<I", len(common)) + common
    fnt += bytes([4]) + struct.pack("<I", len(chars)) + chars
    return BmFont(fnt, Image.new("RGBA", (8, 8)))


def test_table_from_bmfont() -> None:
    table = widths.table_from_bmfont(make_bmfont({65: 14, 105: 5}), "Bm")
    assert table is not None
    assert table.advances == {"A": 14.0, "i": 5.0}


# --- JSON -------------------------------------------------------------------------------------------------------


def test_dump_load_round_trip() -> None:
    table = widths.WidthTable({"a": 0.5, "ş": 0.25}, name="Font ı", approximate=True)
    loaded = widths.load(widths.dump(table))
    assert loaded is not None
    assert loaded.name == "Font ı"
    assert loaded.approximate is True
    assert loaded.advances == table.advances


@pytest.mark.parametrize(
    "text",
    [
        "",
        "{",
        "[]",
        '{"v": 1}',
        '{"v": 1, "name": 3, "approximate": false, "advances": {}}',
        '{"v": 1, "name": "x", "approximate": false, "advances": {"a": "geniş"}}',
        '{"v": 1, "name": "x", "approximate": false, "advances": {"ab": 1}}',
        '{"v": 9, "name": "x", "approximate": false, "advances": {"a": 1}}',
    ],
)
def test_load_corrupt_is_none_and_logged(text: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert widths.load(text) is None
    assert caplog.records


# --- width_problem ----------------------------------------------------------------------------------------------

T = simple({"a": 10, "b": 10, " ": 5})


def test_problem_when_wider_than_tolerance() -> None:
    problem = widths.width_problem("aaaa", "aaaaaa", kind_of, T)
    assert problem is not None
    assert problem.measured == 60
    assert problem.limit == pytest.approx(46)
    assert problem.ratio == pytest.approx(1.5)


def test_within_tolerance_is_none() -> None:
    assert widths.width_problem("a" * 10, "a" * 11, kind_of, T) is None  # %110
    assert widths.width_problem("a" * 10, "a" * 12, kind_of, T, tolerance=0.2) is None  # %120
    assert widths.width_problem("a" * 10, "a" * 13, kind_of, T, tolerance=0.2) is not None  # %130


def test_exactly_at_limit_is_none() -> None:
    assert widths.width_problem("a" * 20, "a" * 23, kind_of, T) is None  # 230 = 200 * 1.15


def test_multiline_source_is_none() -> None:
    assert widths.width_problem("aa\nbb", "a" * 40, kind_of, T) is None
    assert widths.width_problem("aa⟦1⟧bb", "a" * 40, kind_of, T) is None
    assert widths.width_problem("aa⟦5⟧bb", "a" * 40, kind_of, T) is not None  # bilinmeyen tür satır sonu değil


def test_empty_translation_is_none() -> None:
    assert widths.width_problem("aaaa", "", kind_of, T) is None
    assert widths.width_problem("aaaa", "   ", kind_of, T) is None


def test_empty_source_without_box_is_none() -> None:
    assert widths.width_problem("", "aaa", kind_of, T) is None


def test_box_overrides_source_width() -> None:
    assert widths.width_problem("a", "a" * 10, kind_of, T, box=200.0) is None
    problem = widths.width_problem("a", "a" * 30, kind_of, T, box=200.0)
    assert problem is not None
    assert problem.ratio == pytest.approx(1.5)


def test_multiline_translation_uses_widest_line() -> None:
    assert widths.width_problem("aaaa", "aaaa\naaaa", kind_of, T) is None
    assert widths.width_problem("aaaa", "aa\naaaaaa", kind_of, T) is not None


def test_codes_are_counted_like_fit() -> None:
    # Değişken kodu 6 ortalama harf (10) = 60 piksel sayılır.
    assert widths.width_problem("⟦2⟧", "⟦2⟧", kind_of, T) is None
    assert widths.width_problem("a⟦2⟧", "aaa⟦2⟧", kind_of, T) is not None


# --- group_boxes ------------------------------------------------------------------------------------------------


def test_group_boxes_takes_widest_single_line_source() -> None:
    rows = [("menu/a", "aa"), ("menu/b", "aaaa"), ("menu/c", "a\nb"), ("misc/x", "aaa"), ("none/y", "aaaaaaaa")]

    def group_of(key: str) -> str | None:
        head = key.split("/", maxsplit=1)[0]
        return None if head == "none" else head

    boxes = widths.group_boxes(rows, kind_of, T, group_of)
    assert boxes == {"menu": 40.0, "misc": 30.0}


def test_group_boxes_ignores_multiline_only_groups() -> None:
    assert widths.group_boxes([("g/a", "a\nb")], kind_of, T, lambda key: "g") == {}
