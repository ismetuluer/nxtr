"""Basit BC7 kodlayıcı (yalnızca kip 6: tek bölge, RGBA 7777 + p-biti, 4 bit indis).

Oyun dokularındaki yazıyı değiştirmek için yeterlidir: yalnızca değişen 4×4 bloklar yeniden kodlanır, diğer
bloklar özgün baytlarıyla kalır. Çözme Pillow ile yapılır (`Image.frombytes(..., "bcn", 7)`).
"""

from __future__ import annotations

from PIL import Image

_WEIGHTS = (0, 4, 9, 13, 17, 21, 26, 30, 34, 38, 43, 47, 51, 55, 60, 64)
BLOCK_BYTES = 16


def decode(data: bytes, width: int, height: int) -> Image.Image:
    return Image.frombytes("RGBA", (width, height), data[: width * height], "bcn", 7)


def _principal_axis(pixels: list[tuple[int, int, int, int]], mean: list[float]) -> list[float]:
    cov = [[0.0] * 4 for _ in range(4)]
    for p in pixels:
        d = [p[i] - mean[i] for i in range(4)]
        for i in range(4):
            for j in range(i, 4):
                cov[i][j] += d[i] * d[j]
    for i in range(4):
        for j in range(i):
            cov[i][j] = cov[j][i]
    axis = [1.0, 1.0, 1.0, 1.0]
    for _ in range(6):  # kuvvet yinelemesi
        nxt = [sum(cov[i][j] * axis[j] for j in range(4)) for i in range(4)]
        norm = max(abs(v) for v in nxt)
        if norm < 1e-9:
            return [0.0, 0.0, 0.0, 0.0]
        axis = [v / norm for v in nxt]
    return axis


def _quantize(endpoint: list[float]) -> tuple[list[int], int]:
    """8 bitlik uç rengi 7 bit + ortak p-bitine indirir; en az hatalı p seçilir."""
    best: tuple[float, list[int], int] | None = None
    for p in (0, 1):
        q = [min(127, max(0, round((v - p) / 2))) for v in endpoint]
        # alfa ağırlıklı: oyun dokularında alfa çoğunlukla tam 255'tir ve öyle kalmalıdır
        err = sum(
            (((c << 1) | p) - v) ** 2 * (4 if i == 3 else 1) for i, (c, v) in enumerate(zip(q, endpoint, strict=True))
        )
        if best is None or err < best[0]:
            best = (err, q, p)
    assert best is not None
    return best[1], best[2]


def encode_block(pixels: list[tuple[int, int, int, int]]) -> bytes:
    """16 pikseli (satır satır) kip 6 BC7 bloğuna kodlar."""
    mean = [sum(p[i] for p in pixels) / 16 for i in range(4)]
    axis = _principal_axis(pixels, mean)
    ts = [sum((p[i] - mean[i]) * axis[i] for i in range(4)) for p in pixels]
    lo, hi = min(ts), max(ts)
    e0 = [min(255.0, max(0.0, mean[i] + lo * axis[i])) for i in range(4)]
    e1 = [min(255.0, max(0.0, mean[i] + hi * axis[i])) for i in range(4)]
    q0, p0 = _quantize(e0)
    q1, p1 = _quantize(e1)
    c0 = [(c << 1) | p0 for c in q0]
    c1 = [(c << 1) | p1 for c in q1]
    palette = [[((64 - w) * c0[i] + w * c1[i] + 32) >> 6 for i in range(4)] for w in _WEIGHTS]
    indices = []
    for p in pixels:
        best_i, best_e = 0, 1 << 30
        for k, c in enumerate(palette):
            e = (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2 + (p[2] - c[2]) ** 2 + (p[3] - c[3]) ** 2
            if e < best_e:
                best_i, best_e = k, e
        indices.append(best_i)
    if indices[0] >= 8:  # ilk pikselin indisinin üst biti örtüktür (0): uçlar yer değiştirir
        q0, q1, p0, p1 = q1, q0, p1, p0
        indices = [15 - i for i in indices]
    bits = 1 << 6  # kip 6: 7 bitlik "0000001"
    pos = 7
    for channel in range(4):
        for q in (q0, q1):
            bits |= q[channel] << pos
            pos += 7
    bits |= p0 << pos
    bits |= p1 << (pos + 1)
    pos += 2
    for n, idx in enumerate(indices):
        width = 3 if n == 0 else 4
        bits |= idx << pos
        pos += width
    return bits.to_bytes(BLOCK_BYTES, "little")


def reencode(original: bytes, before: Image.Image, after: Image.Image) -> bytes:
    """`before` (özgün `original` verisinin çözülmüşü) ile `after` arasında değişen blokları yeniden kodlar."""
    width, height = after.size
    out = bytearray(original[: width * height])
    old, new = before.tobytes(), after.tobytes()
    stride = width * 4
    for by in range(height // 4):
        for bx in range(width // 4):
            rows = [(by * 4 + r) * stride + bx * 16 for r in range(4)]
            if all(old[r : r + 16] == new[r : r + 16] for r in rows):
                continue
            pixels = []
            for r in rows:
                for x in range(4):
                    i = r + x * 4
                    pixels.append((new[i], new[i + 1], new[i + 2], new[i + 3]))
            at = (by * (width // 4) + bx) * BLOCK_BYTES
            out[at : at + BLOCK_BYTES] = encode_block(pixels)
    return bytes(out)
