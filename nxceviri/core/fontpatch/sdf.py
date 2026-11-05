"""İşaretli mesafe alanı (SDF) yardımcıları: TextMeshPro atlaslarındaki gliflerle çalışmak için.

TMP SDF atlaslarında her piksel, glif kenarına olan işaretli uzaklığı tutar: kenarda ≈127,5,
içeride büyür, dışarıda azalır; eğim (piksel başına değer) atlas dolgusundan gelir. Burada
glifler `Field` olarak (genişlik × yükseklik, satır satır, üstten) tutulur.

- Var olan glif parçaları birleştirilirken (ör. "s" + çengel) değerlerin en büyüğü alınır; iki
  SDF'nin birleşimi için doğru sonuçtur ve özgün glifin kalitesini bozmaz.
- Bir parçayı ayırmak gerektiğinde (ör. "i"nin noktası) ikili maske çıkarılır ve mesafe alanı
  tam Öklid uzaklık dönüşümüyle (Felzenszwalb–Huttenlocher) yeniden hesaplanır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EDGE = 127.5
_INF = 1e20


@dataclass
class Field:
    width: int
    height: int
    values: list[float]  # satır satır, üst satır önce

    @classmethod
    def blank(cls, width: int, height: int) -> Field:
        return cls(width, height, [0.0] * (width * height))

    def get(self, x: int, y: int) -> float:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.values[y * self.width + x]
        return 0.0

    def mask(self) -> list[bool]:
        return [v >= EDGE for v in self.values]

    def to_bytes(self) -> bytes:
        return bytes(max(0, min(255, round(v))) for v in self.values)


def _edt_1d(f: list[float]) -> list[float]:
    """Kare uzaklıkların 1B alt zarfı (Felzenszwalb & Huttenlocher, 2012)."""
    n = len(f)
    v = [0] * n
    z = [0.0] * (n + 1)
    k = 0
    z[0], z[1] = -_INF, _INF
    for q in range(1, n):
        s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k])
        while s <= z[k]:
            k -= 1
            s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k])
        k += 1
        v[k] = q
        z[k] = s
        z[k + 1] = _INF
    d = [0.0] * n
    k = 0
    for q in range(n):
        while z[k + 1] < q:
            k += 1
        d[q] = (q - v[k]) * (q - v[k]) + f[v[k]]
    return d


def _squared_distance(sites: list[bool], width: int, height: int) -> list[float]:
    """Her pikselin en yakın `True` pikseline kare uzaklığı."""
    grid = [0.0 if s else _INF for s in sites]
    for x in range(width):
        col = _edt_1d([grid[y * width + x] for y in range(height)])
        for y in range(height):
            grid[y * width + x] = col[y]
    for y in range(height):
        row = _edt_1d(grid[y * width : (y + 1) * width])
        grid[y * width : (y + 1) * width] = row
    return grid


def from_mask(mask: list[bool], width: int, height: int, slope: float) -> Field:
    """İkili maskeden SDF: kenar ≈127,5, piksel başına `slope` kadar değişir."""
    if not any(mask):
        return Field.blank(width, height)
    to_inside = _squared_distance(mask, width, height)
    to_outside = _squared_distance([not m for m in mask], width, height)
    values = []
    for i, inside in enumerate(mask):
        # Piksel merkezinden kenara: en yakın karşı türden pikselin merkezine uzaklık − yarım piksel.
        d = math.sqrt(to_outside[i]) - 0.5 if inside else 0.5 - math.sqrt(to_inside[i])
        values.append(EDGE + d * slope)
    return Field(width, height, values)


def union(base: Field, part: Field, dx: int, dy: int) -> None:
    """`part`'ı `base` üzerine (dx, dy) kaydırarak birleştirir (yerinde)."""
    for y in range(part.height):
        ty = y + dy
        if not 0 <= ty < base.height:
            continue
        for x in range(part.width):
            tx = x + dx
            if 0 <= tx < base.width:
                i = ty * base.width + tx
                v = part.values[y * part.width + x]
                base.values[i] = max(base.values[i], v)


def components(mask: list[bool], width: int, height: int) -> list[list[int]]:
    """8-komşulu bağlı bileşenler (piksel indeksleri), büyükten küçüğe."""
    seen = [False] * len(mask)
    out = []
    for start, m in enumerate(mask):
        if not m or seen[start]:
            continue
        stack = [start]
        seen[start] = True
        comp = []
        while stack:
            i = stack.pop()
            comp.append(i)
            x, y = i % width, i // width
            for ny in (y - 1, y, y + 1):
                for nx in (x - 1, x, x + 1):
                    if 0 <= nx < width and 0 <= ny < height:
                        j = ny * width + nx
                        if mask[j] and not seen[j]:
                            seen[j] = True
                            stack.append(j)
        out.append(comp)
    out.sort(key=len, reverse=True)
    return out


def bbox(indices: list[int], width: int) -> tuple[int, int, int, int]:
    """(sol, üst, sağ, alt) — sağ/alt dahil değil."""
    xs = [i % width for i in indices]
    ys = [i // width for i in indices]
    return min(xs), min(ys), max(xs) + 1, max(ys) + 1


def estimate_slope(field: Field) -> float:
    """Var olan bir glifin SDF eğimi (piksel başına değer): orta satırdaki tutarlı farkların ortancası."""
    diffs = []
    for y in range(field.height // 3, 2 * field.height // 3 + 1):
        for x in range(field.width - 1):
            a, b = field.get(x, y), field.get(x + 1, y)
            if 20 < a < 235 and 20 < b < 235:
                diffs.append(abs(a - b))
    diffs = [d for d in diffs if d > 1]
    if not diffs:
        return 12.75
    diffs.sort()
    return diffs[len(diffs) // 2]
