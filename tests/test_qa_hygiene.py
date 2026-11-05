"""Metin temizliği, eksik etiket ve korunan ifade denetimleri; kontrol kodu sırası düzeltmesi."""

from __future__ import annotations

import pytest

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.autofix import FIX_KINDS, local_fix, plan_fixes, reorder_codes
from nxceviri.core.qa.checks import KIND_LABELS, SEVERITY_WARNING, run_checks
from nxceviri.core.translate.cleanup import (
    collapse_inner_spaces,
    drop_repeated_words,
    fix_extra_dots,
    missing_markup,
)
from nxceviri.core.translate.status import Status

HYGIENE = ("double_space", "repeated_word", "extra_dots")


def _row(source: str, translation: str, labels: tuple[str, ...] = (), status: str = Status.MACHINE) -> TranslationRow:
    return TranslationRow(1, "f", "k", source, translation, status, "", labels, None, "C/1")


def _kinds(row: TranslationRow) -> set[str]:
    return {i.kind for i in run_checks([row], "", "")}


def test_kinds_registered() -> None:
    for kind in (*HYGIENE, "protected", "missing_markup"):
        assert kind in KIND_LABELS
    assert KIND_LABELS["protected"] == "Korunan ifade"
    assert KIND_LABELS["missing_markup"] == "Eksik etiket"
    assert set(HYGIENE) <= set(FIX_KINDS)


def test_double_space_collapsed_inside_text_only() -> None:
    assert collapse_inner_spaces("Hello there", "Merhaba   dünya") == "Merhaba dünya"
    assert collapse_inner_spaces("Hello there", "  Merhaba dünya  ") == "  Merhaba dünya  "  # kenarlara dokunulmaz
    assert collapse_inner_spaces("Hello there", "Bir  ⟦1⟧  iki\n  üç") == "Bir  ⟦1⟧  iki\n  üç"  # kod ve satır sonu
    assert collapse_inner_spaces("A  B", "C  D") == "C  D"  # kaynakta da var


def test_repeated_word_removed() -> None:
    assert drop_repeated_words("Go on", "Devam et ve ve bitir") == "Devam et ve bitir"  # iki harfli işlev sözcüğü
    assert drop_repeated_words("Bread with milk", "Ekmek ile ile süt") == "Ekmek ile süt"
    assert drop_repeated_words("Ha ha ha", "ha ha ha") == "ha ha ha"  # 3+ tekrar kasıtlı
    assert drop_repeated_words("Ha ha", "Ha ha") == "Ha ha"  # 2 harfli / ses efekti
    assert (
        drop_repeated_words("Really really", "Gerçekten gerçekten") == "Gerçekten gerçekten"
    )  # kaynakta da tekrar var
    assert drop_repeated_words("Go on", "Ve\nve") == "Ve\nve"  # satır sonu ayırır


def test_extra_dots() -> None:
    assert fix_extra_dots("Wait", "Bekle.....") == "Bekle..."
    assert fix_extra_dots("Wait", "Bekle..") == "Bekle..."
    assert fix_extra_dots("Wait…", "Bekle....") == "Bekle…"
    assert fix_extra_dots("Wait...", "Bekle...") == "Bekle..."  # üç nokta doğal
    assert fix_extra_dots("Wait.....", "Bekle.....") == "Bekle....."  # kaynakta da var
    assert fix_extra_dots("Wait..", "Bekle..") == "Bekle.."
    assert fix_extra_dots("Wait", "Sürüm 1.2.3 ve e.g. bu") == "Sürüm 1.2.3 ve e.g. bu"


def test_hygiene_checks_flag_and_local_fix_repairs() -> None:
    row = _row("Go on and on and so", "Devam   et ile ile sonra..... bitti")
    assert set(HYGIENE) <= _kinds(row)
    for issue in run_checks([row], "", ""):
        if issue.kind in HYGIENE:
            assert issue.severity == SEVERITY_WARNING
    fixed = local_fix(row)
    assert fixed == "Devam et ile sonra... bitti"
    assert not set(HYGIENE) & _kinds(_row(row.source, fixed))
    plan = plan_fixes([row], run_checks([row], "", ""))
    assert plan.changes == [(1, "Devam et ile sonra... bitti")]


