"""BMFont ikili (v3) yazı tipi: okuma, yazma ve eksik Türkçe harfleri mevcut glif bitmaplerinden türetme.

NNI biçimli oyunun yazı tipleri `*.fnt` (BMFont ikili biçimi) + `*.png` (glif atlası) çiftidir ve yalnızca Latin-1
harflerini içerir: `ç ö ü` vardır, `ğ ş ı İ Ğ Ş` yoktur. Eksik harfler yazı tipinin **kendi glifleriyle**
türetilir, böylece
dış çizgi, gölge ve renk aynı kalır. İşaretin kaynağı ortak sıradadır (`fontpatch/sources.py`):

- `ı` = `i`nin noktasız gövdesi (nokta gövdeden ayrılamıyorsa eklenemez; bit eşlemde `I` küçültülmez);
- `İ` = `I` + nokta: `i` → `ż Ż ċ Ċ ė Ė` → `ö`/`Ö`'nün soldaki noktası → `.` → çizilen kare nokta;
- `ş`/`Ş` = `s`/`S` + `ç`/`Ç`nin gövdesinin altındaki parça (diğer büyüklükteki de olur) → `,` → çizilen çengel;
- `ğ`/`Ğ` = `g`/`G` + `ă`/`Ă`'nın kavisi → `˘` → `ŭ Ŭ ŏ Ŏ` → kalem izleriyle çizilen breve (kalem `i`nin
  noktasından, `i` yoksa taban harfin dolgusundan kesilir).

Harften alınan işaret taban harfe yatayda ortalanır ve kaynaktaki gövdeye uzaklığını korur; ölçeklenmez.

Parçalar "daha açık olan kazanır" (kanal başına en büyük değer) kuralıyla birleştirilir; açık dolgu koyu dış çizgi ve
gölgenin üstüne çıkar. Yeni glifler atlasın boş bir yerine konur; atlasın boyutu değişmez. Görünüm yaklaşıktır
(TECH_DEBT 50 ile aynı sınır): `ă`/`˘` yoksa breve fontun kendi çizimi değildir.
"""

from __future__ import annotations

import io
import struct
from dataclasses import astuple, dataclass, field
from typing import cast

from PIL import Image, ImageChops, ImageFilter

from nxceviri.core.errors import NxError
from nxceviri.core.fontpatch import sources

MAGIC = b"BMF\x03"
_INFO, _COMMON, _PAGES, _CHARS = 1, 2, 3, 4
_CHAR = struct.Struct("<IHHHHhhhBB")
_PAD = 1  # glifler arasında bırakılan boşluk (piksel)
_MAX_ATLAS = 4096
_CORE_ALPHA = 128  # bundan opak pikseller harfin çekirdeğidir (gölge ve ışıma değil)

#: Eksik harf → (temel harf, ek). `ı` için temel `i`dir ve nokta atılır.
RECIPES: dict[str, tuple[str, str]] = {
    "ı": ("i", "dotless"),
    "İ": ("I", "dot"),
    "ş": ("s", "cedilla"),
    "Ş": ("S", "cedilla"),
    "ğ": ("g", "breve"),
    "Ğ": ("G", "breve"),
}


class BmFontError(NxError):
    """Yazı tipi dosyası çözülemedi veya yamalanamadı."""


@dataclass(frozen=True)
class Char:
    id: int
    x: int
    y: int
    w: int
    h: int
    xoffset: int
    yoffset: int
    xadvance: int
    page: int = 0
    chnl: int = 15


@dataclass(frozen=True)
class Part:
    """Satır koordinatlarında bir görüntü parçası (sol üst köşe: satırın başlangıcına göre)."""

    image: Image.Image
    left: int
    top: int


