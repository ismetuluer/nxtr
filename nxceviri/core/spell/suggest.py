"""Yazım önerisi: bilinmeyen sözcüğün olası doğru yazımları (çevrimdışı, anında).

Yazım süzgeci (Bloom) yalnızca "sözcük var mı?" sorusunu yanıtlar; öneri, sözcükten aday yazımlar üretip her adayı
bu soruyla süzerek bulunur. İki sınıf vardır, **ilki önceliklidir**:

- **Harf değişimi (a):** ı↔i, ş↔s, ğ↔g, ü↔u, ö↔o, ç↔c, iki yönde, en çok `MAX_SWAPS` konumda birden. Türkçe yazım
  hatalarının büyük çoğunluğu budur (yanlış klavye, ASCII'ye çevrilmiş metin). En çok `MAX_SPOTS` değişebilir harfi
  olan sözcüğe bakılır; aday sayısı en çok C(12,1)+C(12,2)+C(12,3) = 298'dir.
- **Tek düzenleme (b):** yalnızca (a) boşken; eksik, fazla, yer değiştirmiş ya da değişmiş tek harf (Türkçe alfabe).

Süzgecin yanlış olumlu oranı %0,1'dir: sözlükte olmayan bir yazım kabaca her bin adayda bir "var" çıkar. Bu yüzden
(a)'da aday sayısı küçük tutulur; (b) iki basamaklıdır: önce fazla ya da yer değiştirmiş harf (≈ 2·uzunluk aday), o
boşsa değişmiş ya da eksik harf (≈ 58·uzunluk aday). (b)'de ek güven ölçütleri vardır: ilk harf korunur, dört ünsüz
yığını ve ünlüsüz aday atılır, en az dört harf aranır, ikiden çok isabet varsa hiç önerilmez, altı harften uzun
adayın kökü de sözlükte olmalıdır. Toplu düzeltmeye yalnızca "güvenli" öneri girer (`Suggestion.safe`): harf
değişimiyle tek isabet ve ya aday sayısı çok az ya da önerinin kökü de sözlükte; tek düzenleme hiç girmez.
"""

from __future__ import annotations

import itertools
from collections.abc import Collection
from dataclasses import dataclass

from nxceviri.core.spell.checker import SpellChecker, is_sound_effect, turkish_lower

MAX_SUGGESTIONS = 5
#: Bir sözcükte bundan çok değiştirilebilir harf varsa (a) denenmez (aday sayısı ve yanlış olumlu riski büyür).
MAX_SPOTS = 12
#: Aynı anda en çok bu kadar harf değiştirilir.
MAX_SWAPS = 3
#: (b) yalnızca bu uzunluk ve üstündeki sözcüklerde denenir (kısa sözcüklerde aday çok, anlam az).
MIN_EDIT_LENGTH = 4
#: (b)'de bundan çok isabet varsa öneri verilmez: belirsizlik ya da süzgeç gürültüsü.
MAX_EDIT_HITS = 2
#: Aday sayısı bu kadar ya da azsa (≈ %0,7 risk) tek öneri kök doğrulaması olmadan güvenli sayılır.
SAFE_TRIED = 7
#: Bu uzunluğa kadar adaylar kök doğrulamasından muaftır (kısa sözcüğün kök olarak ayrıca bakılacak bir ön eki yok).
ROOT_FREE_LENGTH = 5
#: Kök arama: adayın sondan en çok bu kadar harfi çıkarılıp (ek) kalan ön ekin sözlükte olup olmadığına bakılır.
ROOT_SUFFIX_MAX = 6

_PAIRS = {
    "i": "ı",
    "ı": "i",
    "s": "ş",
    "ş": "s",
    "g": "ğ",
    "ğ": "g",
    "u": "ü",
    "ü": "u",
    "o": "ö",
    "ö": "o",
    "c": "ç",
    "ç": "c",
}
_ALPHABET = "abcçdefgğhıijklmnoöprsştuüvyz"
_VOWELS = frozenset("aeıioöuü")


@dataclass(frozen=True)
class Suggestion:
    """`words`: en çok `MAX_SUGGESTIONS` öneri (önce olası). `letters`: harf değişimi (a); yoksa tek düzenleme (b)."""

    words: tuple[str, ...] = ()
    letters: bool = False
    #: Üretilip süzgece sorulan aday sayısı (yanlış olumlu riski ≈ aday sayısı × 0,001).
    tried: int = 0
    #: Önerinin kökü de sözlükte mi (süzgecin uydurma isabetlerine karşı bağımsız ikinci doğrulama).
    rooted: bool = False

    @property
    def safe(self) -> bool:
        """Toplu düzeltmeye uygun mu: harf değişimiyle tek isabet; ayrıca kökü doğrulanmış ya da aday sayısı çok az."""
        return self.letters and len(self.words) == 1 and (self.rooted or self.tried <= SAFE_TRIED)


_NONE = Suggestion()


def _turkish_upper(char: str) -> str:
    return {"i": "İ", "ı": "I"}.get(char, char.upper())


