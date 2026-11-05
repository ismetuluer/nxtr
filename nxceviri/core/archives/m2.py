"""M2 arşivleri (Metal Gear Solid Master Collection gibi M2 yapımı oyunlar): mdf ve `.psb.m` + `.bin`.

mdf: "mdf\\0" | açık boyut u32 | gövde. Gövde, zlib ile sıkıştırılmış veridir ve 64 baytlık
bir anahtar akışıyla XOR'lanmıştır. Akış: MD5(oyun anahtarı + dosya adı küçük harfle,
klasörsüz) → dört u32 (little-endian) → MT19937 init_by_array → 16 çıktı (little-endian).

Oyun anahtarı uygulamada YOKTUR. Kullanıcının kendi dökümündeki oyun kodunda (ExeFS `main`)
geçen dizgeler denenir; bilinen bir `.psb.m` dosyasını gerçekten açan dizge anahtardır.
Anahtar yalnızca bellekte tutulur; loglanmaz, proje dosyasına yazılmaz.

Arşiv: `<ad>.psb.m` bir PSB dizinidir (`file_info`: yol → [ofset, boy]); veriler `<ad>.bin`
içinde 2048 bayta hizalı durur. Adı `.m` ile biten üyeler ayrıca mdf'dir.
Ayrıntılar: docs/formats/m2.md
"""

from __future__ import annotations

import hashlib
import re
import struct
import zlib
from collections.abc import Callable
from dataclasses import dataclass

from nxceviri.core.archives import psb
from nxceviri.core.container.storage import Storage, SubStorage
from nxceviri.core.errors import ArchiveError

MAGIC = b"mdf\0"
INDEX_SUFFIX = ".psb.m"
DATA_SUFFIX = ".bin"
_HEADER = 8
_KEY_STREAM = 64
_KEY_CANDIDATE = re.compile(rb"[\x21-\x7e]{6,40}")
_ZLIB_LEVEL = 9


def is_mdf(data: bytes) -> bool:
    return data[:4] == MAGIC


def _mt19937_init_by_array(seed: list[int]) -> list[int]:
    mt = [0] * 624
    mt[0] = 19650218
    for i in range(1, 624):
        mt[i] = (1812433253 * (mt[i - 1] ^ (mt[i - 1] >> 30)) + i) & 0xFFFFFFFF
    i, j = 1, 0
    for _ in range(max(624, len(seed))):
        mt[i] = ((mt[i] ^ ((mt[i - 1] ^ (mt[i - 1] >> 30)) * 1664525)) + seed[j] + j) & 0xFFFFFFFF
        i, j = i + 1, (j + 1) % len(seed)
        if i >= 624:
            mt[0], i = mt[623], 1
    for _ in range(623):
        mt[i] = ((mt[i] ^ ((mt[i - 1] ^ (mt[i - 1] >> 30)) * 1566083941)) - i) & 0xFFFFFFFF
        i += 1
        if i >= 624:
            mt[0], i = mt[623], 1
    mt[0] = 0x80000000
    return mt


def _mt19937_words(mt: list[int], count: int) -> list[int]:
    for t in range(624):
        y = (mt[t] & 0x80000000) | (mt[(t + 1) % 624] & 0x7FFFFFFF)
        mt[t] = mt[(t + 397) % 624] ^ (y >> 1) ^ (0x9908B0DF if y & 1 else 0)
    out = []
    for word in mt[:count]:
        y = word ^ (word >> 11)
        y ^= (y << 7) & 0x9D2C5680
        y ^= (y << 15) & 0xEFC60000
        out.append(y ^ (y >> 18))
    return out


