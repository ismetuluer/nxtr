"""ASCII'ye çevrilmiş Türkçe metnin harf onarımı: c g i o s u → ç ğ ı ö ş ü (ve büyükleri).

Eski yazı tipi Türkçe harfleri taşımadığı için çevirileri ASCII'ye çevrilmiş yamalar var ("tesekkur ederim"). Onarım
sözlük destekli ve temkinlidir:

- yalnızca yazım sözlüğünde olmayan sözcüklere bakılır; harfler tek tek değiştirilerek aday sözcükler üretilir
  (var olan bir Türkçe harf asla geri alınmaz);
- sözlükte olan aday tam bir tane ise sözcük değiştirilir; hiç ya da birden çok ise (sürat/surat gibi eşyazımlılar)
  dokunulmaz, birden çok olan bulguda "inceleme gerekli" diye bildirilir;
- harf büyüklüğü harf harf korunur: üretilen aday, orijinalle aynı konumlarda büyük/küçük harf taşır
  ("Iste" → "İşte", "ISTE" → "İŞTE"), `I` hem `İ` hem `I` olabilir, `i` hem `i` hem `ı`;
- orijinalde de geçen sözcükler (korunan adlar), cümle ortasındaki özel adlar, kodlar ve sayılı sözcükler atlanır;
- tireli sözcüğün (`mun-hizli`) parçaları ayrı değerlendirilir: orijinalde geçen ya da sözlükte olan parçaya
  dokunulmaz, öteki parça kendi kuralıyla düzelir;
- ayrı yazılmış soru eki (mi/mı/mu/mü) önceki sözcüğün son ünlüsüne göre ünlü uyumuna sokulur.

Kontrol kodlarına dokunulmaz; sonuç tekrar çalıştırılınca değişmez.
"""

from __future__ import annotations

import itertools
from collections.abc import Collection, Iterator
from dataclasses import dataclass

from nxceviri.core.spell.checker import SpellChecker, is_sentence_start, turkish_lower, words_of

#: ASCII harf → Türkçe karşılıklı seçenekler (kendisi dahil).
_OPTIONS: dict[str, tuple[str, ...]] = {
    "c": ("c", "ç"),
    "g": ("g", "ğ"),
    "i": ("i", "ı"),
    "o": ("o", "ö"),
    "s": ("s", "ş"),
    "u": ("u", "ü"),
    "C": ("C", "Ç"),
    "G": ("G", "Ğ"),
    "I": ("I", "İ"),
    "O": ("O", "Ö"),
    "S": ("S", "Ş"),
    "U": ("U", "Ü"),
}
#: Bir sözcükte bundan çok değiştirilebilir harf varsa aday üretilmez (2^n büyür; uzun yabancı sözcükler).
_MAX_TOGGLES = 10
_PARTICLES = frozenset({"mi", "mı", "mu", "mü"})
#: Soru ekinin ünlüsü, önceki sözcüğün son ünlüsüne göre.
_HARMONY = {"a": "ı", "ı": "ı", "e": "i", "i": "i", "o": "u", "u": "u", "ö": "ü", "ü": "ü"}
_BLANKS = " \t "


@dataclass(frozen=True)
class AsciiRepair:
    text: str
    #: Yapılan değişiklikler: (eski sözcük, yeni sözcük); soru ekleri de dahil.
    changes: tuple[tuple[str, str], ...] = ()
    #: Birden çok sözlük adayı olduğu için dokunulmayan sözcükler ve adayları: (anahtar, adaylar); tekrarsız.
    #: Anahtar `fold` ile küçültülmüş sözcüktür; seçilen aday `apply_choice` ile projeye uygulanır.
    choices: tuple[tuple[str, tuple[str, ...]], ...] = ()

    @property
    def ambiguous(self) -> tuple[str, ...]:
        """Dokunulmayan belirsiz sözcükler (küçük harfle, tekrarsız)."""
        return tuple(word for word, _candidates in self.choices)


def _turkish_upper(char: str) -> str:
    return {"i": "İ", "ı": "I"}.get(char, char.upper())


def fold(word: str) -> str:
    """Belirsiz sözcüğün anahtarı: küçük harf; ASCII `I` hem `i` hem `ı` olabileceği için `i` sayılır, `İ` kalır."""
    return word.replace("İ", "").replace("I", "i").lower().replace("", "İ")


def _wanted(text: str, start: int, word: str) -> bool:
    """Onarıma aday sözcük mü: cümle ortasında büyük harfle başlayan (özel ad) sözcük aday değildir."""
    return not (word[0].isupper() and not word.isupper() and not is_sentence_start(text, start))


