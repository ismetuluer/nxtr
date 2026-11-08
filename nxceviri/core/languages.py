"""Dil kodlarının karşılaştırılması (çekirdek ve format eklentileri ortak kullanır)."""

from __future__ import annotations

import re

#: ISO 15924 yazı kodu uzunluğu (ör. "Hant").
_SCRIPT_SUBTAG_LEN = 4


def _normalize(code: str) -> str:
    return code.lower().replace("_", "-")


def base_language(code: str) -> str:
    """Bölge alt etiketini atar ("en-US" → "en"); yazı alt etiketini korur ("zh-Hant" kalır)."""
    parts = _normalize(code).split("-")
    return "-".join([parts[0], *(p for p in parts[1:] if len(p) == _SCRIPT_SUBTAG_LEN)])


def same_language(a: str, b: str) -> bool:
    """İki dil kodu aynı dili mi gösteriyor?

    Dosya adında "en-us", tabloda "en" yazabilir: bölgesiz kod o dilin her bölgesiyle eşleşir.
    İki kodun da bölgesi varsa ("en-us" / "en-eu", "zh-cn" / "zh-tw") tam eşleşme gerekir.
    """
    na, nb = _normalize(a), _normalize(b)
    if na == nb:
        return True
    ba, bb = base_language(na), base_language(nb)
    return ba == bb and (ba == na or bb == nb)


#: Türkçe alfabe sırası (q, w, x Türkçede yoktur; oyun metinlerinde İngilizce sözcükler için araya konur).
_TURKISH_ALPHABET = "abcçdefgğhıijklmnoöpqrsştuüvwxyz"


def _collation_table() -> dict[int, str]:
    table: dict[int, str] = {}
    for rank, ch in enumerate(_TURKISH_ALPHABET):
        mapped = chr(0x100 + rank)  # harf → sıra numarasını taşıyan tek karakter; noktalama ve rakamlar önce gelir
        table[ord(ch)] = mapped
        table[ord(ch.upper())] = mapped
    # Büyük "I" ve "İ" noktalı "i" gibi sıralanır: oyun metinleri çoğunlukla İngilizcedir ("Item" = "item").
    table[ord("I")] = table[ord("i")]
    table[ord("İ")] = table[ord("i")]
    return table


_COLLATION = _collation_table()


def sort_key(text: str) -> str:
    """Türkçe alfabe sırasına göre sıralama anahtarı: ç c'den sonra, ğ g'den sonra, ş s'den sonra gelir;
    büyük/küçük harf ayırt edilmez. `str.casefold` kullanmak "çilek"i "dünya"dan sonraya atardı."""
    return text.translate(_COLLATION)


_DIGITS = re.compile(r"(\d+)")


def natural_sort_key(text: str) -> tuple[tuple[int, int, str], ...]:
    """Doğal sıralama anahtarı: sayılar değerine göre ("2" < "10"), harfler Türkçe sırayla (`sort_key`).

    Rakam öbekleri harflerden önce gelir; aynı sayı değerinde ("07" / "7") metin sırası belirler.
    """
    parts = _DIGITS.split(text)
    key: list[tuple[int, int, str]] = []
    for i, part in enumerate(parts):
        if not part:
            continue
        if i % 2:
            key.append((0, int(part), part))
        else:
            key.append((1, 0, sort_key(part)))
    return tuple(key)