def key_stream(key: bytes, name: str) -> bytes:
    """`name` dosyası için 64 baytlık XOR akışı (`name` klasörsüz dosya adıdır)."""
    digest = hashlib.md5(key + name.lower().encode("utf-8")).digest()
    seed = list(struct.unpack("<4I", digest))
    words = _mt19937_words(_mt19937_init_by_array(seed), _KEY_STREAM // 4)
    return struct.pack(f"<{len(words)}I", *words)


def _xor(data: bytes, stream: bytes) -> bytes:
    reps = len(data) // len(stream) + 1
    full = (stream * reps)[: len(data)]
    return (int.from_bytes(data, "little") ^ int.from_bytes(full, "little")).to_bytes(len(data), "little")


def _base_name(name: str) -> str:
    return name.replace("\\", "/").rsplit("/", 1)[-1]


def decode(blob: bytes, name: str, key: bytes, max_size: int = 512 * 1024 * 1024) -> bytes:
    """mdf verisini açar. `name`, dosyanın oyundaki adıdır (klasörlü olabilir)."""
    if len(blob) < _HEADER or not is_mdf(blob):
        raise ArchiveError(f"{_base_name(name)}: mdf imzası yok.")
    size = struct.unpack_from("<I", blob, 4)[0]
    if size > max_size:
        raise ArchiveError(f"{_base_name(name)}: açık boyut çok büyük ({size:,} bayt).")
    plain = _xor(blob[_HEADER:], key_stream(key, _base_name(name)))
    try:
        d = zlib.decompressobj()
        data = d.decompress(plain, size + 1)
    except zlib.error as exc:
        raise ArchiveError(
            f"{_base_name(name)} açılamadı: anahtar bu oyuna ait değil ya da dosya bozuk.",
            "Oyunun base ve güncelleme dosyalarını birlikte ekleyin; dosyalar kendi konsolunuzdan alınmış olmalı.",
        ) from exc
    if len(data) != size or not d.eof:
        raise ArchiveError(f"{_base_name(name)}: açılan veri boyutu başlıktakiyle uyuşmuyor.")
    return data


def encode(data: bytes, name: str, key: bytes) -> bytes:
    packed = zlib.compress(data, _ZLIB_LEVEL)
    return MAGIC + struct.pack("<I", len(data)) + _xor(packed, key_stream(key, _base_name(name)))


def replace(blob: bytes, name: str, key: bytes, transform: Callable[[bytes], bytes]) -> bytes:
    """İçeriği `transform` ile değiştirir; içerik değişmediyse orijinal baytları döndürür."""
    old = decode(blob, name, key)
    new = transform(old)
    return blob if new == old else encode(new, name, key)


def find_key(code: bytes, name: str, blob: bytes) -> bytes | None:
    """Oyun kodundaki dizgelerden, `blob` (adı `name` olan mdf dosyası) dosyasını açanı bulur."""
    if len(blob) < _HEADER + 2 or not is_mdf(blob):
        return None
    base = _base_name(name)
    head = blob[_HEADER : _HEADER + 2]
    candidates: list[bytes] = _KEY_CANDIDATE.findall(code)
    for candidate in dict.fromkeys(candidates):
        stream = key_stream(candidate, base)
        b0, b1 = head[0] ^ stream[0], head[1] ^ stream[1]
        if b0 & 0x0F != 8 or ((b0 << 8) | b1) % 31:
            continue  # zlib başlığı değil
        try:
            decode(blob, name, candidate)
        except ArchiveError:
            continue
        return candidate
    return None


@dataclass(frozen=True)
class M2Entry:
    path: str
    offset: int
    size: int


class M2Archive:
    """Bir `.psb.m` dizini ve ona ait `.bin` verisi."""

    def __init__(self, index_name: str, index_blob: bytes, data: Storage, key: bytes) -> None:
        self.index_name = index_name
        self.key = key
        self.data = data
        self._index_blob = index_blob
        self._index = decode(index_blob, index_name, key)
        root = psb.Psb(self._index).root()
        info = root.get("file_info") if isinstance(root, dict) else None
        if not isinstance(info, dict):
            raise ArchiveError(f"{index_name}: M2 arşiv dizini değil (file_info yok).")
        self.entries: dict[str, M2Entry] = {}
        for path, span in info.items():
            offset, size = span if isinstance(span, list) and len(span) == 2 else (None, None)
            if not isinstance(offset, int) or not isinstance(size, int):
                raise ArchiveError(f"{index_name}: '{path}' girdisi bozuk.")
            if offset < 0 or size < 0 or offset + size > data.size:
                raise ArchiveError(
                    f"{index_name}: '{path}' veri dosyasının dışını gösteriyor.",
                    "Dizin (.psb.m) ile veri (.bin) aynı oyun sürümünden olmalı.",
                )
            self.entries[path] = M2Entry(path, offset, size)

    @staticmethod
    def data_name(index_name: str) -> str:
        if not index_name.endswith(INDEX_SUFFIX):
            raise ArchiveError(f"{index_name}: M2 arşiv dizini adı '{INDEX_SUFFIX}' ile bitmeli.")
        return index_name[: -len(INDEX_SUFFIX)] + DATA_SUFFIX

    def index_without(self, paths: set[str]) -> bytes:
        """`paths` girdileri `file_info`'dan çıkarılmış yeni dizin (mdf kodlu).

        Diğer girdiler, adlar ve dizgeler aynen kalır. Amaç: değiştirilen üyeleri 8 GB'lık `.bin`'i
        yeniden yazmadan, RomFS'te gevşek dosya olarak vermek (oyunun arşivde bulamadığı dosyayı
        dosya sisteminde araması; bkz. docs/formats/m2.md).
        """
        unknown = sorted(paths - self.entries.keys())
        if unknown:
            raise ArchiveError(f"{self.index_name} içinde dosya bulunamadı: {unknown[0]}")
        if not paths:
            return self._index_blob
        root = psb.Psb(self._index).root()
        assert isinstance(root, dict)  # __init__'te doğrulandı
        info = root["file_info"]
        assert isinstance(info, dict)
        root["file_info"] = {k: v for k, v in info.items() if k not in paths}
        return encode(psb.replace_root(self._index, root), self.index_name, self.key)

    def _entry(self, path: str) -> M2Entry:
        entry = self.entries.get(path)
        if entry is None:
            raise ArchiveError(f"{self.index_name} içinde dosya bulunamadı: {path}")
        return entry

    def open(self, path: str) -> Storage:
        """Üyenin ham (mdf ise hâlâ kodlu) verisi; disk kalıpları gibi büyük üyeler için."""
        entry = self._entry(path)
        return SubStorage(self.data, entry.offset, entry.size)

    def read(self, path: str, max_size: int = 256 * 1024 * 1024) -> bytes:
        """Üyenin verisi; adı `.m` ile bitiyorsa mdf açılmış hâli."""
        entry = self._entry(path)
        if entry.size > max_size:
            raise ArchiveError(f"{path} bir kerede okunamayacak kadar büyük ({entry.size:,} bayt).")
        raw = self.data.read(entry.offset, entry.size)
        return decode(raw, path, self.key, max_size) if path.endswith(".m") and is_mdf(raw) else raw
