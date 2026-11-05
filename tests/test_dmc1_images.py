"""Oyun resimlerindeki yazıyı yerinde değiştirme: BC7 kodlayıcı, sayfa bulma, etiket çizimi (elle üretilmiş resim)."""

from __future__ import annotations

import struct

import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFont

from nxceviri.core.fontpatch import bc7
from nxceviri.core.fontpatch.dmc1_images import FILES, PAGES, iter_pages, page_key, translate_file
from nxceviri.core.fontpatch.labels import Label, LabelError, draw_label, find_font


def _bc7_page(image: Image.Image) -> bytes:
    head = bytearray(148)
    head[0:4] = b"DDS "
    struct.pack_into("<7I", head, 4, 124, 0xA1007, image.height, image.width, image.width * image.height, 1, 1)
    struct.pack_into("<I", head, 80, 4)
    head[84:88] = b"DX10"
    struct.pack_into("<5I", head, 128, 98, 3, 0, 1, 0)
    blank = bytes(image.width * image.height)
    return bytes(head) + bc7.reencode(blank, Image.new("RGBA", image.size, (1, 2, 3, 4)), image)


def _bgra_page(image: Image.Image) -> bytes:
    head = bytearray(128)
    head[0:4] = b"DDS "
    struct.pack_into("<7I", head, 4, 124, 0x81007, image.height, image.width, image.width * image.height * 4, 0, 0)
    struct.pack_into("<2I", head, 76, 32, 0x41)
    struct.pack_into("<I", head, 88, 32)
    return bytes(head) + image.tobytes("raw", "BGRA")


def _label_page(alpha: bool = False) -> Image.Image:
    """Siyah (veya saydam) zeminde parıltılı beyaz "Holy Water" yazan 128×64 sayfa (gerçek oyun verisi değil)."""
    background = (0, 0, 0, 0) if alpha else (0, 0, 0, 255)
    image = Image.new("RGBA", (128, 64), background)
    font = ImageFont.truetype(str(find_font("brush")), 22)
    ImageDraw.Draw(image).text((8, 36), "Holy Water", font=font, fill=(240, 240, 240, 255), anchor="ls")
    return image


def test_bc7_solid_and_unchanged_blocks() -> None:
    block = bc7.encode_block([(10, 200, 30, 255)] * 16)
    assert len(block) == bc7.BLOCK_BYTES
    pixel = bc7.decode(block, 4, 4).getpixel((0, 0))
    assert isinstance(pixel, tuple)
    assert pixel[3] == 255  # alfa tam kalır
    assert all(abs(a - b) <= 1 for a, b in zip(pixel, (10, 200, 30), strict=False))  # ortak p-biti: ±1
    image = _label_page()
    data = _bc7_page(image)[148:]
    decoded = bc7.decode(data, 128, 64)
    assert bc7.reencode(data, decoded, decoded) == data  # değişmeyen bloklar aynen kalır
    diff = ImageChops.difference(decoded, image).convert("L")
    assert max(diff.tobytes()) < 48  # kip 6 yeterince yakın


def test_iter_pages_finds_bc7_and_bgra_and_skips_garbage() -> None:
    page = _label_page()
    data = b"\x07" * 40 + _bc7_page(page) + b"DDS |garbage" + b"\0" * 64 + _bgra_page(page) + b"\x09" * 8
    found = list(iter_pages(data))
    assert [p.compressed for p in found] == [True, False]
    assert found[1].image.tobytes() == page.tobytes()


def test_translate_file_changes_only_known_pages_in_place() -> None:
    page = _label_page()
    other = Image.new("RGBA", (64, 64), (0, 0, 0, 255))
    data = b"HEAD" + _bgra_page(page) + _bc7_page(page) + _bgra_page(other) + b"TAIL"
    pages = list(iter_pages(data))
    table: dict[str, tuple[Label, ...]] = {
        page_key(pages[0].image): (Label((0, 4, 128, 50), "Holy Water", "Kutsal Su", "brush"),),
        page_key(pages[1].image): (Label((0, 4, 128, 50), "Holy Water", "Kutsal Su", "brush"),),
    }
    out = translate_file(data, table)
    assert len(out) == len(data)
    assert out[:4] == b"HEAD"
    assert out[-4:] == b"TAIL"
    new = list(iter_pages(out))
    assert new[0].image.tobytes() != pages[0].image.tobytes()
    assert new[1].image.tobytes() != pages[1].image.tobytes()
    assert new[2].image.tobytes() == pages[2].image.tobytes()  # tabloda olmayan sayfa aynen kalır
    assert out[new[2].offset :] == data[pages[2].offset :]
    assert translate_file(data, {}) == data


