"""Orijinalde olmayan sondaki noktalama: uyarı verilir ve yerel olarak düzeltilir."""

from __future__ import annotations

import pytest

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.autofix import local_fix, plan_fixes
from nxceviri.core.qa.checks import KIND_LABELS, SEVERITY_WARNING, check_row, run_checks
from nxceviri.core.translate.cleanup import added_end_punctuation, strip_added_end_punctuation
from nxceviri.core.translate.status import Status


def _row(source: str, translation: str, i: int = 1) -> TranslationRow:
    return TranslationRow(i, "f", f"k{i}", source, translation, Status.MACHINE, "", (), None)


@pytest.mark.parametrize(
    ("source", "text", "added"),
    [
        ("Start Game", "Oyunu Başlat.", "."),
        ("Yes", "Evet!", "!"),
        ("Options ⟦1⟧", "Seçenekler.⟦1⟧", "."),  # sondaki kodun önündeki işaret de sayılır
        ("Load", "Yükle... ", "..."),
        ("Done.", "Tamam!", ""),  # orijinal de noktalamayla bitiyor
        ("“Run”", "“Koş”", ""),
        ("Run", "Koş", ""),
        ("Wait...", "Bekle…", ""),
    ],
)
def test_added_end_punctuation(source: str, text: str, added: str) -> None:
    assert added_end_punctuation(source, text) == added


def test_strip_keeps_codes_and_spaces() -> None:
    assert strip_added_end_punctuation("Options ⟦1⟧", "Seçenekler.⟦1⟧") == "Seçenekler⟦1⟧"
    assert strip_added_end_punctuation("Load ", "Yükle... ") == "Yükle "
    assert strip_added_end_punctuation("Done.", "Tamam!") == "Tamam!"


def test_qa_reports_only_the_added_end_punctuation() -> None:
    issues = check_row(_row("Start Game", "Oyunu; başlat."), "", "")
    found = {i.kind: i for i in issues}
    assert found["end_punctuation"].severity == SEVERITY_WARNING
    assert found["end_punctuation"].message == "Sonda orijinalde olmayan noktalama var: “.”"
    assert KIND_LABELS["end_punctuation"] == "Sondaki noktalama"
    assert "punctuation" not in KIND_LABELS  # metin içindeki ünlem/soru Türkçede doğal: uyarı gürültüsü olurdu
    assert not [i for i in check_row(_row("Done.", "Tamam."), "", "") if "punctuation" in i.kind]


def test_autofix_removes_added_end_punctuation_locally() -> None:
    row = _row("Start Game", "Oyunu Başlat.")
    assert local_fix(row) == "Oyunu Başlat"
    rows = [row, _row("Let's go now", "Hadi! Şimdi gidelim", 2)]
    plan = plan_fixes(rows, run_checks(rows, "", ""))
    assert plan.changes == [(1, "Oyunu Başlat")]
