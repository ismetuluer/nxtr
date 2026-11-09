"""Redaksiyon ve yeniden çeviri için halüsinasyon önlemleri.

Satırın zaten bir çevirisi varken modelin sonucu ancak şu belirtilerden hiçbiri yoksa yazılır; varsa model bir
kez sorun açıkça söylenerek yeniden istenir, yine olmazsa eski çeviri korunur. Belirtiler, küçük modellerin
(ör. gemma4:12b) gerçek redaksiyon çıktılarında görülen hatalardan çıkarıldı:

- **Çevirmeden yazmak:** Türkçe yerine İngilizce cümle ("You're crazy! Don't you think it's a bit risky?").
- **Metne ekleme:** sonuç hem özgünden hem eski çeviriden belirgin uzun (uydurulmuş cümle, komşu satırın metni).
- **Metinden atma:** sonuç hem özgünden hem eski çeviriden belirgin kısa (cümlenin bir kısmı başka satıra kaçmış).
- **Tekrar döngüsü:** aynı iki sözcük art arda ikiden çok kez ("türlü türlü … türlü türlü").

Eski çevirisi olmayan satırlarda (`translation_problems`) aynı belirtiler orijinalle kıyaslanarak aranır; ayrıca
orijinalde olmayan yabancı alfabe harfleri (Türkçe çeviride Çince, Kiril…) de uydurma belirtisidir.

Eşikler bilerek gevşektir: doğal bir kısaltma ("Oh that's nice!" → "Harika!") veya uzatma reddedilmez; yanlış
alarmda yalnızca eski çeviri kalır, veri kaybolmaz.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from itertools import pairwise

from nxceviri.core.translate import placeholders

#: Sonuç bu kattan uzun ve en az `_MIN_DIFF` karakter fazlaysa "ekleme" sayılır.
GROWTH_RATIO = 1.8
#: Sonuç bu kattan kısa ve en az `_MIN_DIFF` karakter eksikse "atlama" sayılır.
SHRINK_RATIO = 0.6
_MIN_DIFF = 12

#: Türkçe metinde neredeyse hiç geçmeyen İngilizce işlev sözcükleri.
_ENGLISH_WORDS = frozenset(
    (  # noqa: SIM905 - uzun liste tek satır tek sözcük olmasın diye boşlukla ayrılmış metin
        "the a an is are was were be been you you're your i i'm i'll my me we we're our it it's its this that "
        "there they they're them to of and or but not don't doesn't didn't can't won't do does what why how "
        "think know want have has had will would should could just with for from"
    ).split()
)
_WORD_RE = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")  # "you're", "x-ray" tek sözcük


def _visible(text: str) -> str:
    return placeholders.TOKEN_RE.sub(" ", text).strip()


def _words(text: str) -> list[str]:
    return [w.casefold().replace("’", "'") for w in _WORD_RE.findall(_visible(text))]


def looks_english(text: str) -> bool:
    words = _words(text)
    hits = sum(1 for w in words if w in _ENGLISH_WORDS)
    return hits >= 2 and hits >= len(words) * 0.3


def repeated_pair(text: str) -> str | None:
    """İkiden çok geçen ardışık sözcük çifti (tekrar döngüsü); yoksa None."""
    words = _words(text)
    pairs: Counter[tuple[str, str]] = Counter()
    last: dict[tuple[str, str], int] = {}
    for i, pair in enumerate(pairwise(words)):
        if i - last.get(pair, -2) >= 2:  # iç içe geçen çiftler ("çok çok çok") bir kez sayılır
            pairs[pair] += 1
            last[pair] = i
    for pair, count in pairs.items():
        if count >= 2 and words.count(pair[0]) >= 3:
            return " ".join(pair)
    return None


#: Anahtar/kod adı gibi görünen ifadeler: `/(ursa_desc)` ve `ursa_desc` (alt çizgili, boşluksuz, Latin harfli).
#: Model bunları bağlamdan çeviriye kopyalar; oyun dosyasında satırı bölebilir ya da oyunda yazı olarak görünür.
_KEY_LIKE_RE = re.compile(r"/\([^()\s]+\)|\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b")
_NL = "\n"


def foreign_key_tokens(source: str, new: str, old: str = "") -> list[str]:
    """Yeni çeviride olup orijinalde (ve varsa eski çeviride) bulunmayan anahtar benzeri ifadeler."""
    known = set(_KEY_LIKE_RE.findall(source)) | set(_KEY_LIKE_RE.findall(old))
    return list(dict.fromkeys(t for t in _KEY_LIKE_RE.findall(new) if t not in known))


def _foreign_token_problem(tokens: list[str]) -> str:
    return (
        f"Çeviriye orijinalde olmayan kod/anahtar benzeri ifade eklenmiş: {' '.join(tokens[:3])}. "
        "Yalnızca bu satırın çevirisini yaz; anahtar adı ya da başka bir şey ekleme."
    )


def revision_problems(source: str, old: str, new: str, source_lang: str, target_lang: str) -> list[str]:
    """Eski çevirinin yerine yazılmadan önce yeni sonucun denetimi (Türkçe sorun açıklamaları)."""
    problems: list[str] = []
    foreign = foreign_key_tokens(source, new, old)
    if foreign:
        problems.append(_foreign_token_problem(foreign))
    if new.count(_NL) > max(source.count(_NL), old.count(_NL)):
        problems.append(_ADDED_BREAK_PROBLEM)
    if target_lang == "tr" and source_lang == "en" and looks_english(new) and not looks_english(old):
        problems.append("Sonuç Türkçe değil, İngilizce yazılmış; satırı Türkçeye çevir.")
    src, before, after = len(_visible(source)), len(_visible(old)), len(_visible(new))
    longest, shortest = max(src, before), min(src, before)
    if after > longest * GROWTH_RATIO and after - longest >= _MIN_DIFF:
        problems.append(
            "Sonuç orijinalden ve eski çeviriden çok uzun; orijinalde olmayan bir şey eklenmiş görünüyor. "
            "Yalnızca bu satırın anlamını yaz, komşu satırların metnini bu satıra taşıma."
        )
    if after < shortest * SHRINK_RATIO and shortest - after >= _MIN_DIFF:
        problems.append(
            "Sonuç orijinalden ve eski çeviriden çok kısa; satırın bir kısmı atlanmış görünüyor. Orijinaldeki "
            "her şeyi bu satırda çevir."
        )
    pair = repeated_pair(new)
    if pair is not None and repeated_pair(old) is None and repeated_pair(source) is None:
        problems.append(f"“{pair}” sözcükleri tekrar tekrar yazılmış; tekrarı kaldır.")
    return problems


#: Yeni çeviride (eski çeviri yokken) uzunluk eşikleri: yalnızca orijinalle kıyaslandığı için daha gevşektir.
FRESH_GROWTH_RATIO = 2.5
FRESH_SHRINK_RATIO = 0.35
_FRESH_MIN_DIFF = 20
#: Bu kadar sözcükten kısa metin aynen bırakılabilir (ad, "OK" gibi menü yazısı).
_UNCHANGED_MIN_WORDS = 2


def _script(ch: str) -> str | None:
    """Harfin Latin dışı yazı sistemi (CJK, Kiril, Yunan, Arap…); Latin harf ve harf olmayanlar için None."""
    if not ch.isalpha():
        return None
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return None
    first = name.split(" ", 1)[0]
    if first == "LATIN":
        return None
    return "CJK" if first in _CJK_WORDS else first


_CJK_WORDS = frozenset(("CJK", "HIRAGANA", "KATAKANA", "HANGUL", "IDEOGRAPHIC"))


def foreign_letters(source: str, text: str) -> list[str]:
    """Çeviride geçen ama orijinalin yazı sistemlerinde olmayan harfler (ör. Türkçe çeviride Çince karakter)."""
    allowed = {s for s in map(_script, source) if s}
    return sorted({c for c in _visible(text) if (s := _script(c)) and s not in allowed})


_ADDED_BREAK_PROBLEM = "Çeviriye orijinalde olmayan satır sonu eklenmiş; satır sonlarını orijinaldeki gibi bırak."


def translation_problems(source: str, new: str, target_lang: str, *, breaks: bool = True) -> list[str]:
    """Eski çevirisi olmayan satırın yeni çevirisinde uydurma belirtileri (Türkçe sorun açıklamaları).

    Kodlar yerindeyse sonuç yine yazılır; bu belirtiler satırı yeniden istemek ve Kontrol Et'te "şüpheli" olarak
    göstermek içindir. `breaks` kapalıyken eklenen satır sonu sorun sayılmaz (Kontrol Et'te satır sonu bulguları ve
    sığdırma kuralları ayrıca bakar; sığdırma satır sonu ekler).
    """
    problems: list[str] = []
    foreign = foreign_key_tokens(source, new)
    if foreign:
        problems.append(_foreign_token_problem(foreign))
    if breaks and new.count(_NL) > source.count(_NL):
        problems.append(_ADDED_BREAK_PROBLEM)
    if new.strip() == source.strip() and len(_words(source)) >= _UNCHANGED_MIN_WORDS:
        problems.append("Satır çevrilmeden aynen bırakılmış; Türkçeye çevir.")
    elif target_lang.split("-", maxsplit=1)[0].lower() == "tr" and looks_english(new):
        problems.append("Sonuç Türkçe değil, İngilizce yazılmış; satırı Türkçeye çevir.")
    letters = foreign_letters(source, new)
    if letters:
        problems.append(
            f"Orijinalde olmayan yabancı alfabe harfleri var: {' '.join(letters[:6])}. Yalnızca Türkçe harflerle yaz."
        )
    pair = repeated_pair(new)
    if pair is not None and repeated_pair(source) is None:
        problems.append(f"“{pair}” sözcükleri tekrar tekrar yazılmış; tekrarı kaldır.")
    src, after = len(_visible(source)), len(_visible(new))
    if after > src * FRESH_GROWTH_RATIO and after - src >= _FRESH_MIN_DIFF:
        problems.append(
            "Sonuç orijinalden çok uzun; orijinalde olmayan bir şey eklenmiş görünüyor. Yalnızca bu satırın "
            "anlamını yaz."
        )
    if after < src * FRESH_SHRINK_RATIO and src - after >= _FRESH_MIN_DIFF:
        problems.append("Sonuç orijinalden çok kısa; satırın bir kısmı atlanmış görünüyor. Her şeyi çevir.")
    return problems