class BmFont:
    def __init__(self, fnt: bytes, atlas: Image.Image) -> None:
        if not fnt.startswith(MAGIC):
            raise BmFontError("BMFont ikili (v3) dosyası değil.")
        self._blocks: list[tuple[int, bytes]] = []
        self.chars: dict[int, Char] = {}
        self._added: set[int] = set()
        pos = 4
        while pos < len(fnt):
            if pos + 5 > len(fnt):
                raise BmFontError("BMFont dosyası kesik.")
            kind, size = fnt[pos], struct.unpack_from("<I", fnt, pos + 1)[0]
            body = fnt[pos + 5 : pos + 5 + size]
            if len(body) != size:
                raise BmFontError("BMFont bloğu dosyanın dışına taşıyor.")
            self._blocks.append((kind, body))
            if kind == _COMMON:
                self.line_height, self.base, self.scale_w, self.scale_h, self.pages = struct.unpack_from("<5H", body)
            elif kind == _CHARS:
                for i in range(0, size - size % _CHAR.size, _CHAR.size):
                    c = Char(*_CHAR.unpack_from(body, i))
                    self.chars[c.id] = c
            pos += 5 + size
        if not hasattr(self, "line_height"):
            raise BmFontError("BMFont dosyasında 'common' bloğu yok.")
        if self.pages != 1:
            raise BmFontError("Yalnızca tek sayfalı yazı tipleri yamalanabilir.")
        if atlas.size != (self.scale_w, self.scale_h):
            raise BmFontError(
                f"Atlas boyutu ({atlas.size}) yazı tipi dosyasıyla ({self.scale_w}×{self.scale_h}) uyuşmuyor."
            )
        self.atlas = atlas.convert("RGBA")

    def serialize(self) -> bytes:
        out = bytearray(MAGIC)
        for kind, block in self._blocks:
            body = b"".join(_CHAR.pack(*astuple(c)) for c in self.chars.values()) if kind == _CHARS else block
            out += bytes([kind]) + struct.pack("<I", len(body)) + body
        return bytes(out)

    def atlas_png(self) -> bytes:
        buf = io.BytesIO()
        self.atlas.save(buf, "PNG")
        return buf.getvalue()

    def part(self, ch: str) -> Part:
        c = self.chars[ord(ch)]
        return Part(self.atlas.crop((c.x, c.y, c.x + c.w, c.y + c.h)), c.xoffset, c.yoffset)

    def _free_spot(self, w: int, h: int, taken: list[tuple[int, int, int, int]]) -> tuple[int, int] | None:
        """Atlasta, var olan glifleri ve yeni konanları çakıştırmayan ilk (x, y)."""
        width, height = self.scale_w, self.scale_h
        grid = [bytearray(width + 1) for _ in range(height + 1)]
        for c in list(self.chars.values()):
            for y in range(max(0, c.y - _PAD), min(height, c.y + c.h + _PAD)):
                row = grid[y]
                for x in range(max(0, c.x - _PAD), min(width, c.x + c.w + _PAD)):
                    row[x] = 1
        # satır başına "bu x'ten itibaren kaç piksel boş" (sağdan sola)
        run = [[0] * (width + 1) for _ in range(height)]
        for y in range(height):
            row, r = grid[y], run[y]
            for x in range(width - 1, -1, -1):
                r[x] = 0 if row[x] else r[x + 1] + 1
        for y in range(height - h + 1):
            for x in range(width - w + 1):
                if run[y][x] < w:
                    continue
                if all(run[y + dy][x] >= w for dy in range(1, h)) and not any(
                    x < tx + tw + _PAD and tx < x + w + _PAD and y < ty + th + _PAD and ty < y + h + _PAD
                    for tx, ty, tw, th in taken
                ):
                    return x, y
        return None

    def _grow(self) -> None:
        """Atlasın yüksekliğini ikiye katlar (üst kısım aynı kalır, alt kısım boş olur); `common` bloğu güncellenir."""
        grown = Image.new("RGBA", (self.scale_w, self.scale_h * 2), (0, 0, 0, 0))
        grown.paste(self.atlas, (0, 0))
        self.atlas, self.scale_h = grown, self.scale_h * 2
        self._blocks = [
            (kind, struct.pack("<5H", self.line_height, self.base, self.scale_w, self.scale_h, self.pages) + body[10:])
            if kind == _COMMON
            else (kind, body)
            for kind, body in self._blocks
        ]

    def add(self, ch: str, part: Part, xadvance: int) -> None:
        """Glifi atlasın boş bir yerine koyar ve yazı tipine ekler."""
        w, h = part.image.size
        taken = [(c.x, c.y, c.w, c.h) for c in self.chars.values() if c.id in self._added]
        spot = self._free_spot(w, h, taken)
        while spot is None and self.scale_h < _MAX_ATLAS:
            self._grow()
            spot = self._free_spot(w, h, taken)
        if spot is None:
            raise BmFontError(f"Atlasta '{ch}' için {w}×{h} boş yer yok.")
        self.atlas.paste(part.image, spot)
        self.chars[ord(ch)] = Char(ord(ch), spot[0], spot[1], w, h, part.left, part.top, xadvance)
        self._added.add(ord(ch))


