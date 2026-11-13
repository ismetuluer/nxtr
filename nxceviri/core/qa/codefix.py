"""Eksik biçim (renk/stil) kodlarının güvenli onarımı.

Yalnızca anlamı kesin olan durumlar programla onarılır; metnin bir bölümünü kaplayan kodlar (`Bu ⟦1⟧yürü⟦2⟧ orada`)
çeviride hangi sözcüklerin kapsanacağını yalnızca insan bilebilir, bu yüzden elle kalır:

- tam satır zarfı: orijinal baştan sona tek bir açma/kapama çiftiyse (`⟦1⟧metin⟦2⟧`) ve çeviride çiftin hiçbiri yoksa,
  çeviri çiftle sarılır;
- yalnızca kapanış eksikse (çeviri `⟦1⟧` ile başlıyor, `⟦2⟧` yok) kapanış sona eklenir;
- yarım yazılmış yer tutucu (`[1]`, `【1】`, `⟦ 1 ⟧`, `{{1}}`, `⟨1⟩`) asıl biçimine çevrilir (`placeholders.repair`).

Her onarımdan sonra kontrol kodu sorunu kalmıyorsa sonuç döner; yoksa None. Görünen metin hiç değişmez.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from nxceviri.core.translate import placeholders
from nxceviri.core.translate.cleanup import drop_invented_codes, is_line_break
from nxceviri.core.translate.codekinds import KIND_STYLE, guess_kind

_ENVELOPE = re.compile(r"⟦(\d+)⟧(.+)⟦(\d+)⟧", re.DOTALL)


def closer_base(label: str, labels: Sequence[str]) -> str | None:
    """ "Renk sonu" gibi, başka bir kodun ("Renk…") kapanışı olan etiketin kapattığı ad ("renk"); değilse None."""
    text = label.casefold()
    if is_line_break(label) or not text.endswith(" sonu"):
        return None
    base = text.removesuffix(" sonu")
    has_opener = any(o.casefold().startswith(base) and not o.casefold().endswith(" sonu") for o in labels)
    return base if has_opener else None


def _is_format(n: int, labels: Sequence[str]) -> bool:
    return 0 < n <= len(labels) and guess_kind(labels[n - 1]) == KIND_STYLE


def is_format_pair(opener: int, closer: int, labels: Sequence[str]) -> bool:
    """`opener` ve `closer` numaralı kodlar bir biçim açma/kapama çifti mi (ör. "Renk" ve "Renk sonu")?"""
    if not (_is_format(opener, labels) and _is_format(closer, labels)):
        return False
    base = closer_base(labels[closer - 1], labels)
    open_label = labels[opener - 1]
    return base is not None and open_label.casefold().startswith(base) and closer_base(open_label, labels) is None


def _envelope(source: str, labels: Sequence[str]) -> tuple[int, int] | None:
    """Orijinal baştan sona tek bir biçim çiftiyse (başka biçim kodu yok) çiftin numaraları; değilse None."""
    m = _ENVELOPE.fullmatch(source)
    if m is None or not m.group(2).strip():
        return None
    opener, closer = int(m.group(1)), int(m.group(3))
    if not is_format_pair(opener, closer, labels):
        return None
    if [n for n in placeholders.tokens_in(source) if _is_format(n, labels)] != [opener, closer]:
        return None
    return opener, closer


def repair_codes(source: str, text: str, labels: Sequence[str]) -> str | None:
    """Çevirideki kontrol kodu sorununu güvenle onarır; onarılamıyorsa ya da sorun yoksa None.

    Önce yarım yazılmış yer tutucular düzeltilir ve orijinalde olmayan kodlar atılır; sonra gerekirse tam satır
    zarfı eklenir. Sonuçta `placeholders.problems` boş değilse onarım yapılmaz.
    """
    if not placeholders.problems(source, text):
        return None
    fixed = drop_invented_codes(source, placeholders.repair(source, text))
    if placeholders.problems(source, fixed):
        envelope = _envelope(source, labels)
        if envelope is None:
            return None
        opener, closer = envelope
        present = [n for n in placeholders.tokens_in(fixed) if _is_format(n, labels)]
        if not present:
            fixed = placeholders.token(opener) + fixed + placeholders.token(closer)
        elif present == [opener] and fixed.startswith(placeholders.token(opener)):
            fixed += placeholders.token(closer)
        else:
            return None
    if placeholders.problems(source, fixed) or fixed == text:
        return None
    return fixed


def loses_partial_format(source: str, text: str, labels: Sequence[str]) -> bool:
    """Çeviride biçim kodu eksik ve orijinaldeki kod tam satırı değil, yalnızca bir bölümü kaplıyor mu?"""
    have = set(placeholders.tokens_in(text))
    lost = any(_is_format(n, labels) and n not in have for n in placeholders.tokens_in(source))
    return lost and _envelope(source, labels) is None