@pytest.mark.parametrize(
    ("source", "translation"),
    [
        ("Come on, let's go!", "Hadi, gidelim!"),
        ("I'll see you at the inn.", "Seni handa göreceğim."),
        ("Wait...", "Bekle..."),
        ("Really? Really?!", "Gerçekten mi? Gerçekten mi?!"),
        ("Very, very slowly.", "Çok çok yavaşça."),
        ("Slowly.", "Yavaş yavaş."),
        ("No, no, no!", "Hayır, hayır, hayır!"),
        ("Yes yes, I know.", "Evet evet, biliyorum."),
        ("Ha ha ha!", "Ha ha ha!"),
        ("Hmm... I see.", "Hmm... anlıyorum."),
        ("Wait… what?", "Bir dakika… ne?"),
        ("Go.\nNow.", "Git.\nŞimdi."),
        ("Ver. 1.2.3", "Sürüm 1.2.3"),
        ("Pick ⟦1⟧ up", "⟦1⟧ al"),
    ],
)
def test_natural_turkish_raises_no_hygiene_warning(source: str, translation: str) -> None:
    kinds = _kinds(_row(source, translation, ("Renk",)))
    assert not kinds & {*HYGIENE, "protected", "missing_markup"}


def test_hygiene_silent_when_source_has_same_pattern() -> None:
    assert not _kinds(_row("A  b ..... c", "X  y ..... z")) & set(HYGIENE)
    assert not _kinds(_row("Go go", "Git git")) & set(HYGIENE)


def test_missing_markup_helper() -> None:
    assert missing_markup("<i>Hi</i>", "Selam") == ["<i>", "</i>"]
    assert missing_markup("<i>Hi</i>", "<i>Selam</i>") == []
    assert missing_markup("[color=red]Hi[/color]", "Selam") == ["[color=red]", "[/color]"]
    assert missing_markup("Hello {player}", "Merhaba") == ["{player}"]
    assert missing_markup("<b>a</b> <b>b</b>", "<b>a</b> b") == ["<b>", "</b>"]  # sayım: ikisi de bir eksik
    assert missing_markup("[Laughs] Hi", "Selam") == []  # bilinen etiket değil; metin
    assert missing_markup("Plain", "Düz") == []


def test_missing_markup_check_is_warning_without_autofix() -> None:
    row = _row("<i>Hi</i> {name}", "Selam")
    found = [i for i in run_checks([row], "", "") if i.kind == "missing_markup"]
    assert len(found) == 1
    assert found[0].severity == SEVERITY_WARNING
    assert "<i>" in found[0].message
    assert "missing_markup" not in FIX_KINDS
    assert "missing_markup" not in _kinds(_row("<i>Hi</i>", "<i>Selam</i>"))


def test_protected_expression_missing() -> None:
    row = _row("Use Barrel_Cannon and DK_Coin now.", "Şimdi Varil Topu ve DK_Coin kullan.")
    found = [i for i in run_checks([row], "", "") if i.kind == "protected"]
    assert len(found) == 1
    assert found[0].severity == SEVERITY_WARNING
    assert "Barrel_Cannon" in found[0].message
    assert "DK_Coin" not in found[0].message
    assert "protected" not in FIX_KINDS
    kept = _row("Use Barrel_Cannon now.", "Şimdi Barrel_Cannon kullan.")
    assert "protected" not in _kinds(kept)


def test_protected_does_not_double_report_with_identifier() -> None:
    row = _row("Barrel_Cannon", "Varil Topu")
    kinds = _kinds(row)
    assert "identifier" in kinds
    assert "protected" not in kinds


def test_order_fix_swapped_and_in_order() -> None:
    labels = ("Renk", "Renk sonu", "Satır sonu", "Satır sonu", "Bekle")
    source = "⟦1⟧A⟦2⟧⟦3⟧B⟦4⟧⟦5⟧"
    assert reorder_codes(source, "⟦1⟧A⟦2⟧⟦4⟧B⟦3⟧⟦5⟧", labels) == source  # satır sonları yer değiştirmiş
    assert reorder_codes(source, source, labels) is None  # sıralı: dokunulmaz
    assert reorder_codes("a⟦1⟧b⟦2⟧", "x⟦2⟧y⟦1⟧", ("Satır sonu", "Satır sonu")) == "x⟦1⟧y⟦2⟧"
    # Farklı türdeki kodlar birbirinin yerine geçmez.
    assert reorder_codes("a⟦1⟧b⟦2⟧", "x⟦2⟧y⟦1⟧", ("Renk", "Satır sonu")) is None


