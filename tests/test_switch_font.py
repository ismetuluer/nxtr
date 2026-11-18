"""Switch sistem fontları (`.bfttf` / `.bfotf`, `.zs`): font denetimi, font yaması ve dışa aktarma.

Fontlar FontBuilder ile elle üretilir ve `switchfont.wrap` ile kapsayıcıya konur; gerçek font kullanılmaz.
"""

from __future__ import annotations

import io
import string
from dataclasses import dataclass
from pathlib import Path

import pytest
import zstandard
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from pytestqt.qtbot import QtBot

from nxceviri.arac import main
from nxceviri.core.archives import sarc
from nxceviri.core.export.layeredfs import (
    INFO_FILE,
    LAYOUT_ATMOSPHERE,
    LAYOUT_EMULATOR,
    ExportError,
    ExportInfo,
    ExportOptions,
    ExportResult,
    TextFileRef,
    export_mod,
)
from nxceviri.core.fontpatch import switchfont
from nxceviri.core.keys import load_keys
from nxceviri.core.pipeline import Inputs, extract_texts, opened_view, scan_sources
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import Project
from nxceviri.core.qa.fonts import (
    DURUM_YAMALANABILIR,
    KIND_SWITCH,
    KIND_TTF,
    FontInfo,
    FontReport,
    font_advice,
    font_verdict,
    is_editable_font,
    is_switch_font_path,
    scan_fonts,
    switch_font_source,
)
from tests import nxbuild

TID = 0x0100EEEE00000000
TID_HEX = f"{TID:016X}"
HEADER = bytes.fromhex("d99b871a01020304")
KEY = bytes.fromhex("5a3c9e11")
#: Avrupa dillerinin aksanlı harfleri (Latin-1 Ek): Latin metin fontu bunları taşır (Türkçenin ç ö ü'sü dahil).
WESTERN = "".join(chr(c) for c in range(0xC0, 0x100) if c not in (0xD7, 0xF7))
PATCHABLE = "ıİşŞğĞ"

LATIN_ZS = "mesg/Font/Latin.bfttf.zs"
ASIA_ZS = "mesg/Font/AsiaKDH.bfotf.zs"  # yalnızca ASCII + CJK: dile özgü
JPLATIN_ZS = "mesg/Font/Standard.bfttf.zs"  # CJK glifleri + Avrupa harfleri: Latin metin fontu
RAW_FONT = "mesg/Font/Ham.bfttf"  # sıkıştırılmamış kapsayıcı
FULL_ZS = "mesg/Font/Tam.bfttf.zs"  # Türkçe harflerin hepsi var
PACK = "Pack/Fonts.sarc"
PACKED_FONT = f"{PACK}>Font/Ic.bfttf.zs"


def _draw(pen: TTGlyphPen, rects: list[tuple[int, int, int, int]]) -> None:
    for x0, y0, x1, y1 in rects:
        pen.moveTo((x0, y0))
        pen.lineTo((x0, y1))
        pen.lineTo((x1, y1))
        pen.lineTo((x1, y0))
        pen.closePath()


def make_font(extra: str = "", cjk: int = 0) -> bytes:
    """ASCII harfleri (+ `extra`) taşıyan küçük glyf fontu; `cjk` kadar CJK kod noktası tek glife bağlanır."""
    shapes: dict[str, list[tuple[int, int, int, int]]] = {c: [(30, 0, 400, 600)] for c in string.ascii_letters}
    shapes["i"] = [(50, 0, 130, 500), (40, 560, 140, 660)]  # noktası ayrı
    shapes["g"] = [(30, -200, 430, 500)]
    shapes["."] = [(20, 0, 120, 100)]
    shapes[","] = [(20, -150, 120, 100)]
    for c in extra:
        shapes[c] = [(30, 0, 400, 600), (100, 650, 300, 700)]
    names = {c: f"u{ord(c):04X}" for c in shapes}
    order = [".notdef", "space", *names.values()]
    cmap = {32: "space", **{ord(c): names[c] for c in shapes}}
    for cp in range(0x4E00, 0x4E00 + cjk):
        cmap[cp] = names["x"]
    glyphs = {}
    metrics = {".notdef": (500, 0), "space": (250, 0)}
    for c, name in names.items():
        pen = TTGlyphPen(None)
        _draw(pen, shapes[c])
        glyphs[name] = pen.glyph()
        metrics[name] = (200 if c == "i" else 480, 30)
    for name in (".notdef", "space"):
        glyphs[name] = TTGlyphPen(None).glyph()
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": "Deneme", "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    out = io.BytesIO()
    fb.font.save(out)
    return out.getvalue()


