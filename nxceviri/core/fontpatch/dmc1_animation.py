"""Görev girişi animasyonlarını (`mssn_ips_*.ip2`: 60 kare DXT1) Türkçe son kareye uyarlama.

Özgün animasyonda görev adı ve açıklaması dalgalanarak belirir. Kullanıcı yalnızca son kareyi Türkçeleştirir;
ara kareler buradan türetilir. Son karede yazının bulunduğu bölgeler (özgün ile Türkçe son kare arasındaki fark)
ayrı parçalara ayrılır; her parçanın "belirme oranı" özgün karelerdeki parlaklık artışından ölçülür (başlık erken,
açıklama geç belirir). Karedeki o bölge, özgün karenin yazısı silinmiş hâli ile Türkçe son karenin bu orana göre
karışımına çevrilir. Dalgalanma efekti yoktur; yazı aynı zamanlamayla yumuşakça belirir.
"""

from __future__ import annotations

from PIL import Image, ImageChops, ImageFilter, ImageMath

from nxceviri.core.fontpatch import bc1
from nxceviri.core.fontpatch.dmc1_images import Page, iter_pages, page_key

_GRID = 8  # bölge ayırma çözünürlüğü (piksel)
_MIN_CELLS = 6  # bundan küçük bölgeler gürültüdür
_SHRINK = 4  # parlaklık ölçümü ve doldurma bu kadar küçültülmüş karede yapılır


def _difference_mask(before: Image.Image, after: Image.Image) -> Image.Image:
    diff = ImageChops.difference(before.convert("RGB"), after.convert("RGB")).convert("L")
    return diff.point(lambda v: 255 if v > 14 else 0)


def _components(mask: Image.Image) -> list[Image.Image]:
    """Maskenin birbirine yakın (yaklaşık 3 hücre) bölgeleri, her biri tam çözünürlükte yumuşak kenarlı maske."""
    cells = mask.reduce(_GRID).point(lambda v: 255 if v > 0 else 0).filter(ImageFilter.MaxFilter(7))
    width, height = cells.size
    px = cells.load()
    assert px is not None
    seen: set[tuple[int, int]] = set()
    parts: list[Image.Image] = []
    for y in range(height):
        for x in range(width):
            if not px[x, y] or (x, y) in seen:
                continue
            stack, members = [(x, y)], []
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                members.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < width and 0 <= ny < height and px[nx, ny] and (nx, ny) not in seen:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            if len(members) < _MIN_CELLS:
                continue
            region = Image.new("L", cells.size)
            rp = region.load()
            assert rp is not None
            for cx, cy in members:
                rp[cx, cy] = 255
            parts.append(region.resize(mask.size, Image.Resampling.NEAREST).filter(ImageFilter.GaussianBlur(6)))
    return parts


def _luminance(small: Image.Image, part: Image.Image) -> float:
    """Parçanın ağırlıklı ortalama parlaklığı (küçültülmüş kare ve parça üzerinde)."""
    weights = part.tobytes()
    total = sum(weights) or 1
    return sum(a * b for a, b in zip(small.convert("L").tobytes(), weights, strict=True)) / total


def _fill(frame: Image.Image, hole: Image.Image) -> Image.Image:
    """Yazının silinmiş hâli: bölge çevresindeki karelerin renginden yumuşakça doldurulur (küçük çözünürlükte)."""
    small = frame.convert("RGB").reduce(_SHRINK)
    hole_small = hole.reduce(_SHRINK).point(lambda v: 255 if v > 40 else 0)
    known = ImageChops.invert(hole_small)
    out = small
    done = known
    for radius in (2, 5, 12):
        den = known.filter(ImageFilter.GaussianBlur(radius))
        den_f = den.convert("F")
        premult = ImageChops.multiply(small, Image.merge("RGB", [known] * 3)).filter(ImageFilter.GaussianBlur(radius))
        bands = [
            ImageMath.lambda_eval(lambda a: a["n"] * 255.0 / (a["d"] + 0.01), n=c.convert("F"), d=den_f).convert("L")
            for c in premult.split()
        ]
        ok = den.point(lambda v: 255 if v > 8 else 0)
        take = ImageChops.subtract(ok, done)
        out = Image.composite(Image.merge("RGB", bands), out, take)
        done = ImageChops.lighter(done, ok)
    return out.resize(frame.size, Image.Resampling.BILINEAR)


def animate_pages(frames: list[Image.Image], last_english: Image.Image, last_turkish: Image.Image) -> list[Image.Image]:
    """Özgün kareleri Türkçe son kareye uyarlanmış karelere çevirir."""
    parts = _components(_difference_mask(last_english, last_turkish))
    if not parts:
        return frames
    turkish = last_turkish.convert("RGB")
    small_parts = [p.reduce(_SHRINK) for p in parts]
    end = [_luminance(last_english.reduce(_SHRINK), p) for p in small_parts]
    start = [_luminance(frames[0].reduce(_SHRINK), p) for p in small_parts]
    progress = [0.0] * len(parts)
    result: list[Image.Image] = []
    for frame in frames:
        out = frame.convert("RGB")
        small = out.reduce(_SHRINK)
        levels = [_luminance(small, p) for p in small_parts]
        for k, part in enumerate(parts):
            span = end[k] - start[k]
            level = (levels[k] - start[k]) / span if abs(span) > 1.0 else 1.0
            progress[k] = max(progress[k], min(1.0, max(0.0, level)))
            mixed = Image.blend(_fill(out, part), turkish, progress[k])
            out = Image.composite(mixed, out, part)
        result.append(out.convert("RGBA"))
    result[-1] = turkish.convert("RGBA")  # son kare, kullanıcının hazırladığıyla birebir aynı
    return result


def translate_animation(data: bytes, last_english: Image.Image, last_turkish: Image.Image) -> bytes:
    """`.ip2` dosyasının karelerini Türkçeleştirir (son karesi `last_english` olan animasyon); boyut ve yapı korunur."""
    pages: list[Page] = list(iter_pages(data))
    if not pages or page_key(pages[-1].image) != page_key(last_english) or any(p.format != "bc1" for p in pages):
        return data
    new = animate_pages([p.image for p in pages], last_english, last_turkish)
    out = bytearray(data)
    for page, image in zip(pages, new, strict=True):
        original = data[page.data_offset : page.data_offset + page.size]
        out[page.data_offset : page.data_offset + page.size] = bc1.reencode(original, page.image, image)
    return bytes(out)
