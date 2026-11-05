"""İki çeviri arasındaki sözcük düzeyi fark (değişiklikleri göstermek için)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

#: Fark parçası türleri.
SAME = "same"
REMOVED = "removed"
ADDED = "added"

#: Sözcükler, yer tutucular (⟦1⟧), noktalama ve boşluklar ayrı parçalar.
_TOKEN_RE = re.compile(r"⟦\d+⟧|\w+|\s+|[^\w\s]", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def word_diff(old: str, new: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """(eski metnin parçaları, yeni metnin parçaları); her parça (tür, metin).

    Eski tarafta silinenler `REMOVED`, yeni tarafta eklenenler `ADDED` işaretlenir; ortak kısımlar `SAME`.
    """
    a, b = _tokens(old), _tokens(new)
    left: list[tuple[str, str]] = []
    right: list[tuple[str, str]] = []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            left.append((SAME, "".join(a[i1:i2])))
            right.append((SAME, "".join(b[j1:j2])))
            continue
        if i2 > i1:
            left.append((REMOVED, "".join(a[i1:i2])))
        if j2 > j1:
            right.append((ADDED, "".join(b[j1:j2])))
    return left, right
