"""Devil May Cry (Switch) menü başlığı resimlerini Türkçeleştirme: `status_e/st_init.dat` dokuları.

Durum (pause) menüsünün başlıkları (Weapon, Item, Map, File, Exit …) metin değil, `st_init.dat` dosyasının
1–4. bölümlerindeki T32 dokularına çizilmiş resimlerdir (docs/formats/dmc1.md). Switch dokuları BC7 (DX10 DDS)
sayfalarıdır; her sayfa okunur, İngilizce sözcüğün bulunduğu pencere silinir ve Türkçe karşılığı aynı yükseklikte,
aynı taban çizgisinde, özgün renk ve parıltıyla çizilir. Dokular PC sürümünün (ve oyunun yazı dokusunun, cihazda
doğrulandı) kullandığı sıkıştırılmamış biçimde geri yazılır: 0xC0 baytlık T32 başlığı + sayfa başına DDS.

Oyun dokuları toplamsal karıştırmayla çizer: siyah görünmez, alfa her yerde 255'tir.
"""

from __future__ import annotations

import struct

from PIL import Image

from nxceviri.core.fontpatch.dmc1 import FontError
from nxceviri.core.fontpatch.labels import Label, draw_label, find_font

T32_HEADER = 0xC0
_DDS = 128
_DX10 = 148
#: BC7_UNORM (DXGI_FORMAT 98).
_BC7 = 98


_STATUS_WORDS = (
    Label((6, 30, 124, 80), "Weapon", "Silah"),
    Label((134, 30, 188, 62), "New", "Yeni"),
    Label((6, 88, 118, 130), "Total Exp", "Toplam Puan"),
    Label((6, 144, 112, 184), "Action", "Hareket"),
    Label((128, 160, 220, 206), "Map", "Harita"),
    Label((6, 200, 82, 236), "Item", "Eşya"),
)
_FILE_WORDS = (
    Label((3, 4, 80, 50), "File", "Dosya", align="left", shift=6),  # solundaki "Harita" ile arası açılsın
    Label((96, 6, 162, 46), "Exit", "Çıkış"),
)
_MAP_WORDS = (
    Label((4, 2, 166, 33), "Floor Select mode", "Kat Seçimi", style="serif", align="left"),
    Label((4, 34, 164, 61), "Move MAP mode", "Haritayı Kaydır", style="serif", align="left"),
    Label((4, 65, 100, 93), "Roll MAP", "Döndür", style="serif", align="left"),
)
#: Doku kimliği (T32 başlığında 0x14) → sözcükler. Pencereler her sayfada (normal ve seçili) aynıdır.
#: Aynı resimler `status_e` ve `status_u` dosyalarında farklı kimliklerle iki kez bulunur.
WORDS: dict[int, tuple[Label, ...]] = {
    0xAECBB6FE: _STATUS_WORDS,
    0x3729D0FF: _FILE_WORDS,
    0xF6A70F3F: _MAP_WORDS,
    0x7C3C275B: _STATUS_WORDS,
    0xE5DE415A: _FILE_WORDS,
    0x24509E9A: _MAP_WORDS,
}


def texture_id(t32: bytes) -> int:
    return struct.unpack_from("<I", t32, 0x14)[0] if len(t32) >= 0x18 and t32[1:4] == b"2MT" else 0


def read_pages(t32: bytes) -> list[Image.Image]:
    """T32 dokusunun sayfaları (BC7 veya sıkıştırılmamış BGRA DDS) RGBA resim olarak."""
    pages = []
    pos = struct.unpack_from("<I", t32, 8)[0]
    for _ in range(struct.unpack_from("<I", t32, 4)[0]):
        if t32[pos : pos + 4] != b"DDS ":
            raise FontError("Menü dokusunun yapısı beklenenden farklı.")
        height, width = struct.unpack_from("<II", t32, pos + 12)
        if t32[pos + 84 : pos + 88] == b"DX10":
            if struct.unpack_from("<I", t32, pos + _DDS)[0] != _BC7:
                raise FontError("Menü dokusu bilinmeyen bir sıkıştırma kullanıyor.")
            size = width * height
            pages.append(Image.frombytes("RGBA", (width, height), t32[pos + _DX10 : pos + _DX10 + size], "bcn", 7))
            pos += _DX10 + size
        else:
            size = width * height * 4
            pages.append(Image.frombytes("RGBA", (width, height), t32[pos + _DDS : pos + _DDS + size], "raw", "BGRA"))
            pos += _DDS + size
    return pages


def _dds_header(width: int, height: int) -> bytes:
    """Sıkıştırılmamış A8R8G8B8 DDS başlığı (PC sürümünün menü dokularıyla aynı alanlar)."""
    head = bytearray(_DDS)
    head[0:4] = b"DDS "
    struct.pack_into("<7I", head, 4, 124, 0x81007, height, width, width * height * 4, 0, 0)
    struct.pack_into("<I", head, 36, _DDS + width * height * 4)
    struct.pack_into("<8I", head, 76, 32, 0x41, 0, 32, 0xFF0000, 0xFF00, 0xFF, 0xFF000000)
    struct.pack_into("<I", head, 108, 0x1000)
    return bytes(head)


def write_t32(original: bytes, pages: list[Image.Image]) -> bytes:
    """Özgün başlığı koruyup sayfaları sıkıştırılmamış yazar (başlık boyu 0xC0, 0x3C = bir sayfanın boyu)."""
    head = bytearray(original[:T32_HEADER])
    struct.pack_into("<I", head, 8, T32_HEADER)
    struct.pack_into("<I", head, 0x3C, _DDS + pages[0].width * pages[0].height * 4)
    body = b"".join(_dds_header(p.width, p.height) + p.tobytes("raw", "BGRA") for p in pages)
    return bytes(head) + body


def translate_texture(t32: bytes) -> bytes | None:
    """Bilinen bir menü dokusuysa Türkçe başlıklı hâlini döndürür; değilse None."""
    words = WORDS.get(texture_id(t32))
    if words is None:
        return None
    fonts = {style: find_font(style) for style in {word.style for word in words}}
    pages = read_pages(t32)
    for i in range(len(pages)):
        for word in words:
            pages[i] = draw_label(pages[i], word, fonts[word.style])
    return write_t32(t32, pages)
