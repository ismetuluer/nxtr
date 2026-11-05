"""Kalite denetimi bulgularının türe göre düzeltilmesi."""

from __future__ import annotations

from dataclasses import replace

import pytest

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa import autofix as autofix_module
from nxceviri.core.qa.autofix import FIX_KINDS, local_fix, plan_fixes
from nxceviri.core.qa.checks import KIND_LABELS, run_checks
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import FitConfig, FitOptions
from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.core.translate.status import Status

GLOSSARY = [GlossaryTerm("Sheriff", "Şerif")]


def test_local_fix() -> None:
    row = TranslationRow(1, "f", "k", "Hello ", "  Tek\n satır", "machine", "", (), None)
    assert local_fix(row) == "Tek satır "
    keep = TranslationRow(2, "f", "k", "A\nB", "C\nD", "machine", "", (), None)
    assert local_fix(keep) == "C\nD"


def test_program_fixes_lines_codes_and_glossary() -> None:
    from nxceviri.core.qa.autofix import apply_glossary, rebalance_lines, reorder_codes

    assert rebalance_lines("Kaleyi çubuklardan yapabiliriz ya da başka bir şeyden", 3) == (
        "Kaleyi çubuklardan\nyapabiliriz ya da\nbaşka bir şeyden"
    )
    assert rebalance_lines("Tek", 2) is None  # sözcük yetmez
    lb = ("Satır sonu", "Satır sonu")
    assert reorder_codes("a⟦1⟧b⟦2⟧", "x⟦2⟧y⟦1⟧", lb) == "x⟦1⟧y⟦2⟧"
    assert reorder_codes("a⟦1⟧b⟦2⟧", "x⟦2⟧y⟦1⟧", ("Renk", "Satır sonu")) is None  # farklı türler yer değiştirmez
    assert reorder_codes("a⟦1⟧", "x⟦1⟧", lb[:1]) is None  # sorun yok
    assert apply_glossary("Talk to the Sheriff.", "Sheriff'e git.", GLOSSARY) == "Şerif'e git."
    assert apply_glossary("Talk to the Sheriff.", "Polise git.", GLOSSARY) == "Polise git."  # model gerekir


FIT = FitConfig(default=FitRules(40, 3))
FIT_KINDS = {"line_too_long", "page_too_tall", "bad_break"}
PAGES = ("Sayfa sonu", "Sayfa sonu", "Sayfa sonu")
FIT_SOURCE = (
    "Just a word of warning.⟦1⟧This setting can sometimes give odd results. For example, you might hear the "
    "success sound even though you failed.⟦2⟧Sorry about that; it happens sometimes when we change the TV "
    "settings like this.⟦3⟧Ah! But it should never happen in handheld mode! Thank goodness for that."
)
BADLY_SPLIT = (
    "Yalnız bir uyarı.⟦1⟧Bu ayar bazen garip\n"
    "sonuç verebilir. Örneğin başarısız olduğun\n"
    "hâlde başarılı hareket sesi duyabilirsin.⟦2⟧Kusura\n"
    "bakma; TV ayarını böyle değiştirdiğimizde\n"
    "bazen oluyor.⟦3⟧Aa! Ama elde\n"
    "taşınır modda hiç yaşanmamalı! Buna da şükür."
)


def _fit_row(translation: str, source: str = FIT_SOURCE, status: str = Status.MACHINE) -> TranslationRow:
    labels = PAGES if "⟦" in source else ()
    return TranslationRow(1, "f", "k", source, translation, status, "", labels, None)


def _fit_kinds(row: TranslationRow) -> list[str]:
    return [i.kind for i in run_checks([row], "", "", None, FIT) if i.kind in FIT_KINDS]


def test_local_fix_fits_when_rules_set() -> None:
    row = _fit_row(BADLY_SPLIT)
    assert _fit_kinds(row)  # önce sorunlu
    fixed = local_fix(row, fit=FIT)
    assert _fit_kinds(replace(row, translation=fixed)) == []
    assert placeholders.tokens_in(fixed) == placeholders.tokens_in(BADLY_SPLIT)


