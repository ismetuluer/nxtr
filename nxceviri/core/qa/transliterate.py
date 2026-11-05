"""Harf dönüştürme: fontta olmayan Türkçe harfleri en yakın karşılığına çevirir (ğ→g, ş→s, ı→i …).

Dönüştürme yalnızca dışa aktarırken uygulanır; projedeki çeviriler değişmez. Böylece font
yamalama (M8) geldiğinde aynı çeviriler dönüştürmeden kullanılabilir.
"""

from __future__ import annotations

from nxceviri.core.qa.fonts import TURKISH_LETTERS

MAPPING = {
    "ç": "c",
    "ğ": "g",
    "ı": "i",
    "İ": "I",
    "ö": "o",
    "ş": "s",
    "ü": "u",
    "Ç": "C",
    "Ğ": "G",
    "Ö": "O",
    "Ş": "S",
    "Ü": "U",
}

MODE_NONE = "none"
MODE_MISSING = "missing"
MODE_ALL = "all"

MODE_LABELS = {
    MODE_NONE: "Dönüştürme yapma (harfler olduğu gibi yazılır)",
    MODE_MISSING: "Yalnızca fontta eksik harfleri dönüştür",
    MODE_ALL: "Tüm Türkçe harfleri dönüştür (ç ğ ı İ ö ş ü → c g i I o s u)",
}


def letters_for(mode: str, missing: str) -> str:
    if mode == MODE_ALL:
        return TURKISH_LETTERS
    if mode == MODE_MISSING:
        return "".join(c for c in missing if c in MAPPING)
    return ""


def apply(text: str, letters: str) -> str:
    """`letters` içindeki harfleri dönüştürür. Yer tutucular (⟦1⟧) rakam içerdiğinden etkilenmez."""
    if not letters:
        return text
    table = str.maketrans({c: MAPPING[c] for c in letters if c in MAPPING})
    return text.translate(table)
