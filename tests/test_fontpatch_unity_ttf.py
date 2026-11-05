"""Unity `Font` nesnelerindeki gömülü TTF/OTF'lere font yaması (dinamik TextMeshPro fontlarının kaynağı)."""

from __future__ import annotations

import io

import pytest
import UnityPy
from fontTools.ttLib import TTFont

from nxceviri.core.fontpatch import ttf
from nxceviri.core.fontpatch.unity import patch_fonts
from nxceviri.core.qa.fonts import is_language_specific
from tests.test_fontpatch_ttf import make_font
from tests.unitybuild import build_bundle, font_object, other_behaviour


def _fonts(data: bytes) -> dict[str, bytes]:
    return {o.read().m_Name: bytes(o.read().m_FontData) for o in UnityPy.load(data).objects if o.type.name == "Font"}


def _letters(font: bytes) -> str:
    cmap = TTFont(io.BytesIO(font)).getBestCmap()
    return "".join(c for c in ttf.PATCHABLE if ord(c) in cmap)


def test_plan_reports_patchable_letters_without_touching_the_file() -> None:
    bundle = build_bundle([font_object("Hand-Regular", make_font())], compress=False)
    out, reports = patch_fonts(bundle, write=False)
    assert out == bundle
    assert [(r.font, r.added, r.skipped, r.vector) for r in reports] == [("Hand-Regular", ttf.PATCHABLE, {}, True)]


@pytest.mark.parametrize("glyf", [True, False], ids=["glyf", "cff"])
def test_writes_patched_font_back_into_the_bundle(glyf: bool) -> None:
    original = make_font(glyf)
    bundle = build_bundle([font_object("Hand-Regular", original), other_behaviour("Other")])
    out, reports = patch_fonts(bundle)
    assert reports[0].added == ttf.PATCHABLE
    patched = _fonts(out)["Hand-Regular"]
    assert _letters(patched) == ttf.PATCHABLE
    assert _letters(original) == ""
    # Font dışındaki nesneler değişmez.
    kept = {o.path_id: bytes(o.get_raw_data()) for o in UnityPy.load(bundle).objects if o.type.name != "Font"}
    assert kept == {o.path_id: bytes(o.get_raw_data()) for o in UnityPy.load(out).objects if o.type.name != "Font"}
    # İkinci kez yamalamak bir şey değiştirmez.
    again, again_reports = patch_fonts(out)
    assert again == out
    assert again_reports == []


def test_language_specific_and_complete_fonts_are_left_alone() -> None:
    complete = ttf.patch_font(make_font()).data
    bundle = build_bundle([font_object("Japanese-Regular", make_font()), font_object("Complete", complete)])
    out, reports = patch_fonts(bundle, skip=is_language_specific)
    assert out == bundle
    assert reports == []


def test_font_without_base_letters_is_reported_as_skipped() -> None:
    bundle = build_bundle([font_object("Icons", make_font(drop="iIsSgG"))])
    out, reports = patch_fonts(bundle)
    assert out == bundle
    assert reports[0].added == ""
    assert all(why.startswith(ttf.NO_BASE_LETTER) for why in reports[0].skipped.values())
