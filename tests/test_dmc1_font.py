"""Devil May Cry yazı dokusu üretici (`etc_e/msg_tex.t32`)."""

from __future__ import annotations

import io
import struct

import pytest
from PIL import Image

from nxceviri.core.fontpatch import dmc1 as font
from nxceviri.core.formats.dmc1 import codec

try:
    REGULAR = font.system_font()
except font.FontError:  # pragma: no cover - serif yazı tipi olmayan makine
    pytest.skip("Sistemde serif yazı tipi yok", allow_module_level=True)

#: Rusça modun, PC Türkçe yamasının ve oyunun `etc_u/msg_tex2.t32` dosyasının DDS başlığı (ilk 32 bayt).
REFERENCE_DDS = bytes.fromhex("444453207c000000071008000001000000010000000004000000000000000000")
PAGE_BYTES = 128 + 256 * 256 * 4


def _pages(data: bytes) -> list[Image.Image]:
    return [
        Image.open(
            io.BytesIO(data[font.HEADER_SIZE + i * PAGE_BYTES : font.HEADER_SIZE + (i + 1) * PAGE_BYTES])
        ).convert("RGBA")
        for i in range(2)
    ]


def _ink(page: Image.Image, origin: tuple[int, int]) -> int:
    x, y = origin
    alphas = page.crop((x, y, x + font.CELL_W, y + font.CELL_H)).tobytes()[3::4]
    return sum(1 for a in alphas if a > 40)


@pytest.fixture(scope="module")
def texture() -> bytes:
    return font.build_texture(codec.FONT_CELLS, REGULAR)


def test_file_layout_matches_the_reference_format(texture: bytes) -> None:
    assert len(texture) == font.HEADER_SIZE + 2 * PAGE_BYTES == 524736  # topluluk dokularıyla aynı boyut
    assert texture[:4] == bytes((0x00, 0x32, 0x33, 0x54))
    assert struct.unpack_from("<III", texture, 4) == (1, font.HEADER_SIZE, 0x80080)
    # 0x14: dokunun sabit kimliği (özgün dokuda, Rusça modda ve PC yamasında aynı); içerik özeti değil
    assert struct.unpack_from("<I", texture, 0x14)[0] == font.TEXTURE_ID == 0x4FE396F0
    for i in range(2):  # iki sıkıştırılmamış DDS sayfası; DDS başlığı olmayan dosya oyunu çökertti
        start = font.HEADER_SIZE + i * PAGE_BYTES
        assert texture[start : start + 32] == REFERENCE_DDS


def test_every_cell_except_0x47_has_a_glyph(texture: bytes) -> None:
    """Oyun dokudaki her hücreyi ölçer; boş hücreli bir doku Switch'te oyunu açılışta çökertti."""
    page1, page2 = _pages(texture)
    assert [code for code in range(0x80) if _ink(page1, font.cell_origin(code)) == 0] == [0x47]
    assert [code for code in range(0x80) if _ink(page2, font.cell_origin(code))] == list(range(9))


def test_cells_are_16_by_32_without_shift(texture: bytes) -> None:
    assert font.cell_origin(0x00) == (0, 0)
    assert font.cell_origin(0x0E) == (224, 0)  # 'A'
    assert font.cell_origin(0x10) == (0, 32)  # 'C'
    page1, _ = _pages(texture)
    x, y = font.cell_origin(0x0E)
    box = page1.crop((x, y, x + 16, y + 32)).getchannel("A").point(lambda a: 255 if a > 60 else 0).getbbox()
    assert box is not None
    assert box[1] >= 2
    assert box[3] <= 29


def test_turkish_letters_differ_from_their_base_letters(texture: bytes) -> None:
    page1, _ = _pages(texture)
    cells = {
        char: page1.crop(
            (*font.cell_origin(code), font.cell_origin(code)[0] + 16, font.cell_origin(code)[1] + 32)
        ).tobytes()
        for code, char in codec.FONT_CELLS.items()
    }
    for turkish, base in (("ş", "s"), ("ğ", "g"), ("ı", "i"), ("İ", "I"), ("Ş", "S"), ("Ğ", "G")):
        assert cells[turkish] != cells[base]


def test_errors() -> None:
    with pytest.raises(font.FontError):
        font.build_texture({0x80: "x"}, REGULAR)
    with pytest.raises(font.FontError):
        font.build_texture({0x0E: "A"}, REGULAR.with_name("yok.ttf"))