def test_alpha_page_keeps_transparent_background() -> None:
    page = _label_page(alpha=True)
    out = draw_label(page, Label((0, 4, 128, 50), "Holy Water", "Kutsal Su", "brush"))
    alpha = out.getchannel("A")
    assert alpha.getpixel((2, 60)) == 0  # pencere dışı saydam kalır
    assert max(alpha.crop((0, 4, 128, 50)).tobytes()) > 200  # yeni yazı opak


def test_missing_english_text_is_an_error() -> None:
    with pytest.raises(LabelError):
        draw_label(Image.new("RGBA", (64, 32), (0, 0, 0, 255)), Label((0, 0, 64, 32), "A", "B", "brush"))


def test_table_is_consistent() -> None:
    assert all(path.startswith("data/dmc1/") for path in FILES)
    for labels in PAGES.values():
        for label in labels:
            left, top, right, bottom = label.window
            assert 0 <= left < right
            assert 0 <= top < bottom
            assert label.english
            assert label.turkish
            find_font(label.style)


def _art_paragraph() -> Image.Image:
    """Desenli (resim gibi) zemin üzerinde üç satırlık beyaz paragraf (gerçek oyun verisi değil)."""
    image = Image.new("RGBA", (240, 120), (90, 30, 30, 255))
    draw = ImageDraw.Draw(image)
    for x in range(0, 240, 6):
        draw.line((x, 0, x - 60, 120), fill=(120, 40, 40, 255), width=2)
    font = ImageFont.truetype(str(find_font("bold")), 16)
    for i, line in enumerate(("First line of text", "second line here", "third")):
        draw.text((10, 30 + i * 26), line, font=font, fill=(250, 250, 250, 255), anchor="ls")
    return image


def test_paragraph_lines_are_found_and_redrawn() -> None:
    page = _art_paragraph()
    label = Label(
        (2, 8, 238, 110),
        "First line of text\nsecond line here\nthird",
        "Birinci satır\nikinci satır\n ",
        "bold",
        "left",
        ink=(250, 250, 250),
        glow=(40, 40, 40),
    )
    out = draw_label(page, label)
    assert out.size == page.size
    third = (10, 66, 120, 90)
    assert max(out.crop(third).convert("L").tobytes()) < 200  # boş bırakılan satırın özgün yazısı silindi
    first = (10, 12, 200, 36)
    assert max(out.crop(first).convert("L").tobytes()) > 200  # yeni yazı çizildi
    with pytest.raises(LabelError):
        draw_label(page, Label(label.window, "a\nb", "x", "bold"))


def test_user_graphics_replace_pages_and_are_matched_by_original(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from nxceviri.core.fontpatch import dmc1_graphics

    original = _label_page()
    turkish = original.copy()
    ImageDraw.Draw(turkish).rectangle((60, 0, 127, 20), fill=(250, 0, 0, 255))
    (tmp_path / "orijinal").mkdir()
    (tmp_path / "temiz").mkdir()
    original.save(tmp_path / "orijinal" / "a.png")
    turkish.save(tmp_path / "temiz" / "a.png")
    original.save(tmp_path / "orijinal" / "b.png")  # hiç değiştirilmemiş sayfa yok sayılır
    original.save(tmp_path / "temiz" / "b.png")
    original.save(tmp_path / "orijinal" / "status_u__mssn_ips_01.ip2__son_kare.png")
    turkish.save(tmp_path / "temiz" / "status_u__mssn_ips_01.ip2__son_kare.png")
    graphics = dmc1_graphics.load(tmp_path)
    assert list(graphics.pages) == [page_key(original)]
    assert list(graphics.animations) == ["data/dmc1/status_u/mssn_ips_01.ip2"]
    data = b"HEAD" + _bgra_page(original) + _bgra_page(Image.new("RGBA", (64, 64), (0, 0, 0, 255))) + b"TAIL"
    out = translate_file(data, {}, graphics.pages)
    assert len(out) == len(data)
    assert next(iter(iter_pages(out))).image.tobytes() == turkish.tobytes()
    assert out[-4:] == b"TAIL"
    assert translate_file(data, {}, {}) == data