def _letter_variants(low: str) -> list[str]:
    """Harf değişimi adayları: önce az değişim, sonra konum sırası. Çok değişebilir harfli sözcükte boş."""
    spots = [n for n, c in enumerate(low) if c in _PAIRS]
    if not spots or len(spots) > MAX_SPOTS:
        return []
    out: list[str] = []
    for count in range(1, min(MAX_SWAPS, len(spots)) + 1):
        for combo in itertools.combinations(spots, count):
            chars = list(low)
            for n in combo:
                chars[n] = _PAIRS[chars[n]]
            out.append("".join(chars))
    return out


def _plausible(word: str) -> bool:
    """Türkçe ses dizilimine kabaca uyar mı: ünlü var, dört ünsüz ya da üç aynı harf art arda yok."""
    if not any(c in _VOWELS for c in word):
        return False
    run = 0
    for n, c in enumerate(word):
        run = 0 if c in _VOWELS else run + 1
        if run >= 4 or (n >= 2 and word[n - 2] == word[n - 1] == c):
            return False
    return True


def _edit_tiers(low: str) -> tuple[list[str], list[str]]:
    """Tek düzenleme adayları (ilk harf korunur), iki basamakta: (fazla, yer değiştirmiş), (değişmiş, eksik harf).

    İlk basamak küçüktür (≈ 2·uzunluk aday): çift basılmış ve ters yazılmış harf en yaygın hatadır ve uydurma isabet
    riski düşüktür. İkinci basamak büyüktür (≈ 58·uzunluk), yalnızca ilki boşsa bakılır. Tekrarsız, ses dizilimine uyan.
    """
    size = len(low)
    first: dict[str, None] = {}
    for i in range(1, size):  # fazla harf
        first[low[:i] + low[i + 1 :]] = None
    for i in range(1, size - 1):  # yer değiştirmiş iki harf
        first[low[:i] + low[i + 1] + low[i] + low[i + 2 :]] = None
    second: dict[str, None] = {}
    for i in range(1, size):  # değişmiş harf
        for c in _ALPHABET:
            if c != low[i]:
                second[low[:i] + c + low[i + 1 :]] = None
    for i in range(1, size + 1):  # eksik harf
        for c in _ALPHABET:
            second[low[:i] + c + low[i:]] = None
    drop = {low}
    return (
        [w for w in first if w not in drop and _plausible(w)],
        [w for w in second if w not in drop and w not in first and _plausible(w)],
    )


def _rooted(word: str, spell: SpellChecker, extra: Collection[str]) -> bool:
    """Kısa sözcük ya da sondaki en çok `ROOT_SUFFIX_MAX` harfi (ek) atılınca kalan ön ek sözlükte olan sözcük."""
    if len(word) <= ROOT_FREE_LENGTH:
        return True
    return any(spell.is_known(word[:n], extra) for n in range(max(3, len(word) - ROOT_SUFFIX_MAX), len(word)))


def _cased(word: str, suggestion: str) -> str:
    """Önerinin harf büyüklüğünü sözcüğünkine uydurur (Türkçe İ/I kuralıyla): "Iste" → "İşte"."""
    if word[:1].isupper():
        return _turkish_upper(suggestion[:1]) + suggestion[1:]
    return suggestion


def suggestions(
    word: str, spell: SpellChecker, extra: Collection[str] = frozenset(), *, edits: bool = True
) -> Suggestion:
    """`word` için öneriler ve hangi sınıftan geldikleri. Yalnızca bilinmeyen, düz harflerden oluşan sözcüğe verilir.

    Tamamı büyük harfli (kısaltma), ses efekti, rakam/kesme/tire içeren ve sözlükte zaten olan sözcüklere öneri
    yoktur; yazım denetimi de bunları işaretlemez. İlk harfi büyük sözcüğün önerisi de büyük harfle başlar.
    `edits=False` yalnızca harf değişimine bakar (ucuzdur; tablodaki öneri sütunu için), tek düzenleme aramaz.
    """
    if not word or not word.isalpha() or (len(word) > 1 and word.isupper()):
        return _NONE
    low = turkish_lower(word)
    if is_sound_effect(low) or spell.is_known(low, extra):
        return _NONE
    letters = _letter_variants(low)
    found = [c for c in letters if spell.is_known(c, extra)]
    if found:
        rooted = len(found) == 1 and _rooted(found[0], spell, extra)
        return Suggestion(tuple(_cased(word, c) for c in found[:MAX_SUGGESTIONS]), True, len(letters), rooted)
    if not edits or len(low) < MIN_EDIT_LENGTH:
        return Suggestion(tried=len(letters))
    tried = len(letters)
    for tier in _edit_tiers(low):
        tried += len(tier)
        found = [c for c in tier if spell.is_known(c, extra) and _rooted(c, spell, extra)]
        if found:
            if len(found) > MAX_EDIT_HITS:
                break  # çok isabet: belirsizlik ya da süzgeç gürültüsü; ikinci basamağa geçilmez
            return Suggestion(tuple(_cased(word, c) for c in found), False, tried)
    return Suggestion(tried=tried)


def suggest(word: str, spell: SpellChecker, extra: Collection[str] = frozenset()) -> list[str]:
    """`suggestions(...).words` listesi (harf değişimi önce; yalnızca o boşsa tek düzenleme)."""
    return list(suggestions(word, spell, extra).words)