def test_order_fix_moves_color_pairs_as_pairs() -> None:
    labels = ("Renk", "Renk sonu", "Renk", "Renk sonu")
    source = "⟦1⟧A⟦2⟧ ⟦3⟧B⟦4⟧"
    assert reorder_codes(source, "⟦3⟧B⟦4⟧ ⟦1⟧A⟦2⟧", labels) == "⟦1⟧B⟦2⟧ ⟦3⟧A⟦4⟧"
    # Çevirideki çift yapısı geçersizse (kapanış açılıştan önce) dokunulmaz.
    assert reorder_codes(source, "⟦2⟧B⟦1⟧ ⟦3⟧A⟦4⟧", labels) is None
    # Etiketleri farklı (farklı renk) çiftler birbirinin yerine geçmez.
    assert reorder_codes(source, "⟦3⟧B⟦4⟧ ⟦1⟧A⟦2⟧", ("Renk kırmızı", "Renk sonu", "Renk mavi", "Renk sonu")) is None
    # Kaynağın kendisi geçerli bir çift yapısı değilse dokunulmaz.
    assert reorder_codes("⟦2⟧A⟦1⟧", "⟦1⟧A⟦2⟧", ("Renk", "Renk sonu")) is None


def test_order_fix_never_swaps_variables() -> None:
    labels = ("Oyuncu adı", "Eşya adı", "Kişi adı")
    source = "⟦1⟧ gave ⟦2⟧ to ⟦3⟧"
    text = "⟦1⟧, ⟦3⟧ kişisine ⟦2⟧ verdi"  # doğru Türkçe sözdizimi; değişkenler başka koda çevrilmemeli
    assert reorder_codes(source, text, labels) is None
    error = _row(source, text, labels, Status.ERROR)
    plan = plan_fixes([error], run_checks([error], "", ""))
    assert plan.changes == []
    assert plan.unfixed == 1
    machine = _row(source, text, labels)
    assert local_fix(machine) == text


def test_order_fix_mixed_row() -> None:
    labels = ("Oyuncu adı", "Satır sonu", "Satır sonu", "Sayı 0001")
    source = "⟦1⟧ a⟦2⟧b⟦3⟧c ⟦4⟧"
    # Değişkenler yerinde, satır sonları yer değiştirmiş: yalnızca satır sonları düzelir.
    assert reorder_codes(source, "⟦1⟧ x⟦3⟧y⟦2⟧z ⟦4⟧", labels) == "⟦1⟧ x⟦2⟧y⟦3⟧z ⟦4⟧"
    # Değişkenlerin sırası da farklıysa hiçbir şeye dokunulmaz.
    assert reorder_codes(source, "⟦4⟧ x⟦3⟧y⟦2⟧z ⟦1⟧", labels) is None


def test_order_fix_leaves_different_multisets() -> None:
    labels = ("Satır sonu",) * 3
    assert reorder_codes("⟦1⟧a⟦2⟧b⟦3⟧", "⟦1⟧a⟦2⟧b⟦2⟧", labels) is None  # çoklu küme farklı
    assert reorder_codes("⟦1⟧a⟦2⟧", "⟦2⟧a", labels) is None  # eksik kod


def test_error_row_with_swapped_order_fixed_locally() -> None:
    labels = ("Renk", "Renk sonu", "Satır sonu", "Satır sonu", "Bekle")
    source = "⟦1⟧Bir⟦2⟧⟦3⟧iki⟦4⟧⟦5⟧"
    row = _row(source, "⟦1⟧Bir⟦2⟧⟦4⟧iki⟦3⟧⟦5⟧", labels, Status.ERROR)
    plan = plan_fixes([row], run_checks([row], "", ""))
    assert plan.changes == [(1, "⟦1⟧Bir⟦2⟧⟦3⟧iki⟦4⟧⟦5⟧")]


def test_error_row_with_missing_code_still_goes_to_model() -> None:
    row = _row("⟦1⟧Bir⟦2⟧", "⟦2⟧Bir", ("Renk", "Renk sonu"), Status.ERROR)
    plan = plan_fixes([row], run_checks([row], "", ""))
    assert plan.changes == []
    assert plan.unfixed == 1
