"""Bilinmeyen bir dosyanın içinde okunabilir metin olup olmadığını kabaca sezer (UTF-8 ve UTF-16LE).

Bu bir tahmindir: ikili tablolar arasına gömülü cümleleri yakalamak için kullanılır, bir metin biçimini
kanıtlamaz. Örnek satırlar teşhis raporunda ajana ipucu olarak gösterilir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from nxceviri.arac.ortak import kisalt

#: En az bu uzunlukta, yazdırılabilir karakterlerden oluşan diziler cümle adayıdır.
_DIZI = re.compile(r"[^\x00-\x1f\x7f�]{10,}")
_KANA = re.compile(r"[぀-ヿ]")
#: Bir dosyada bunun altındaki sayıda cümle adayı varsa dosya metin sayılmaz.
EN_AZ_DIZI = 3
#: Cümle adaylarının toplam karakterinin örneğe oranı bunun altındaysa dosya metin sayılmaz.
EN_AZ_YOGUNLUK = 0.25
ORNEK_SAYISI = 3
ORNEK_UZUNLUGU = 80


@dataclass(frozen=True)
class MetinSezgisi:
    kodlama: str
    yogunluk: float  # cümle adaylarının örnekteki payı (0-1)
    ornekler: tuple[str, ...]


def _cumle_mi(dizi: str) -> bool:
    harfler = sum(c.isalpha() for c in dizi)
    if harfler < len(dizi) * 0.6:
        return False
    if len(_KANA.findall(dizi)) >= 6:
        return True
    ascii_harf = sum((c.isascii() and c.isalpha()) or ord(c) in range(0xC0, 0x250) for c in dizi)
    return dizi.count(" ") >= 2 and ascii_harf >= harfler * 0.5


def _degerlendir(metin: str, kodlama: str) -> MetinSezgisi | None:
    diziler = [d.strip() for d in _DIZI.findall(metin)]
    cumleler = [d for d in diziler if _cumle_mi(d)]
    if len(cumleler) < EN_AZ_DIZI or not metin:
        return None
    yogunluk = sum(len(c) for c in cumleler) / len(metin)
    if yogunluk < EN_AZ_YOGUNLUK:
        return None
    benzersiz = list(dict.fromkeys(kisalt(c, ORNEK_UZUNLUGU) for c in cumleler))
    return MetinSezgisi(kodlama, yogunluk, tuple(benzersiz[:ORNEK_SAYISI]))


def sezgi(ornek: bytes) -> MetinSezgisi | None:
    """Örnek baytlarda UTF-8 ya da UTF-16LE metin yoğunluğu yeterliyse en yoğun olanı döndürür."""
    adaylar = [
        _degerlendir(ornek.decode("utf-8", errors="replace"), "UTF-8"),
        _degerlendir(ornek[: len(ornek) // 2 * 2].decode("utf-16-le", errors="replace"), "UTF-16LE"),
    ]
    bulunan = [a for a in adaylar if a is not None]
    return max(bulunan, key=lambda a: a.yogunluk, default=None)
