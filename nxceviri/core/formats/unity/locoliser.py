"""Despelote'nin `Locoliser` MonoBehaviour'u: TSV yerelleştirme tablolarının oyuna gömülmüş, ayrıştırılmış kopyası.

Oyun çalışırken metinleri TSV TextAsset'lerinden değil, bu nesneden okur (TSV'ler yalnızca editörde
önbelleği üretmek için kullanılır). `resources.assets` içindedir ve tip ağacı silinmiştir; bu yüzden ham
bayttan çözülür. Unity serileştirmesi sıralıdır (nesne içinde ofset yoktur): bir dizgenin boyu değişince
yalnızca uzunluk alanı ve 4 bayt hizalaması değişir, geri kalan alanlar olduğu gibi yazılır.

Dizilim (Despelote 1.0.1, Unity 2021.3):

```
MonoBehaviour başlığı (m_GameObject, m_Enabled, m_Script, m_Name)
int, int                                   bilinmeyen alanlar (aynen korunur)
PPtr<TextAsset>       diyalog TSV'si       (ör. despelote_loc_monsterFile)
string[]              anahtarlar           "01_kids/conversations/armararcodiscussion/nina1_01"
Entry[]               her anahtar için:    Sub[] { int sıra; float başlangıç; float bitiş; string[] diller }
PPtr<TextAsset>       menü TSV'si          (ör. despelote_loc_UI)
Row[]                 menü satırları:      string[] diller
...                   kalan alanlar (font başvuruları vb., aynen korunur)
```

Dil sırası başvurulan TSV'nin dil sütunlarıyla aynıdır (es, en, fr, de, br, chs). Ayrıntılar:
docs/formats/unity.md
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, replace

#: Bu nesnenin sonunda kalabilecek bilinmeyen alanların üst sınırı (bayt); daha fazlası başka bir yapıdır.
_MAX_TAIL = 4096
#: Makul üst sınırlar: bozuk veriyi dizi sanıp bellek tüketmemek için.
_MAX_COUNT = 1_000_000


@dataclass(frozen=True)
class Subtitle:
    index: int
    timing: bytes  # başlangıç ve bitiş (iki float32), aynen korunur
    texts: tuple[str, ...]


@dataclass(frozen=True)
class Locoliser:
    #: anahtar dizisine kadar olan baytlar (başlık, iki bilinmeyen alan, diyalog TSV başvurusu)
    prefix: bytes
    dialogue_file: int  # diyalog TSV'sinin path_id'si (aynı dosyada)
    keys: tuple[str, ...]
    entries: tuple[tuple[Subtitle, ...], ...]
    ui_pointer: bytes  # menü TSV başvurusu (12 bayt), aynen korunur
    ui_file: int
    ui_rows: tuple[tuple[str, ...], ...]
    tail: bytes

    @property
    def language_count(self) -> int:
        for subs in self.entries:
            for sub in subs:
                return len(sub.texts)
        return len(self.ui_rows[0]) if self.ui_rows else 0


class _Reader:
    def __init__(self, raw: bytes, pos: int) -> None:
        self.raw = raw
        self.pos = pos

    def i32(self) -> int:
        if self.pos + 4 > len(self.raw):
            raise ValueError("veri bitti")
        value = int(struct.unpack_from("<i", self.raw, self.pos)[0])
        self.pos += 4
        return value

    def count(self) -> int:
        """Dizi boyu: her öğe en az 4 bayt tuttuğundan kalan veriden büyük olamaz."""
        n = self.i32()
        if not 0 <= n <= _MAX_COUNT or n * 4 > len(self.raw) - self.pos:
            raise ValueError("geçersiz dizi boyu")
        return n

    def take(self, n: int) -> bytes:
        if self.pos + n > len(self.raw):
            raise ValueError("veri bitti")
        out = self.raw[self.pos : self.pos + n]
        self.pos += n
        return out

    def string(self) -> str:
        n = self.i32()
        if n < 0:
            raise ValueError("geçersiz dizge boyu")
        text = self.take(n).decode("utf-8", "surrogateescape")
        self.pos += -self.pos % 4
        return text

    def strings(self) -> tuple[str, ...]:
        return tuple(self.string() for _ in range(self.count()))


def _header_end(raw: bytes) -> int:
    """MonoBehaviour başlığının (m_GameObject, m_Enabled, m_Script, m_Name) bittiği konum."""
    r = _Reader(raw, 12 + 4 + 12)  # PPtr, m_Enabled (hizalı), PPtr
    r.string()
    return r.pos


def parse(raw: bytes) -> Locoliser | None:
    """Nesne bu yapıdaysa çözer; değilse None (yapı kesin doğrulanır, tahminle yazılmaz)."""
    try:
        r = _Reader(raw, _header_end(raw))
        r.i32()
        r.i32()
        r.take(4)  # PPtr m_FileID
        dialogue_file = int(struct.unpack("<q", r.take(8))[0])
        prefix = raw[: r.pos]
        keys = r.strings()
        n_entries = r.count()
        if n_entries != len(keys) or not keys:
            return None
        entries = []
        languages = None
        for _ in range(n_entries):
            subs = []
            for _ in range(r.count()):
                index = r.i32()
                timing = r.take(8)
                texts = r.strings()
                if languages is None:
                    languages = len(texts)
                if len(texts) != languages or languages < 2:
                    return None
                subs.append(Subtitle(index, timing, texts))
            entries.append(tuple(subs))
        ui_pointer = r.take(12)
        ui_file = int(struct.unpack_from("<q", ui_pointer, 4)[0])
        ui_rows = tuple(r.strings() for _ in range(r.count()))
        if languages is None or any(len(row) != languages for row in ui_rows):
            return None
        tail = raw[r.pos :]
        if len(tail) > _MAX_TAIL:
            return None
    except (ValueError, struct.error):
        return None
    return Locoliser(prefix, dialogue_file, keys, tuple(entries), ui_pointer, ui_file, ui_rows, tail)


def _w_string(out: bytearray, text: str) -> None:
    data = text.encode("utf-8", "surrogateescape")
    out += struct.pack("<i", len(data))
    out += data
    out += b"\0" * (-len(out) % 4)


def _w_strings(out: bytearray, items: tuple[str, ...]) -> None:
    out += struct.pack("<i", len(items))
    for item in items:
        _w_string(out, item)


def serialize(loc: Locoliser) -> bytes:
    out = bytearray(loc.prefix)
    _w_strings(out, loc.keys)
    out += struct.pack("<i", len(loc.entries))
    for subs in loc.entries:
        out += struct.pack("<i", len(subs))
        for sub in subs:
            out += struct.pack("<i", sub.index)
            out += sub.timing
            _w_strings(out, sub.texts)
    out += loc.ui_pointer
    out += struct.pack("<i", len(loc.ui_rows))
    for row in loc.ui_rows:
        _w_strings(out, row)
    out += loc.tail
    return bytes(out)


def with_texts(
    loc: Locoliser,
    dialogue: dict[tuple[int, int], tuple[str, ...]],
    ui: dict[int, tuple[str, ...]],
) -> Locoliser:
    """`(girdi, altyazı) → diller` ve `menü satırı → diller` değişikliklerini uygular."""
    entries = tuple(
        tuple(replace(sub, texts=dialogue[(ei, si)]) if (ei, si) in dialogue else sub for si, sub in enumerate(subs))
        for ei, subs in enumerate(loc.entries)
    )
    rows = tuple(ui.get(i, row) for i, row in enumerate(loc.ui_rows))
    return replace(loc, entries=entries, ui_rows=rows)
