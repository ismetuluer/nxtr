"""Doku üzerindeki yazılı etiketi Türkçesiyle değiştirme (oyun resimlerindeki başlık, eşya adı, menü yazısı).

İngilizce yazının bulunduğu pencere silinir, Türkçesi aynı yükseklikte ve aynı taban çizgisinde, penceredeki özgün
yazının rengi ve parıltısıyla çizilir. Yalnızca koyu zemin üzerindeki, toplamsal karıştırmayla çizilen yazılar için
uygundur (siyah görünmez; resmin üzerindeki yazılar için değil).

Yazı tipleri: el yazısı (Windows'un Monotype Corsiva'sı), kalın serif (Times New Roman Bold), fırça yazısı (Kaushan
Script) ve gotik (Pirata One). Son ikisi SIL Open Font License ile uygulamayla birlikte dağıtılır
(`nxceviri/assets/fonts`, lisans metinleri yanlarında).
"""

from __future__ import annotations

import itertools
import os
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from nxceviri.core.errors import NxError


class LabelError(NxError):
    """Doku üzerindeki yazı değiştirilemedi."""


@dataclass(frozen=True)
class Style:
    fonts: tuple[str, ...]  # aranacak yazı tipleri (önce uygulamanınkiler, sonra Windows'unkiler)
    bold: int  # maskenin kalınlaştırılması (tek sayı, 2× çözünürlükte piksel); 0 = yok
    glow: float  # parıltının, penceredeki orta parlaklıktaki piksellerin ortalamasına göre gücü


STYLES: dict[str, Style] = {
    "script": Style(("MTCORSVA.TTF", "Gabriola.ttf", "segoesc.ttf", "timesi.ttf", "DejaVuSerif-Italic.ttf"), 3, 1.1),
    "serif": Style(("timesbd.ttf", "DejaVuSerif-Bold.ttf"), 3, 1.8),
    "brush": Style(("KaushanScript-Regular.ttf",), 1, 1.1),
    "gothic": Style(("PirataOne-Regular.ttf",), 1, 1.1),
    "plain": Style(("times.ttf", "DejaVuSerif.ttf"), 1, 1.1),
    "sans": Style(("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"), 1, 1.1),
    "bold": Style(("timesbd.ttf", "DejaVuSerif-Bold.ttf"), 1, 1.1),
    "serif_italic": Style(("timesbi.ttf", "DejaVuSerif-BoldItalic.ttf"), 1, 1.1),
}


@dataclass(frozen=True)
class Label:
    window: tuple[int, int, int, int]  # yazıyı (parıltısıyla) içine alan pencere: sol, üst, sağ, alt
    english: str
    turkish: str
    style: str = "script"
    align: str = "center"  # "center", "left" veya "right"
    # Otomatik bulunanın yerine kullanılacak değerler (zor resimler için): yazı rengi, parıltı/kontur rengi ve
    # yazıyı zeminden ayıran parlaklık eşiği.
    ink: tuple[int, int, int] | None = None
    glow: tuple[int, int, int] | None = None
    threshold: int | None = None
    # Yazının elle ölçülmüş kutusu (otomatik ayırmanın yetmediği resimler için); taban çizgisi kutunun altıdır.
    box: tuple[int, int, int, int] | None = None
    # Resim üzerinde silinen yazının zemini: "spread" çevreden yayarak doldurur (düz zemin), "filter" ince yazı
    # çizgilerini morfolojik süzgeçle kaldırır (arkasında ayrıntılı resim olan paragraflar).
    fill: str = "spread"
    size: int | None = None  # yazı tipi boyu (piksel); verilmezse İngilizce yazının yüksekliğinden bulunur
    shift: int = 0  # yeni yazının yatay kaydırması (piksel; komşu yazıyla arası açılsın diye)