def test_local_fix_unchanged_without_rules() -> None:
    row = _fit_row(BADLY_SPLIT)
    assert local_fix(row, fit=FitConfig()) == local_fix(row)  # kural yoksa eski davranış birebir
    other_file = FitConfig(per_file={"g": FitRules(40, 3)})
    assert local_fix(row, fit=other_file) == local_fix(row)


def test_local_fix_skips_newline_rebalance_when_rules_set() -> None:
    row = _fit_row("Bu bir satır.\nBu da ikinci satır.", source="One line only here.")
    assert local_fix(row, fit=FIT) == "Bu bir satır.\nBu da ikinci satır."  # satır sayısını sınır belirler
    assert local_fix(row) == "Bu bir satır. Bu da ikinci satır."  # sınır yokken eski birleştirme
    two = _fit_row("Birinci ve ikinci satır", source="Line one\nLine two")
    assert local_fix(two, fit=FIT) == "Birinci ve ikinci satır"
    assert local_fix(two) == "Birinci ve\nikinci satır"


def test_unfittable_row_is_left_alone() -> None:
    fit = FitConfig(default=FitRules(5, 1))
    row = _fit_row("Upuzunkelime", source="Longword")
    plan = plan_fixes([row], run_checks([row], "", "", None, fit), fit=fit)
    assert plan.changes == []
    assert plan.unfixed == 1  # sığmayan satır elle bakılsın diye sayılır


def test_plan_fixes_respects_approved() -> None:
    row = _fit_row(BADLY_SPLIT, status=Status.APPROVED)
    plan = plan_fixes([row], run_checks([row], "", "", None, FIT), fit=FIT)
    assert plan.approved == 1
    assert plan.changes == []
    with_approved = plan_fixes([row], run_checks([row], "", "", None, FIT), include_approved=True, fit=FIT)
    assert [i for i, _ in with_approved.changes] == [1]


def test_plan_fixes_fits_locally() -> None:
    row = _fit_row(BADLY_SPLIT)
    plan = plan_fixes([row], run_checks([row], "", "", None, FIT), fit=FIT)
    assert dict(plan.changes) == {1: local_fix(row, fit=FIT)}
    assert plan.applied[1] == ("line_too_long", "bad_break")  # düzelen sığdırma türleri


def test_options_gate_cleanup() -> None:
    row = _fit_row("Dur....", source="Wait!")
    off = FitConfig(default=FitRules(40, 3), options=FitOptions(repeated_punct=False))
    assert local_fix(row, fit=off) == "Dur...."
    assert local_fix(row, fit=FIT) == "Dur..."
    assert local_fix(row) == "Dur..."  # sınır yokken de 4+ nokta temizlenir (kaynakta yoksa)
    spaced = _fit_row("Dur  bakalım !", source="Wait!")
    assert local_fix(spaced, fit=FIT) == "Dur bakalım!"
    no_spaces = FitConfig(default=FitRules(40, 3), options=FitOptions(spaces=False, space_before_punct=False))
    assert local_fix(spaced, fit=no_spaces) == "Dur  bakalım !"


def test_fix_keeps_placeholders() -> None:
    row = _fit_row(BADLY_SPLIT + "  !!!!")
    fixed = local_fix(row, fit=FIT)
    assert placeholders.problems(row.source, fixed) == []
    assert fixed.endswith("!!!")


def test_tidy_that_breaks_fit_is_refitted() -> None:
    fit = FitConfig(default=FitRules(12, 3))
    row = _fit_row("Aa   bb\ncc", source="x y z")
    # Çift boşluk temizlenince ilk satır gereksiz kısa kalır; metin yeniden sığdırılır.
    assert [i.kind for i in run_checks([row], "", "", None, fit)] == ["double_space"]  # yalnızca boşluk bulgusu
    assert local_fix(row, fit=fit) == "Aa bb cc"