def zs(sfnt: bytes) -> bytes:
    return switchfont.wrap(HEADER, sfnt, KEY)


def cmap_of(data: bytes) -> set[str]:
    font = TTFont(io.BytesIO(switchfont.unwrap(data)[1]))
    try:
        return {chr(c) for c in font.getBestCmap()}
    finally:
        font.close()


ROMFS: dict[str, bytes] = {
    "Message/Menu.msbt": nxbuild.build_msbt([("Start", ["Start"]), ("Exit", ["Exit"])]),
    LATIN_ZS: zs(make_font(WESTERN)),
    ASIA_ZS: zs(make_font(cjk=250)),
    JPLATIN_ZS: zs(make_font(WESTERN, cjk=250)),
    RAW_FONT: switchfont.wrap(HEADER, make_font(WESTERN), KEY, compress=False),
    FULL_ZS: zs(make_font(WESTERN + "ğıİşĞŞ")),
    PACK: nxbuild.build_sarc({"Font/Ic.bfttf.zs": zs(make_font(WESTERN)), "Data/x.bin": b"\x01" * 16}),
}


@dataclass
class Game:
    inputs: Inputs
    nsp: Path
    keys: Path
    project: Project
    fonts: FontReport


@pytest.fixture(scope="module")
def switch_game(tmp_path_factory: pytest.TempPathFactory) -> Game:
    folder = tmp_path_factory.mktemp("switch font oyunu")
    keys = nxbuild.TestKeys.random()
    pkg = nxbuild.build_package(
        keys, kind="base", title_id=TID, application_id=TID, version=0, romfs_files=ROMFS, name="Font Oyunu"
    )
    nsp = folder / "oyun.nsp"
    nsp.write_bytes(pkg.nsp)
    keys_path = keys.write(folder / "prod.keys")
    inputs = Inputs((nsp,), load_keys(keys_path))
    report = scan_sources(inputs, TaskContext())
    project = Project.new()
    project.import_texts(extract_texts(inputs, report, TaskContext()).files)
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations([(rows["Start"].id, "Başla")])
    with opened_view(inputs, TaskContext()) as view:
        fonts = scan_fonts(view, report)
    return Game(inputs, nsp, keys_path, project, fonts)


def _by_source(report: FontReport) -> dict[str, FontInfo]:
    return {f.source: f for f in report.fonts}


# --- yol ve kapsayıcı -------------------------------------------------------------------------


def test_canonical_source_is_the_outermost_font_file() -> None:
    assert switch_font_source("mesg/Font/A.bfttf.zs") == "mesg/Font/A.bfttf.zs"
    assert switch_font_source("mesg/Font/A.bfttf.zs>A.bfttf") == "mesg/Font/A.bfttf.zs"
    assert switch_font_source("mesg/Font/B.BFOTF") == "mesg/Font/B.BFOTF"
    assert switch_font_source("p.sarc>Font/C.bfotf.zs>C.bfotf") == "p.sarc>Font/C.bfotf.zs"
    assert switch_font_source("mesg/Font/a.ttf") is None
    assert switch_font_source("mesg/x.sarc.zs>x.sarc") is None
    assert is_switch_font_path("mesg/Font/A.bfttf.zs")
    assert not is_switch_font_path("mesg/Font/A.bffnt")


# --- font denetimi --------------------------------------------------------------------------


def test_each_font_is_listed_once_at_its_romfs_path(switch_game: Game) -> None:
    sources = [f.source for f in switch_game.fonts.fonts]
    assert sorted(sources) == sorted([LATIN_ZS, ASIA_ZS, JPLATIN_ZS, RAW_FONT, FULL_ZS, PACKED_FONT])
    assert {f.kind for f in switch_game.fonts.fonts} == {KIND_SWITCH}
    assert _by_source(switch_game.fonts)[LATIN_ZS].name == "Latin.bfttf"
    assert not switch_game.fonts.warnings


def test_chars_patchable_and_widths_come_from_the_unwrapped_font(switch_game: Game) -> None:
    latin = _by_source(switch_game.fonts)[LATIN_ZS]
    assert latin.chars is not None
    assert "a" in latin.chars
    assert "ç" in latin.chars
    assert latin.missing() == "ğıİşĞŞ"
    assert sorted(latin.patchable) == sorted(PATCHABLE)
    assert not latin.language_specific
    assert latin.widths is not None
    assert latin.widths.advances["a"] == pytest.approx(0.48)
    assert latin.widths.advances["i"] == pytest.approx(0.2)
    raw = _by_source(switch_game.fonts)[RAW_FONT]
    assert sorted(raw.patchable) == sorted(PATCHABLE)
    full = _by_source(switch_game.fonts)[FULL_ZS]
    assert full.missing() == ""
    assert full.patchable == ""


