"""Satırları yeniden bölme planı: seçili satırlar ve sığdırma sorunu olan satırlar."""

from __future__ import annotations

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.autofix import plan_reflow, reflow_row
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import FitConfig
from nxceviri.core.translate.status import Status

LABELS = ("Sayfa sonu", "Satır sonu")
FIT = FitConfig(default=FitRules(24, 3))


def _row(
    rid: int, source: str, translation: str, status: str = Status.MACHINE, labels: tuple[str, ...] = ()
) -> TranslationRow:
    return TranslationRow(rid, "f", f"k{rid}", source, translation, status, "", labels, None)


def test_reflow_row_with_rules_uses_rules() -> None:
    row = _row(1, "One two three four five", "Bir\niki üç dört beş altı yedi sekiz dokuz")
    new = reflow_row(row, FIT)
    assert new is not None
    assert max(len(line) for line in new.split("\n")) <= 24
    assert " ".join(new.split()) == " ".join(row.translation.split())


def test_reflow_row_without_rules_uses_source_lines() -> None:
    row = _row(1, "One two three four\nfive six seven eight", "bir iki üç dört beş altı yedi sekiz")
    new = reflow_row(row, FitConfig())
    assert new is not None
    assert new.count("\n") == 1


def test_reflow_row_keeps_codes_and_returns_none_when_unchanged() -> None:
    row = _row(1, "a⟦2⟧b⟦1⟧", "Merhaba dünya bugün⟦2⟧hava⟦1⟧", labels=LABELS)
    new = reflow_row(row, FitConfig())
    assert new is not None
    assert placeholders.tokens_in(new) == placeholders.tokens_in(row.translation)
    assert reflow_row(_row(2, "x", "kısa"), FIT) is None
    assert reflow_row(_row(3, "x", ""), FIT) is None


def test_plan_reflow_selected_rows_includes_approved_and_skips_empty() -> None:
    rows = [
        _row(1, "a b", "bir\niki üç dört beş altı yedi sekiz dokuz on"),
        _row(2, "a b", "bir\niki üç dört beş altı yedi sekiz dokuz on", Status.APPROVED),
        _row(3, "a b", ""),
    ]
    plan = plan_reflow(rows, FIT)
    assert [rid for rid, _text in plan] == [1, 2]


def test_plan_reflow_covers_given_rows_including_approved() -> None:
    long_text = "bir iki üç dört beş altı yedi sekiz dokuz on onbir on iki"
    rows = [
        _row(1, "a b", long_text),
        _row(2, "a b", long_text, Status.APPROVED),
        _row(3, "a b", "kısa"),
        _row(4, "a b", "bir iki üç dört beş altı\nyedi sekiz dokuz on"),  # sınır içinde, sorunsuz
    ]
    plan = plan_reflow(rows, FIT)
    assert [rid for rid, _text in plan][:2] == [1, 2]  # verilen satırlar, onaylılar dahil
    assert 3 not in [rid for rid, _text in plan]  # zaten uygun satır değişmez
