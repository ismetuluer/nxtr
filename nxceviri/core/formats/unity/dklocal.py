"""Donkey Kong Country Returns HD'nin `Localization` MonoBehaviour'u (`resources.assets`).

Oyunun tüm metinleri, tip ağacı silinmiş tek bir nesnededir ve Unity'nin `[SerializeReference]` kayıt defteri
olarak saklanır. Metin yok sayılsa bile yapı sıralıdır (nesne içinde ofset yoktur); bir dizgenin boyu değişince
yalnızca uzunluk alanı ve 4 bayt hizalaması değişir.

```
MonoBehaviour başlığı (m_GameObject, m_Enabled, m_Script, m_Name = "Localization")
int n; n × int64                  dil listesi: her dil için LanguageData kimliği (rid); -2 = boş yuva
int sürüm (2); int sayı           kayıt defteri
sayı × kayıt:
    int64 rid; dizge sınıf; dizge ad alanı ("dk3ds"); dizge derleme ("Assembly-CSharp")
    sınıfa göre veri:
      (boş)                       rid -2, üç boş dizge, veri yok
      LanguageData                int dil sırası; int m; m × int64 (yuvaların rid'i)
      SingleLanguageDataItem      [dizge ad]; dizge metin; uint32 numara; dizge etiket ("*", "Core"…); uint32; uint32
      MultipleLanguageDataItem    uint32 numara; [dizge ad]; int m; m × int64 (SingleLanguageDataItem rid'leri)
```

İlk sürümde (v0) tekli öğenin başında, çoklu öğenin numarasından sonra bir ad dizgesi (`NewText_60`, `blow`)
vardır; güncellemede (v65536) yoktur.
`parse` iki düzeni de dener, kayıt defterini tam bitiren geçerli olur.

Bir dilin yuvası ya tekli öğeye ya da çoklu öğeye (birkaç metin: değişkenler) başvurur. Ayrıntılar:
docs/formats/dkcr.md
"""

from __future__ import annotations

import struct
from collections.abc import Mapping
from dataclasses import dataclass, replace

NAMESPACE = "dk3ds"
ASSEMBLY = "Assembly-CSharp"
SINGLE = "SingleLanguageDataItem"
MULTIPLE = "MultipleLanguageDataItem"
LANGUAGE = "LanguageData"
_NULL_RID = -2
_REGISTRY_VERSION = 2
#: Makul üst sınırlar: bozuk veriyi dizi sanıp bellek tüketmemek için.
_MAX_COUNT = 1_000_000


@dataclass(frozen=True)
class Language:
    rid: int
    index: int
    slots: tuple[int, ...]


@dataclass(frozen=True)
class Single:
    rid: int
    text: str
    number: int
    tag: str
    extra: tuple[int, int]
    #: Yalnızca adlı düzende (v0) dolu; adsız düzende boş.
    name: str = ""


@dataclass(frozen=True)
class Multiple:
    rid: int
    number: int
    refs: tuple[int, ...]
    #: Yalnızca adlı düzende (v0) dolu.
    name: str = ""


@dataclass(frozen=True)
class Document:
    #: Kayıt defterine kadar olan baytlar (başlık ve dil listesi).
    prefix: bytes
    entries: tuple[Language | Single | Multiple | None, ...]
    #: Kayıt defteri bittikten sonra kalan baytlar (varsa), aynen korunur.
    tail: bytes
    null_rids: tuple[int, ...]
    #: Tekli öğelerin başında ad dizgesi var mı (v0 düzeni).
    named: bool = False

    @property
    def languages(self) -> list[Language]:
        return [e for e in self.entries if isinstance(e, Language)]

    @property
    def singles(self) -> dict[int, Single]:
        return {e.rid: e for e in self.entries if isinstance(e, Single)}

    @property
    def multiples(self) -> dict[int, Multiple]:
        return {e.rid: e for e in self.entries if isinstance(e, Multiple)}


class _Reader:
    def __init__(self, raw: bytes, pos: int = 0) -> None:
        self.raw = raw
        self.pos = pos

    def take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.raw):
            raise ValueError("veri bitti")
        out = self.raw[self.pos : self.pos + n]
        self.pos += n
        return out

    def i32(self) -> int:
        return int(struct.unpack("<i", self.take(4))[0])

    def u32(self) -> int:
        return int(struct.unpack("<I", self.take(4))[0])

    def i64(self) -> int:
        return int(struct.unpack("<q", self.take(8))[0])

    def count(self, unit: int) -> int:
        n = self.i32()
        if not 0 <= n <= _MAX_COUNT or n * unit > len(self.raw) - self.pos:
            raise ValueError("geçersiz dizi boyu")
        return n

    def string(self) -> str:
        n = self.i32()
        if n < 0:
            raise ValueError("geçersiz dizge boyu")
        text = self.take(n).decode("utf-8", "surrogateescape")
        self.pos += -self.pos % 4
        if self.pos > len(self.raw):
            raise ValueError("veri bitti")
        return text

    def rids(self) -> tuple[int, ...]:
        return tuple(self.i64() for _ in range(self.count(8)))


def parse(raw: bytes) -> Document | None:
    """Nesne bu yapıdaysa çözer; değilse None (yapı kesin doğrulanır, tahminle yazılmaz)."""
    for named in (False, True):
        doc = _parse(raw, named)
        if doc is not None:
            return doc
    return None