def test_glossary_lengthened_line_is_fitted() -> None:
    fit = FitConfig(default=FitRules(20, 3))
    glossary = [GlossaryTerm("Sheriff", "Kasaba Şerifimiz")]
    row = _fit_row("Sheriff'e bunu şimdi sor", source="Ask the Sheriff about this now, please.")
    fixed = local_fix(row, glossary, fit)
    assert "Kasaba Şerifimiz'e" in fixed
    assert [
        i.kind for i in run_checks([replace(row, translation=fixed)], "", "", None, fit) if i.kind in FIT_KINDS
    ] == []
    assert local_fix(replace(row, translation=fixed), glossary, fit) == fixed  # ikinci onarım aynı sonucu verir
    plan = plan_fixes([row], run_checks([row], "", "", glossary, fit), glossary=glossary, fit=fit)
    assert dict(plan.changes) == {1: fixed}


def test_tidy_kept_out_when_refit_cannot_help() -> None:
    fit = FitConfig(default=FitRules(10, 3))
    # 1. satırdaki kelime sığmaz (sayfa onarılamaz); boşluk temizliği 2. satırı gereksiz kısa bırakırdı.
    row = _fit_row("abcdefghijkl\nab    c\nef", source="x y z")
    assert local_fix(row, fit=fit) == "abcdefghijkl\nab    c\nef"


