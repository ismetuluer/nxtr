"""Devil May Cry (Switch) metin eklentisi.

- `fsd/*.fsd`: dizindeki 23. bölüm İngilizce mesaj tablosudur (73 dosyada doğrulandı); diğer bölümler
  başka dillerdir. Yazarken yalnızca bu bölüm yeniden kurulur, sonraki bölümler kaydırılır, dizin güncellenir.
- `etc_e/*.msg`: dosyanın kendisi bir mesaj tablosudur (dizgiler 16 bayta doldurulur).

Ayrıntı: docs/formats/dmc1.md. Cihazda doğrulanana kadar yazma deneyseldir.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping

from nxceviri.core.fontpatch import dmc1 as font
from nxceviri.core.fontpatch import dmc1_animation, dmc1_graphics
from nxceviri.core.fontpatch import dmc1_images as images
from nxceviri.core.fontpatch import dmc1_menu as menu
from nxceviri.core.formats.base import Context, FormatError, TextEntry
from nxceviri.core.formats.dmc1 import codec, exe, fsd
from nxceviri.core.translate import placeholders

#: `.fsd` dizininde İngilizce tablonun bölüm numarası.
ENGLISH_SLOT = 23
_MSG_PAD = 16


def _lang_dir(path: str) -> str:
    parts = path.replace("\\", "/").split("/")
    return parts[-2] if len(parts) > 1 else ""


def _has_words(text: str) -> bool:
    return any(ch.isalpha() for ch in placeholders.TOKEN_RE.sub("", text))


def _escape(data: bytes, table: codec.MessageTable) -> int:
    """Tablonun kaçış baytı: `.atm` dosyaları 0x80, diğerleri 0x7E kullanır (boşluk ve bitiş kodlarından anlaşılır)."""
    counts = dict.fromkeys((codec.ESCAPE, codec.ATM_ESCAPE), 0)
    for off, length in table.strings:
        seg = data[off : off + length]
        for esc in counts:
            counts[esc] += seg.count(bytes((esc, codec.CODE_SPACE))) + seg.count(bytes((esc, codec.CODE_END)))
    return codec.ATM_ESCAPE if counts[codec.ATM_ESCAPE] > counts[codec.ESCAPE] else codec.ESCAPE


def _messages(data: bytes, table: codec.MessageTable) -> list[codec.Message]:
    escape = _escape(data, table)
    return [codec.decode(data[off : off + length], escape) for off, length in table.strings]


def translate_menu_textures(data: bytes) -> bytes:
    """`st_init.dat` içindeki menü başlığı dokularını Türkçe hâlleriyle değiştirir (metin bölümüne dokunmaz)."""
    out: dict[int, bytes] = {}
    for offset in fsd.read_directory(data, wide=False):
        if not offset:
            continue
        start, end = fsd.block_range(data, offset, wide=False)
        texture = menu.translate_texture(data[start:end])
        if texture is not None:
            out[offset] = texture
    return fsd.replace_blocks(data, out, wide=False) if out else data


#: Menü başlığı resimlerini taşıyan dosyalar. `status_u` Japonca metin içerir (çevrilmez) ama oyun aynı resimlerin
#: oradaki kopyasını da kullanır; ikisi de değiştirilir.
MENU_FILES = ("data/dmc1/status_e/st_init.dat", "data/dmc1/status_u/st_init.dat")


def _pad(table: codec.MessageTable) -> int:
    """Yeniden yazılan dizgilerin dolgu katı: özgün dizgilerin hepsinin uzunluğu neyin katıysa."""
    for pad in (16, 4):
        if all(n % pad == 0 for _o, n in table.strings):
            return pad
    return 1


#: Dosya düzenleri: tek başına mesaj tablosu (`.msg`), sahne (`.fsd`, u64 dizin) ve durum (`st_init.dat`, u32 dizin).
MSG, FSD, DAT = "msg", "fsd", "dat"


def _layout(data: bytes) -> tuple[str, codec.MessageTable] | None:
    """Dosyanın düzeni ve İngilizce tablosu; tanınmıyorsa None. Dosya yolu gerekmez (dışa aktarma doğrulaması)."""
    table = codec.parse_table(data, 0)
    if table is not None:
        return MSG, table
    for kind, wide in ((FSD, True), (DAT, False)):
        try:
            offsets = fsd.read_directory(data, wide=wide)
        except FormatError:
            continue
        # `.fsd`: İngilizce tablo 23. bölümdedir. u32 dizinli dosyalarda tablo, mesaj tablosu olan ilk bölümdür
        # (`st_init.dat`: 0, `memicon.dat`: 3; diğer bölümler dokudur).
        slots = [ENGLISH_SLOT] if kind == FSD else range(len(offsets))
        for slot in slots:
            if len(offsets) > slot and offsets[slot]:
                table = codec.parse_table(data, offsets[slot])
                if table is not None:
                    return kind, table
    return None


class Dmc1Plugin:
    name = "dmc1"
    label = "Devil May Cry (mesaj tabloları)"
    candidates_only = True
    path_suffixes: tuple[str, ...] = (".fsd", ".msg", ".atm", "st_init.dat", "memicon.dat")
    #: Dışa aktarma bu oyun için kendi yazı dokusunu (`support_files`) ekler; hiçbir harf dönüştürülmez.
    unsupported_letters = ""

    def detect(self, path: str, head: bytes) -> bool:
        lower = path.lower().replace("\\", "/")
        if lower.endswith(".fsd"):
            return "/dmc1/" in lower
        if lower.endswith("etc_u/memicon.dat"):  # kayıt ekranı mesajları (İngilizcesi yalnızca `etc_u` içinde)
            return True
        return lower.endswith((".msg", ".atm", "st_init.dat")) and _lang_dir(lower).endswith("_e")

    def normalize_text(self, text: str) -> str:
        """Dışa aktarmadan önce çeviriye uygulanır; böylece yazılan metin geri okunanla birebir aynı olur."""
        return codec.normalize(text)

    def support_files(self) -> dict[str, bytes]:
        """Moda eklenmesi gereken ek dosyalar (RomFS'e göre yol → içerik): Türkçe harfli yazı dokusu."""
        regular = font.system_font()
        return {"data/dmc1/etc_e/msg_tex.t32": font.build_texture(codec.FONT_CELLS, regular)}

    def game_file_patches(self) -> dict[str, Callable[[bytes], bytes]]:
        """Oyunun metin dışında değiştirilecek dosyaları (RomFS'e göre yol → dönüştürücü): resimlerdeki yazılar."""
        patches: dict[str, Callable[[bytes], bytes]] = dict.fromkeys(images.FILES, images.translate_file)
        graphics = dmc1_graphics.from_environment()
        if graphics is not None:  # kullanıcının hazırladığı Türkçe sayfalar (etiketlerin yerine geçer)
            ready = functools.partial(images.translate_file, replacements=graphics.pages)
            patches.update(dict.fromkeys((*images.FILES, *graphics.files), ready))
            for path, (english, turkish) in graphics.animations.items():
                patches[path] = functools.partial(
                    dmc1_animation.translate_animation, last_english=english, last_turkish=turkish
                )
        patches.update(dict.fromkeys(MENU_FILES, translate_menu_textures))
        return patches

    def exefs_patches(self, code: bytes) -> dict[str, bytes]:
        """Program koduna uygulanacak IPS yamaları (yapı kimliği → yama): Türkçe düşman açıklamaları."""
        return {exe.BUILD_ID: exe.ips(exe.build_patch(code, exe.translations()))}

    def collect_context(self, data: bytes, path: str = "") -> dict[object, object]:
        return {}

    def language(self, data: bytes) -> str | None:
        return None  # İngilizce tablo dosya içinde sabit yerdedir

    def _entries(self, data: bytes) -> tuple[str, list[tuple[str, codec.MessageTable, int, codec.Message]]]:
        layout = _layout(data)
        if layout is None:
            return MSG, []
        kind, table = layout
        out = []
        for i, message in enumerate(_messages(data, table)):
            if _has_words(message.text):  # boş ya da yalnızca kod/rakam doldurmalı satır: çevrilecek metin yok
                out.append((f"{table.offset:x}/{i}" if kind == FSD else str(i), table, i, message))
        return kind, out

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        _kind, entries = self._entries(data)
        return [TextEntry(key, n, message.text, message.codes) for n, (key, _table, _i, message) in enumerate(entries)]

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        """Çevirileri İngilizce tabloya yazar; tablo büyüyebilir, sonraki fsd bölümleri kaydırılır."""
        if not translations:
            return data
        kind, found = self._entries(data)
        standalone = kind == MSG
        entries = {key: (table, i, message) for key, table, i, message in found}
        unknown = [k for k in translations if k not in entries]
        if unknown:
            raise FormatError(f"Dosyada olmayan satırlar için çeviri verildi: {', '.join(unknown[:5])}")
        table = entries[next(iter(translations))][0]
        strings = [data[off : off + length] for off, length in table.strings]
        first = entries[next(iter(translations))][2]
        # `.msg` dizgileri cihazda doğrulandığı gibi 16'nın katına doldurulur; diğerleri özgün dolgu katını izler.
        pad = _MSG_PAD if standalone and first.escape == codec.ESCAPE else _pad(table)
        changed = False
        for key, new in translations.items():
            _table, index, message = entries[key]
            issues = placeholders.problems(message.text, new)
            if issues:
                raise FormatError(f"'{key}' çevirisi yazılamadı: {' '.join(issues)}")
            if new != message.text:  # değişmeyen dizgi özgün baytlarıyla kalır
                strings[index] = codec.encode(message, new, pad_to=pad)
                changed = True
        if not changed:
            return data
        rebuilt = codec.build_table(strings, first=table.first)
        if standalone:
            if table.offset != 0 or table.end > len(data):
                raise FormatError("Mesaj dosyasının yapısı beklenenden farklı.")
            return rebuilt + data[table.end :]
        return fsd.replace_blocks(data, {table.offset: rebuilt}, wide=kind == FSD)
