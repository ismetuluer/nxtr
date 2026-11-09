"""Yazım raporu: projede sözlükte olmayan sözcükler (kaç satırda geçtikleriyle) ve toplu sözcük değiştirme."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from nxceviri.core.languages import sort_key
from nxceviri.core.project import TranslationRow
from nxceviri.core.spell.checker import SpellChecker, turkish_lower, words_of


@dataclass(frozen=True)
class WordUse:
    word: str
    #: Sözcüğün geçtiği satır sayısı (aynı satırda birkaç kez geçse de bir sayılır).
    count: int
    row_ids: tuple[int, ...]


def unknown_words(
    rows: Sequence[TranslationRow],
    spell: SpellChecker,
    extra: frozenset[str] = frozenset(),
    ignored: Collection[str] = (),
) -> list[WordUse]:
    """Çevirilerdeki sözlükte olmayan sözcükler; sayıya göre azalan, eşitlikte Türkçe alfabe sırasıyla."""
    skip = {turkish_lower(w) for w in ignored}
    uses: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        if not row.translation or row.translation.strip() == row.source.strip():
            continue
        for word in spell.unknown_words(row.translation, row.source, extra):
            if word not in skip:
                uses[word].append(row.id)
    ranked = sorted(uses.items(), key=lambda kv: (-len(kv[1]), sort_key(kv[0])))
    return [WordUse(word, len(ids), tuple(ids)) for word, ids in ranked]


def _turkish_upper(text: str) -> str:
    return text.replace("i", "İ").replace("ı", "I").upper()


def _match_case(found: str, new: str) -> str:
    if len(found) > 1 and found.isupper():
        return _turkish_upper(new)
    if found[:1].isupper():
        return _turkish_upper(new[:1]) + new[1:]
    return new


def replace_word(text: str, word: str, new: str) -> str:
    """Metindeki `word` sözcüğünü (büyük/küçük harf fark etmez, sözcük sınırıyla) `new` ile değiştirir.

    Bulunan sözcüğün büyük harf biçimi korunur (Ev→Yuva, EV→YUVA). Kontrol kodlarına ve kesme işaretli sözcüklere
    (yazım denetimi bunları atlar) dokunulmaz.
    """
    target = turkish_lower(word)
    out: list[str] = []
    pos = 0
    for found, start in words_of(text):
        if turkish_lower(found) != target:
            continue
        out.append(text[pos:start])
        out.append(_match_case(found, new))
        pos = start + len(found)
    if not out:
        return text
    out.append(text[pos:])
    return "".join(out)