def test_local_fix_never_worsens_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Yerel düzeltme kontrol kodu bütünlüğünü bozacaksa (ör. kod sırası) satır düzeltilmemiş kalır."""
    fit = FitConfig(default=FitRules(36, 2))
    source = "You found⟦1⟧⟦2⟧ gold coins in the old chest, great."
    text = "Eski sandıkta⟦1⟧⟦2⟧ altın para buldun, harika bir şey bu."
    row = TranslationRow(1, "f", "k", source, text, Status.MACHINE, "", ("Satır sonu", "Sayı 0001"), None)
    swapped = "Eski sandıkta ⟦2⟧ altın para buldun,⟦1⟧harika bir şey bu."
    monkeypatch.setattr(autofix_module, "fit_and_tidy", lambda _row, _text, _fit: swapped)
    assert local_fix(row, fit=fit) == text
    plan = plan_fixes([row], run_checks([row], "", "", None, fit), fit=fit)
    assert plan.changes == []


def test_local_fix_with_line_break_next_to_variable_keeps_order() -> None:
    fit = FitConfig(default=FitRules(36, 2))
    source = "You found⟦1⟧⟦2⟧ gold coins in the old chest, great."
    text = "Eski sandıkta⟦1⟧⟦2⟧ altın para buldun, harika bir şey bu."
    row = TranslationRow(1, "f", "k", source, text, Status.MACHINE, "", ("Satır sonu <br>", "Sayı 0001"), None)
    plan = plan_fixes([row], run_checks([row], "", "", None, fit), fit=fit)
    for _row_id, fixed in plan.changes:
        assert placeholders.problems(source, fixed) == []


def test_bad_break_in_source_not_merged() -> None:
    row = _fit_row("Evet\nHayır", source="Yes\nNo")
    assert local_fix(row, fit=FIT) == "Evet\nHayır"
    plan = plan_fixes([row], run_checks([row], "", "", None, FIT), fit=FIT)
    assert plan.empty
    new_break = _fit_row("Evet\nhiç sorun yok.", source="Yes, and no problem at all.")
    assert local_fix(new_break, fit=FIT) == "Evet hiç sorun yok."


MESSY = TranslationRow(
    1, "f", "k", "Start the Sheriff quest", " Sheriff ile ile  görevi başlat.. şimdi", Status.MACHINE, "", (), None
)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("spaces", "Sheriff ile ile  görevi başlat.. şimdi"),
        ("glossary", " Şerif ile ile  görevi başlat.. şimdi"),
        ("repeated_word", " Sheriff ile  görevi başlat.. şimdi"),
        ("double_space", " Sheriff ile ile görevi başlat.. şimdi"),
        ("extra_dots", " Sheriff ile ile  görevi başlat... şimdi"),
    ],
)
def test_each_kind_alone_applies_only_its_fix(kind: str, expected: str) -> None:
    assert local_fix(MESSY, GLOSSARY, kinds={kind}) == expected
    plan = plan_fixes([MESSY], run_checks([MESSY], "", "", GLOSSARY), {kind}, glossary=GLOSSARY)
    assert plan.changes == [(1, expected)]
    assert plan.applied == {1: (kind,)}


def test_several_kinds_together_and_unselected_untouched() -> None:
    assert local_fix(MESSY, GLOSSARY, kinds={"spaces", "glossary"}) == "Şerif ile ile  görevi başlat.. şimdi"
    assert local_fix(MESSY, GLOSSARY) == "Şerif ile görevi başlat... şimdi"  # hepsi
    assert local_fix(MESSY, GLOSSARY, kinds=set()) == MESSY.translation
    plan = plan_fixes([MESSY], run_checks([MESSY], "", "", GLOSSARY), {"glossary", "extra_dots"}, glossary=GLOSSARY)
    assert plan.changes == [(1, " Şerif ile ile  görevi başlat... şimdi")]
    assert plan.applied == {1: ("glossary", "extra_dots")}
    # Seçilmeyen türde bulgusu olmayan seçim hiçbir şeyi değiştirmez.
    assert plan_fixes([MESSY], run_checks([MESSY], "", "", GLOSSARY), {"markup"}, glossary=GLOSSARY).empty


def test_other_kinds_alone() -> None:
    def row(source: str, text: str, labels: tuple[str, ...] = ()) -> TranslationRow:
        return TranslationRow(1, "f", "k", source, text, Status.MACHINE, "", labels, None)

    punct = row("Start Game", "Oyunu Başlat.")
    assert local_fix(punct, kinds={"end_punctuation"}) == "Oyunu Başlat"
    assert local_fix(punct, kinds={"markup"}) == "Oyunu Başlat."
    markup = row("Hi", "<div>Selam</div>")
    assert local_fix(markup, kinds={"markup"}) == "Selam"
    assert local_fix(markup, kinds={"spaces"}) == "<div>Selam</div>"
    single = row("One line only", "Tek\nsatır")
    assert local_fix(single, kinds={"newlines"}) == "Tek satır"
    assert local_fix(single, kinds={"spaces"}) == "Tek\nsatır"
    swapped = row("a⟦1⟧b⟦2⟧c", "x⟦2⟧y⟦1⟧z", ("Satır sonu", "Satır sonu"))
    assert local_fix(swapped, kinds={"placeholder"}) == "x⟦1⟧y⟦2⟧z"
    assert local_fix(swapped, kinds={"markup", "spaces"}) == swapped.translation


def test_fit_kind_applies_fit_only_when_selected() -> None:
    row = _fit_row(BADLY_SPLIT)
    assert local_fix(row, kinds={"spaces"}, fit=FIT) == BADLY_SPLIT
    fixed = local_fix(row, kinds={"line_too_long"}, fit=FIT)
    assert fixed == local_fix(row, kinds=autofix_module.FIT_KINDS, fit=FIT)
    assert _fit_kinds(replace(row, translation=fixed)) == []


def test_error_row_order_fix_clears_error_row() -> None:
    labels = ("Renk", "Renk sonu", "Renk", "Renk sonu")
    row = TranslationRow(1, "f", "k", "⟦1⟧A⟦2⟧ ⟦3⟧B⟦4⟧", "⟦3⟧B⟦4⟧ ⟦1⟧A⟦2⟧", Status.ERROR, "kod sırası", labels, None)
    plan = plan_fixes([row], run_checks([row], "", ""), {"placeholder"})
    assert plan.changes == [(1, "⟦1⟧B⟦2⟧ ⟦3⟧A⟦4⟧")]
    assert plan.applied == {1: ("placeholder",)}
    assert placeholders.problems(row.source, plan.changes[0][1]) == []
    # Başka tür seçilince Hatalı satıra dokunulmaz.
    assert plan_fixes([row], run_checks([row], "", ""), {"spaces"}).empty


def test_all_fix_kinds_have_labels() -> None:
    assert set(FIX_KINDS) <= set(KIND_LABELS)
    assert set(FIX_KINDS) >= autofix_module.FIT_KINDS