def _bbox_part(image: Image.Image, left: int, top: int) -> Part | None:
    box = image.getbbox()
    if box is None:
        return None
    return Part(image.crop(box), left + box[0], top + box[1])


def merge(parts: list[Part]) -> Part:
    """Parçaları satır koordinatlarında birleştirir ("daha açık olan kazanır")."""
    left, top = min(p.left for p in parts), min(p.top for p in parts)
    right = max(p.left + p.image.width for p in parts)
    bottom = max(p.top + p.image.height for p in parts)
    canvas = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
    for p in parts:
        box = (p.left - left, p.top - top, p.left - left + p.image.width, p.top - top + p.image.height)
        canvas.paste(ImageChops.lighter(canvas.crop(box), p.image), box[:2])
    return Part(canvas, left, top)


def _fill_mask(image: Image.Image) -> Image.Image:
    """Harfin dolgusu (dış çizgi, gölge ve ışıma hariç): opak ve en açık renge yakın pikseller.

    Yalnızca alfa kanalı olan yazı tiplerinde (renk kanalları sıfır) opak pikseller dolgudur."""
    r, g, b, a = image.split()
    brightness = ImageChops.lighter(r, ImageChops.lighter(g, b))
    top = brightness.getextrema()[1]
    opaque = a.point(lambda v: 255 if v >= _CORE_ALPHA else 0)
    if top == 0:
        return opaque
    bright = brightness.point(lambda v: 255 if v * 10 >= top * 6 else 0)
    return ImageChops.darker(opaque, bright)


def _core_rows(image: Image.Image) -> list[bool]:
    """Her satır için "bu satırda dolgu pikseli var mı"."""
    pixels = _fill_mask(image).tobytes()
    w, h = image.size
    return [any(pixels[y * w : (y + 1) * w]) for y in range(h)]


def _core_bbox(image: Image.Image) -> tuple[int, int, int, int] | None:
    return _fill_mask(image).getbbox()


def _split_rows(image: Image.Image) -> tuple[int, int] | None:
    """(üstteki işaretin bittiği satır, gövdenin başladığı satır); aralarında boş satır yoksa None."""
    rows = _core_rows(image)
    if True not in rows:
        return None
    end = rows.index(True)
    while end < len(rows) and rows[end]:
        end += 1
    start = end
    while start < len(rows) and not rows[start]:
        start += 1
    return (end, start) if start < len(rows) else None


def _left_column_run(image: Image.Image) -> int | None:
    """İki noktalı işarette (ö) soldaki noktanın bittiği yer: iki nokta arasındaki boşluğun ortası."""
    mask = _fill_mask(image)
    w, h = image.size
    pixels = mask.tobytes()
    cols = [any(pixels[y * w + x] for y in range(h)) for x in range(w)]
    if True not in cols:
        return None
    end = cols.index(True)
    while end < w and cols[end]:
        end += 1
    start = end
    while start < w and not cols[start]:
        start += 1
    return (end + start) // 2 if start < w else None


@dataclass(frozen=True)
class Mark:
    """Kaynak harften kesilmiş işaret ve kaynakta gövdeyle arasındaki boş satır sayısı."""

    part: Part
    gap: int


