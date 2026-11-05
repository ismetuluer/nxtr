"""Devil May Cry menü başlığı dokuları: okuma (BC7 / BGRA), Türkçe başlık çizimi ve geri yazma."""

from __future__ import annotations

import struct

import pytest
from PIL import Image, ImageDraw, ImageFont

from nxceviri.core.fontpatch import dmc1_menu as menu
from nxceviri.core.fontpatch.labels import LabelError

FILE_EXIT = 0x3729D0FF  # "File / Exit" dokusu (256×128)


def _t32(texture_id: int, pages: list[bytes], header: int = 0x160) -> bytes:
    """Switch biçimine benzer T32: başlık + sayfa başına DDS (BGRA veya DX10/BC7)."""
    head = bytearray(header)
    head[0:4] = b"\x002MT"
    struct.pack_into("<III", head, 4, len(pages), header, 0x40)
    struct.pack_into("<I", head, 0x14, texture_id)
    return bytes(head) + b"".join(pages)


def _bgra_page(image: Image.Image) -> bytes:
    head = bytearray(128)
    head[0:4] = b"DDS "
    struct.pack_into("<7I", head, 4, 124, 0x81007, image.height, image.width, image.width * image.height * 4, 0, 0)
    struct.pack_into("<2I", head, 76, 32, 0x41)
    return bytes(head) + image.tobytes("raw", "BGRA")


def _bc7_page(width: int, height: int) -> bytes:
    head = bytearray(148)
    head[0:4] = b"DDS "
    struct.pack_into("<7I", head, 4, 124, 0xA1007, height, width, width * height, 1, 1)
    struct.pack_into("<I", head, 80, 4)
    head[84:88] = b"DX10"
    struct.pack_into("<5I", head, 128, 98, 3, 0, 1, 0)
    return bytes(head) + bytes(width * height)  # sıfır blok: geçersiz kip, saydam siyah çözülür


def _file_exit_page() -> Image.Image:
    """Siyah zemin üzerinde beyaz "File" ve "Exit" yazan 256×128 sayfa (gerçek oyun verisi değil)."""
    image = Image.new("RGBA", (256, 128), (0, 0, 0, 255))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("times.ttf", 30)
    draw.text((12, 40), "File", font=font, fill=(255, 255, 255, 255), anchor="ls")
    draw.text((104, 38), "Exit", font=font, fill=(255, 255, 255, 255), anchor="ls")
    draw.rectangle((200, 100, 220, 120), fill=(200, 0, 0, 255))  # pencere dışındaki çizim korunmalı
    return image


def test_read_pages_decodes_bgra_and_bc7() -> None:
    page = _file_exit_page()
    data = _t32(FILE_EXIT, [_bgra_page(page), _bc7_page(256, 128)])
    first, second = menu.read_pages(data)
    assert first.tobytes() == page.tobytes()
    assert second.size == (256, 128)


def test_translate_texture_replaces_words_and_writes_uncompressed() -> None:
    page = _file_exit_page()
    data = _t32(FILE_EXIT, [_bgra_page(page), _bgra_page(page)])
    out = menu.translate_texture(data)
    assert out is not None
    assert len(out) == 0xC0 + 2 * (128 + 256 * 128 * 4)  # PC sürümünün menü dokusuyla aynı boy
    assert struct.unpack_from("<I", out, 8)[0] == 0xC0
    assert struct.unpack_from("<I", out, 0x3C)[0] == 128 + 256 * 128 * 4
    assert menu.texture_id(out) == FILE_EXIT
    after = menu.read_pages(out)
    assert len(after) == 2
    for new in after:
        window = (3, 4, 80, 50)
        assert new.crop(window).tobytes() != page.crop(window).tobytes()  # "File" yerine "Dosya"
        assert new.crop(window).convert("L").getbbox() is not None  # yeni yazı çizildi
        assert new.crop((190, 90, 230, 128)).tobytes() == page.crop((190, 90, 230, 128)).tobytes()
        assert new.getchannel("A").getextrema() == (255, 255)


def test_unknown_texture_is_left_alone() -> None:
    data = _t32(0x12345678, [_bgra_page(_file_exit_page())])
    assert menu.translate_texture(data) is None
    assert menu.translate_texture(b"not a texture") is None


def test_missing_english_word_is_an_error() -> None:
    empty = Image.new("RGBA", (256, 128), (0, 0, 0, 255))
    with pytest.raises(LabelError):
        menu.translate_texture(_t32(FILE_EXIT, [_bgra_page(empty)]))


def test_status_file_menu_textures_are_replaced_and_text_kept() -> None:
    from nxceviri.core.export.layeredfs import TextFileRef, game_file_patches
    from nxceviri.core.formats.dmc1 import Dmc1Plugin, fsd
    from nxceviri.core.formats.dmc1.plugin import MENU_FILES, translate_menu_textures
    from tests.dmc1build import message, table

    texture = _t32(FILE_EXIT, [_bgra_page(_file_exit_page())])
    blocks = [table([message("Equip?")]), texture, b"\x22" * 32]
    head = 4 + 4 * len(blocks)
    pos = (head + 15) & ~15
    offsets, body = [], bytearray()
    for block in blocks:
        body += bytes(-(pos + len(body)) % 16)
        offsets.append(pos + len(body))
        body += block
    data = struct.pack(f"<I{len(blocks)}I", len(blocks), *offsets)
    data += bytes(pos - len(data)) + bytes(body)

    out = translate_menu_textures(data)
    assert [e.source for e in Dmc1Plugin().extract(out)] == ["Equip?"]  # metin bölümüne dokunulmaz
    new_offsets = fsd.read_directory(out, wide=False)
    start = fsd.block_range(out, new_offsets[1], wide=False)[0]
    assert struct.unpack_from("<I", out, start + 8)[0] == 0xC0  # doku sıkıştırılmamış biçimde yeniden yazıldı
    assert out[new_offsets[2] :] == b"\x22" * 32
    no_menu = data[: offsets[1]] + bytes(len(data) - offsets[1])
    assert translate_menu_textures(no_menu) is no_menu  # menü dokusu olmayan dosya aynen kalır

    refs = [TextFileRef("data/dmc1/fsd/r002.fsd", "T", "dmc1"), TextFileRef("a.msbt", "T", "msbt")]
    patches = game_file_patches(refs)
    from nxceviri.core.fontpatch.dmc1_images import FILES

    assert set(patches) == {("T", path) for path in (*MENU_FILES, *FILES)}
