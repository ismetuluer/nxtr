"""Sınırlar tablosu istatistikleri: grup ve anahtar deseni başına satır sayısı, en uzun satır, en çok satır."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from nxceviri.core.project import TranslationRow, row_group
from nxceviri.core.translate.codekinds import CodeKinds
from nxceviri.core.translate.fitconfig import key_matches, key_names, learn_rules

SCOPE_GROUP = "group:"
SCOPE_KEY = "key:"


@dataclass(frozen=True)
class LimitStat:
    """Bir kapsamın ölçüsü; `scope` "group:<ad>" ya da "key:<desen>", `label` arayüzde görünen ad."""

    scope: str
    label: str
    rows: int
    longest_source_line: int
    max_source_lines: int


def valid_pattern(pattern: str) -> bool:
    """Anahtar deseni boş olmamalı ve denetim karakteri (satır sonu vb.) içermemeli."""
    return bool(pattern.strip()) and pattern.isprintable()


def _stat(scope: str, label: str, rows: Sequence[TranslationRow], kinds: CodeKinds) -> LimitStat:
    measured = learn_rules(rows, kinds)
    if measured is None:
        return LimitStat(scope, label, len(rows), 0, 0)
    return LimitStat(scope, label, len(rows), measured.width, measured.max_lines)


def group_stats(rows: Sequence[TranslationRow], kinds: CodeKinds | None = None) -> list[LimitStat]:
    """Her grup (`row_group`) için istatistik; ad sırasına göre. Kodlar çıkarılır, satır sonu kodları satır böler."""
    kinds = kinds or CodeKinds({})
    by_group: dict[str, list[TranslationRow]] = {}
    for row in rows:
        by_group.setdefault(row_group(row), []).append(row)
    return [_stat(SCOPE_GROUP + g, g, by_group[g], kinds) for g in sorted(by_group, key=str.casefold)]


def key_stats(
    rows: Sequence[TranslationRow], patterns: Iterable[str], kinds: CodeKinds | None = None
) -> list[LimitStat]:
    """Her anahtar deseni için, desene uyan satırların istatistiği (hiç uymayan desen 0 satırla yer alır)."""
    kinds = kinds or CodeKinds({})
    names = [key_names(r) for r in rows]
    result: list[LimitStat] = []
    for pattern in patterns:
        matched = [r for r, n in zip(rows, names, strict=True) if key_matches(pattern, n)]
        result.append(_stat(SCOPE_KEY + pattern, pattern, matched, kinds))
    return result
