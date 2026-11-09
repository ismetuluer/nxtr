"""Yazım raporu: projede sözlükte olmayan sözcükler (kaç satırda geçtikleriyle) ve toplu sözcük değiştirme."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from nxceviri.core.languages import sort_key
from nxceviri.core.project import TranslationRow
from nxceviri.core.spell.checker import SpellChecker, turkish_lower


@dataclass(frozen=True)
class WordUse:
    word: str
    #: Sözcüğün geçtiği satır sayısı (aynı satırda birkaç kez geçse de bir sayılır).
    count: int
    row_ids: tuple[int, ...]


def row_unknown_words(row: TranslationRow, spell: SpellChecker, extra: frozenset[str]) -> tuple[str, ...]:
    """Satırın çevirisindeki sözlükte olmayan sözcükler (çevrilmemiş ya da kaynakla aynı çeviri denetlenmez)."""
    if not row.translation or row.translation.strip() == row.source.strip():
        return ()
    return tuple(spell.unknown_words(row.translation, row.source, extra))


#: Satır → (denetlenen satır nesnesi, bilinmeyen sözcükleri).
Scanned = dict[int, tuple[TranslationRow, tuple[str, ...]]]


class UnknownWordCache:
    """Satır başına bilinmeyen sözcük önbelleği: yalnızca değişen satırlar yeniden taranır.

    `TranslationRow` değişmezdir; satır değişince nesnesi de değişir, böylece önbellek `is` ile doğrulanır.
    Yazım sözlüğü ya da ek sözcükler değişince çağıran `clear()` demelidir. `scan` yan etkisizdir (arka plan iş
    parçacığında çalışabilir); sonucu ana iş parçacığında `store` ile önbelleğe yazılır.
    """

    def __init__(self) -> None:
        self._rows: Scanned = {}

    def clear(self) -> None:
        self._rows.clear()

    def stale(self, rows: Sequence[TranslationRow]) -> list[TranslationRow]:
        """Önbellekte olmayan ya da değişmiş satırlar."""
        cached = self._rows
        return [r for r in rows if (c := cached.get(r.id)) is None or c[0] is not r]

    @staticmethod
    def scan(rows: Sequence[TranslationRow], spell: SpellChecker, extra: frozenset[str]) -> Scanned:
        return {r.id: (r, row_unknown_words(r, spell, extra)) for r in rows}

    def store(self, scanned: Scanned) -> None:
        self._rows.update(scanned)

    def words(self, rows: Sequence[TranslationRow], ignored: Collection[str] = ()) -> list[WordUse]:
        """`rows` için sözcük dökümü (sayıya göre azalan, eşitlikte Türkçe alfabe sırası); önbelleksiz satır yoktur."""
        skip = {turkish_lower(w) for w in ignored}
        uses: dict[str, list[int]] = defaultdict(list)
        for row in rows:
            cached = self._rows.get(row.id)
            if cached is None:
                continue
            for word in cached[1]:
                if word not in skip:
                    uses[word].append(row.id)
        ranked = sorted(uses.items(), key=lambda kv: (-len(kv[1]), sort_key(kv[0])))
        return [WordUse(word, len(ids), tuple(ids)) for word, ids in ranked]


def unknown_words(
    rows: Sequence[TranslationRow],
    spell: SpellChecker,
    extra: frozenset[str] = frozenset(),
    ignored: Collection[str] = (),
) -> list[WordUse]:
    """Çevirilerdeki sözlükte olmayan sözcükler; sayıya göre azalan, eşitlikte Türkçe alfabe sırasıyla."""
    cache = UnknownWordCache()
    cache.store(cache.scan(rows, spell, extra))
    return cache.words(rows, ignored)


def _turkish_upper(text: str) -> str:
    return text.replace("i", "İ").replace("ı", "I").upper()


def _match_case(found: str, new: str) -> str:
    """Bulunan sözcük büyük harfle başlıyorsa yenisi de başlar (tamamı büyük harfli sözcükler listelenmez)."""
    if found[:1].isupper():
        return _turkish_upper(new[:1]) + new[1:]
    return new


def replace_unknown(
    translation: str, source: str, spell: SpellChecker, extra: Collection[str], *, word: str, new: str
) -> str:
    """`word`'ü yalnızca `unknown_words`un da bilinmeyen saydığı geçişlerde `new` ile değiştirir.

    Kaynakta da geçen, tamamı büyük harfli ya da cümle ortasında büyük harfle başlayan (özel ad) geçişlere ve
    çevirisi kaynakla aynı olan (çevrilmemiş) satırlara dokunulmaz; böylece değişen satırlar penceredeki sayıyla
    aynıdır. Kontrol kodlarına ve kesme işaretli sözcüklere dokunulmaz (yazım denetimi bunları atlar).
    """
    if not translation or translation.strip() == source.strip():
        return translation
    target = turkish_lower(word)
    out: list[str] = []
    pos = 0
    for start, end, low in spell.unknown_spans(translation, source, extra):
        if low != target:
            continue
        out.append(translation[pos:start])
        out.append(_match_case(translation[start:end], new))
        pos = end
    if not out:
        return translation
    out.append(translation[pos:])
    return "".join(out)
