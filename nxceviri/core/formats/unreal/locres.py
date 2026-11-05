"""Unreal Engine yerelleştirme kaynağı (.locres) okuma ve geri yazma.

Sürümler (ELocResVersion):

- **0 Legacy:** sihirli GUID yok. `u32 ad alanı sayısı`, her ad alanı: `FString ad, u32 anahtar
  sayısı`, her anahtar: `FString anahtar, u32 kaynak özeti, FString yerelleştirilmiş metin`.
- **1 Compact:** `GUID | u8 sürüm | i64 metin dizisi ofseti | u32 ad alanı sayısı` …; anahtar
  kaydı `FString anahtar, u32 kaynak özeti, i32 metin indeksi`. Metinler dosya sonunda tek dizide.
- **2 Optimized_CRC32 / 3 Optimized_CityHash64_UTF16:** ofsetten sonra `u32 toplam girdi sayısı`;
  ad alanı ve anahtar adlarının önünde `u32 özet`; metin dizisindeki her metnin ardından `i32 referans
  sayısı`.

FString: `i32 uzunluk` (boş sonlandırıcı dahil); pozitifse ANSI baytlar, negatifse UTF-16LE.

Geri yazma: ad alanları, anahtarlar, özetler ve kaynak özetleri olduğu gibi kalır (kaynak özeti
oyunun "metin güncel mi" denetiminde kullanılır; değiştirilirse çeviri yok sayılabilir). Yalnızca
metinler değişir. Değişmeyen metinlerin ham baytları korunur; yeni metinler dizinin sonuna eklenir.
Hiçbir metin değişmediyse orijinal dosya aynen döner. Ayrıntılar: docs/formats/unreal.md
"""

from __future__ import annotations

import re
import struct
from collections.abc import Mapping
from dataclasses import dataclass, field

from nxceviri.core.formats.base import Context, ControlCode, FormatError, TextEntry
from nxceviri.core.translate import markup, placeholders

MAGIC = bytes.fromhex("0E147475674A03FC4A15909DC3377F1B")

#: UMG zengin metin etiketleri: `<Bold>`, `</>`, `<img id="X"/>`, `<RichText.Style>`.
_TAG_RE = re.compile(r"</?[A-Za-z0-9_.\-]*(?:\s[^<>\n]{0,200})?/?>")


def _tag_label(tag: str) -> str:
    if tag.startswith("{"):
        return f"Değişken {tag}" if len(tag) <= 40 else "Değişken / biçim ifadesi"
    if tag == "</>":
        return "Biçim sonu"
    m = re.match(r"<(/?)([A-Za-z0-9_.\-]*)", tag)
    name = m.group(2) if m else ""
    if name.lower() == "img":
        return "Simge (img)"
    return f"Biçim etiketi <{name}>" if name else "Biçim etiketi"


class _Reader:
    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.data = data
        self.pos = pos

    def take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise FormatError(".locres dosyası bozuk: veri beklenenden önce bitti.")
        out = self.data[self.pos : self.pos + n]
        self.pos += n
        return out

    def u8(self) -> int:
        return self.take(1)[0]

    def u32(self) -> int:
        return int(struct.unpack("<I", self.take(4))[0])

    def i32(self) -> int:
        return int(struct.unpack("<i", self.take(4))[0])

    def i64(self) -> int:
        return int(struct.unpack("<q", self.take(8))[0])

    def fstring(self) -> tuple[str, bytes]:
        """(metin, ham bayt dizisi — uzunluk alanı dahil)."""
        start = self.pos
        length = self.i32()
        if length == 0:
            return "", self.data[start : self.pos]
        if length > 0:
            raw = self.take(length)
            if raw[-1:] != b"\0":
                raise FormatError(".locres dosyası bozuk: metin sonlandırıcısı yok.")
            text = raw[:-1].decode("latin-1")
        else:
            if -length > 0x1000000:
                raise FormatError(".locres dosyası bozuk: metin uzunluğu mantıksız.")
            raw = self.take(-length * 2)
            if raw[-2:] != b"\0\0":
                raise FormatError(".locres dosyası bozuk: metin sonlandırıcısı yok.")
            try:
                text = raw[:-2].decode("utf-16-le")
            except UnicodeDecodeError:
                raise FormatError(".locres dosyası bozuk: geçersiz UTF-16 metin.") from None
        return text, self.data[start : self.pos]