def test_cjk_font_with_only_ascii_is_language_specific(switch_game: Game) -> None:
    fonts = _by_source(switch_game.fonts)
    asia = fonts[ASIA_ZS]
    assert asia.language_specific
    assert asia.patchable == ""
    assert asia.widths is None
    assert ASIA_ZS not in switch_game.fonts.patch_files
    # CJK glifleri olsa da Avrupa harflerini taşıyan font Latin metin fontudur: yamalanır, ölçülür.
    standard = fonts[JPLATIN_ZS]
    assert not standard.language_specific
    assert sorted(standard.patchable) == sorted(PATCHABLE)
    assert standard.widths is not None


def test_cjk_font_with_a_few_accented_letters_is_language_specific() -> None:
    from nxceviri.core.qa import fonts as qa_fonts

    # Çince fontlar pinyin için ü, é, à gibi birkaç aksanlı harf taşır; Avrupa metin fontu değildir.
    cjk = frozenset(chr(c) for c in range(0x4E00, 0x4E00 + 3000)) | frozenset("abcdefghijklmnopqrstuvwxyzüéàèòù")
    assert qa_fonts.is_language_specific_switch_font("FZTLJW.bfttf", cjk)
    western = cjk | frozenset(chr(c) for c in range(0xC0, 0x100) if c not in (0xD7, 0xF7))
    assert not qa_fonts.is_language_specific_switch_font("FOT-Std.bfotf", western)


def test_patch_files_and_verdict(switch_game: Game) -> None:
    assert switch_game.fonts.patch_files == tuple(sorted([LATIN_ZS, JPLATIN_ZS, RAW_FONT, PACKED_FONT]))
    verdict = font_verdict(switch_game.fonts)
    assert verdict.durum == DURUM_YAMALANABILIR
    assert sorted(verdict.yamalanabilir) == sorted(PATCHABLE)
    assert verdict.kalan == ""
    assert switch_game.fonts.measuring_table() is not None


def test_broken_switch_font_becomes_a_warning() -> None:
    from nxceviri.core.qa import fonts as qa_fonts

    info, warning = qa_fonts.read_switch_font(b"\x28\xb5\x2f\xfd bozuk", "mesg/Font/Bozuk.bfttf.zs")
    assert info is None
    assert "Bozuk.bfttf.zs" in warning


def test_advice_and_editability() -> None:
    latin = frozenset(string.ascii_letters)
    font = FontInfo("Latin.bfttf", LATIN_ZS, KIND_SWITCH, latin, False, "", "ışğ")
    assert "yaması" in font_advice(font)
    assert "dönüştürme" in font_advice(FontInfo("L", LATIN_ZS, KIND_SWITCH, latin, False))
    assert not is_editable_font(font)


def test_font_tool_lists_switch_fonts(switch_game: Game, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["font", str(switch_game.nsp), "--anahtar", str(switch_game.keys)]) == 0
    out = capsys.readouterr().out
    assert "Latin.bfttf" in out
    assert KIND_SWITCH in out
    assert "font bulunamadı" not in out
    assert out.strip().splitlines()[-1].startswith("Sonuç: Eksik harfler font yamasıyla eklenebilir")


# --- dışa aktarma ---------------------------------------------------------------------------


def _export(game: Game, dest: Path, layout: str = LAYOUT_ATMOSPHERE, **options: object) -> ExportResult:
    return export_mod(
        game.inputs,
        [TextFileRef(*f) for f in game.project.text_files()],
        game.project.translation_rows(),
        options=ExportOptions(layout, dest, "Türkçe", **options),  # type: ignore[arg-type]
        info=ExportInfo("Font Oyunu", TID_HEX, 0, None),
    )