class Deriver:
    """Bir yazı tipinin kendi glifleriyle eksik harfleri üretir; işaret kaynakları `fontpatch/sources.py` sırasıyladır.

    Glif kutuları gölge/ışıma payı içerdiğinden (`yoffset` farkı güvenilir değildir) parçalar, harfin opak çekirdeğinin
    satırlarına bakılarak ayrılır."""

    def __init__(self, font: BmFont) -> None:
        self.font = font
        self._i_dot = self._mark("i", single=True)

    def _has(self, ch: str) -> bool:
        return ord(ch) in self.font.chars

    def _core_top(self, ch: str) -> int:
        """Harfin opak çekirdeğinin satır koordinatındaki üst kenarı."""
        part = self.font.part(ch)
        box = _core_bbox(part.image)
        return part.top + (box[1] if box else 0)

    def _core_bottom(self, ch: str) -> int:
        part = self.font.part(ch)
        box = _core_bbox(part.image)
        return part.top + (box[3] if box else part.image.height)

    def _gap(self) -> int:
        """İşaretle gövde arasındaki boşluk: i'deki kadar (i yoksa 1 satır)."""
        return max(1, self._i_dot.gap) if self._i_dot is not None else 1

    def _mark(self, ch: str, single: bool) -> Mark | None:
        """Harfin gövdesinin üstündeki işaret (`single`: iki noktadan soldaki); ayrılamıyorsa None."""
        if not self._has(ch):
            return None
        part = self.font.part(ch)
        if ch == sources.SPACING_BREVE:
            whole = _bbox_part(part.image, part.left, part.top)
            return Mark(whole, self._gap()) if whole is not None else None
        split = _split_rows(part.image)
        if split is None:
            return None
        end, start = split
        mark = _bbox_part(part.image.crop((0, 0, part.image.width, (end + start) // 2)), part.left, part.top)
        if mark is not None and single:
            cut = _left_column_run(mark.image)
            if cut is not None:
                mark = _bbox_part(mark.image.crop((0, 0, cut, mark.image.height)), mark.left, mark.top)
        return Mark(mark, start - end) if mark is not None else None

    def _place_above(self, mark: Mark, base_ch: str, base: Char) -> Part:
        """İşareti, taban harfin çekirdeğinin üstüne kaynaktaki boşlukla koyar (yatayda ortalı)."""
        image = mark.part.image
        core_end = (_core_bbox(image) or (0, 0, 0, image.height))[3]
        top = self._core_top(base_ch) - max(1, mark.gap) - core_end
        left = round(base.xoffset + base.w / 2 - image.width / 2)
        return Part(image, left, top)

    def _pen(self, base_ch: str) -> tuple[Image.Image, Image.Image]:
        """(çizim kalemi, dış çizgi rengi için örnek): i'nin noktasından, yoksa taban harfin dolgusundan kesilir."""
        source = self._i_dot.part.image if self._i_dot is not None else self.font.part(base_ch).image
        box = _core_bbox(source) or (0, 0, source.width, source.height)
        if self._i_dot is not None:
            pen_size = max(1, round((box[3] - box[1]) * 0.55))
        else:
            pen_size = max(1, round(min(box[2] - box[0], box[3] - box[1]) * 0.3))
        left = box[0] + (box[2] - box[0] - pen_size) // 2
        top = box[1] + (box[3] - box[1] - pen_size) // 2
        return source.crop((left, top, left + pen_size, top + pen_size)), source

    def _stroked(self, pens: list[Part], base_ch: str, sample: Image.Image) -> Part:
        """Kalem izlerini birleştirir, parlaklığı taban harfinkine çıkarır, dış çizgi ekler."""
        core = self._match_brightness(merge(pens), self.font.part(base_ch).image)
        outline = self._outline(core, sample)
        return merge([outline, core]) if outline is not None else core

    def _drawn_dot(self, base_ch: str, base: Char) -> Part:
        pen, sample = self._pen(base_ch)
        size = pen.width
        square = [
            Part(pen, dx, dy) for dx in range(0, size + 1, max(1, size)) for dy in range(0, size + 1, max(1, size))
        ]
        dot = self._stroked(square, base_ch, sample)
        return self._place_above(Mark(dot, self._gap()), base_ch, base)

    def _breve(self, base_ch: str, base: Char) -> Part:
        """Taban harfin çekirdeğinin üstünde, ortalanmış yay (kalem: i'nin noktasından ya da taban harften).

        Kalemin parlaklığı taban harfinki kadar yükseltilir ve dış çizgi rengiyle bir kenarlık eklenir (yalnızca alfa
        kanallı yazı tiplerinde kenarlık olmaz)."""
        pen, sample = self._pen(base_ch)
        pen_size = pen.width
        base_box = _core_bbox(self.font.part(base_ch).image)
        base_width = (base_box[2] - base_box[0]) if base_box else base.w
        width = max(3 * pen_size, round(base_width * 0.55))
        depth = max(1, round(width * 0.16))
        bottom = self._core_top(base_ch) - self._gap()
        center = base.xoffset + ((base_box[0] + base_box[2]) / 2 if base_box else base.w / 2)
        parts = []
        for step in range(width):
            t = (2 * step / (width - 1) - 1) if width > 1 else 0.0
            sink = round(depth * (1 - t * t))  # ortada en aşağıda: kâse biçimi
            parts.append(Part(pen, round(center - width / 2) + step, bottom - pen_size - depth + sink))
        return self._stroked(parts, base_ch, sample)

    def _drawn_cedilla(self, base_ch: str, base: Char) -> Part:
        """Taban harfin altında kısa, sola kıvrılan çengel (kalem izleri)."""
        pen, sample = self._pen(base_ch)
        size = pen.width
        center = round(base.xoffset + base.w / 2 - size / 2)
        top = self._core_bottom(base_ch) - 1
        steps = [(center, top + k) for k in range(2 * size + 1)] + [(center - size, top + 2 * size)]
        return self._stroked([Part(pen, x, y) for x, y in steps], base_ch, sample)

    @staticmethod
    def _match_brightness(part: Part, reference: Image.Image) -> Part:
        """Parçanın her kanalının en büyük değerini referans glifinkine çıkarır (soluk kalmasın)."""
        lut: list[int] = []
        wanted = cast(tuple[tuple[int, int], ...], reference.getextrema())
        found = cast(tuple[tuple[int, int], ...], part.image.getextrema())
        for (_, want), (_, have) in zip(wanted, found, strict=True):
            lut += [min(255, v * want // have) if have else v for v in range(256)]
        return Part(part.image.point(lut), part.left, part.top)

    @staticmethod
    def _outline(core: Part, dot: Image.Image) -> Part | None:
        """Çekirdeğin bir piksel genişletilmişi; renk, örneğin koyu ve opak (dış çizgi) piksellerinin ortalaması."""
        raw = dot.tobytes()
        pixels = [px for px in zip(raw[0::4], raw[1::4], raw[2::4], raw[3::4], strict=True) if px[3] >= _CORE_ALPHA]
        if not pixels:
            return None
        brightest = max(sum(px[:3]) for px in pixels)
        if brightest == 0:
            return None  # yalnızca alfa kanalı olan yazı tipi: dış çizgi yok
        dark = [px for px in pixels if sum(px[:3]) * 2 <= brightest]
        if not dark:
            return None
        color = (
            sum(px[0] for px in dark) // len(dark),
            sum(px[1] for px in dark) // len(dark),
            sum(px[2] for px in dark) // len(dark),
        )
        padded = Image.new("RGBA", (core.image.width + 2, core.image.height + 2), (0, 0, 0, 0))
        padded.paste(core.image, (1, 1))
        ring = Image.new("RGBA", padded.size, (*color, 0))
        ring.putalpha(padded.getchannel("A").filter(ImageFilter.MaxFilter(3)))
        return Part(ring, core.left - 1, core.top - 1)

    def _hook(self, donor: str, base_ch: str, target: Char) -> Part | None:
        """`ç`/`Ç`'nin gövdesinin altındaki parçası (çengel), taban harfin altına; çengel yoksa None.

        Gövdenin alt kenarı `c`/`C`'den (yoksa taban harften) okunur; diğer büyüklükteki kaynaktan alınan çengel
        taban harfin alt kenarına göre kaydırılır."""
        if not self._has(donor):
            return None
        plain = {"ç": "c", "Ç": "C"}[donor]
        body = plain if self._has(plain) else base_ch
        glyph = self.font.chars[ord(donor)]
        part = self.font.part(donor)
        start = max(0, self._core_bottom(body) - glyph.yoffset - 1)
        crop = _bbox_part(part.image.crop((0, start, part.image.width, part.image.height)), part.left, part.top + start)
        if crop is None or crop.top + crop.image.height <= self._core_bottom(body):
            return None
        shift = round((target.xoffset + target.w / 2) - (glyph.xoffset + glyph.w / 2))
        drop = self._core_bottom(base_ch) - self._core_bottom(body)
        return Part(crop.image, crop.left + shift, crop.top + drop)

    def _comma(self, base_ch: str, target: Char) -> Part | None:
        if not self._has(sources.COMMA):
            return None
        part = self.font.part(sources.COMMA)
        whole = _bbox_part(part.image, 0, 0)
        if whole is None:
            return None
        left = round(target.xoffset + target.w / 2 - whole.image.width / 2)
        return Part(whole.image, left, self._core_bottom(base_ch) - 1)

    def _above(self, letter: str, base_ch: str, base: Char) -> tuple[Part, str]:
        for donor in sources.donors(letter):
            if donor == sources.PERIOD:
                if not self._has(donor):
                    continue
                part = self.font.part(donor)
                period = _bbox_part(part.image, part.left, part.top)
                if period is not None:
                    return self._place_above(Mark(period, self._gap()), base_ch, base), sources.label(letter, donor)
                continue
            mark = self._mark(donor, single=letter == "İ")
            if mark is not None:
                return self._place_above(mark, base_ch, base), sources.label(letter, donor)
        drawn = self._drawn_dot(base_ch, base) if letter == "İ" else self._breve(base_ch, base)
        return drawn, sources.DRAWN

    def _below(self, letter: str, base_ch: str, base: Char) -> tuple[Part, str]:
        for donor in sources.donors(letter):
            hook = self._comma(base_ch, base) if donor == sources.COMMA else self._hook(donor, base_ch, base)
            if hook is not None:
                return hook, sources.label(letter, donor)
        return self._drawn_cedilla(base_ch, base), sources.DRAWN

    def derive(self, letter: str) -> tuple[Part, int, str]:
        """(glif parçası, xadvance, işaretin kaynağı)."""
        base_ch, kind = RECIPES[letter]
        base = self.font.chars[ord(base_ch)]
        part = self.font.part(base_ch)
        if kind == "dotless":
            split = _split_rows(part.image)
            if split is None:
                raise BmFontError("'i' glifinde nokta ile gövde ayrılamadı.")
            cut = max(0, split[1] - 1)
            body = _bbox_part(part.image.crop((0, cut, part.image.width, part.image.height)), part.left, part.top + cut)
            if body is None:
                raise BmFontError("'ı' gövdesi çıkarılamadı.")
            return body, base.xadvance, sources.DOTLESS_FROM_I
        mark, why = self._below(letter, base_ch, base) if kind == "cedilla" else self._above(letter, base_ch, base)
        return merge([part, mark]), base.xadvance, why


@dataclass(frozen=True)
class PatchResult:
    """Eklenen harfler ve her birinin işaret kaynağı (`sources.label`)."""

    added: str = ""
    sources: dict[str, str] = field(default_factory=dict)


def patch_missing(font: BmFont, letters: str) -> PatchResult:
    """Yazı tipinde olmayan harfleri türetip ekler. Taban harfi (i, I, s, S, g, G) olmayan harf varsa hata."""
    wanted = [c for c in letters if ord(c) not in font.chars]
    if not wanted:
        return PatchResult()
    missing = sorted({RECIPES[c][0] for c in wanted} - {chr(c) for c in font.chars})
    if missing:
        raise BmFontError(f"Temel harfler yazı tipinde yok: {' '.join(missing)}")
    deriver = Deriver(font)
    found: dict[str, str] = {}
    for letter in wanted:
        part, advance, why = deriver.derive(letter)
        font.add(letter, part, advance)
        found[letter] = why
    return PatchResult("".join(wanted), found)


def add_missing(font: BmFont, letters: str) -> str:
    """Yazı tipinde olmayan harfleri türetip ekler; eklenenleri döndürür (`patch_missing`)."""
    return patch_missing(font, letters).added


__all__ = [
    "RECIPES",
    "BmFont",
    "BmFontError",
    "Char",
    "Deriver",
    "Part",
    "PatchResult",
    "add_missing",
    "merge",
    "patch_missing",
]