def encode_fstring(text: str) -> bytes:
    if not text:
        return struct.pack("<i", 0)
    if all(ord(c) < 0x80 for c in text):
        raw = text.encode("ascii") + b"\0"
        return struct.pack("<i", len(raw)) + raw
    raw = text.encode("utf-16-le") + b"\0\0"
    return struct.pack("<i", -(len(raw) // 2)) + raw


@dataclass
class _Entry:
    namespace: str
    key: str
    source_hash: int
    string_index: int  # Legacy'de kendi metni; diğerlerinde dizideki yeri
    record_offset: int  # metin indeksi alanının dosyadaki konumu (Compact+)


@dataclass
class LocresFile:
    version: int
    entries: list[_Entry] = field(default_factory=list)
    strings: list[str] = field(default_factory=list)
    string_raw: list[bytes] = field(default_factory=list)
    refcounts: list[int] = field(default_factory=list)
    offset_field: int = 0  # metin dizisi ofsetinin dosyadaki konumu
    strings_offset: int = 0
    legacy_layout: list[tuple[int, int]] = field(default_factory=list)  # (metin başlangıcı, bitişi)


def read(data: bytes) -> LocresFile:
    r = _Reader(data)
    if data.startswith(MAGIC):
        r.take(16)
        version = r.u8()
        if version > 3:
            raise FormatError(f".locres sürümü desteklenmiyor ({version}).")
        f = LocresFile(version)
        f.offset_field = r.pos
        f.strings_offset = r.i64()
        if not 0 < f.strings_offset <= len(data):
            raise FormatError(".locres dosyası bozuk: metin dizisi ofseti geçersiz.")
        if version >= 2:
            r.u32()  # toplam girdi sayısı
    else:
        f = LocresFile(0)
    ns_count = r.u32()
    if ns_count > 1_000_000:
        raise FormatError("Dosya bir .locres değil veya bozuk (ad alanı sayısı mantıksız).")
    for _ in range(ns_count):
        if f.version >= 2:
            r.u32()
        namespace, _raw = r.fstring()
        key_count = r.u32()
        if key_count > 10_000_000:
            raise FormatError(".locres dosyası bozuk: anahtar sayısı mantıksız.")
        for _ in range(key_count):
            if f.version >= 2:
                r.u32()
            key, _raw = r.fstring()
            source_hash = r.u32()
            if f.version == 0:
                start = r.pos
                text, raw = r.fstring()
                f.legacy_layout.append((start, r.pos))
                f.entries.append(_Entry(namespace, key, source_hash, len(f.strings), start))
                f.strings.append(text)
                f.string_raw.append(raw)
            else:
                record = r.pos
                f.entries.append(_Entry(namespace, key, source_hash, r.i32(), record))
    if f.version >= 1:
        r.pos = f.strings_offset
        count = r.u32()
        if count > 10_000_000:
            raise FormatError(".locres dosyası bozuk: metin sayısı mantıksız.")
        for _ in range(count):
            text, raw = r.fstring()
            f.strings.append(text)
            f.string_raw.append(raw)
            f.refcounts.append(r.i32() if f.version >= 2 else 1)
        for e in f.entries:
            if not 0 <= e.string_index < len(f.strings):
                raise FormatError(".locres dosyası bozuk: geçersiz metin indeksi.")
        if r.pos != len(data):
            raise FormatError(".locres dosyası beklenmeyen baytlarla bitiyor; desteklenmeyen bir biçim olabilir.")
    return f


def _entry_key(e: _Entry) -> str:
    return f"{e.namespace}/{e.key}" if e.namespace else e.key


def _unique_keys(f: LocresFile) -> list[str]:
    seen: set[str] = set()
    keys = []
    for i, e in enumerate(f.entries):
        k = _entry_key(e)
        if k in seen:
            k = f"{k}#{i}"
        seen.add(k)
        keys.append(k)
    return keys


def tokenize(text: str) -> tuple[str, tuple[ControlCode, ...]]:
    return markup.tokenize(text, _TAG_RE, _tag_label)


class LocresPlugin:
    name = "unreal"
    label = "Unreal yerelleştirme (.locres)"
    candidates_only = True
    path_suffixes: tuple[str, ...] = (".locres",)

    def detect(self, path: str, head: bytes) -> bool:
        return head.startswith(MAGIC) or path.lower().endswith(".locres")

    def collect_context(self, data: bytes, path: str = "") -> dict[object, object]:
        return {}  # ad alanı ve anahtar dosyanın içinde

    def language(self, data: bytes) -> str | None:
        return None  # dil, dosyanın yolundan (…/Localization/Game/<dil>/Game.locres) anlaşılır

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        f = read(data)
        out = []
        for i, (e, key) in enumerate(zip(f.entries, _unique_keys(f), strict=True)):
            display, codes = tokenize(f.strings[e.string_index])
            out.append(TextEntry(key, i, display, codes, context=_entry_key(e)))
        return out

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        if not translations:
            return data
        f = read(data)
        keys = _unique_keys(f)
        unknown = [k for k in translations if k not in set(keys)]
        if unknown:
            raise FormatError(f".locres dosyasında olmayan girdiler için çeviri verildi: {', '.join(unknown[:5])}")
        new_texts: list[str] = []
        changed = False
        for e, key in zip(f.entries, keys, strict=True):
            original = f.strings[e.string_index]
            new = translations.get(key)
            if new is None:
                new_texts.append(original)
                continue
            display, codes = tokenize(original)
            issues = placeholders.problems(display, new)
            if issues:
                raise FormatError(f"'{key}' çevirisi yazılamadı: {' '.join(issues)}")
            text = markup.detokenize(new, codes)
            changed |= text != original
            new_texts.append(text)
        if not changed:
            return data
        return _build_legacy(data, f, new_texts) if f.version == 0 else _build_compact(data, f, new_texts)


def _build_legacy(data: bytes, f: LocresFile, texts: list[str]) -> bytes:
    out = bytearray()
    pos = 0
    for (start, end), text, raw, old in zip(f.legacy_layout, texts, f.string_raw, f.strings, strict=True):
        out += data[pos:start]
        out += raw if text == old else encode_fstring(text)
        pos = end
    out += data[pos:]
    return bytes(out)


def _build_compact(data: bytes, f: LocresFile, texts: list[str]) -> bytes:
    strings = list(f.strings)
    raws = list(f.string_raw)
    index_of = {s: i for i, s in reversed(list(enumerate(strings)))}
    new_index: list[int] = []
    for e, text in zip(f.entries, texts, strict=True):
        if text == f.strings[e.string_index]:
            new_index.append(e.string_index)
            continue
        idx = index_of.get(text)
        if idx is None:
            idx = len(strings)
            strings.append(text)
            raws.append(encode_fstring(text))
            index_of[text] = idx
        new_index.append(idx)
    refcounts = [0] * len(strings)
    for idx in new_index:
        refcounts[idx] += 1
    head = bytearray(data[: f.strings_offset])
    for e, idx in zip(f.entries, new_index, strict=True):
        struct.pack_into("<i", head, e.record_offset, idx)
    tail = bytearray(struct.pack("<I", len(strings)))
    for i, raw in enumerate(raws):
        tail += raw
        if f.version >= 2:
            tail += struct.pack("<i", refcounts[i])
    struct.pack_into("<q", head, f.offset_field, len(head))
    return bytes(head + tail)
