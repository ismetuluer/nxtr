"""Biçim kodu zarfı onarımı: yalnızca güvenli durumlar otomatik düzeltilir, gerisi elle kalır."""

from __future__ import annotations

from dataclasses import replace

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.autofix import local_fix, plan_fixes
from nxceviri.core.qa.checks import check_row
from nxceviri.core.qa.codefix import repair_codes
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.status import Status

LABELS = ("Renk", "Renk sonu", "Oyuncu adı", "Satır sonu")


def _row(source: str, text: str, status: str = Status.ERROR, labels: tuple[str, ...] = LABELS) -> TranslationRow:
    return TranslationRow(1, "f", "k", source, text, status, "", labels, None)


def _visible(text: str) -> str:
    return placeholders.TOKEN_RE.sub("", text)


def test_full_envelope_is_wrapped() -> None:
    fixed = repair_codes("⟦1⟧Walk over there.⟦2⟧", "Şurada yürü.", LABELS)
    assert fixed == "⟦1⟧Şurada yürü.⟦2⟧"
    assert placeholders.problems("⟦1⟧Walk over there.⟦2⟧", fixed) == []


def test_partial_range_is_left_alone() -> None:
    source = "Use this ⟦1⟧walk⟦2⟧ over there."
    assert repair_codes(source, "Şurada yürü.", LABELS) is None
    assert local_fix(_row(source, "Şurada yürü."), kinds=["placeholder"]) == "Şurada yürü."


def test_missing_close_is_appended() -> None:
    assert repair_codes("⟦1⟧Walk.⟦2⟧", "⟦1⟧Yürü.", LABELS) == "⟦1⟧Yürü.⟦2⟧"


def test_missing_close_mid_sentence_is_left_alone() -> None:
    assert repair_codes("⟦1⟧Walk⟦2⟧ there.", "⟦1⟧Yürü orada.", LABELS) is None
    assert repair_codes("Go ⟦1⟧walk.⟦2⟧", "⟦1⟧Yürü.", LABELS) is None  # zarf tam satırı kaplamıyor


def test_half_written_placeholder_is_repaired() -> None:
    fixed = repair_codes("⟦1⟧Walk.⟦2⟧", "[1]Yürü.⟦2⟧", LABELS)
    assert fixed == "⟦1⟧Yürü.⟦2⟧"
    assert repair_codes("⟦1⟧Walk.⟦2⟧", "{{1}}Yürü.⟦2⟧", LABELS) == "⟦1⟧Yürü.⟦2⟧"
    assert repair_codes("⟦1⟧Walk.⟦2⟧", "⟨ 1 ⟩Yürü.⟦2⟧", LABELS) == "⟦1⟧Yürü.⟦2⟧"
    assert repair_codes("[1] ⟦1⟧", "[1] z", LABELS) is None  # kaynakta da geçen yazım onarılmaz


def test_missing_variable_is_left_alone() -> None:
    assert repair_codes("Hi ⟦3⟧!", "Selam!", LABELS) is None
    assert repair_codes("⟦1⟧Hi ⟦3⟧!⟦2⟧", "Selam!", LABELS) is None  # zarf var ama değişken de eksik


def test_several_pairs_and_invented_codes() -> None:
    labels = ("Renk", "Renk sonu", "Biçim", "Biçim sonu")
    assert repair_codes("⟦1⟧⟦3⟧Hi.⟦4⟧⟦2⟧", "Selam.", labels) is None  # iç içe çiftler elle kalır
    assert repair_codes("⟦1⟧Hi⟦2⟧ ve ⟦3⟧bye⟦4⟧", "Selam.", labels) is None  # birden çok çift
    assert repair_codes("⟦1⟧Hi.⟦2⟧", "⟦3⟧Selam.⟦4⟧", labels) == "⟦1⟧Selam.⟦2⟧"  # uydurma kodlar atılır


def test_non_pair_codes_are_not_wrapped() -> None:
    labels = ("Satır sonu", "Satır sonu")
    assert repair_codes("⟦1⟧Hi.⟦2⟧", "Selam.", labels) is None
    assert repair_codes("⟦1⟧Hi.⟦2⟧", "Selam.", ("Renk", "Renk 2 sonu")) is None  # eşi olmayan kapanış


def test_repair_is_idempotent_and_keeps_visible_text() -> None:
    row = _row("⟦1⟧Walk over there.⟦2⟧", "Şurada yürü.")
    once = local_fix(row, kinds=["placeholder"])
    assert once == "⟦1⟧Şurada yürü.⟦2⟧"
    assert _visible(once) == _visible(row.translation)
    assert local_fix(replace(row, translation=once, status=Status.MACHINE), kinds=["placeholder"]) == once
    assert repair_codes(row.source, once, LABELS) is None


def test_error_row_is_fixed_by_plan_and_manual_row_counts_unfixed() -> None:
    fixable = _row("⟦1⟧Walk.⟦2⟧", "Yürü.")
    manual = replace(_row("Use this ⟦1⟧walk⟦2⟧ over there.", "Şurada yürü."), id=2)
    rows = [fixable, manual]
    issues = [i for r in rows for i in check_row(r, "", "")]
    plan = plan_fixes(rows, issues, ["placeholder"])
    assert plan.changes == [(1, "⟦1⟧Yürü.⟦2⟧")]
    assert plan.unfixed == 1


def test_issue_message_says_what_to_do() -> None:
    fixable = check_row(_row("⟦1⟧Walk.⟦2⟧", "Yürü."), "", "")
    assert fixable[0].message.startswith("Düzeltmeler ile onarılabilir:")
    manual = check_row(_row("Use this ⟦1⟧walk⟦2⟧ over there.", "Şurada yürü."), "", "")
    assert manual[0].message.startswith("Elle düzeltilmeli: renk/biçim yalnızca metnin bir bölümünü kaplıyor.")
    variable = check_row(_row("Hi ⟦3⟧!", "Selam!"), "", "")
    assert variable[0].message.startswith("Elle düzeltilmeli:")
    order = check_row(_row("a⟦3⟧b⟦4⟧", "x⟦4⟧y⟦3⟧"), "", "")
    assert not order[0].message.startswith(("Elle", "Düzeltmeler ile"))  # eksik kod yok: eski ileti
