"""Basit BC1 (DXT1) kodlayıcı/çözücü: dört renkli kip, alfasız. Yalnızca değişen 4×4 bloklar yeniden kodlanır."""

from __future__ import annotations

import struct

from PIL import Image

BLOCK_BYTES = 8


def decode(data: bytes, width: int, height: int) -> Image.Image:
    return Image.frombytes("RGBA", (width, height), data[: width * height // 2], "bcn", 1)


def _rgb565(color: tuple[int, int, int]) -> int:
    return ((color[0] >> 3) << 11) | ((color[1] >> 2) << 5) | (color[2] >> 3)


def _expand(value: int) -> tuple[int, int, int]:
    r, g, b = (value >> 11) & 31, (value >> 5) & 63, value & 31
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def encode_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    """16 pikseli (satır satır) 4 renkli BC1 bloğuna kodlar; uçlar renk kutusunun içeri çekilmiş köşeleridir."""
    reds = [p[0] for p in pixels]
    greens = [p[1] for p in pixels]
    blues = [p[2] for p in pixels]
    lo = [min(reds), min(greens), min(blues)]
    hi = [max(reds), max(greens), max(blues)]
    inset = [(h - lw) // 16 for lw, h in zip(lo, hi, strict=True)]
    c0 = _rgb565((hi[0] - inset[0], hi[1] - inset[1], hi[2] - inset[2]))
    c1 = _rgb565((lo[0] + inset[0], lo[1] + inset[1], lo[2] + inset[2]))
    if c0 == c1:
        indices = 0
    else:
        if c0 < c1:
            c0, c1 = c1, c0
        a, b = _expand(c0), _expand(c1)
        palette = [
            a,
            b,
            tuple((2 * a[i] + b[i]) // 3 for i in range(3)),
            tuple((a[i] + 2 * b[i]) // 3 for i in range(3)),
        ]
        indices = 0
        for n, p in enumerate(pixels):
            errors = [sum((p[i] - color[i]) ** 2 for i in range(3)) for color in palette]
            indices |= errors.index(min(errors)) << (2 * n)
    return struct.pack("<HHI", c0, c1, indices)


def reencode(original: bytes, before: Image.Image, after: Image.Image) -> bytes:
    """`before` ile `after` arasında değişen blokları yeniden kodlar (`bc7.reencode` ile aynı sözleşme)."""
    width, height = after.size
    out = bytearray(original[: width * height // 2])
    old, new = before.tobytes(), after.tobytes()
    stride = width * 4
    for by in range(height // 4):
        for bx in range(width // 4):
            rows = [(by * 4 + r) * stride + bx * 16 for r in range(4)]
            if all(old[r : r + 16] == new[r : r + 16] for r in rows):
                continue
            pixels = [(new[i], new[i + 1], new[i + 2], new[i + 3]) for r in rows for i in range(r, r + 16, 4)]
            at = (by * (width // 4) + bx) * BLOCK_BYTES
            out[at : at + BLOCK_BYTES] = encode_block(pixels)
    return bytes(out)
