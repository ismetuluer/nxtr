"""Devil May Cry (Switch) program kodundaki metinler: düşman dosyası açıklamaları.

Düşman açıklamaları RomFS'te değil, oyunun program kodunda (ExeFS `main`, `ro` bölümü) oyunun kendi harf
kodlamasıyla durur (docs/formats/dmc1.md). Japonca, İngilizce, Fransızca, Almanca, İtalyanca ve İspanyolca
açıklamalar art arda dizilmiştir; her biri `7E 0E 00 00` ile biter. Oyun bunlara bir işaretçi dizisiyle ulaşır ve
dizinin değerleri yükleme anında `.rela.dyn` içindeki R_AARCH64_RELATIVE kayıtlarıyla yazılır.

Türkçe metinler İngilizce metinlerin kapladığı bölgeye art arda yazılır ve her kaydın adresi (addend) yeni yerine
çevrilir; böylece tek tek metinlerin İngilizcesine sığması gerekmez, yalnızca toplam bölgeye sığmaları gerekir.
Değişiklik oyunun dosyasına yazılmaz: Atmosphère/emülatörlerin okuduğu bir IPS yamasıdır (`<build id>.ips`).
"""

from __future__ import annotations

import hashlib
import itertools
import json
import struct
from dataclasses import dataclass
from importlib import resources

from nxceviri.core.formats.base import FormatError
from nxceviri.core.formats.dmc1 import codec

#: Desteklenen sürüm (v0): yama yalnızca bu yapı kimliğine uygulanır.
BUILD_ID = "883F54C67475ABAE9611355F210059F8"
#: Açılmış koddaki (text + ro + data art arda) `ro` bölümünün başı ve bellekteki adresi.
_RO_FILE, _RO_MEM = 0x57F700, 0x580000
_RELATIVE = 0x403
_NSO_HEADER = 0x100
_END = b"\x7e\x0e"
#: Bir açıklamanın en çok bayt sayısı (aday taramasında bundan uzun, metin olmayan aralıklar atlanır).
_MAX_TEXT = 2000


@dataclass(frozen=True)
class Entry:
    rela: int  # açılmış kodda `.rela.dyn` kaydının başı (r_offset, r_info, r_addend)
    start: int  # metnin açılmış koddaki başı
    end: int  # bitiş kodu ve parametreleri dahil sonu
    english: str  # koddan çözülen metin; yalnızca özetlenip karşılaştırılır


def _mem(offset: int) -> int:
    return _RO_MEM + offset - _RO_FILE


def _file(mem: int) -> int:
    return mem - _RO_MEM + _RO_FILE


def _span(code: bytes, mem: int) -> tuple[int, int]:
    start = _file(mem)
    end = code.find(_END, start)
    if not 0 <= start < len(code) or end < 0:
        raise FormatError("Oyun kodunda düşman açıklaması beklenen yerde değil.")
    return start, end + 4


def digest(text: str) -> str:
    """Özgün metnin SHA-256 özeti (satır sonu türü ve satır sonu boşlukları atılır); metin depoda tutulmaz."""
    rows = text.splitlines()
    return hashlib.sha256(chr(10).join(r.rstrip() for r in rows).strip().encode("utf-8")).hexdigest()


def _find_text(code: bytes, first_digest: str) -> int:
    """Özeti `first_digest` olan açıklamanın koddaki başı (her bitiş kodundan sonra başlayan aday taranır); yoksa -1."""
    end = code.find(_END, _RO_FILE)
    while end >= 0:
        start = end + 4
        stop = code.find(_END, start)
        if stop < 0:
            break
        if stop - start < _MAX_TEXT and digest(codec.decode(code[start : stop + 4]).text) == first_digest:
            return start
        end = stop
    return -1


