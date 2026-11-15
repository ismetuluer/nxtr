"""Arama için metin katlama: Türkçe harflerde büyük/küçük harf ayırt edilmez."""

from __future__ import annotations


def fold_search(text: str) -> str:
    """Metni arama için katlar: büyük/küçük harf ve I, ı, İ, i ayrımı kalkar.

    `casefold()` tek başına "I"yı "i"ye, "İ"yi ise "i" + birleşen nokta (U+0307) yapar, "ı"ya dokunmaz; bu yüzden
    "IŞIK" içinde "ışık" ya da "İSTANBUL" içinde "istanbul" bulunamazdı. Burada noktalı ve noktasız i tek harf sayılır.
    """
    return text.casefold().replace("\u0307", "").replace("ı", "i")