@pytest.mark.parametrize(
    ("layout", "root"),
    [
        (LAYOUT_ATMOSPHERE, Path("atmosphere", "contents", TID_HEX, "romfs")),
        (LAYOUT_EMULATOR, Path(TID_HEX, "Türkçe", "romfs")),
    ],
)
def test_export_patches_switch_fonts(switch_game: Game, tmp_path: Path, layout: str, root: Path) -> None:
    dest = tmp_path / "mod"
    result = _export(switch_game, dest, layout, patch_fonts=True, font_files=frozenset(switch_game.fonts.patch_files))
    written = set(result.files)
    for path in (LATIN_ZS, JPLATIN_ZS, RAW_FONT, PACK):
        assert (root / path).as_posix() in written, path
    assert (root / ASIA_ZS).as_posix() not in written
    assert (root / FULL_ZS).as_posix() not in written
    latin = (dest / root / LATIN_ZS).read_bytes()
    assert latin.startswith(zstandard.FRAME_HEADER)
    assert switchfont.unwrap(latin)[0] == HEADER
    assert switchfont.unwrap(latin)[2] == KEY
    assert set(PATCHABLE) <= cmap_of(latin)
    raw = (dest / root / RAW_FONT).read_bytes()
    assert raw.startswith(HEADER)  # sıkıştırılmamış kaldı
    assert set(PATCHABLE) <= cmap_of(raw)
    # SARC içindeki font yamalandı; arşivin diğer üyesi aynı kaldı.
    pack = sarc.read((dest / root / PACK).read_bytes())
    assert set(PATCHABLE) <= cmap_of(pack.get("Font/Ic.bfttf.zs"))
    assert pack.get("Data/x.bin") == b"\x01" * 16
    assert any(line.startswith("Latin.bfttf") and "ğ" in line for line in result.font_patches)
    assert any(line.startswith("Ic.bfttf") for line in result.font_patches)
    assert all("ı: i'den nokta silindi" in line for line in result.font_patches)  # işaret kaynakları satırda
    assert "Font yaması (eklenen harfler)" in (dest / INFO_FILE).read_text(encoding="utf-8")


def test_export_without_font_patch_writes_no_font(switch_game: Game, tmp_path: Path) -> None:
    result = _export(switch_game, tmp_path / "mod", font_files=frozenset(switch_game.fonts.patch_files))
    assert not [f for f in result.files if "Font" in f or f.endswith(".sarc")]
    assert not result.font_patches


def test_export_skips_fonts_with_nothing_missing(switch_game: Game, tmp_path: Path) -> None:
    result = _export(switch_game, tmp_path / "mod", patch_fonts=True, font_files=frozenset({FULL_ZS}))
    assert not [f for f in result.files if "Font" in f]
    assert not result.font_patches


def test_export_skips_language_specific_switch_font(switch_game: Game, tmp_path: Path) -> None:
    """Eski bir ayarda dile özgü font listede kalmış olsa da dışa aktarma ona harf eklemez."""
    result = _export(switch_game, tmp_path / "mod", patch_fonts=True, font_files=frozenset({ASIA_ZS}))
    assert not [f for f in result.files if "Font" in f]
    assert any("AsiaKDH" in note for note in result.font_notes)


def test_failed_rewrap_verification_is_an_error(
    switch_game: Game, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_wrap = switchfont.wrap

    def broken_wrap(header: bytes, _sfnt: bytes, key: bytes, compress: bool = True) -> bytes:
        return original_wrap(header, make_font(WESTERN), key, compress)  # yama kayboldu

    monkeypatch.setattr(switchfont, "wrap", broken_wrap)
    with pytest.raises(ExportError, match=r"Latin.bfttf"):
        _export(switch_game, tmp_path / "mod", patch_fonts=True, font_files=frozenset({LATIN_ZS}))
    assert not (tmp_path / "mod").exists()


# --- arayüz ---------------------------------------------------------------------------------


def test_switch_font_rows_disable_edit_buttons_with_reason(qtbot: QtBot) -> None:
    from nxceviri.gui.qa_page import QaPage

    page = QaPage()
    qtbot.addWidget(page)
    latin = frozenset(string.ascii_letters)
    report = FontReport(
        [
            FontInfo("A", "Font/a.ttf", KIND_TTF, latin, False),
            FontInfo("Latin.bfttf", LATIN_ZS, KIND_SWITCH, latin, False, "", "ışğ"),
        ]
    )
    page.show_font_report(report, "")
    page.set_font_overrides({})
    rows = {page.font_table.item(r, 4).toolTip(): r for r in range(2)}  # type: ignore[union-attr]
    kind = page.font_table.item(rows[LATIN_ZS], 1)
    assert kind is not None
    assert kind.text() == KIND_SWITCH
    page.font_table.selectRow(rows[LATIN_ZS])
    assert not page.font_export_button.isEnabled()
    assert not page.font_import_button.isEnabled()
    assert "düzenlenemez" in page.font_export_button.toolTip()
    page.font_table.selectRow(rows["Font/a.ttf"])
    assert page.font_export_button.isEnabled()
    assert "düzenlenemez" not in page.font_export_button.toolTip()
