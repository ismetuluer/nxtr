"""Kontrol kodu türleri: kod etiketinden tür tahmini ve projeye özgü tür eşlemesi.

Metin sığdırma ve denetimler, bir kontrol kodunun ne işe yaradığını bilmek ister (satır sonu mu, sayfa sonu mu,
değişken mi …). Format eklentileri koda yalnızca bir etiket verir ("Satır sonu", "Kod 0x05"); bu modül:

- etiketi anahtar sözcüklerle bir **türe** çevirir (`guess_kind`; büyük/küçük harf ve Türkçe `İ`/`ı` fark etmez),
- kullanıcının bir etikete elle verdiği türü (hazır altı türden biri ya da kendi yazdığı ad) saklar
  (`CodeKinds`); eşlemede olmayan etiket tahmine düşer,
- eşlemeyi proje ayarlarında tutulabilecek JSON metnine çevirir ve geri okur. Bozuk veri çökertmez:
  uyarı günlüğe yazılır, boş eşleme döner.

Modül saftır; arayüz veya veritabanı bilmez.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

log = logging.getLogger(__name__)

KIND_LINE_BREAK = "line_break"
KIND_PAGE_BREAK = "page_break"
KIND_VARIABLE = "variable"
KIND_SYMBOL = "symbol"
KIND_STYLE = "style"
KIND_OTHER = "other"

BUILTIN_KINDS: tuple[str, ...] = (
    KIND_LINE_BREAK,
    KIND_PAGE_BREAK,
    KIND_VARIABLE,
    KIND_SYMBOL,
    KIND_STYLE,
    KIND_OTHER,
)

#: Hazır türlerin arayüzde görünen Türkçe adları.
KIND_NAMES: dict[str, str] = {
    KIND_LINE_BREAK: "Satır sonu",
    KIND_PAGE_BREAK: "Sayfa sonu",
    KIND_VARIABLE: "Değişken",
    KIND_SYMBOL: "Sembol",
    KIND_STYLE: "Biçim",
    KIND_OTHER: "Diğer",
}

#: Kod numarası -> tür adı.
KindOf = Callable[[int], str]

#: Tahmin sırası önemlidir: ilk eşleşen tür kazanır.
_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (KIND_LINE_BREAK, ("satır sonu",)),
    (KIND_PAGE_BREAK, ("sayfa", "bekle", "temizle")),
    (KIND_STYLE, ("renk", "biçim", "stil")),
    (KIND_VARIABLE, ("değişken", "oyuncu", "sayı")),
    (KIND_SYMBOL, ("simge", "tuş", "düğme")),
)


def _norm(text: str) -> str:
    """Küçük harfe indirir; Türkçe `İ`/`ı` ile `I`/`i` aynı sayılır."""
    return text.casefold().replace("̇", "").replace("ı", "i")


#: Bu türlerin anahtar sözcükleri yalnızca tam sözcük olarak eşleşir: sayfa sonu tahmini metni böldüğü için kesin
#: olmalıdır ("Bekleme" duraklamadır, satır ortasında olur; "bekle" sözcüğünü içerse de sayfa sonu değildir).
_WHOLE_WORD_KINDS = frozenset({KIND_PAGE_BREAK})


def _matcher(kind: str, word: str) -> Callable[[str], bool]:
    if kind in _WHOLE_WORD_KINDS:
        pattern = re.compile(r"(?<!\w)" + re.escape(word) + r"(?!\w)")
        return lambda text: pattern.search(text) is not None
    return lambda text: word in text


_MATCHERS = tuple((kind, tuple(_matcher(kind, _norm(w)) for w in words)) for kind, words in _KEYWORDS)


def guess_kind(label: str) -> str:
    """Kod etiketinden tür tahmin eder; tanınmayan etiket `KIND_OTHER` olur."""
    text = _norm(label)
    for kind, matchers in _MATCHERS:
        if any(match(text) for match in matchers):
            return kind
    return KIND_OTHER


@dataclass(frozen=True)
class CodeKinds:
    """Etiket -> tür eşlemesi (kullanıcının elle verdikleri); olmayan etiket için tahmin yapılır."""

    mapping: dict[str, str]

    def kind_of(self, label: str) -> str:
        found = self.mapping.get(label)
        return found if found is not None else guess_kind(label)

    def dump(self) -> str:
        return json.dumps(self.mapping, ensure_ascii=False, sort_keys=True)

    @classmethod
    def load(cls, text: str) -> CodeKinds:
        """JSON metninden okur; bozuk veya beklenmedik biçim uyarıyla boş eşleme verir."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            log.warning("Kod türü eşlemesi okunamadı, boş eşleme kullanılıyor: %s", exc)
            return cls({})
        if not isinstance(data, dict):
            log.warning("Kod türü eşlemesi bir sözlük değil, boş eşleme kullanılıyor.")
            return cls({})
        mapping = {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
        if len(mapping) != len(data):
            log.warning("Kod türü eşlemesinde metin olmayan girdiler atlandı.")
        return cls(mapping)


_TOKEN_RE = re.compile(r"⟦(\d+)⟧")
#: Şüphe için en az bu kadar satırda görülmeli ve görülmelerin bu oranı boşluksuz satır ortasında olmalı.
_SUSPECT_MIN_ROWS = 3
_SUSPECT_RATIO = 0.7


def suspected_line_breaks(rows: Iterable[tuple[str, Sequence[str]]], kinds: CodeKinds) -> list[str]:
    """Türü tahmin edilemeyen ("diğer") ama satır sonu gibi davranan kod etiketleri.

    `rows`: (yer tutuculu orijinal metin, kod etiketleri). Kod sözcüklerin arasına boşluksuz giriyorsa
    ("Merhaba⟦1⟧dünya") büyük olasılıkla satır sonudur; kullanıcı türünü elle verdiyse sorulmaz.
    """
    seen: dict[str, int] = {}
    tight: dict[str, int] = {}
    for text, labels in rows:
        for m in _TOKEN_RE.finditer(text):
            n = int(m.group(1))
            if not 0 < n <= len(labels):
                continue
            label = labels[n - 1]
            if label in kinds.mapping or guess_kind(label) != KIND_OTHER:
                continue
            seen[label] = seen.get(label, 0) + 1
            before = text[m.start() - 1] if m.start() > 0 else ""
            after = text[m.end()] if m.end() < len(text) else ""
            if before.isalnum() and after.isalnum():
                tight[label] = tight.get(label, 0) + 1
    return sorted(
        label for label, n in seen.items() if n >= _SUSPECT_MIN_ROWS and tight.get(label, 0) / n >= _SUSPECT_RATIO
    )
