"""Devil May Cry (Switch) yazı dokusu üretici: `etc_e/msg_tex.t32`.

Oyunun İngilizce diyalog yazısı bir T32 dosyasından çizilir (docs/formats/dmc1.md). Biçim, topluluğun
Rusça modunun ve PC Türkçe yamasının (ikisi de Switch'te açılıyor) dosyalarından ve oyunun kendi
`etc_u/msg_tex2.t32` dosyasından doğrulandı:

- 0xC0 baytlık T32 başlığı + iki **sıkıştırılmamış DDS** sayfası (her biri "DDS " + 124 bayt başlık +
  256×256 piksel, bayt sırası B G R A);
- 1. sayfa yazı tipidir: 16 sütun × 8 satır, **16×32 piksellik hücreler**; kod `c` → sütun `c % 16`,
  satır `c // 16`. Taban çizgisi y=27, büyük harfler y≈4'ten başlar, inen harfler y=31'e kadar iner.
  Oyun her hücreyi ölçer: yalnızca 0x47 boş olabilir (boş hücreler ve DDS başlığı olmayan dosya oyunu
  açılışta çökertti);
- 2. sayfa birkaç simge içerir (µ ¡ · ¿ ° ` § ´ ® → hücre 0–8).

Karakterler sistemdeki serif bir yazı tipiyle çizilir; özgün yazının ince uzun görünümü için yatayda daraltılır.
"""

from __future__ import annotations

import os
import struct
from collections.abc import Mapping
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from nxceviri.core.errors import NxError

PAGE = 256
CELL_W = 16
CELL_H = 32
HEADER_SIZE = 0xC0
#: Başlıktaki 0x14 alanı: `msg_tex` dokusunun sabit kimliği. Oyunun kendi dokusunda, Rusça modda ve PC Türkçe
#: yamasında içerik farklı olsa da aynı değerdedir; içerik özeti DEĞİLDİR.
TEXTURE_ID = 0x4FE396F0
#: 2. sayfadaki simgeler (hücre 0'dan başlayarak).
PAGE2_CHARS = "µ¡·¿°`§´®"
_BACKGROUND = (80, 80, 80, 0)
_INK = (200, 217, 200)
_BASELINE = 27
_FONT_SIZE = 33
#: Yatay daraltma: özgün yazı tipi ince uzundur (hücre 16×32).
_SQUEEZE = 0.72
#: Gölgenin en yüksek opaklığı (özgün dokudaki gölge pikselleri ~30–110 arasında).
_SHADOW_ALPHA = 100
_SEARCH = ("times.ttf", "georgia.ttf", "cambria.ttc", "DejaVuSerif.ttf")


class FontError(NxError):
    """Yazı dokusu üretilemedi."""


def system_font() -> Path:
    """Sistemde bulunan serif yazı tipinin dosyası."""
    roots = [Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts", Path("/usr/share/fonts/truetype/dejavu")]
    for name in _SEARCH:
        for root in roots:
            if (root / name).is_file():
                return root / name
    raise FontError(
        "Dokuyu çizmek için sistemde serif bir yazı tipi bulunamadı.",
        "Windows'ta Times New Roman (times.ttf) yüklü olmalıdır.",
    )


def _t32_header() -> bytes:
    """Rusça modun, PC yamasının ve oyunun kendi dokusunun kullandığı T32 başlığı."""
    head = bytearray(HEADER_SIZE)
    head[0:4] = bytes((0x00, 0x32, 0x33, 0x54))  # "T32\0" (küçük sonlu)
    struct.pack_into("<IIIII", head, 4, 1, HEADER_SIZE, 0x80080, 0, TEXTURE_ID)
    struct.pack_into("<I", head, 0x18, 2)
    struct.pack_into("<Q", head, 0x20, 0x40040)
    struct.pack_into("<Q", head, 0x28, 0x2000000621410000)
    struct.pack_into("<I", head, 0x3C, 0x40080)
    return bytes(head)


def _dds_header() -> bytes:
    """256×256, 32 bit, sıkıştırılmamış (A8R8G8B8) DDS başlığı."""
    head = bytearray(128)
    head[0:4] = b"DDS "
    struct.pack_into("<7I", head, 4, 124, 0x81007, PAGE, PAGE, PAGE * PAGE * 4, 0, 0)
    struct.pack_into("<8I", head, 76, 32, 0x41, 0, 32, 0xFF0000, 0xFF00, 0xFF, 0xFF000000)
    struct.pack_into("<I", head, 108, 0x1000)
    return bytes(head)


def _glyph_mask(char: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    """Karakterin 16×32 hücreye yerleştirilmiş kaplama maskesi (taban çizgisi y=27)."""
    canvas = Image.new("L", (CELL_H * 3, CELL_H), 0)
    ImageDraw.Draw(canvas).text((CELL_H, _BASELINE), char, font=font, fill=255, anchor="ls")
    box = canvas.getbbox()
    cell = Image.new("L", (CELL_W, CELL_H), 0)
    if box is None:
        return cell
    strip = canvas.crop((box[0], 0, box[2], CELL_H))
    width = min(CELL_W, max(1, round(strip.width * _SQUEEZE)))
    strip = strip.resize((width, CELL_H), Image.Resampling.LANCZOS)
    cell.paste(strip, ((CELL_W - width) // 2, 0))
    return cell


def _draw_cell(char: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    mask = _glyph_mask(char, font)
    # Özgün dokudaki gibi yazının çevresinde yumuşak, koyu bir gölge: metin her zeminde okunur.
    halo = mask.filter(ImageFilter.MaxFilter(3)).tobytes()
    coverage = mask.tobytes()
    cell = Image.new("RGBA", (CELL_W, CELL_H), _BACKGROUND)
    pixels = cell.load()
    assert pixels is not None
    for y in range(CELL_H):
        for x in range(CELL_W):
            alpha = coverage[y * CELL_W + x]
            shadow = halo[y * CELL_W + x] * _SHADOW_ALPHA // 255
            if alpha > shadow:
                pixels[x, y] = (*_INK, alpha)
            elif shadow:  # arka plan alfa 0 kalır; yalnızca yazı ve gölge pikselleri görünür
                pixels[x, y] = (0, 0, 0, shadow)
    return cell


def cell_origin(code: int) -> tuple[int, int]:
    """Kodun hücresinin sayfadaki sol üst köşesi (piksel)."""
    row, col = divmod(code, PAGE // CELL_W)
    return col * CELL_W, row * CELL_H


def _page(chars: Mapping[int, str], font: ImageFont.FreeTypeFont) -> Image.Image:
    image = Image.new("RGBA", (PAGE, PAGE), _BACKGROUND)
    for code, char in chars.items():
        image.paste(_draw_cell(char, font), cell_origin(code))
    return image


def build_texture(chars: Mapping[int, str], regular: Path) -> bytes:
    """`chars` (kod → karakter) için tam T32 dosyasını üretir (yazı sayfası + simge sayfası)."""
    if any(not 0 <= code < 0x80 for code in chars):
        raise FontError("Yazı dokusu yalnızca 0x00–0x7F tek baytlık kodları barındırır.")
    try:
        font = ImageFont.truetype(str(regular), _FONT_SIZE)
    except OSError as exc:
        raise FontError(f"Yazı tipi açılamadı: {exc}", "Yazı tipi dosyasını kontrol edin.") from None
    pages = (_page(chars, font), _page(dict(enumerate(PAGE2_CHARS)), font))
    body = b"".join(_dds_header() + page.tobytes("raw", "BGRA") for page in pages)
    return _t32_header() + body
