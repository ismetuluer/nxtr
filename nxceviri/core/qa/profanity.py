"""Küfür ve argo denetimi: çocuklara yönelik oyunlarda çeviride kaba ifade çıkmasın diye (Kontrol Et → "Küfür / argo").

Sözlük elle yazılmış bir veri dosyasındadır (`data/kufur.txt`; biçimi dosyanın başında). Eşleştirme Türkçe küçük harfe
çevrilmiş (İ → i, I → ı) görünen metinde, sözcük sözcük yapılır; kontrol kodları (⟦n⟧) sözcüğü bölen boşluk sayılır.
Hassasiyet için üç koruma vardır:

- Masum sözcükler (`haric` satırları: sikke, götürmek, boks...) kök eşleşmesinden önce elenir.
- Üç harfe kadar BÜYÜK HARFLİ kısaltmalar argo düzeyinde atlanır (LAN ağı); ağır düzeyde atlanmaz (AMK).
- Orijinal metinde aynen geçen sözcük (özel ad, çevrilmeden kalmış ad) bulgu sayılmaz.

Kullanıcı bir sözcüğü "Bu kelime argo değil" ile projenin izin listesine ekleyebilir (`ProfanityConfig.allowed`).
Sözlük bir sözcüğün masum anlamını bilemez; denetim bu yüzden bulguyu uyarı olarak bildirir, dışa aktarmayı engellemez.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache
from importlib import resources

from nxceviri.core.spell.checker import turkish_lower
from nxceviri.core.translate import placeholders

#: Denetim düzeyleri (proje ayarında saklanan değerler).
LEVEL_OFF = "off"
LEVEL_HEAVY = "heavy"
LEVEL_ALL = "all"

#: Düzeylerin arayüzdeki adları (menü).
LEVEL_LABELS: dict[str, str] = {
    LEVEL_OFF: "Kapalı",
    LEVEL_HEAVY: "Yalnızca ağır küfür",
    LEVEL_ALL: "Ağır küfür ve argo",
}

#: Bulgudaki sözcüğün seviyesi (sözlük dosyasındaki ad değil, arayüzde görünen etiket aşağıda).
KIND_HEAVY = LEVEL_HEAVY
KIND_SLANG = "slang"
_KIND_TITLES = {KIND_HEAVY: "Ağır küfür", KIND_SLANG: "Argo"}

#: Orijinalde de kaba ifade varsa iletiye eklenen not.
RUDE_SOURCE_NOTE = "orijinalde de kaba ifade var"

#: Bu uzunluğa kadar büyük harfli sözcük kısaltma sayılır ve argo düzeyinde atlanır.
_ACRONYM_MAX = 3

_WORD = re.compile(r"[^\W\d_]+")
_ENGLISH_RUDE = re.compile(
    r"\b(?:fuck\w*|motherfuck\w*|shit\w*|bullshit|bitch\w*|asshole\w*|bastard\w*|dick|dicks|dickhead|piss\w*"
    r"|cunt\w*|whore\w*|slut\w*|damn|damned|goddamn\w*|wtf)\b",
    re.IGNORECASE,
)


def parse_level(value: object) -> str:
    """Kayıtlı düzeyi okur; yok ya da bozuksa denetim kapalıdır."""
    text = str(value) if value is not None else ""
    return text if text in LEVEL_LABELS else LEVEL_OFF


@dataclass(frozen=True)
class ProfanityConfig:
    """Projenin küfür denetimi ayarı: düzey ve "argo değil" denen (küçük harfli) sözcükler."""

    level: str = LEVEL_OFF
    allowed: frozenset[str] = field(default_factory=frozenset)

    @property
    def enabled(self) -> bool:
        return self.level in (LEVEL_HEAVY, LEVEL_ALL)


#: Kapalı denetim (varsayılan).
NO_PROFANITY = ProfanityConfig()


@dataclass(frozen=True)
class Match:
    """Çeviride bulunan kaba sözcük: yazıldığı gibi, küçük harfli anahtarı ve düzeyi (`KIND_HEAVY`/`KIND_SLANG`)."""

    word: str
    key: str
    level: str


@dataclass(frozen=True)
class Rules:
    """Bir sözlük bölümü: tam sözcükler ve sözcük başı (kök) eşleşmeleri."""

    whole: frozenset[str] = frozenset()
    stems: tuple[str, ...] = ()

    def __len__(self) -> int:
        return len(self.whole) + len(self.stems)

    def matches(self, low: str) -> bool:
        return low in self.whole or (bool(self.stems) and low.startswith(self.stems))


@dataclass(frozen=True)
class Entries:
    heavy: Rules
    slang: Rules
    exceptions: Rules


def parse_entries(text: str) -> Entries:
    """Sözlük dosyasının metnini ayrıştırır; biçim hatası satır numarasıyla bildirilir."""
    whole: dict[str, set[str]] = {"agir": set(), "argo": set(), "haric": set()}
    stems: dict[str, list[str]] = {"agir": [], "argo": [], "haric": []}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        level, _, entry = line.partition(" ")
        entry = entry.strip()
        if level not in whole or not entry:
            raise ValueError(f"Küfür sözlüğü, {number}. satır: bilinmeyen seviye ya da boş giriş: {raw!r}")
        if entry.startswith("=") and len(entry) > 1 and "*" not in entry:
            whole[level].add(turkish_lower(entry[1:]))
        elif entry.endswith("*") and len(entry) > 2 and "=" not in entry and "*" not in entry[:-1]:
            stems[level].append(turkish_lower(entry[:-1]))
        else:
            raise ValueError(f"Küfür sözlüğü, {number}. satır: giriş '=sözcük' ya da 'kök*' olmalı: {raw!r}")
    return Entries(*(Rules(frozenset(whole[k]), tuple(stems[k])) for k in ("agir", "argo", "haric")))


@cache
def load_entries() -> Entries:
    """Pakete gömülü sözlüğü okur (bir kez)."""
    text = (resources.files("nxceviri") / "core" / "qa" / "data" / "kufur.txt").read_text(encoding="utf-8")
    return parse_entries(text)


def _visible_words(text: str) -> list[str]:
    """Görünen metindeki sözcükler (kontrol kodları sözcüğü bölen boşluk sayılır)."""
    return _WORD.findall(placeholders.TOKEN_RE.sub(" ", text))


def find_profanity(text: str, config: ProfanityConfig, source: str = "") -> list[Match]:
    """Çeviri metnindeki kaba sözcükler (tekrarsız, ilk görünme sırasıyla); kapalı düzeyde boş.

    `source`: orijinal metin; içinde aynen geçen sözcük özel ad sayılıp atlanır.
    """
    if not config.enabled or not text:
        return []
    entries = load_entries()
    in_source = {turkish_lower(w) for w in _visible_words(source)} if source else set()
    found: dict[str, Match] = {}
    # Büyük harfli kısaltma ayrımı yalnızca küçük harfli sözcük de varsa yapılır: bütün satırı bağıran metinde
    # ("GEL LAN BURAYA") her sözcük büyüktür ve kısaltma sayılamaz.
    mixed_case = any(c.islower() for c in text)
    for word in _visible_words(text):
        low = turkish_lower(word)
        if low in found or low in config.allowed or low in in_source or entries.exceptions.matches(low):
            continue
        if entries.heavy.matches(low):
            found[low] = Match(word, low, KIND_HEAVY)
        elif (
            config.level == LEVEL_ALL
            and entries.slang.matches(low)
            and not (mixed_case and word.isupper() and len(word) <= _ACRONYM_MAX)
        ):
            found[low] = Match(word, low, KIND_SLANG)
    return list(found.values())


def english_rude(source: str) -> bool:
    """Orijinal (İngilizce) metinde yaygın bir kaba ifade var mı? Çevirideki kabalığın sadakatini göstermek için."""
    return _ENGLISH_RUDE.search(placeholders.TOKEN_RE.sub(" ", source)) is not None


def describe(matches: list[Match], rude_source: bool) -> str:
    """Bulgu iletisi: "Ağır küfür: a, b · Argo: c" (+ orijinalde de varsa not)."""
    parts = []
    for level in (KIND_HEAVY, KIND_SLANG):
        words = [m.word for m in matches if m.level == level]
        if words:
            parts.append(f"{_KIND_TITLES[level]}: {', '.join(words)}")
    message = " · ".join(parts)
    return f"{message} ({RUDE_SOURCE_NOTE})" if rude_source else message
