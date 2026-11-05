"""Ys Origin: BMFont yazı tiplerine eksik Türkçe harfleri ekleme (elle üretilmiş küçük yazı tipleriyle)."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from nxceviri.core.fontpatch import ys_fonts
from nxceviri.core.fontpatch.bmfont import BmFont, BmFontError, Part, add_missing
from tests.ysuobuild import build_bmfont, latin_glyphs

LETTERS = "ğĞşŞıİ"


def make_font(*, outline: bool = True, alpha_only: bool = False, atlas: tuple[int, int] = (96, 96)) -> BmFont:
    fnt, sheet = build_bmfont(latin_glyphs(outline=outline), atlas=atlas, alpha_only=alpha_only)
    return BmFont(fnt, sheet)


@pytest.mark.parametrize("outline", [True, False])
@pytest.mark.parametrize("alpha_only", [True, False])
def test_adds_all_six_letters_without_overlapping_existing_glyphs(outline: bool, alpha_only: bool) -> None:
    font = make_font(outline=outline, alpha_only=alpha_only)
    old = dict(font.chars)
    assert add_missing(font, LETTERS) == LETTERS
    rects = [(c.x, c.y, c.x + c.w, c.y + c.h) for c in font.chars.values()]
    for i, a in enumerate(rects):
        assert 0 <= a[0] < a[2] <= font.scale_w
        assert 0 <= a[1] < a[3] <= font.scale_h
        for b in rects[i + 1 :]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], "glifler çakışıyor"
    assert all(font.chars[k] == v for k, v in old.items())  # var olan glifler değişmedi
    for ch in LETTERS:
        c = font.chars[ord(ch)]
        assert font.atlas.crop((c.x, c.y, c.x + c.w, c.y + c.h)).getchannel("A").getbbox() is not None


def test_letter_shapes_follow_their_base_letters() -> None:
    font = make_font()
    add_missing(font, LETTERS)
    ch = font.chars
    i, dotless, big_i, dotted = ch[ord("i")], ch[ord("ı")], ch[ord("I")], ch[ord("İ")]
    assert dotless.h < i.h
    assert dotless.yoffset > i.yoffset
    assert dotted.yoffset < big_i.yoffset
    assert dotted.h > big_i.h
    s, cedilla_s = ch[ord("s")], ch[ord("ş")]
    assert cedilla_s.yoffset + cedilla_s.h > s.yoffset + s.h  # sedil taban çizgisinin altına iner
    g, breve_g = ch[ord("g")], ch[ord("ğ")]
    assert breve_g.yoffset < g.yoffset  # breve harfin üstünde
    for letter, base in zip("ıİşŞğĞ", "iIsSgG", strict=True):
        assert ch[ord(letter)].xadvance == ch[ord(base)].xadvance


def test_second_call_adds_nothing_and_serialization_round_trips() -> None:
    font = make_font()
    add_missing(font, LETTERS)
    assert add_missing(font, LETTERS) == ""
    again = BmFont(font.serialize(), Image.open(io.BytesIO(font.atlas_png())))
    assert again.chars == font.chars
    assert again.serialize() == font.serialize()


def test_atlas_grows_when_there_is_no_room() -> None:
    font = make_font(atlas=(64, 64))
    big = Part(Image.new("RGBA", (60, 60), (255, 255, 255, 255)), 0, 0)
    font.add("Ω", big, 10)
    assert (font.scale_w, font.scale_h) == (64, 128)
    assert font.atlas.size == (64, 128)
    again = BmFont(font.serialize(), Image.open(io.BytesIO(font.atlas_png())))  # common bloğu yeni boyutu söyler
    assert again.chars[ord("Ω")] == font.chars[ord("Ω")]


def test_missing_base_letters_and_bad_files_are_reported() -> None:
    glyphs = latin_glyphs(outline=True)
    del glyphs["G"]
    fnt, sheet = build_bmfont(glyphs)
    with pytest.raises(BmFontError, match=r"Temel harfler.*G"):
        add_missing(BmFont(fnt, sheet), LETTERS)
    with pytest.raises(BmFontError, match="BMFont"):
        BmFont(b"XXXX", sheet)
    with pytest.raises(BmFontError, match="Atlas boyutu"):
        BmFont(fnt, Image.new("RGBA", (10, 10)))


def _files(names: list[str]) -> tuple[dict[str, bytes], list[str]]:
    files: dict[str, bytes] = {}
    for name in names:
        fnt, sheet = build_bmfont(latin_glyphs(outline=True), alpha_only=name == "arial")
        buf = io.BytesIO()
        sheet.save(buf, "PNG")
        files[f"{ys_fonts.FONT_DIR}{name}.fnt"] = fnt
        files[f"{ys_fonts.FONT_DIR}{name}.png"] = buf.getvalue()
    return files, list(files)


def test_patch_fonts_returns_fnt_and_png_for_every_latin_font() -> None:
    files, names = _files(list(ys_fonts.FONTS))
    out, notes, warnings = ys_fonts.patch_fonts(files.__getitem__, names)
    assert sorted(out) == sorted(names)
    assert not warnings
    assert len(notes) == len(ys_fonts.FONTS)
    assert all(n.split(": ")[1].split(" (")[0].replace(" ", "") == LETTERS for n in notes)
    font = BmFont(out[f"{ys_fonts.FONT_DIR}ysfont.fnt"], Image.open(io.BytesIO(out[f"{ys_fonts.FONT_DIR}ysfont.png"])))
    assert all(ord(c) in font.chars for c in LETTERS)


def test_patch_fonts_warns_about_missing_and_broken_fonts() -> None:
    files, names = _files(["ysfont"])
    files[f"{ys_fonts.FONT_DIR}arial.fnt"] = b"XXXX"
    files[f"{ys_fonts.FONT_DIR}arial.png"] = b""
    out, notes, warnings = ys_fonts.patch_fonts(
        files.__getitem__, [*names, f"{ys_fonts.FONT_DIR}ARIAL.fnt".lower(), f"{ys_fonts.FONT_DIR}arial.png"]
    )
    assert sorted(out) == [f"{ys_fonts.FONT_DIR}ysfont.fnt", f"{ys_fonts.FONT_DIR}ysfont.png"]
    assert len(notes) == 1
    assert any("arial" in w and "yamalanamadı" in w for w in warnings)
    assert sum("bulunamadı" in w for w in warnings) == 3  # linuxwhite, linuxshadow, linuxwhitesmall


def test_fonts_that_already_have_the_letters_are_left_alone() -> None:
    glyphs = latin_glyphs(outline=True)
    for letter, base in zip("ıİşŞğĞ", "iIsSgG", strict=True):
        glyphs[letter] = glyphs[base]
    fnt, sheet = build_bmfont(glyphs)
    buf = io.BytesIO()
    sheet.save(buf, "PNG")
    files = {f"{ys_fonts.FONT_DIR}ysfont.fnt": fnt, f"{ys_fonts.FONT_DIR}ysfont.png": buf.getvalue()}
    out, notes, _warnings = ys_fonts.patch_fonts(files.__getitem__, list(files))
    assert out == {}
    assert notes == []
