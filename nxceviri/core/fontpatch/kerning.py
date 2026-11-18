"""Yeni gliflere türetildikleri harfin aralık (kerning) çiftlerini aktarma (`ttf` font yaması için).

Yeni glif (ör. `ş`), taban harfinin (`s`) her çiftine hem sol hem sağ üye olarak katılır; iki yeni glifin birbiriyle
çifti de (`ğ`–`ş`) oluşur:

- eski `kern` tablosu, biçim 0: çiftler kopyalanır;
- GPOS PairPos biçim 1 (tek glif çiftleri): tabanın PairSet'i yeni glif için kopyalanır, her PairSet'te tabana giden
  kayıt yeni glif için yinelenir;
- GPOS PairPos biçim 2 (sınıf çiftleri): yeni glif tabanın ClassDef1/ClassDef2 sınıfına ve kapsamına (Coverage)
  eklenir.

Extension (tür 9) sarmalı açılır. Yeni gliflerin numaraları var olanlardan büyük olduğundan kapsam ve kayıt listelerinin
sonuna numara sırasıyla eklenmeleri sıralamayı korur. Tanınmayan yapı değiştirilmeden atlanır ve not döner.
"""

from __future__ import annotations

import copy
from typing import Any

from fontTools.ttLib import TTFont

#: Biçim 0 alt tablosunun uzunluk alanı 16 bittir: 14 baytlık başlık + çift başına 6 bayt.
_KERN_MAX_PAIRS = (0xFFFF - 14) // 6
_STRUCTURE_ERRORS = (AttributeError, IndexError, KeyError, TypeError)


def inherit(font: TTFont, bases: dict[str, str]) -> list[str]:
    """`bases`: yeni glif adı → taban glif adı. Font yerinde değişir; atlanan yapılar için kısa notlar döner."""
    if not bases:
        return []
    order = sorted(bases, key=font.getGlyphID)
    notes: list[str] = []
    if "kern" in font:
        notes += _kern(font["kern"], bases)
    if "GPOS" in font:
        notes += _gpos(font["GPOS"].table, bases, order)
    return notes


def _kern(table: Any, bases: dict[str, str]) -> list[str]:
    news: dict[str, list[str]] = {}
    for new, base in bases.items():
        news.setdefault(base, []).append(new)
    notes: list[str] = []
    for sub in getattr(table, "kernTables", None) or []:
        pairs = getattr(sub, "kernTable", None)
        if getattr(sub, "format", None) != 0 or not isinstance(pairs, dict):
            notes.append("kerning: kern tablosunun biçim 0 olmayan alt tablosu atlandı")
            continue
        extra: dict[tuple[str, str], int] = {}
        for (left, right), value in pairs.items():
            for a in (left, *news.get(left, ())):
                for b in (right, *news.get(right, ())):
                    if (a, b) not in pairs:
                        extra[(a, b)] = value
        if len(pairs) + len(extra) > _KERN_MAX_PAIRS:
            notes.append("kerning: kern tablosu dolu, yeni harflere aktarılmadı")
            continue
        pairs.update(extra)
    return notes


def _gpos(table: Any, bases: dict[str, str], order: list[str]) -> list[str]:
    notes: list[str] = []
    lookup_list = getattr(table, "LookupList", None)
    for lookup in getattr(lookup_list, "Lookup", None) or []:
        for entry in getattr(lookup, "SubTable", None) or []:
            kind, sub = lookup.LookupType, entry
            if kind == 9:
                kind = getattr(entry, "ExtensionLookupType", None)
                sub = getattr(entry, "ExtSubTable", None)
            if kind != 2 or sub is None:
                continue
            try:
                if sub.Format == 1:
                    _pair_glyphs(sub, bases, order)
                elif sub.Format == 2:
                    _pair_classes(sub, bases, order)
                else:
                    notes.append(f"kerning: GPOS çift biçimi {sub.Format} atlandı")
            except _STRUCTURE_ERRORS as exc:
                notes.append(f"kerning: beklenmeyen GPOS yapısı atlandı ({type(exc).__name__})")
    return notes


def _pair_glyphs(sub: Any, bases: dict[str, str], order: list[str]) -> None:
    """PairPos biçim 1: önce sol (PairSet kopyası), sonra sağ (kayıt kopyası); yeni–yeni çiftleri de oluşur."""
    glyphs: list[str] = sub.Coverage.glyphs
    index = {g: i for i, g in enumerate(glyphs)}
    copies = [(new, copy.deepcopy(sub.PairSet[index[bases[new]]])) for new in order if bases[new] in index]
    for new, pair_set in copies:
        if new not in index:
            glyphs.append(new)
            sub.PairSet.append(pair_set)
    for pair_set in sub.PairSet:
        records = pair_set.PairValueRecord
        seconds = {r.SecondGlyph: r for r in records}
        for new in order:
            record = seconds.get(bases[new])
            if record is not None and new not in seconds:
                twin = copy.deepcopy(record)
                twin.SecondGlyph = new
                records.append(twin)
        pair_set.PairValueCount = len(records)
    sub.PairSetCount = len(sub.PairSet)


def _pair_classes(sub: Any, bases: dict[str, str], order: list[str]) -> None:
    """PairPos biçim 2: yeni glif tabanın sol/sağ sınıfına girer; tabanı kapsayan alt tabloda kapsama eklenir."""
    glyphs: list[str] = sub.Coverage.glyphs
    covered = set(glyphs)
    left = sub.ClassDef1.classDefs if sub.ClassDef1 is not None else {}
    right = sub.ClassDef2.classDefs if sub.ClassDef2 is not None else {}
    for new in order:
        base = bases[new]
        if base in covered and new not in covered:
            glyphs.append(new)
            covered.add(new)
            if base in left:
                left[new] = left[base]
        if base in right and new not in right:
            right[new] = right[base]
