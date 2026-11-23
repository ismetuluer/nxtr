"""Başlık bandı animasyonlarını Türkçeleştirme (elle üretilmiş küçük kareler; gerçek oyun verisi değil)."""

from __future__ import annotations

import struct

from PIL import Image

from nxceviri.core.fontpatch import bc1, bc7
from nxceviri.core.fontpatch.fsdmsg_animation import animate_banner, translate_animation
from nxceviri.core.fontpatch.fsdmsg_images import iter_pages

W, H = 32, 16


def _frame(shift: int, letters: tuple[int, int, int] | None) -> Image.Image:
    """Her karede kayan arka plan (kırmızı kanal) ve sabit bir "yazı" bloğu."""
    image = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    for x in range(W):
        for y in range(H):
            image.putpixel((x, y), (((x // 4 + shift) % 4) * 64, 0, 0, 255))
    if letters is not None:
        for x in range(8, 24):
            for y in range(4, 12):
                image.putpixel((x, y), (*letters, 255))
    return image


def _px(image: Image.Image, x: int, y: int) -> tuple[int, ...]:
    pixel = image.getpixel((x, y))
    assert isinstance(pixel, tuple)
    return pixel


def _dds(image: Image.Image, fmt: str) -> bytes:
    if fmt == "bc7":
        head = bytearray(148)
        head[0:4] = b"DDS "
        struct.pack_into("<7I", head, 4, 124, 0xA1007, H, W, W * H, 1, 1)
        struct.pack_into("<I", head, 80, 4)
        head[84:88] = b"DX10"
        struct.pack_into("<5I", head, 128, 98, 3, 0, 1, 0)
        blank = bytes(W * H)
        return bytes(head) + bc7.reencode(blank, Image.new("RGBA", image.size, (1, 2, 3, 4)), image)
    head = bytearray(128)
    head[0:4] = b"DDS "
    struct.pack_into("<7I", head, 4, 124, 0xA1007, H, W, W * H // 2, 1, 1)
    struct.pack_into("<I", head, 80, 4)
    head[84:88] = b"DXT1"
    blank = bytes(W * H // 2)
    return bytes(head) + bc1.reencode(blank, Image.new("RGBA", image.size, (1, 2, 3, 4)), image)


def _clip(fmt: str, letters: tuple[int, int, int], frames: int = 4) -> bytes:
    return b"".join(_dds(_frame(i, letters), fmt) for i in range(frames))


ENGLISH = (192, 192, 192)
TURKISH = (0, 192, 0)


def test_banner_keeps_background_motion_and_replaces_letters_in_every_frame() -> None:
    english = [_frame(i, ENGLISH) for i in range(4)]
    last_turkish = _frame(3, TURKISH)
    result = animate_banner(english, english[-1], last_turkish)
    assert len(result) == 4
    for i, frame in enumerate(result):
        assert _px(frame, 16, 8)[:3] == TURKISH  # yazı her karede Türkçe
        assert _px(frame, 2, 2) == _px(english[i], 2, 2)  # yazı dışı arka plan özgün karede kalır
    assert _px(result[0], 2, 2) != _px(result[1], 2, 2)  # arka plan hareketi korunur
    assert result[-1].tobytes() == last_turkish.tobytes()


def test_banner_without_difference_returns_frames_unchanged() -> None:
    english = [_frame(i, ENGLISH) for i in range(3)]
    assert animate_banner(english, english[-1], english[-1]) == english


def test_translate_animation_handles_bc1_and_bc7_banners_and_keeps_size() -> None:
    for fmt in ("bc1", "bc7"):
        data = _clip(fmt, ENGLISH)
        english_last = list(iter_pages(data))[-1].image
        out = translate_animation(data, english_last, _frame(3, TURKISH))
        assert len(out) == len(data)
        pages = list(iter_pages(out))
        assert len(pages) == 4
        assert all(_px(p.image, 16, 8)[0] < 40 and _px(p.image, 16, 8)[1] > 150 for p in pages)


def test_translate_animation_ignores_other_files() -> None:
    data = _clip("bc1", ENGLISH)
    assert translate_animation(data, _frame(0, (1, 2, 3)), _frame(3, TURKISH)) == data
