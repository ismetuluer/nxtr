"""Font yaması (M8): SDF araçları, glif üretimi, atlas yerleşimi, bundle yazımı ve dışa aktarma."""

from __future__ import annotations

import itertools
import random
from pathlib import Path
from typing import Any

import pytest
import UnityPy

from nxceviri.core.export.layeredfs import (
    INFO_FILE,
    LAYOUT_ATMOSPHERE,
    ExportInfo,
    ExportOptions,
    ExportResult,
    TextFileRef,
    _info_text,
    _patch_font_file,
    export_mod,
)
from nxceviri.core.fontpatch import sdf
from nxceviri.core.fontpatch.tmp import TmpFont
from nxceviri.core.fontpatch.unity import FontPatch, FontPatchError, patch_fonts
from nxceviri.core.keys import load_keys
from nxceviri.core.pipeline import Inputs, extract_texts, opened_view, scan_sources
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import Project
from nxceviri.core.qa.fonts import is_language_specific, scan_fonts
from tests import nxbuild
from tests.unitybuild import SYNTH_GLYPHS, build_bundle, string_table, synth_atlas, tmp_font_bundle


def test_edt_matches_brute_force() -> None:
    rng = random.Random(7)
    w, h = 19, 11
    sites = [rng.random() < 0.08 for _ in range(w * h)]
    got = sdf._squared_distance(sites, w, h)
    for y in range(h):
        for x in range(w):
            want = min((x - i % w) ** 2 + (y - i // w) ** 2 for i in range(w * h) if sites[i])
            assert got[y * w + x] == pytest.approx(want)


def test_from_mask_edges_and_slope() -> None:
    w = 20
    mask = [5 <= x < 15 for x in range(w)]  # tek satırlık, 10 piksel genişliğinde şerit
    f = sdf.from_mask(mask, w, 1, 12.75)
    assert f.values[5] == pytest.approx(sdf.EDGE + 0.5 * 12.75)  # kenarın hemen içi
    assert f.values[4] == pytest.approx(sdf.EDGE - 0.5 * 12.75)  # kenarın hemen dışı
    assert sdf.estimate_slope(sdf.Field(w, 3, f.values * 3)) == pytest.approx(12.75)
    assert sdf.from_mask([False] * 4, 2, 2, 10).values == [0.0] * 4


def _font(glyphs: dict[str, Any] | None = None, size: tuple[int, int] = (256, 256)) -> tuple[TmpFont, dict[str, Any]]:
    image, fields = synth_atlas(glyphs or SYNTH_GLYPHS, size)
    tree = {"m_Name": "Deneme SDF", **fields}
    return TmpFont(tree, image), tree


def _components(font: TmpFont, ch: str) -> int:
    g = font.glyph(ch)
    assert g is not None
    return len(sdf.components(g.field.mask(), g.field.width, g.field.height))


def _overlaps(a: dict[str, int], b: dict[str, int]) -> bool:
    return not (
        a["m_X"] >= b["m_X"] + b["m_Width"]
        or b["m_X"] >= a["m_X"] + a["m_Width"]
        or a["m_Y"] >= b["m_Y"] + b["m_Height"]
        or b["m_Y"] >= a["m_Y"] + a["m_Height"]
    )


def test_patch_adds_all_turkish_letters() -> None:
    font, tree = _font()
    original_used = [dict(r) for r in tree["m_UsedGlyphRects"]]
    result = font.patch()
    assert result.added == "ıİşŞğĞ"
    assert result.skipped == {}
    after = TmpFont(tree, font.atlas_image())
    assert _components(after, "ı") == 1  # nokta kaldırıldı
    assert _components(after, "İ") == 2  # I + nokta
    assert _components(after, "ğ") == 2  # g + kısa çizgi
    s_hook = after.glyph("ş")
    assert s_hook is not None
    assert any(s_hook.top - i // s_hook.field.width < 0 for i in s_hook.ink())  # çengel taban çizgisinin altında
    dot = after.glyph("İ")
    plain = after.glyph("I")
    assert dot is not None
    assert plain is not None
    assert dot.top > plain.top  # nokta harfin üstünde
    new_rects = tree["m_UsedGlyphRects"][len(original_used) :]
    assert len(new_rects) == 6
    for r in new_rects:
        assert not any(_overlaps(r, u) for u in original_used)
        assert r["m_X"] + r["m_Width"] <= tree["m_AtlasWidth"]
        assert r["m_Y"] + r["m_Height"] <= tree["m_AtlasHeight"]
    for a, b in itertools.combinations(new_rects, 2):  # yeni glifler birbiriyle çakışmaz
        assert not _overlaps(a, b)
    # Var olan glifler yerinde ve değişmeden kalır.
    original, _fields = _font()
    for ch in "AIisç":
        g0, g1 = original.glyph(ch), after.glyph(ch)
        assert g0 is not None
        assert g1 is not None
        assert g0.field.values == g1.field.values


def test_patch_grows_full_atlas() -> None:
    font, tree = _font(size=(256, 128))
    assert tree["m_FreeGlyphRects"] == [] or all(r["m_Height"] < 60 for r in tree["m_FreeGlyphRects"])
    result = font.patch()
    assert result.added == "ıİşŞğĞ"
    assert tree["m_AtlasHeight"] == 256
    image = font.atlas_image()
    assert image.size == (256, 256)
    after = TmpFont(tree, image)
    original, _fields = _font(size=(256, 128))
    for ch in "AIisç":  # sol-alt başlangıçlı koordinatlar büyütmeden etkilenmez
        g0, g1 = original.glyph(ch), after.glyph(ch)
        assert g0 is not None
        assert g1 is not None
        assert g0.field.values == g1.field.values


def test_lowercase_donor_builds_uppercase_letters() -> None:
    """Ç/Ü olmayan fontta Ş/Ğ, küçük harfli çengel/breveden aynı boyutta üretilir."""
    glyphs = {k: v for k, v in SYNTH_GLYPHS.items() if k not in ("Ç", "Ü")}
    font, tree = _font(glyphs, size=(512, 512))
    result = font.patch()
    assert result.added == "ıİşŞğĞ"
    assert result.skipped == {}
    after = TmpFont(tree, font.atlas_image())

    def below(g: Any) -> list[int]:
        return [i for i in g.ink() if g.top - i // g.field.width < 0]

    upper, lower = after.glyph("Ş"), after.glyph("ş")
    assert upper is not None
    assert lower is not None
    upper_hook, lower_hook = below(upper), below(lower)
    assert upper_hook
    assert lower_hook

    def height(g: Any, indices: list[int]) -> int:
        _x0, y0, _x1, y1 = sdf.bbox(indices, g.field.width)
        return y1 - y0

    # Çengel büyük harfte büyütülmez: iki harf de aynı ç (donör) çengelini kullanır.
    assert height(upper, upper_hook) == height(lower, lower_hook)

    def top_mark_width(g: Any) -> int:
        comps = sdf.components(g.field.mask(), g.field.width, g.field.height)
        comps.sort(key=lambda c: min(i // g.field.width for i in c))
        x0, _y0, x1, _y1 = sdf.bbox(comps[0], g.field.width)
        return x1 - x0

    upper_g, lower_g = after.glyph("Ğ"), after.glyph("ğ")
    assert upper_g is not None
    assert lower_g is not None
    assert _components(after, "Ğ") == 2
    # Breve de aynı ü (donör) noktalarından, aynı boyutta üretilir.
    assert top_mark_width(upper_g) == top_mark_width(lower_g)


def test_font_with_empty_atlas_slots_is_patched() -> None:
    """TMP'nin 4/8 yuvalı `m_AtlasTextures` dizisindeki boş yuvalar atlas sayılmaz."""
    data = tmp_font_bundle([("Ana SDF", SYNTH_GLYPHS, (256, 256))], atlas_slots=4)
    out, patches = patch_fonts(data)
    assert out != data
    assert [(p.font, p.added) for p in patches] == [("Ana SDF", "ıİşŞğĞ")]
    font = _bundle_objects(out)["fonts"]["Ana SDF"]
    assert [s["m_PathID"] for s in font["m_AtlasTextures"]][1:] == [0, 0, 0]
    assert {chr(c["m_Unicode"]) for c in font["m_CharacterTable"]} >= set("ıİşŞğĞ")


def test_caps_font_aliases_dotless_i_and_reports_missing_donors() -> None:
    glyphs = {"I": SYNTH_GLYPHS["I"], "i": SYNTH_GLYPHS["I"], "A": SYNTH_GLYPHS["A"], "s": SYNTH_GLYPHS["s"]}
    font, tree = _font(glyphs)
    result = font.patch()
    assert result.added == "ı"  # "i" noktasız: "ı" aynı glife bağlanır, atlasa çizilmez
    i_index = next(c["m_GlyphIndex"] for c in tree["m_CharacterTable"] if c["m_Unicode"] == ord("i"))
    assert next(c["m_GlyphIndex"] for c in tree["m_CharacterTable"] if c["m_Unicode"] == ord("ı")) == i_index
    assert font.placed == 0
    assert result.skipped["ş"] == "kaynak harf yok: ç"
    assert result.skipped["İ"] == "kaynak harfin yapısı beklenenden farklı"  # nokta kaynağı yok
    assert "ğ" in result.skipped


def test_existing_letters_are_left_alone() -> None:
    glyphs = {**SYNTH_GLYPHS, "ı": SYNTH_GLYPHS["I"]}
    font, _tree = _font(glyphs)
    assert "ı" not in font.patch().added


def _bundle_objects(data: bytes) -> dict[str, Any]:
    env = UnityPy.load(data)
    out: dict[str, Any] = {"fonts": {}, "textures": {}, "materials": {}}
    for obj in env.objects:
        if obj.type.name == "MonoBehaviour":
            tree = obj.read_typetree()
            out["fonts"][tree["m_Name"]] = tree
        elif obj.type.name == "Texture2D":
            out["textures"][obj.path_id] = obj.read()
        elif obj.type.name == "Material":
            tree = obj.read_typetree()
            out["materials"][tree["m_Name"]] = dict(tree["m_SavedProperties"]["m_Floats"])
    return out


def test_patch_fonts_bundle_round_trip() -> None:
    data = tmp_font_bundle([("Ana SDF", SYNTH_GLYPHS, (256, 128)), ("Japanese SDF", SYNTH_GLYPHS, (256, 256))])
    same, plan = patch_fonts(data, write=False, skip=is_language_specific)
    assert same == data
    assert [(p.font, p.added) for p in plan] == [("Ana SDF", "ıİşŞğĞ")]
    out, patches = patch_fonts(data, skip=is_language_specific)
    assert [(p.font, p.added) for p in patches] == [("Ana SDF", "ıİşŞğĞ")]
    objs = _bundle_objects(out)
    font = objs["fonts"]["Ana SDF"]
    assert {chr(c["m_Unicode"]) for c in font["m_CharacterTable"]} >= set("ıİşŞğĞ")
    assert font["m_AtlasHeight"] == 256
    tex = objs["textures"][font["m_AtlasTextures"][0]["m_PathID"]]
    assert tex.image.size == (256, 256)
    assert objs["materials"]["Ana SDF Material"]["_TextureHeight"] == 256.0
    assert objs["materials"]["Japanese SDF Material"]["_TextureHeight"] == 256.0
    japanese = objs["fonts"]["Japanese SDF"]
    assert not {chr(c["m_Unicode"]) for c in japanese["m_CharacterTable"]} & set("ıİşŞğĞ")
    # Yazılan atlas yeniden okunduğunda yeni glifler yerinde.
    after = TmpFont(font, tex.image)
    assert after.glyph("ş") is not None
    assert patch_fonts(out, skip=is_language_specific)[0] == out  # ikinci kez: eklenecek harf yok, dosya aynı


def test_shared_atlas_is_skipped() -> None:
    data = tmp_font_bundle([("A SDF", SYNTH_GLYPHS, (256, 256)), ("B SDF", SYNTH_GLYPHS, (256, 256))], share_atlas=True)
    out, patches = patch_fonts(data)
    assert out == data
    assert {p.font for p in patches} == {"A SDF", "B SDF"}
    assert all(set(p.skipped.values()) == {"atlas başka bir fontla ortak"} for p in patches)


def test_corrupt_bundle() -> None:
    with pytest.raises(FontPatchError):
        patch_fonts(b"UnityFS\0" + b"\xff" * 64)


#: Latin fontu sayılması için tüm İngiliz harfleri (basit dikdörtgenler) + yamanın kaynak harfleri.
LATIN_GLYPHS = {
    **{c: [(0, 0, 10, 20)] for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"},
    **SYNTH_GLYPHS,
}


@pytest.fixture
def font_game(tmp_path: Path) -> tuple[Inputs, Path]:
    keys = nxbuild.TestKeys.random()
    aa = "Data/StreamingAssets/aa/Switch/"
    files = {
        "Data/globalgamemanagers": b"\0" * 8 + (22).to_bytes(4, "big") + b"\0" * 20,
        aa + "localization-string-tables-english(en)_assets_all.bundle": build_bundle(
            [string_table("UI_en", "en", 0, [(1, "Start"), (2, "Exit")])]
        ),
        aa + "fonts_assets_all.bundle": tmp_font_bundle([("Ana SDF", LATIN_GLYPHS, (512, 512))]),
        # Dile özgü bundle: fontun adında dil geçmese de yamalanmaz.
        aa + "fonts-japanese_assets_all.bundle": tmp_font_bundle([("Mincho SDF", LATIN_GLYPHS, (512, 512))]),
    }
    pkg = nxbuild.build_package(
        keys,
        kind="base",
        title_id=0x0100DDDD00000000,
        application_id=0x0100DDDD00000000,
        version=0,
        romfs_files=files,
        name="Font Oyunu",
    )
    nsp = tmp_path / "Font Oyunu.nsp"
    nsp.write_bytes(pkg.nsp)
    return Inputs((nsp,), load_keys(keys.write(tmp_path / "prod.keys"))), tmp_path


def test_scan_reports_patchable_letters(font_game: tuple[Inputs, Path]) -> None:
    inputs, _tmp = font_game
    report = scan_sources(inputs, TaskContext())
    with opened_view(inputs, TaskContext()) as view:
        fonts = scan_fonts(view, report)
    ana = next(f for f in fonts.fonts if f.name == "Ana SDF")
    assert ana.patchable == "ıİşŞğĞ"
    assert next(f for f in fonts.fonts if f.name == "Mincho SDF").patchable == ""
    assert fonts.missing_letters() == "ğıİöşĞŞ"
    assert fonts.missing_letters(patched=True) == "ö"  # "ö" için kaynak yok: dönüştürme gerekir
    assert fonts.patchable_letters == "ğıİşĞŞ"
    assert ana.missing(patched=True) == "ö"


def test_export_with_font_patch(font_game: tuple[Inputs, Path]) -> None:
    inputs, tmp_path = font_game
    report = scan_sources(inputs, TaskContext())
    project = Project.new()
    project.import_texts(extract_texts(inputs, report, TaskContext(), "en").files)
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations([(rows["UI_en/1"].id, "Başla"), (rows["UI_en/2"].id, "Çıkış")])
    dest = tmp_path / "mod"
    result = export_mod(
        inputs,
        [TextFileRef(*f) for f in project.text_files()],
        project.translation_rows(),
        options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "x", "", patch_fonts=True),
        info=ExportInfo("Font Oyunu", "0100DDDD00000000", 0, None),
    )
    root = "atmosphere/contents/0100DDDD00000000/romfs/Data/StreamingAssets/aa/Switch/"
    assert sorted(result.files) == [
        root + "fonts_assets_all.bundle",
        root + "localization-string-tables-english(en)_assets_all.bundle",
    ]
    assert result.font_patches == ["Ana SDF (fonts_assets_all.bundle): ı İ ş Ş ğ Ğ"]
    font = _bundle_objects((dest / root / "fonts_assets_all.bundle").read_bytes())["fonts"]["Ana SDF"]
    assert {chr(c["m_Unicode"]) for c in font["m_CharacterTable"]} >= set("ıİşŞğĞ")
    assert "Font yaması" in (dest / INFO_FILE).read_text(encoding="utf-8")


def test_export_without_font_patch_leaves_fonts(font_game: tuple[Inputs, Path]) -> None:
    inputs, tmp_path = font_game
    report = scan_sources(inputs, TaskContext())
    project = Project.new()
    project.import_texts(extract_texts(inputs, report, TaskContext(), "en").files)
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations([(rows["UI_en/1"].id, "Başla")])
    result = export_mod(
        inputs,
        [TextFileRef(*f) for f in project.text_files()],
        project.translation_rows(),
        options=ExportOptions(LAYOUT_ATMOSPHERE, tmp_path / "mod", "x", ""),
        info=ExportInfo("Font Oyunu", "0100DDDD00000000", 0, None),
    )
    assert not any("fonts_assets_all" in f for f in result.files)
    assert result.font_patches == []


def _fake_patches(monkeypatch: pytest.MonkeyPatch, patches: list[FontPatch]) -> ExportResult:
    monkeypatch.setattr("nxceviri.core.export.layeredfs.patch_fonts", lambda data, skip: (data, patches))
    result = ExportResult(Path("x"))
    _patch_font_file(b"", "romfs/fonts-base_assets_all.bundle", result)
    return result


def test_placeholder_font_is_noted_without_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Temel harfleri hiç olmayan yer tutucu font (ör. yalnızca "¤" içeren BaseFont) uyarı üretmez."""
    skipped = {"ı": "kaynak harf yok: i", "ş": "kaynak harf yok: sç"}
    result = _fake_patches(monkeypatch, [FontPatch("BaseFont", "", skipped)])
    assert result.warnings == []
    assert result.font_patches == []
    assert result.font_notes == [
        "BaseFont (fonts-base_assets_all.bundle): temel Latin harfleri yok, metin fontu değil; atlandı"
    ]


def test_unpatchable_text_font_is_warned_and_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    """Harf eklenemeyen gerçek bir font hem uyarı verir hem nedeni bilgi dosyasına yazılır."""
    result = _fake_patches(monkeypatch, [FontPatch("Ana", "", {"ş": "atlasta yer yok"})])
    assert len(result.warnings) == 1
    assert result.font_notes == ["Ana (fonts-base_assets_all.bundle): harf eklenemedi — ş (atlasta yer yok)"]
    info = _info_text(
        ExportInfo("Oyun", "0100DDDD00000000", 0, None),
        ExportOptions(LAYOUT_ATMOSPHERE, Path("x"), "x", ""),
        result,
    )
    assert "atlasta yer yok" in info