def find_entries(code: bytes, first_digest: str) -> list[Entry]:
    """İngilizce açıklamaların işaretçi kayıtları (ilk açıklamasının özeti `first_digest` olan ardışık dizi)."""
    target = _find_text(code, first_digest)
    if target < 0:
        raise FormatError("Oyun kodunda düşman açıklamaları bulunamadı.", "Desteklenen oyun sürümü: v0.")
    # kaydın addend alanı (16. bayt) metnin adresidir; kaydın info alanı RELATIVE olmalı
    rela = code.find(struct.pack("<Q", _mem(target)))
    while rela >= 0 and struct.unpack_from("<Q", code, rela - 8)[0] != _RELATIVE:
        rela = code.find(struct.pack("<Q", _mem(target)), rela + 1)
    if rela < 0:
        raise FormatError("Düşman açıklamalarının işaretçi kaydı bulunamadı.")
    entries: list[Entry] = []
    pos = rela - 16
    while True:
        r_offset, info, addend = struct.unpack_from("<QQQ", code, pos)
        if info != _RELATIVE or (entries and r_offset != struct.unpack_from("<Q", code, entries[-1].rela)[0] + 8):
            break
        start, end = _span(code, addend)
        entries.append(Entry(pos, start, end, codec.decode(code[start:end]).text))
        pos += 24
    return entries


def build_patch(code: bytes, pairs: list[tuple[str, str]]) -> list[tuple[int, bytes]]:
    """(İngilizce özeti, Türkçe) çiftlerini koda yerleştiren yama kayıtları: (NSO bellek adresi + 0x100, veri).

    Çiftlerin özetleri koddaki İngilizce metinlerin özetleriyle sırayla aynı olmalıdır (farklı sürüm koruması)."""
    entries = find_entries(code, pairs[0][0])[: len(pairs)]
    if len(entries) != len(pairs) or any(digest(e.english) != en for e, (en, _tr) in zip(entries, pairs, strict=False)):
        raise FormatError(
            "Oyun kodundaki düşman açıklamaları beklenenden farklı; bu sürüme yama üretilemez.",
            "Mod yalnızca oyunun v0 sürümü için hazırlanmıştır.",
        )
    region_start, region_end = entries[0].start, entries[-1].end
    if any(a.end != b.start for a, b in itertools.pairwise(entries)):
        raise FormatError("Düşman açıklamaları kodda ardışık değil.")
    blob = bytearray()
    records: list[tuple[int, bytes]] = []
    for entry, (_en, tr) in zip(entries, pairs, strict=True):
        tail = code[entry.end - 4 : entry.end]
        data = codec.encode(codec.Message("", (), tail), codec.normalize(tr))
        address = region_start + len(blob)
        blob += data
        records.append((_mem(entry.rela + 16) + _NSO_HEADER, struct.pack("<Q", _mem(address))))
    if region_start + len(blob) > region_end:
        raise FormatError(
            f"Türkçe düşman açıklamaları {len(blob)} bayt; koddaki yer {region_end - region_start} bayt.",
            "Açıklamaları kısaltın.",
        )
    blob += bytes(region_end - region_start - len(blob))
    records.append((_mem(region_start) + _NSO_HEADER, bytes(blob)))
    return records


def ips(records: list[tuple[int, bytes]]) -> bytes:
    """IPS32 yaması (Atmosphère ve emülatörler destekler): "IPS32" | (u32 ofset, u16 boy, veri)… | "EEOF"."""
    out = bytearray(b"IPS32")
    for offset, data in records:
        for i in range(0, len(data), 0xFFFF):
            chunk = data[i : i + 0xFFFF]
            out += struct.pack(">IH", offset + i, len(chunk)) + chunk
    return bytes(out + b"EEOF")


def translations() -> list[tuple[str, str]]:
    """Uygulamayla gelen Türkçe düşman açıklamaları (özgün metnin özeti, Türkçe) kod sırasıyla."""
    raw = (resources.files("nxceviri") / "assets" / "dmc1" / "dusman_aciklamalari.json").read_text(encoding="utf-8")
    return [(row["sha256"], row["tr"]) for row in json.loads(raw)]