def _source_words(source: str) -> set[str]:
    """Orijinaldeki sözcükler ve tireli sözcüklerin parçaları (küçük harfle)."""
    found: set[str] = set()
    for word, _start in words_of(source):
        found.add(turkish_lower(word))
        found.update(turkish_lower(part) for part in word.split("-"))
    return found


def _parts(word: str, start: int) -> Iterator[tuple[str, int]]:
    """Tireli sözcüğün parçaları ve konumları (tiresiz sözcükte sözcüğün kendisi)."""
    offset = 0
    for part in word.split("-"):
        yield part, start + offset
        offset += len(part) + 1


def _candidates(word: str) -> list[str]:
    """Sözcüğün değiştirilebilir harflerinin tüm kombinasyonları (kendisi hariç); çoksa boş."""
    spots = [n for n, c in enumerate(word) if c in _OPTIONS]
    if not spots or len(spots) > _MAX_TOGGLES:
        return []
    out: list[str] = []
    for combo in itertools.product(*(_OPTIONS[word[n]] for n in spots)):
        chars = list(word)
        for n, c in zip(spots, combo, strict=True):
            chars[n] = c
        candidate = "".join(chars)
        if candidate != word:
            out.append(candidate)
    return out


def _repair_particles(text: str, changes: list[tuple[str, str]]) -> str:
    """Ayrı yazılmış soru eklerini önceki sözcüğe göre düzeltir (önceki parça sözcük değilse dokunmaz)."""
    found = list(words_of(text))
    edits: list[tuple[int, int, str]] = []
    for k in range(1, len(found)):
        word, start = found[k]
        prev, prev_start = found[k - 1]
        if turkish_lower(word) not in _PARTICLES or (word[0].isupper() and not word.isupper()):
            continue
        gap = text[prev_start + len(prev) : start]
        vowel = next((c for c in reversed(turkish_lower(prev)) if c in _HARMONY), None)
        if not gap or gap.strip(_BLANKS) or vowel is None:
            continue
        target = "m" + _HARMONY[vowel]
        if turkish_lower(word) == target:
            continue
        new = "".join(_turkish_upper(c) if o.isupper() else c for c, o in zip(target, word, strict=True))
        edits.append((start, start + len(word), new))
        changes.append((word, new))
    for start, end, new in reversed(edits):
        text = text[:start] + new + text[end:]
    return text


def repair_ascii_turkish(
    source: str, text: str, spell: SpellChecker, extra: Collection[str] = frozenset()
) -> AsciiRepair:
    """Çevirideki ASCII'ye çevrilmiş sözcükleri onarır; `extra`: ek kabul edilen sözcükler (oyun sözlüğü vb.)."""
    from_source = _source_words(source)
    edits: list[tuple[int, int, str]] = []
    changes: list[tuple[str, str]] = []
    choices: dict[str, tuple[str, ...]] = {}
    for word, word_start in words_of(text):
        if turkish_lower(word) in from_source or spell.is_known(word, extra) or not _wanted(text, word_start, word):
            continue
        for part, start in _parts(word, word_start):
            if turkish_lower(part) in from_source or spell.is_known(part, extra):
                continue
            known = [c for c in _candidates(part) if spell.is_known(c, extra)]
            if len(known) == 1:
                edits.append((start, start + len(part), known[0]))
                changes.append((part, known[0]))
            elif known:
                choices.setdefault(fold(part), tuple(turkish_lower(c) for c in known))
    for start, end, new in reversed(edits):
        text = text[:start] + new + text[end:]
    text = _repair_particles(text, changes)
    return AsciiRepair(text, tuple(changes), tuple(choices.items()))


def apply_choice(source: str, text: str, key: str, new: str) -> str:
    """Belirsiz sözcüğü (`fold` anahtarı `key`) seçilen yazımla (`new`, küçük harfli) değiştirir.

    Yalnızca tam sözcükler (ve tireli sözcüğün tam parçaları) değişir; harf büyüklüğü harf harf korunur.
    Orijinalde geçen sözcüklere, cümle ortasındaki özel adlara ve kodlara dokunulmaz (onarımdaki kurallar).
    """
    if len(new) != len(key) or key not in fold(text):
        return text
    from_source = _source_words(source)
    edits: list[tuple[int, int, str]] = []
    for word, word_start in words_of(text):
        if not _wanted(text, word_start, word):
            continue
        for part, start in _parts(word, word_start):
            if fold(part) == key and turkish_lower(part) not in from_source:
                shaped = "".join(_turkish_upper(c) if o.isupper() else c for c, o in zip(new, part, strict=True))
                edits.append((start, start + len(part), shaped))
    for start, end, shaped in reversed(edits):
        text = text[:start] + shaped + text[end:]
    return text
