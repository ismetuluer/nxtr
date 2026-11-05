"""Ek satır denetimleri: sözlük uyumu ve kod adı."""

from __future__ import annotations

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import KIND_LABELS, SEVERITY_WARNING, run_checks
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import FitConfig
from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.core.translate.status import Status

GLOSSARY = [
    GlossaryTerm("Police Department", "Polis Merkezi"),
    GlossaryTerm("Eddie", "Eddie"),
    GlossaryTerm("Key", "Anahtar"),
    GlossaryTerm("", "boş terim yok sayılır"),
]


def _row(i: int, source: str, translation: str) -> TranslationRow:
    return TranslationRow(i, "f", f"k{i}", source, translation, Status.MACHINE, "", (), None, f"C/{i}")


def _kinds(rows: list[TranslationRow], glossary: list[GlossaryTerm] | None = GLOSSARY) -> list[tuple[int, str]]:
    return [(i.row_id, i.kind) for i in run_checks(rows, "", "", glossary) if i.kind in ("glossary", "identifier")]


def test_glossary_term_missing_in_translation() -> None:
    rows = [
        _row(1, "Police Department Restroom", "Polis Karakolu Tuvaleti"),  # terim kullanılmamış
        _row(2, "Police Department Restroom", "Polis Merkezi Tuvaleti"),  # tamam
        _row(3, "Ask Eddie.", "Eddie'ye sor."),  # ek alan terimle uyumlu
        _row(4, "Ask Eddie.", "Ona sor."),  # ad kaybolmuş
        _row(5, "Keys are here.", "Anahtarlar burada."),  # "Keys" ayrı sözcük: terim eşleşmez
        _row(6, "Turn the Key", "Düğmeye bas"),
        _row(7, "Nothing to see", "Görülecek bir şey yok"),
    ]
    assert _kinds(rows) == [(1, "glossary"), (4, "glossary"), (6, "glossary")]
    messages = [i.message for i in run_checks(rows[:1], "", "", GLOSSARY)]
    assert messages == ["Sözlükte “Police Department” → “Polis Merkezi” var; çeviride yok."]


def test_glossary_check_is_off_without_glossary() -> None:
    assert _kinds([_row(1, "Police Department", "Karakol")], glossary=None) == []
    assert "glossary" in KIND_LABELS
    assert "identifier" in KIND_LABELS


def test_identifier_like_sources_are_flagged() -> None:
    rows = [
        _row(1, "Motel_Interior_Grizzly_TopFloor", "Motel_İç Mekan_Grizzly_En Üst Kat"),  # çevrilmiş kod adı
        _row(2, "Misc_Church_Medallion", "Misc_Church_Medallion"),  # aynen bırakılmış: sorun yok
        _row(3, "Apartment_2C", "Apartman_2C"),
        _row(4, "Sheriff_Office desk", "Şerif masası"),  # boşluk var: kod adı değil
        _row(5, "Hello_World.", "Merhaba"),  # nokta var: kod adı değil
        _row(6, "Cable Car", "Teleferik"),
    ]
    assert _kinds(rows, glossary=None) == [(1, "identifier"), (3, "identifier")]


def _fit_row(i: int, source: str, translation: str, file: str = "f") -> TranslationRow:
    return TranslationRow(i, file, f"k{i}", source, translation, Status.MACHINE, "", (), None, f"C/{i}")


def _fit_messages(rows: list[TranslationRow], fit: FitConfig | None) -> list[tuple[str, str]]:
    fit_kinds = ("line_too_long", "page_too_tall", "bad_break")
    return [(i.kind, i.message) for i in run_checks(rows, "", "", None, fit) if i.kind in fit_kinds]


def test_fit_issues_reported() -> None:
    fit = FitConfig(default=FitRules(40, 3))
    long_line = "a" * 47
    got = _fit_messages([_fit_row(1, "x", f"kısa\n{long_line}")], fit)
    assert got == [("line_too_long", "1. sayfa, 2. satır 47 karakter; sınır 40.")]
    tall = _fit_messages([_fit_row(2, "x", "bir\niki\nüç\ndört")], fit)
    assert ("page_too_tall", "1. sayfada 4 satır var; sınır 3.") in tall
    broken = _fit_messages([_fit_row(3, "x", "Merhaba\ndünya nasılsın bugün")], fit)
    assert [k for k, _ in broken] == ["bad_break"]
    assert broken[0][1] == "1. sayfa, 1. satır gereksiz kısa kesilmiş; sonraki sözcük sığardı."
    severities = {i.severity for i in run_checks([_fit_row(1, "x", f"kısa\n{long_line}")], "", "", None, fit)}
    assert SEVERITY_WARNING in severities


def test_no_fit_issues_without_rules() -> None:
    rows = [_fit_row(1, "x", "a" * 200 + "\nb\nc\nd\ne")]
    assert _fit_messages(rows, None) == []
    assert _fit_messages(rows, FitConfig()) == []


def test_newlines_check_suppressed_when_rules_apply() -> None:
    row = _fit_row(1, "a\nb", "bir\niki\nüç")
    kinds = [i.kind for i in run_checks([row], "", "", None, None)]
    assert "newlines" in kinds
    kinds = [i.kind for i in run_checks([row], "", "", None, FitConfig(default=FitRules(40, 5)))]
    assert "newlines" not in kinds


def test_per_file_rule_used() -> None:
    fit = FitConfig(per_file={"a.msbt": FitRules(10, 3)})
    text = "bu satır on karakterden uzun"
    rows = [_fit_row(1, "x", text, "a.msbt"), _fit_row(2, "x", text, "b.msbt")]
    assert [i.row_id for i in run_checks(rows, "", "", None, fit) if i.kind == "line_too_long"] == [1]


def test_untranslated_row_has_no_fit_issue() -> None:
    fit = FitConfig(default=FitRules(5, 1))
    assert _fit_messages([_fit_row(1, "çok uzun bir kaynak metin", "")], fit) == []


def test_bad_break_in_source_not_reported() -> None:
    fit = FitConfig(default=FitRules(40, 3))
    assert _fit_messages([_fit_row(1, "Yes\nNo", "Evet\nHayır")], fit) == []
    assert [k for k, _ in _fit_messages([_fit_row(2, "Yes, no", "Evet\nHayır")], fit)] == ["bad_break"]
