"""BC7 kodlayıcı (etcpak içindeki bc7enc; tüm kipler) ve çözücü (Pillow).

Oyun dokularındaki yazıyı değiştirmek için: sayfa bir kez kodlanır, yalnızca değişen 4×4 bloklar özgün sayfaya
kopyalanır, diğer bloklar özgün baytlarıyla kalır. Çözme Pillow ile yapılır (`Image.frombytes(..., "bcn", 7)`).
"""

from __future__ import annotations

import etcpak
from PIL import Image

BLOCK_BYTES = 16


def decode(data: bytes, width: int, height: int) -> Image.Image:
    return Image.frombytes("RGBA", (width, height), data[: width * height], "bcn", 7)


_UBER_LEVEL = 2
#: Opak bloklarda yalnızca 0-3. kipler (alfa örtük 255): tüm kiplerde bc7enc alfayı 254 yazıyordu.
_OPAQUE_MODES = 0b1111
_ALL_MODES = 0xFFFFFFFF
_OPAQUE_ROW = bytes([255] * 4)


def _compress(raw: bytes, width: int, height: int, modes: int) -> bytes:
    params = etcpak.BC7CompressBlockParams()
    params.m_uber_level = _UBER_LEVEL
    params.m_mode_mask = modes
    return bytes(etcpak.compress_bc7(raw, width, height, params))


def encode(image: Image.Image) -> bytes:
    """Tüm sayfayı BC7'ye kodlar (etcpak/bc7enc); opak bloklarda alfa tam 255 kalır."""
    width, height = image.size
    if width % 4 or height % 4:
        raise ValueError("BC7 için görüntü boyutları 4'ün katı olmalı")
    rgba = image.convert("RGBA")
    raw = rgba.tobytes()
    mixed = _compress(raw, width, height, _ALL_MODES)
    opaque = _compress(raw, width, height, _OPAQUE_MODES)
    alpha = rgba.getchannel("A").tobytes()
    out = bytearray(mixed)
    blocks_per_row = width // 4
    for by in range(height // 4):
        for bx in range(blocks_per_row):
            start = by * 4 * width + bx * 4
            if all(alpha[start + r * width : start + r * width + 4] == _OPAQUE_ROW for r in range(4)):
                at = (by * blocks_per_row + bx) * BLOCK_BYTES
                out[at : at + BLOCK_BYTES] = opaque[at : at + BLOCK_BYTES]
    return bytes(out)


def encode_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    """16 pikseli (satır satır) tek bir BC7 bloğuna kodlar."""
    block = Image.new("RGBA", (4, 4))
    block.putdata(pixels)
    return encode(block)


def reencode(original: bytes, before: Image.Image, after: Image.Image) -> bytes:
    """`before` (özgün `original` verisinin çözülmüşü) ile `after` arasında değişen blokları yeniden kodlar."""
    width, height = after.size
    out = bytearray(original[: width * height])
    old, new = before.tobytes(), after.tobytes()
    stride = width * 4
    encoded: bytes | None = None
    for by in range(height // 4):
        for bx in range(width // 4):
            rows = [(by * 4 + r) * stride + bx * 16 for r in range(4)]
            if all(old[r : r + 16] == new[r : r + 16] for r in rows):
                continue
            if encoded is None:
                encoded = encode(after)
            at = (by * (width // 4) + bx) * BLOCK_BYTES
            out[at : at + BLOCK_BYTES] = encoded[at : at + BLOCK_BYTES]
    return bytes(out)
