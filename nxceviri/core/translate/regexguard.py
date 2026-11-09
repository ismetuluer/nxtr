"""Düzenli ifade aramasını kilitlenmeye karşı korur.

Python'un `re` modülü eşleştirmeyi kesmeye izin vermez ve eşleştirirken GIL'i bırakmaz: arka plan iş parçacığı,
sinyal ya da sayaç donmuş bir eşleştirmeyi durduramaz (Windows'ta `setitimer` de yoktur). Ek bağımlılık
(`regex` modülünün zaman aşımı) kullanmamak için iki katmanlı koruma uygulanır:

1. **Önden denetim** (`is_risky`): `(a+)+$`, `(a|aa)*` gibi üstel geri izleme doğuran yapılar (tekrarlanan bir
   grubun içinde yine sınırsız tekrar ya da başlangıcı çakışan seçenekler) desen kurulurken reddedilir. Bu, tek
   bir kısa satırda bile saatler süren desenleri eşleştirme başlamadan eler. Güvenli ama nadir kullanılan bazı
   desenler de (ör. `(?:ab+)*`) reddedilir; sadeleştirmek kolaydır.
2. **Süre bütçesi** (`Deadline`): çok satırlı aramada her satırdan sonra süre denetlenir; toplam bütçe dolarsa
   arama durur. Her satırı ayrı ayrı yavaşlatan ama sonlanan desenler (ör. `.*.*.*x`) böyle kesilir.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

#: Bir desenin tüm satırlardaki toplam eşleştirme süresi için bütçe (saniye).
SEARCH_BUDGET = 0.5

#: Süre bütçesi dolunca kullanıcıya gösterilen ileti.
TIMEOUT_MESSAGE = "Arama çok uzun sürdü; deseni sadeleştirin."

#: Önden denetimin reddettiği desenlerde gösterilen ileti.
RISKY_MESSAGE = "Bu desen aramayı kilitleyebilir; deseni sadeleştirin."


class SearchTimeout(Exception):
    """Arama bütçesi doldu."""


class RiskyPattern(Exception):
    """Desen üstel geri izleme doğurabilir; aranmaz."""


class Deadline:
    """Toplam süre bütçesi; `check` her satırdan sonra çağrılır."""

    def __init__(self, seconds: float = SEARCH_BUDGET) -> None:
        self._end = time.perf_counter() + seconds

    def check(self) -> None:
        if time.perf_counter() > self._end:
            raise SearchTimeout


_QUANTIFIER = re.compile(r"\{(\d*)(?:(,)(\d*))?\}")


@dataclass
class _Level:
    """Açık bir grubun (ya da en üst düzeyin) tarama durumu."""

    unbounded: bool = False  # içinde (iç içe gruplar dahil) sınırsız tekrar var
    firsts: list[str] = field(default_factory=list)  # seçeneklerin ilk simgeleri
    first: str | None = None  # geçerli seçeneğin ilk simgesi

    def note_atom(self, token: str) -> None:
        if self.first is None:
            self.first = token

    def end_branch(self) -> None:
        self.firsts.append(self.first or "")
        self.first = None

    def has_overlap(self) -> bool:
        """Seçeneklerden ikisi aynı simgeyle (ya da belirsiz bir simgeyle) başlıyor mu."""
        if len(self.firsts) < 2:
            return False
        return len(set(self.firsts)) != len(self.firsts) or "*" in self.firsts


def _skip_class(pattern: str, i: int) -> int:
    """`[` ile başlayan karakter sınıfının bittiği konumdan sonrasını verir."""
    n = len(pattern)
    i += 1
    if i < n and pattern[i] == "^":
        i += 1
    if i < n and pattern[i] == "]":
        i += 1
    while i < n and pattern[i] != "]":
        i += 2 if pattern[i] == "\\" else 1
    return i + 1


def _group_prefix(pattern: str, i: int) -> tuple[int, bool]:
    """`(` konumundan sonraki uzantı önekini atlar; (sonraki konum, grup açıldı mı) verir.

    Bayrak grupları `(?i)` ve yorumlar `(?#...)` ile ad başvurusu `(?P=ad)` grup açmaz.
    """
    n = len(pattern)
    i += 1
    if i >= n or pattern[i] != "?":
        return i, True
    i += 1
    if i >= n:
        return i, True
    ch = pattern[i]
    if ch in ":=!":
        return i + 1, True
    if ch == "<":
        return (i + 2 if pattern[i + 1 : i + 2] in ("=", "!") else i + 1), True
    if ch == "P":
        close = pattern.find(">" if pattern[i + 1 : i + 2] == "<" else ")", i)
        if pattern[i + 1 : i + 2] == "<":
            return (close + 1 if close >= 0 else n), True
        return (close + 1 if close >= 0 else n), False
    close = min((p for p in (pattern.find(":", i), pattern.find(")", i)) if p >= 0), default=n)
    if close >= n:
        return n, True
    return close + 1, pattern[close] == ":"


def is_risky(pattern: str) -> bool:
    """Desen, üstel geri izleme doğurabilen bir yapı içeriyor mu (bkz. modül açıklaması)."""
    stack: list[_Level] = []
    level = _Level()
    n = len(pattern)
    i = 0
    #: Son tamamlanan atom bir grupsa (içinde sınırsız tekrar ya da çakışan seçenek varsa True, yoksa False).
    last_group: bool | None = None
    while i < n:
        ch = pattern[i]
        if ch == "\\":
            level.note_atom("*" if pattern[i + 1 : i + 2].isalpha() else pattern[i + 1 : i + 2])
            last_group = None
            i += 2
        elif ch == "[":
            level.note_atom("*")
            last_group = None
            i = _skip_class(pattern, i)
        elif ch == "(":
            i, opened = _group_prefix(pattern, i)
            last_group = None
            if opened:
                stack.append(level)
                level = _Level()
        elif ch == ")":
            i += 1
            if not stack:
                continue
            inner, level = level, stack.pop()
            inner.end_branch()
            level.note_atom("*")
            level.unbounded = level.unbounded or inner.unbounded
            last_group = inner.unbounded or inner.has_overlap()
        elif ch == "|":
            level.end_branch()
            last_group = None
            i += 1
        elif (quant := _quantifier_at(pattern, i)) is not None:
            unbounded, i = quant
            if unbounded:
                if last_group:
                    return True
                level.unbounded = True
            last_group = None
            if i < n and pattern[i] in "?+":  # tembel (`+?`) ve sahiplenici (`++`) ek simgeleri
                i += 1
        else:
            level.note_atom("*" if ch == "." else ch.casefold())
            last_group = None
            i += 1
    return False


def _quantifier_at(pattern: str, i: int) -> tuple[bool, int] | None:
    """Konumdaki niceleyiciyi çözer; (sınırsız mı, sonraki konum) verir, niceleyici değilse (düz `{`) None."""
    ch = pattern[i]
    if ch in "*+":
        return True, i + 1
    if ch == "?":
        return False, i + 1
    if ch != "{":
        return None
    found = _QUANTIFIER.match(pattern, i)
    if found is None or not (found.group(1) or found.group(3)):
        return None
    return bool(found.group(2)) and not found.group(3), found.end()
