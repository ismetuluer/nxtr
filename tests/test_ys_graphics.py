"""Ys Origin: çevrilmiş resimleri (DDS) yerleştirme, grafik klasörü ve dışa aktarma kancası (elle üretilmiş)."""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from PIL import Image, ImageChops, ImageDraw

from nxceviri.core.archives import nni
from nxceviri.core.archives.access import MemberReader
from nxceviri.core.container.romfs import RomFs
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.container.view import ContentTree, LayeredRomFs, RomFsLayer
from nxceviri.core.export import extras
from nxceviri.core.export.layeredfs import ExportResult, _export_member_archive
from nxceviri.core.fontpatch import ys_fonts, ys_graphics
from nxceviri.core.fontpatch.ys_graphics import GraphicsError
from tests.nxbuild import build_romfs
from tests.ysuobuild import build_bmfont, build_dds, build_nni, latin_glyphs

TID = "0100F90010882000"
MEMBER = "EXTENSION/STORY/EN/V_1.DDS"
TOP = "ys_data/archives/data-en.ni"
NA = "ys_data/archives/data-en.na"


def picture(text: str, size: tuple[int, int] = (64, 32)) -> Image.Image:
    """Saydam zeminli, büyük düz renk şekillerden oluşan küçük bir 'yazı' resmi (BC3 sıkıştırmasına dayanıklı)."""
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for i, ch in enumerate(text):
        draw.rectangle((4 + i * 12, 8, 12 + i * 12, 24), fill=(255, 255, 255, 255) if ch == "x" else (230, 40, 40, 255))
    return image


def close(a: Image.Image, b: Image.Image, tolerance: int = 40) -> bool:
    diff = ImageChops.difference(a.convert("RGBA"), b.convert("RGBA"))
    extrema = cast(tuple[tuple[int, int], ...], diff.getextrema())
    return all(high <= tolerance for _low, high in extrema)


def reader(files: dict[str, bytes]) -> Callable[[str], bytes]:
    return files.__getitem__


def test_encode_keeps_header_size_format_and_mip_chain() -> None:
    original = build_dds(picture("xx"), mips=3)
    out = ys_graphics.encode(original, picture("yy"))
    assert len(out) == len(original)
    assert out[:148] == original[:148]
    assert close(ys_graphics.decode(out), picture("yy"))
    assert out[148:] != original[148:]  # mip seviyeleri de yeniden kodlandı (özgünde sıfırdı)


def test_encode_rescales_other_sizes_and_supports_bc1() -> None:
    original = build_dds(picture("xx"), code="BC1")
    out = ys_graphics.encode(original, picture("xx", (128, 64)))
    assert len(out) == len(original)
    assert ys_graphics.decode(out).size == (64, 32)


def test_flipped_images_are_shown_upright_and_written_back_flipped() -> None:
    upside_down = picture("xx").transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    original = build_dds(upside_down)
    upright = ys_graphics.decode(original, "demo_over")
    assert close(upright, picture("xx"))
    out = ys_graphics.encode(original, upright, "demo_over")
    assert close(ys_graphics.decode(out), upside_down)


def test_unsupported_and_broken_dds_are_rejected() -> None:
    with pytest.raises(GraphicsError, match="DDS"):
        ys_graphics.decode(b"not a dds file" * 20)
    bad = bytearray(build_dds(picture("x")))
    bad[128:132] = (28).to_bytes(4, "little")  # DXGI R8G8B8A8: desteklenmez
    with pytest.raises(GraphicsError, match="BC1 ve BC3"):
        ys_graphics.decode(bytes(bad))


def test_export_originals_load_and_replacements(tmp_path: Path) -> None:
    dds = {
        ys_graphics.member_path("V_1"): build_dds(picture("xx")),
        ys_graphics.source_path("demo_over"): build_dds(picture("yy")),
    }
    names = ys_graphics.export_originals(
        reader(dds), [MEMBER, "EXTENSION/STORY/EN/readme.txt"], tmp_path, [ys_graphics.LOOSE["demo_over"]]
    )
    assert names == ["V_1", "demo_over"]
    assert sorted(p.name for p in (tmp_path / "orijinal").iterdir()) == ["V_1.png", "demo_over.png"]
    assert (tmp_path / "temiz").is_dir()
    assert "orijinal" in (tmp_path / "OKUBENI.txt").read_text(encoding="utf-8")
    assert ys_graphics.load(tmp_path) == ({}, [])  # hiçbir şey çevrilmedi
    picture("zz").save(tmp_path / "temiz" / "V_1.png")
    (tmp_path / "temiz" / "demo_over.png").write_bytes((tmp_path / "orijinal" / "demo_over.png").read_bytes())
    images, warnings = ys_graphics.load(tmp_path)  # özgünle aynı kalan yok sayılır
    assert list(images) == ["V_1"]
    assert warnings == []
    out, notes, problems = ys_graphics.replacements(reader(dds), {TOP, ys_graphics.LOOSE["demo_over"]}, tmp_path)
    assert list(out) == [ys_graphics.member_path("V_1")]
    assert notes == ["V_1"]
    assert problems == []
    assert close(ys_graphics.decode(out[ys_graphics.member_path("V_1")]), picture("zz"))


