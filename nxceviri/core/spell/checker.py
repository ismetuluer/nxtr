"""Yazım denetleyicisi: çevirideki sözlükte olmayan sözcükleri bulur.

Yanlış alarmı azaltmak için sayılmayan sözcükler: kontrol kodları, sayı içerenler, kesme işaretli olanlar
(özel ad + ek: Eddie'ye), tamamı büyük harf olanlar (kısaltma), cümle ortasında büyük harfle başlayanlar (özel ad),
orijinal metinde de geçenler (korunan adlar), ses efektleri (hihihi, ahhh), kullanıcı sözlüğündekiler ve çağıranın
verdiği ek sözcükler (ör. oyun sözlüğündeki terimler).

`flag_copied` açıksa orijinalden aynen kopyalanan sözcükler (büyük harfli olsalar da) atlanmaz; yalnızca bilinen
sözcükler, kullanıcı sözlüğü, kısaltmalar ve ses efektleri yine işaretlenmez.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Iterator

from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.translate import placeholders

_WORD = re.compile(r"(?<!\w)[^\W\d_]+(?:['’][^\W\d_]+)*(?:-[^\W\d_]+)*(?!\w)")
#: Ses efektleri ve kahkahalar ("hihihi", "ehehehe", "ahhh"): sözcük değil, yazım hatası sayılmaz.
_SOUND_EFFECT = re.compile(r"(.{1,3}?)\1{2,}.{0,2}|.*(.)\2{2,}.*", re.IGNORECASE)
_SENTENCE_BREAKS = ".!?…:\n"
_OPENERS = " \t\"“”'‘’(«»[—-"


def turkish_lower(text: str) -> str:
    """Türkçe küçük harfe çevirir (İ→i, I→ı); Python'un `lower()`ı bunu yapmaz."""
    return text.replace("İ", "i").replace("I", "ı").lower()


def words_of(text: str) -> Iterator[tuple[str, int]]:
    """Denetlenebilir sözcükler ve başlangıç konumları (kodlar, sayılı ve kesme işaretli sözcükler atlanır)."""
    visible = placeholders.TOKEN_RE.sub(lambda m: " " * len(m.group(0)), text)
    for m in _WORD.finditer(visible):
        word = m.group(0)
        if "'" in word or "’" in word:
            continue
        yield word, m.start()


def _sentence_start(text: str, start: int) -> bool:
    before = text[:start].rstrip(_OPENERS)
    return not before or before[-1] in _SENTENCE_BREAKS


class SpellChecker:
    def __init__(self, bloom: BloomFilter, user_words: Iterable[str] = ()) -> None:
        self._bloom = bloom
        self._user = {turkish_lower(w) for w in user_words}
        #: Orijinal metinde de geçen sözcükler de denetlensin (varsayılan: korunan ad sayılıp atlanır).
        self.flag_copied = False

    def add_user_words(self, words: Iterable[str]) -> None:
        self._user |= {turkish_lower(w) for w in words}

    def _known(self, low: str, extra: Collection[str]) -> bool:
        return low in self._user or low in extra or low in self._bloom

    def is_known(self, word: str, extra: Collection[str] = frozenset()) -> bool:
        low = turkish_lower(word)
        if self._known(low, extra):
            return True
        parts = low.split("-")  # "x-ray" gibi birleşikler: her parça biliniyorsa kabul
        return len(parts) > 1 and all(self._known(p, extra) for p in parts)

    def unknown_spans(
        self, text: str, source: str = "", extra: Collection[str] = frozenset()
    ) -> list[tuple[int, int, str]]:
        """Metindeki sözlükte olmayan sözcüklerin (başlangıç, bitiş, küçük harfli sözcük) konumları."""
        from_source = {turkish_lower(w) for w, _ in words_of(source)}
        found: list[tuple[int, int, str]] = []
        for word, start in words_of(text):
            low = turkish_lower(word)
            copied = low in from_source
            if (copied and not self.flag_copied) or (len(word) > 1 and word.isupper()) or _SOUND_EFFECT.fullmatch(low):
                continue
            if word[0].isupper() and not copied and not _sentence_start(text, start):
                continue  # cümle ortasında büyük harf: özel ad (orijinalden kopya işaretlenecekse bu kural uygulanmaz)
            if not self.is_known(word, extra):
                found.append((start, start + len(word), low))
        return found

    def unknown_words(self, text: str, source: str = "", extra: Collection[str] = frozenset()) -> list[str]:
        """Metindeki sözlükte olmayan sözcükler (küçük harf, ilk geçiş sırasıyla, tekrarsız)."""
        return list(dict.fromkeys(low for _, _, low in self.unknown_spans(text, source, extra)))