def find_font(style: str) -> Path:
    bundled = resources.files("nxceviri") / "assets" / "fonts"
    roots = [Path(str(bundled)), Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"]
    roots.append(Path("/usr/share/fonts/truetype/dejavu"))
    for name in STYLES[style].fonts:
        for root in roots:
            if (root / name).is_file():
                return root / name
    raise LabelError(
        "Oyun resimlerindeki yazıları çizmek için uygun yazı tipi bulunamadı.",
        "Windows'ta Times New Roman ve Monotype Corsiva yüklü olmalıdır; uygulama klasörü eksiksiz olmalıdır.",
    )


def _uses_alpha(page: Image.Image, window: tuple[int, int, int, int]) -> bool:
    """Pencere saydamlıkla mı çiziliyor (zemin alfa 0), yoksa toplamsal mı (alfa her yerde ~255, zemin siyah)?"""
    low = min(page.crop(window).getchannel("A").tobytes())
    return low < 200


def _coverage(page: Image.Image) -> Image.Image:
    """Görünen parlaklık: RGB parlaklığı × alfa (saydam pikseller görünmez)."""
    return ImageChops.multiply(page.convert("RGB").convert("L"), page.getchannel("A"))


def _ink_box(page: Image.Image, window: tuple[int, int, int, int], alpha: bool) -> tuple[int, int, int, int]:
    """Penceredeki yazının (parıltı hariç) sınırları."""
    crop = page.crop(window)
    lum = (_coverage(crop) if alpha else crop.convert("L")).point(lambda v: 255 if v > 90 else 0)
    box = lum.getbbox()
    if box is None:
        raise LabelError("Oyun resminde beklenen İngilizce yazı bulunamadı.")
    return window[0] + box[0], window[1] + box[1], window[0] + box[2], window[1] + box[3]


def _baseline(mask: Image.Image, threshold: int) -> int:
    """Yazının taban çizgisi: mürekkep içeren sütunların en alt mürekkep pikselinin ortancası."""
    width, height = mask.size
    pixels = mask.tobytes()
    bottoms = []
    for x in range(width):
        for y in range(height - 1, -1, -1):
            if pixels[y * width + x] > threshold:
                bottoms.append(y)
                break
    return int(statistics.median_low(bottoms)) if bottoms else height - 1


def _mask(text: str, font: ImageFont.FreeTypeFont, bold: int) -> tuple[Image.Image, int]:
    """Yazının 2× çözünürlükte çizilmiş, kırpılmış maskesi ve taban çizgisinin maskenin üstüne uzaklığı."""
    canvas = Image.new("L", (int(font.size) * (len(text) + 4), int(font.size) * 3))
    baseline = int(font.size) * 2
    ImageDraw.Draw(canvas).text((int(font.size), baseline), text, font=font, fill=255, anchor="ls")
    if bold:
        canvas = canvas.filter(ImageFilter.MaxFilter(bold))
    box = canvas.getbbox()
    if box is None:  # boş satır: yalnızca özgün yazı silinir
        return Image.new("L", (2, 2)), 0
    return canvas.crop(box), baseline - box[1]


def _fit_size(text: str, font_path: Path, bold: int, height: int) -> int:
    """Yazının çizildiğinde `height` piksel yüksekliğe ulaştığı en büyük yazı tipi boyu."""
    size = 8
    while _mask(text, ImageFont.truetype(str(font_path), (size + 1) * 2), bold)[0].height <= height * 2:
        size += 1
    return size


def _half(mask: Image.Image, width: int | None = None) -> Image.Image:
    return mask.resize((width or max(1, mask.width // 2), max(1, mask.height // 2)), Image.Resampling.LANCZOS)


def draw_label(
    page: Image.Image, label: Label, font_path: Path | None = None, reference: Image.Image | None = None
) -> Image.Image:
    """`page` üzerindeki İngilizce yazıyı Türkçesiyle değiştirilmiş yeni bir resim döndürür.

    `reference`: yazının ölçüldüğü ve renklerinin alındığı özgün sayfa. Bir sayfaya birden çok etiket çizilirken
    özgün sayfa verilmelidir; yoksa komşu etiketin yeni çizilen harfleri (ör. Ş'nin çengeli) ölçümü bozar.
    """
    style = STYLES[label.style]
    font_path = font_path or find_font(label.style)
    source = page if reference is None else reference
    if "\n" in label.english:
        return _draw_block(page, label, font_path, source)
    alpha = _uses_alpha(source, label.window)
    art = not alpha and (label.fill == "filter" or _on_art(source))
    keep = label.fill == "keep"  # zemin önceden hazırlandı (paragraf paneli): silme yapılmaz
    if keep:
        background: Image.Image | None = page.convert("RGB")
    elif art:
        fill = _filter_text if label.fill == "filter" else _inpaint
        background = fill(source.convert("RGB"), label.window)
    else:
        background = None
    # Yazı haritası: saydam dokuda görünen parlaklık, resim üzerinde özgün ile tahmin edilen zemin arasındaki fark,
    # siyah zeminde parlaklık.
    crop = source.crop(label.window)
    if alpha:
        ink_map, threshold = _coverage(crop), label.threshold or 90
        if ink_map.point(lambda v: 255 if v > threshold else 0).getbbox() is None:
            # koyu (siyaha yakın) yazı: görünürlüğü yalnızca alfa kanalından anlaşılır
            ink_map, threshold = crop.getchannel("A"), label.threshold or 160
    elif keep:
        ink_map, threshold = crop.convert("L"), label.threshold or 150
    elif background is not None:
        ink_map, threshold = (
            ImageChops.difference(crop.convert("RGB"), background.crop(label.window)).convert("L"),
            label.threshold or 40,
        )
    else:
        ink_map, threshold = crop.convert("L"), label.threshold or 90
    found = ink_map.point(lambda v: 255 if v > threshold else 0).getbbox()
    if found is None:
        raise LabelError("Oyun resminde beklenen İngilizce yazı bulunamadı.")
    box = label.box or (
        label.window[0] + found[0],
        label.window[1] + found[1],
        label.window[0] + found[2],
        label.window[1] + found[3],
    )
    width, height = box[2] - box[0], box[3] - box[1]
    # İngilizce yazı özgün yüksekliğe ulaşana kadar büyüt; Türkçesi aynı boyda ve aynı taban çizgisinde çizilir.
    size = label.size or _fit_size(label.english, font_path, style.bold, height)
    font = ImageFont.truetype(str(font_path), size * 2)
    turkish = _mask(label.turkish, font, style.bold)[0]
    small = _half(turkish)
    # Türkçe yazı pencerenin içinde kalacak kadar genişleyebilir; sığmazsa yatayda daraltılır.
    left, right = label.window[0] + 4, label.window[2] - 4
    room = {"left": max(width, right - box[0]), "right": max(width, box[2] - left)}.get(
        label.align, max(width, right - left)
    )
    if small.width > room:
        small = _half(turkish, room)
    centered = min(max(left, (box[0] + box[2] - small.width) // 2), right - small.width)  # pencereden taşmadan
    x = {"left": box[0], "right": box[2] - small.width}.get(label.align, centered) + label.shift
    baseline = box[3] if label.box else label.window[1] + _baseline(ink_map, threshold)
    y = baseline - _baseline(small, 128)

    mask = Image.new("L", page.size)
    mask.paste(small, (x, y))
    halo = mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(3))
    erase = Image.new("L", page.size)
    left, top, right, bottom = label.window
    if not keep:
        ImageDraw.Draw(erase).rectangle((left + 3, top + 3, right - 4, bottom - 4), fill=255)
        erase = erase.filter(ImageFilter.GaussianBlur(2))
    layers = _Layers(mask, halo, erase, (x, y, small.width, small.height))
    if alpha:
        return _draw_alpha(page, source, label, layers)
    if background is not None:
        return _draw_art(page, source, label, layers, background=background, ink_map=ink_map)
    return _draw_additive(page, source, label, layers, style.glow)


@dataclass(frozen=True)
class _Layers:
    mask: Image.Image  # yeni yazının kaplaması
    halo: Image.Image  # parıltı/gölge kaplaması
    erase: Image.Image  # özgün yazının silineceği yumuşak kenarlı alan
    area: tuple[int, int, int, int]  # yeni yazının kutusu: x, y, genişlik, yükseklik


def _gradient(size: tuple[int, int], ink: tuple[int, ...], area: tuple[int, int, int, int]) -> Image.Image:
    """Yazı alanında yukarıdan aşağı hafifçe koyulaşan renk."""
    x, y, width, height = area
    color = Image.new("RGB", size)
    draw = ImageDraw.Draw(color)
    for row in range(height):
        k = 1.0 - 0.2 * row / max(1, height)
        draw.line((x, y + row, x + width, y + row), fill=tuple(int(c * k) for c in ink))
    return color


def _average(pixels: Sequence[tuple[int, ...]], fallback: tuple[int, ...]) -> tuple[int, ...]:
    if not pixels:
        return fallback
    return tuple(sum(c[i] for c in pixels) // len(pixels) for i in range(len(pixels[0])))


def _draw_additive(
    page: Image.Image, source: Image.Image, label: Label, layers: _Layers, strength: float
) -> Image.Image:
    """Toplamsal doku: zemin siyah, yazı ve parıltı renkle (alfa değişmez)."""
    window = label.window
    rgb = page.convert("RGB")
    raw = source.convert("RGB").crop(window).tobytes()
    pixels = [(raw[i], raw[i + 1], raw[i + 2]) for i in range(0, len(raw), 3)]
    ink = _average(sorted(pixels, key=sum)[-max(1, len(pixels) // 40) :], (255, 255, 255))
    mids = [c for c in pixels if 50 < max(c) < 140] or [(60, 60, 60)]
    glow = tuple(min(255, int(sum(c[i] for c in mids) / len(mids) * strength)) for i in range(3))
    ink, glow = label.ink or ink, label.glow or glow
    black = Image.new("RGB", page.size)
    rgb = Image.composite(black, rgb, layers.erase)
    text_rgb = Image.composite(_gradient(page.size, ink, layers.area), black, layers.mask)
    glow_rgb = Image.composite(Image.new("RGB", page.size, glow), black, layers.halo)
    out = ImageChops.lighter(ImageChops.lighter(rgb, glow_rgb), text_rgb).convert("RGBA")
    out.putalpha(page.getchannel("A"))
    return out


def _text_rows(ink_map: Image.Image, threshold: int, count: int) -> list[tuple[int, int, int, int]]:
    """Paragraftaki `count` satırın kutuları (pencereye göre). Parıltı satırları birbirine bağladığı için satırlar
    yatay izdüşümün en derin `count - 1` vadisinden ayrılır; her parçada yoğun bant satırın kendisidir."""
    width, height = ink_map.size
    raw = ink_map.point(lambda v: 255 if v > threshold else 0).tobytes()
    profile = [raw[y * width : (y + 1) * width].count(255) for y in range(height)]
    peak = max(profile)
    if peak == 0:
        raise LabelError("Oyun resminde beklenen İngilizce paragraf bulunamadı.")
    active = [y for y, v in enumerate(profile) if v > peak * 0.1]
    first, last = active[0], active[-1] + 1
    gap = max(2, (last - first) // (count * 2))
    cuts: list[int] = []
    for y in sorted(range(first + gap, last - gap), key=lambda y: profile[y]):
        if len(cuts) == count - 1:
            break
        if all(abs(y - c) >= gap * 2 for c in cuts):
            cuts.append(y)
    edges = [first, *sorted(cuts), last]
    rows = []
    for top, bottom in itertools.pairwise(edges):
        # satır kutusu: parçadaki yazı piksellerinin sınırları (çıkıntılı ve kuyruklu harfler dahil)
        band = ink_map.crop((0, top, width, bottom)).point(lambda v: 255 if v > threshold else 0).getbbox()
        if band is None:
            raise LabelError(f"Paragrafta {count} satır bekleniyordu; satırlar ayrılamadı.")
        rows.append((band[0], top + band[1], band[2], top + band[3]))
    return rows


def _draw_block(page: Image.Image, label: Label, font_path: Path, source: Image.Image) -> Image.Image:
    """Resim üzerindeki paragraf: önce paragrafın alanı yazısı süzülmüş ve koyulaştırılmış bir panelle kapatılır
    (arkadaki resim soluk biçimde görünür kalır), sonra her satır özgün satırın yerine ve boyunda çizilir.
    Satırlar parlak yazının yatay izdüşümünden bulunur; renkler etikette verilmelidir."""
    english, turkish = label.english.split("\n"), label.turkish.split("\n")
    if len(english) != len(turkish):
        raise LabelError("Paragrafın İngilizce ve Türkçe satır sayıları farklı.")
    threshold = label.threshold or 150
    rgb = source.convert("RGB")
    # yazı haritası: en küçük renk kanalı. Yazılar beyaz/açık camgöbeğidir; arkadaki ateş (mavi kanalı düşük) ve
    # şimşek (kırmızı kanalı düşük) böylece yazı sayılmaz.
    channels = rgb.crop(label.window).split()
    whiteness = ImageChops.darker(ImageChops.darker(channels[0], channels[1]), channels[2])
    rows = _text_rows(whiteness, threshold, len(english))
    panel = _filter_text(rgb, label.window).point(lambda v: v // 4)
    left, top, right, bottom = label.window
    # Panel yalnızca özgün yazının (ve parıltısının) üstüne konur: arkadaki resim (ateş, şimşek) kutu gibi
    # karartılmaz.
    lettering = whiteness.point(lambda v: 255 if v > threshold * 2 // 3 else 0)
    lettering = lettering.filter(ImageFilter.MaxFilter(11)).filter(ImageFilter.GaussianBlur(3))
    shape = Image.new("L", page.size)
    shape.paste(lettering, (left, top))
    out = Image.composite(panel.convert("RGBA"), page, shape)
    out.putalpha(page.getchannel("A"))
    # Paragrafın tüm satırları aynı boyda: satır başına bulunan boyların en küçüğü (komşu satırın parıltısı
    # veya arkadaki parlak resim satır kutusunu büyütebilir, küçültemez)
    style = STYLES[label.style]
    size = label.size or min(
        _fit_size(e, font_path, style.bold, r[3] - r[1]) for r, e in zip(rows, english, strict=True)
    )
    for (x0, y0, x1, y1), eng, tur in zip(rows, english, turkish, strict=True):
        pad = max(3, (y1 - y0) // 3)
        window = (left, max(top, top + y0 - pad), right, min(bottom, top + y1 + pad))
        box = (left + x0, top + y0, left + x1, top + y1)
        line = Label(window, eng, tur, label.style, label.align, label.ink, label.glow, threshold, box, "keep", size)
        out = draw_label(out, line, font_path, reference=source)
    return out


def _filter_text(rgb: Image.Image, window: tuple[int, int, int, int]) -> Image.Image:
    """Pencere içindeki ince yazı çizgilerini (parlak dolgu ve koyu kontur) morfolojik açma/kapama ile kaldırır;
    resmin daha kalın ayrıntıları kalır."""
    left, top, right, bottom = window
    margin = 8
    region = (
        max(0, left - margin),
        max(0, top - margin),
        min(rgb.width, right + margin),
        min(rgb.height, bottom + margin),
    )
    part = rgb.crop(region)
    for size in (7, 9):
        part = part.filter(ImageFilter.MinFilter(size)).filter(ImageFilter.MaxFilter(size))  # parlak çizgiler
        part = part.filter(ImageFilter.MaxFilter(size)).filter(ImageFilter.MinFilter(size))  # koyu kontur
    part = part.filter(ImageFilter.GaussianBlur(2))
    out = rgb.copy()
    out.paste(part, region[:2])
    return out


def _on_art(page: Image.Image) -> bool:
    """Yazılar bir resmin üzerinde mi? Yazı sayfaları (siyah zeminde yazılar) çoğunlukla siyahtır; tam ekran
    resimlerde (yükleme ekranı, görev ekranı) ortanca parlaklık belirgin biçimde yüksektir."""
    return statistics.median_low(page.convert("L").reduce(4).tobytes()) > 12


def _inpaint(rgb: Image.Image, window: tuple[int, int, int, int]) -> Image.Image:
    """Pencerenin içini kenarındaki resimden yayılarak doldurur (yazının arkasındaki zemini tahmin eder)."""
    left, top, right, bottom = window
    margin = 6
    region = (
        max(0, left - margin),
        max(0, top - margin),
        min(rgb.width, right + margin),
        min(rgb.height, bottom + margin),
    )
    known = rgb.crop(region)
    hole = Image.new("L", known.size, 0)
    ImageDraw.Draw(hole).rectangle(
        (left - region[0] + 2, top - region[1] + 2, right - region[0] - 3, bottom - region[1] - 3), fill=255
    )
    fill = known.filter(ImageFilter.GaussianBlur(12))
    for _ in range(40):  # yayılma: bilinen pikseller her adımda geri konur
        fill = Image.composite(fill.filter(ImageFilter.BoxBlur(3)), known, hole)
    out = rgb.copy()
    out.paste(fill, region[:2])
    return out


def _draw_art(
    page: Image.Image,
    source: Image.Image,
    label: Label,
    layers: _Layers,
    *,
    background: Image.Image,
    ink_map: Image.Image,
) -> Image.Image:
    """Resim üzerindeki yazı: zemin çevresinden doldurulur, yazı ve çevresindeki parıltı/kontur üstüne konur."""
    window = label.window
    raw = source.convert("RGB").crop(window).tobytes()
    strength = ink_map.tobytes()
    text = [(raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]) for i, d in enumerate(strength) if d > 60]
    halo = [(raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2]) for i, d in enumerate(strength) if 15 < d <= 60]
    text.sort(key=sum)
    ink = _average(text[len(text) // 2 :], (255, 255, 255))  # yazının dolgusu: farklı piksellerin parlak yarısı
    dark = text[: len(text) // 4]
    base = statistics.fmean(background.crop(window).convert("L").tobytes()) * 3
    # yazının koyu bir konturu varsa onu, yoksa çevresindeki yumuşak parıltıyı kullan
    if dark and statistics.fmean(sum(c) for c in dark) < base - 90:
        glow = _average(dark, (0, 0, 0))
        halo_mask = layers.mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1))
    else:
        glow = _average(halo, (0, 0, 0))
        halo_mask = layers.halo
    ink, glow = label.ink or ink, label.glow or glow
    cleared = Image.composite(background, page.convert("RGB"), layers.erase).convert("RGBA")
    glow_layer = Image.new("RGBA", page.size, (*glow, 0))
    glow_layer.putalpha(halo_mask)
    text_layer = _gradient(page.size, ink, layers.area).convert("RGBA")
    text_layer.putalpha(layers.mask)
    out = Image.alpha_composite(Image.alpha_composite(cleared, glow_layer), text_layer)
    out.putalpha(page.getchannel("A"))
    return out


def _draw_alpha(page: Image.Image, source: Image.Image, label: Label, layers: _Layers) -> Image.Image:
    """Saydam doku: zemin alfa 0; yazı opak, parıltı/gölge yarı saydam (renkleri özgün yazıdan)."""
    window = label.window
    raw = source.crop(window).tobytes()
    pixels = [tuple(raw[i : i + 4]) for i in range(0, len(raw), 4)]
    ink = _average(
        sorted((c for c in pixels if c[3] > 200), key=lambda c: sum(c[:3]))[-max(1, len(pixels) // 40) :],
        (255, 255, 255, 255),
    )[:3]
    # özgün yazının çevresindeki yarı saydam koyu gölge (yoksa açık renkli parıltı)
    soft = [c for c in pixels if 30 < c[3] < 220]
    dark = [c for c in soft if sum(c[:3]) < 240]
    glow = _average([c[:3] for c in dark or soft], (0, 0, 0))
    ink, glow = label.ink or ink, label.glow or glow
    glow_alpha = min(255, int(_average([(c[3],) for c in dark or soft], (0,))[0] * 1.4))
    cleared = page.copy()
    cleared.putalpha(ImageChops.multiply(page.getchannel("A"), ImageChops.invert(layers.erase)))
    glow_layer = Image.new("RGBA", page.size, (*glow, 0))
    glow_layer.putalpha(layers.halo.point(lambda v: v * glow_alpha // 255))
    text_layer = _gradient(page.size, ink, layers.area).convert("RGBA")
    text_layer.putalpha(layers.mask.point(lambda v: min(255, v * 3 // 2)))  # saydam yazı daha dolgun görünsün
    return Image.alpha_composite(Image.alpha_composite(cleared, glow_layer), text_layer)