def _parse(raw: bytes, named: bool) -> Document | None:
    try:
        r = _Reader(raw, 12 + 4 + 12)  # m_GameObject, m_Enabled (hizalı), m_Script
        if r.string() != "Localization":
            return None
        listed = r.rids()
        if r.i32() != _REGISTRY_VERSION:
            return None
        total = r.i32()
        prefix = raw[: r.pos]
        if not 0 < total <= _MAX_COUNT:
            return None
        entries: list[Language | Single | Multiple | None] = []
        null_rids: list[int] = []
        for _ in range(total):
            rid = r.i64()
            kind, namespace, assembly = r.string(), r.string(), r.string()
            if not kind and not namespace and not assembly:
                if rid != _NULL_RID:
                    return None
                null_rids.append(rid)
                entries.append(None)
                continue
            if (namespace, assembly) != (NAMESPACE, ASSEMBLY):
                return None
            if kind == LANGUAGE:
                index = r.i32()
                entries.append(Language(rid, index, r.rids()))
            elif kind == SINGLE:
                name = r.string() if named else ""
                text = r.string()
                number = r.u32()
                tag = r.string()
                entries.append(Single(rid, text, number, tag, (r.u32(), r.u32()), name))
            elif kind == MULTIPLE:
                number = r.u32()
                name = r.string() if named else ""
                entries.append(Multiple(rid, number, r.rids(), name))
            else:
                return None
        doc = Document(prefix, tuple(entries), raw[r.pos :], tuple(null_rids), named)
    except (ValueError, struct.error):
        return None
    if r.pos != len(raw):
        return None  # kayıt defteri nesnenin sonunda biter; artık bayt varsa düzen yanlıştır
    known = {e.rid for e in doc.entries if e is not None}
    if len(known) != sum(1 for e in doc.entries if e is not None) or not doc.languages:
        return None
    if any(rid != _NULL_RID and rid not in known for rid in listed):
        return None
    return doc


def _w_string(out: bytearray, text: str) -> None:
    data = text.encode("utf-8", "surrogateescape")
    out += struct.pack("<i", len(data))
    out += data
    out += b"\0" * (-len(out) % 4)


def _w_rids(out: bytearray, rids: tuple[int, ...]) -> None:
    out += struct.pack("<i", len(rids))
    for rid in rids:
        out += struct.pack("<q", rid)


def serialize(doc: Document) -> bytes:
    out = bytearray(doc.prefix)
    for entry in doc.entries:
        if entry is None:
            out += struct.pack("<q", _NULL_RID)
            for _ in range(3):
                _w_string(out, "")
            continue
        out += struct.pack("<q", entry.rid)
        kind = LANGUAGE if isinstance(entry, Language) else SINGLE if isinstance(entry, Single) else MULTIPLE
        for part in (kind, NAMESPACE, ASSEMBLY):
            _w_string(out, part)
        if isinstance(entry, Language):
            out += struct.pack("<i", entry.index)
            _w_rids(out, entry.slots)
        elif isinstance(entry, Single):
            if doc.named:
                _w_string(out, entry.name)
            _w_string(out, entry.text)
            out += struct.pack("<I", entry.number)
            _w_string(out, entry.tag)
            out += struct.pack("<II", *entry.extra)
        else:
            out += struct.pack("<I", entry.number)
            if doc.named:
                _w_string(out, entry.name)
            _w_rids(out, entry.refs)
    out += doc.tail
    return bytes(out)


def with_texts(doc: Document, texts: Mapping[int, str]) -> Document:
    """`rid → yeni metin` değişikliklerini uygular."""
    return replace(
        doc,
        entries=tuple(
            replace(e, text=texts[e.rid]) if isinstance(e, Single) and e.rid in texts else e for e in doc.entries
        ),
    )


#: Dil sırası → dil kodu. Sıra, her dilin metinlerinden çıkarıldı (gerçek oyunda); 5. yuva boştur. İki yuva aynı dili
#: taşıyabilir (0 ve 7 İngilizce, biri ötekinden birkaç satırda farklı yazılmış; 1 ve 8 Fransızca; 2 ve 9 İspanyolca).
LANGUAGE_CODES = {
    0: "en",
    1: "fr",
    2: "es",
    3: "de",
    4: "it",
    6: "ja",
    7: "en",
    8: "fr",
    9: "es",
    10: "nl",
    11: "pt",
    12: "zh-hans",
    13: "zh-hant",
    14: "ko",
}


def language_code(language: Language) -> str:
    return LANGUAGE_CODES.get(language.index, "")


def unique_slots(doc: Document, language: Language) -> list[tuple[str, Single]]:
    """Dilin benzersiz metinleri sırayla: (yuva anahtarı, öğe).

    Doğrudan yuvanın anahtarı sırası (`12`); yalnızca bir çoklu öğenin çocuğu olan metin `yuva.k` (`40.1`) alır.
    Çoklu öğe aynı dilin başka bir yuvasındaki metne de başvurabilir; her metin bir kez, ilk yerinde sayılır.
    """
    singles, multiples = doc.singles, doc.multiples
    direct = {rid for rid in language.slots if rid in singles}
    seen: set[int] = set()
    out: list[tuple[str, Single]] = []
    for i, rid in enumerate(language.slots):
        if rid in singles:
            if rid not in seen:
                seen.add(rid)
                out.append((str(i), singles[rid]))
        elif rid in multiples:
            for k, ref in enumerate(multiples[rid].refs):
                if ref in singles and ref not in direct and ref not in seen:
                    seen.add(ref)
                    out.append((f"{i}.{k}", singles[ref]))
    return out