def test_load_reports_problems_and_keeps_alpha_when_ready_image_has_none(tmp_path: Path) -> None:
    (tmp_path / "orijinal").mkdir()
    (tmp_path / "temiz").mkdir()
    picture("xx").save(tmp_path / "orijinal" / "A.png")
    picture("yy").convert("RGB").save(tmp_path / "temiz" / "A.png")  # saydamlık kaydedilmemiş
    picture("xx", (128, 64)).save(tmp_path / "temiz" / "B.png")  # özgünü yok
    (tmp_path / "temiz" / "notlar.txt").write_text("x", encoding="utf-8")
    picture("zz", (32, 16)).save(tmp_path / "temiz" / "C.png")
    picture("xx").save(tmp_path / "orijinal" / "C.png")  # boyut farklı
    images, warnings = ys_graphics.load(tmp_path)
    assert sorted(images) == ["A", "C"]
    assert images["A"].getchannel("A").tobytes() == picture("xx").getchannel("A").tobytes()
    assert any("B.png" in w and "orijinal" in w for w in warnings)
    assert any("C.png" in w and "boyut" in w for w in warnings)


def test_missing_game_file_is_skipped_with_a_warning(tmp_path: Path) -> None:
    (tmp_path / "orijinal").mkdir()
    (tmp_path / "temiz").mkdir()
    picture("xx").save(tmp_path / "orijinal" / "V_1.png")
    picture("zz").save(tmp_path / "temiz" / "V_1.png")
    out, notes, problems = ys_graphics.replacements(reader({}), set(), tmp_path)
    assert out == {}
    assert notes == []
    assert "oyunda" in problems[0]


def test_folder_for_prefers_environment_then_game_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ys_graphics.ENV, raising=False)
    assert ys_graphics.folder_for(None) is None
    assert ys_graphics.folder_for(tmp_path) is None
    (tmp_path / ys_graphics.FOLDER / "temiz").mkdir(parents=True)
    assert ys_graphics.folder_for(tmp_path) == tmp_path / ys_graphics.FOLDER
    other = tmp_path / "baska"
    (other / "temiz").mkdir(parents=True)
    monkeypatch.setenv(ys_graphics.ENV, str(other))
    assert ys_graphics.folder_for(tmp_path) == other


def _game() -> dict[str, bytes]:
    ni, na = build_nni({MEMBER: build_dds(picture("xx")), "LOC/EN/DATA/A.XSO": b"x"})
    files = {TOP: ni, NA: na, ys_graphics.LOOSE["categories_atlas"]: build_dds(picture("yy"))}
    for name in ys_fonts.FONTS:
        fnt, sheet = build_bmfont(latin_glyphs(outline=True), alpha_only=name == "arial")
        buf = io.BytesIO()
        sheet.save(buf, "PNG")
        files[f"{ys_fonts.FONT_DIR}{name}.fnt"] = fnt
        files[f"{ys_fonts.FONT_DIR}{name}.png"] = buf.getvalue()
    return files


def _tree(files: dict[str, bytes]) -> ContentTree:
    romfs = RomFs(MemoryStorage(build_romfs(files)))
    return ContentTree(TID, "Ana oyun", LayeredRomFs([RomFsLayer("base", romfs)]), lambda: None)


def test_extras_patch_fonts_and_place_translated_pictures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ys_graphics.ENV, raising=False)
    tree = _tree(_game())
    folder = tmp_path / ys_graphics.FOLDER
    ys_graphics.export_originals(reader({ys_graphics.member_path("V_1"): build_dds(picture("xx"))}), [MEMBER], folder)
    picture("zz").save(folder / "temiz" / "V_1.png")
    derived = extras.collect({(TID, "ysorigin"), (TID, "srt")}, {TID: tree}, tmp_path)[TID]
    assert sorted(derived.members) == [ys_graphics.member_path("V_1")]
    assert f"{ys_fonts.FONT_DIR}ysfont.fnt" in derived.files
    assert len(derived.font_notes) == 5
    assert any("V_1" in n for n in derived.notes)
    grouped = extras.split_members(derived)
    assert grouped == {TOP: {MEMBER: derived.members[ys_graphics.member_path("V_1")]}}
    outputs = _export_member_archive(
        tree, TOP, [], translations={}, root=Path("romfs"), result=ExportResult(Path("x")), extra=grouped[TOP]
    )
    built = {rel.as_posix(): blob for rel, blob in outputs}
    archive = nni.NniArchive("n", built[f"romfs/{TOP}"], MemoryStorage(built[f"romfs/{NA}"]))
    assert close(ys_graphics.decode(archive.read(MEMBER)), picture("zz"))
    assert archive.read("LOC/EN/DATA/A.XSO") == b"x"  # dokunulmayan üye aynı


def test_extras_without_graphics_folder_only_patch_fonts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ys_graphics.ENV, raising=False)
    tree = _tree(_game())
    derived = extras.collect({(TID, "ysorigin")}, {TID: tree}, None)[TID]
    assert derived.members == {}
    assert len(derived.files) == 2 * len(ys_fonts.FONTS)
    assert extras.collect({(TID, "msbt")}, {TID: tree}, None) == {}
    assert extras.collect({(TID, "ysorigin")}, {}, None) == {}


def test_unchanged_extra_member_writes_nothing() -> None:
    tree = _tree(_game())
    same = MemberReader(tree.view).read(f"{TOP}>{MEMBER}")
    result = ExportResult(Path("x"))
    out = _export_member_archive(tree, TOP, [], translations={}, root=Path("r"), result=result, extra={MEMBER: same})
    assert out == []
    assert result.unchanged_files == 1
