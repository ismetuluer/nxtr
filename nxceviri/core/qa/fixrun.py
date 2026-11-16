"""Kontrol Et → Düzelt için düzeltme planı: ekrandaki bildirim ile gerçek düzeltme aynı plandan gelir.

Düzelt, seçilen bulguları onaylı satırlarda da düzeltir (satır onaylı kalır; yazımı arayüz yapar). Makine
çevirisinin onaylı satıra yazmama kuralı `Project.set_translations`ta durur ve buradan etkilenmez.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.autofix import FixPlan, plan_fixes
from nxceviri.core.qa.checks import QaIssue, run_checks, spell_extra_words
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.translate.fitconfig import FitConfig
from nxceviri.core.translate.providers.base import GlossaryTerm


@dataclass(frozen=True)
class FixSettings:
    """Denetimin ve düzeltmenin ihtiyaç duyduğu proje ayarları; iş parçacığına ana iş parçacığında okunup verilir."""

    missing_letters: str = ""
    transliterated: str = ""
    glossary: list[GlossaryTerm] = field(default_factory=list)
    fit: FitConfig | None = None
    spell: SpellChecker | None = None
    ignored_terms: Collection[str] = ()
    spell_ignored: Collection[str] = ()


def plan_for_issues(
    rows: Sequence[TranslationRow], issues: Sequence[QaIssue], kinds: Collection[str], settings: FixSettings
) -> FixPlan:
    """Hazır bulgulardan düzeltme planı (onaylı satırlar dahil). `rows` bulguların satırlarını içermelidir."""
    extra = spell_extra_words(settings.glossary, settings.spell_ignored) if settings.spell is not None else frozenset()
    return plan_fixes(
        rows,
        issues,
        kinds,
        include_approved=True,
        glossary=settings.glossary,
        fit=settings.fit,
        spell=settings.spell,
        spell_extra=extra,
    )


def plan_for_rows(rows: Sequence[TranslationRow], kinds: Collection[str], settings: FixSettings) -> FixPlan:
    """Yalnızca verilen satırları denetleyip düzeltme planı çıkarır (tüm projeyi denetlemez).

    Terim tutarsızlığı otomatik düzeltilemez; bu yüzden bulgusu hesaplanmaz (`terms={}`).
    """
    issues = run_checks(
        list(rows),
        settings.missing_letters,
        settings.transliterated,
        settings.glossary,
        settings.fit,
        spell=settings.spell,
        ignored_terms=settings.ignored_terms,
        spell_ignored=settings.spell_ignored,
        terms={},
    )
    return plan_for_issues(rows, issues, kinds, settings)
