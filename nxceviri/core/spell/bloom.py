"""Bloom süzgeci: milyonlarca sözcük biçimini küçük bir dosyada, "var mı?" sorusuna yanıt verecek biçimde tutar.

Türkçe sözlük (hunspell-tr) her kökün yanında geçerli ek yığınlarını tek tek sıralar: yaklaşık 6,1 milyon sözcük biçimi.
Hunspell kütüphaneleri bunu yüklerken yüzlerce MB bellek kullanır. Süzgeç tüm biçimleri ~11 MB'ta tutar, anında
yüklenir. **Yanlış olumsuz yoktur** (sözlükteki her biçim bulunur); **yanlış olumlu** oranı oluşturulurken seçilir
(sözlükte olmayan bir yazım hata olarak yakalanmaz). Biçimleri `packaging/build_spell_filter.py` üretir.
"""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Iterable

_MAGIC = b"NXBF1"
_HEADER = struct.Struct("<5sBQQ")  # sihir, k, bit sayısı, öğe sayısı


def _hashes(word: str) -> tuple[int, int]:
    digest = hashlib.blake2b(word.encode("utf-8"), digest_size=16).digest()
    return int.from_bytes(digest[:8], "little"), int.from_bytes(digest[8:], "little") | 1


class BloomFilter:
    def __init__(self, bits: bytearray, hashes: int, bit_count: int, items: int) -> None:
        self._bits = bits
        self._k = hashes
        self._m = bit_count
        self.items = items

    @classmethod
    def sized(cls, items: int, error_rate: float = 0.001) -> BloomFilter:
        """`items` sözcük için, hedef yanlış olumlu oranına göre boyutlandırılmış boş süzgeç."""
        n = max(items, 1)
        m = max(math.ceil(-n * math.log(error_rate) / (math.log(2) ** 2)), 64)
        m += (-m) % 8
        return cls(bytearray(m // 8), max(round(m / n * math.log(2)), 1), m, 0)

    @classmethod
    def build(cls, words: Iterable[str], error_rate: float = 0.001) -> BloomFilter:
        unique = set(words)
        bloom = cls.sized(len(unique), error_rate)
        for word in unique:
            bloom.add(word)
        return bloom

    def add(self, word: str) -> None:
        self.items += 1
        h1, h2 = _hashes(word)
        for i in range(self._k):
            pos = (h1 + i * h2) % self._m
            self._bits[pos >> 3] |= 1 << (pos & 7)

    def __contains__(self, word: object) -> bool:
        if not isinstance(word, str):
            return False
        h1, h2 = _hashes(word)
        bits, m = self._bits, self._m
        for i in range(self._k):
            pos = (h1 + i * h2) % m
            if not bits[pos >> 3] & (1 << (pos & 7)):
                return False
        return True

    def to_bytes(self) -> bytes:
        return _HEADER.pack(_MAGIC, self._k, self._m, self.items) + bytes(self._bits)

    @classmethod
    def from_bytes(cls, data: bytes) -> BloomFilter:
        if len(data) < _HEADER.size:
            raise ValueError("Yazım süzgeci dosyası bozuk.")
        magic, k, m, items = _HEADER.unpack_from(data)
        if magic != _MAGIC or k < 1 or m < 8 or len(data) != _HEADER.size + m // 8:
            raise ValueError("Yazım süzgeci dosyası bozuk.")
        return cls(bytearray(data[_HEADER.size :]), k, m, items)
