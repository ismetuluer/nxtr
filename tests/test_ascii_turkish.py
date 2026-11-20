"""ASCII'ye çevrilmiş Türkçe metnin harf onarımı (ç ğ ı İ ö ş ü); sözlük destekli, belirsizlikte dokunmaz."""

from __future__ import annotations

from dataclasses import replace

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.asciitr import apply_choice, repair_ascii_turkish
from nxceviri.core.qa.autofix import FIX_KINDS, local_fix, plan_fixes
from nxceviri.core.qa.checks import KIND_LABELS, check_row
from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.spell.loader import load_spell_checker
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.status import Status
from tests.perf import best_time

WORDS = [
    "teşekkür",
    "ederim",
    "işte",
    "burada",
    "kitap",
    "mı",
    "mi",
    "mu",
    "mü",
    "sürat",
    "surat",
    "sakin",
    "sakın",
    "göz",
    "çok",
    "güzel",
    "ev",
    "sen",
    "bu",
    "yürü",
]
SPELL = SpellChecker(BloomFilter.build(WORDS, error_rate=0.00001))
TURKISH = "çğıİöşüÇĞÖŞÜ"


def _fix(text: str, source: str = "Thanks") -> str:
    return repair_ascii_turkish(source, text, SPELL).text


def _row(source: str, text: str) -> TranslationRow:
    return TranslationRow(1, "f", "k", source, text, Status.MACHINE, "", (), None)


def test_letters_are_restored() -> None:
    assert _fix("tesekkur ederim") == "teşekkür ederim"
    assert _fix("cok guzel") == "çok güzel"


def test_case_is_kept_per_letter_with_turkish_rules() -> None:
    assert _fix("Iste burada") == "İşte burada"  # cümle başındaki I → İ, "işte" değil
    assert _fix("ISTE") == "İŞTE"
    assert _fix("Tesekkur ederim") == "Teşekkür ederim"
    assert _fix("TESEKKUR EDERIM") == "TEŞEKKÜR EDERİM"


def test_ambiguous_word_is_left_and_reported() -> None:
    homograph = SpellChecker(BloomFilter.build(["sürat", "şurat", "burada"], error_rate=0.00001))
    result = repair_ascii_turkish("Hi", "surat burada", homograph)  # iki aday da sözlükte
    assert result.text == "surat burada"
    assert result.ambiguous == ("surat",)
    unique = SpellChecker(BloomFilter.build(["sakın", "burada"], error_rate=0.00001))
    assert repair_ascii_turkish("Hi", "sakin burada", unique).text == "sakın burada"
    assert repair_ascii_turkish("Hi", "xyzzy burada", unique).ambiguous == ()  # aday yok: sessiz kalır


def test_word_from_source_is_untouched() -> None:
    assert repair_ascii_turkish("Say tesekkur now", "tesekkur ederim", SPELL).text == "tesekkur ederim"


def test_codes_are_kept() -> None:
    text = "⟦1⟧tesekkur⟦2⟧ ederim"
    fixed = _fix(text)
    assert fixed == "⟦1⟧teşekkür⟦2⟧ ederim"
    assert placeholders.tokens_in(fixed) == placeholders.tokens_in(text)


def test_question_particle_follows_vowel_harmony() -> None:
    assert _fix("Kitap mi?") == "Kitap mı?"
    assert _fix("Sen mu?") == "Sen mi?"
    assert _fix("Ev mi?") == "Ev mi?"
    assert _fix("Göz mi?") == "Göz mü?"
    assert _fix("KITAP MI") == "KİTAP MI"
    assert _fix("Kitap ⟦1⟧ mi") == "Kitap ⟦1⟧ mi"  # önceki parça kod: dokunulmaz
    assert _fix("3 mi") == "3 mi"
    assert _fix("Hye Mi") == "Hye Mi"  # cümle ortasında büyük harfli: özel ad


def test_repair_is_idempotent_and_never_removes_turkish_letters() -> None:
    for text in ("tesekkur ederim", "Iste burada", "ISTE", "Kitap mi?", "surat çok güzel"):
        once = _fix(text)
        assert _fix(once) == once
        assert sum(c in TURKISH for c in once) >= sum(c in TURKISH for c in text)


def test_check_row_reports_and_fix_applies() -> None:
    row = _row("Thanks", "tesekkur ederim")
    issues = [i for i in check_row(row, "", "", spell=SPELL) if i.kind == "ascii_turkish"]
    assert len(issues) == 1
    assert "tesekkur → teşekkür" in issues[0].message
    assert "ascii_turkish" in KIND_LABELS
    assert "ascii_turkish" in FIX_KINDS
    assert local_fix(row, kinds=["ascii_turkish"], spell=SPELL) == "teşekkür ederim"
    assert local_fix(row, kinds=["spaces"], spell=SPELL) == "tesekkur ederim"  # yalnızca seçilen tür
    clean = _row("Thanks", "teşekkür ederim")
    assert not [i for i in check_row(clean, "", "", spell=SPELL) if i.kind == "ascii_turkish"]


def test_plan_fixes_uses_spell_and_reports_ambiguous_as_review() -> None:
    homograph = SpellChecker(BloomFilter.build(["sürat", "şurat", "burada"], error_rate=0.00001))
    fixable = _row("Thanks", "tesekkur ederim")
    review = replace(_row("Hi", "surat burada"), id=2)
    issues = check_row(fixable, "", "", spell=SPELL)
    plan = plan_fixes([fixable], issues, ["ascii_turkish"], spell=SPELL)
    assert plan.changes == [(1, "teşekkür ederim")]
    issues = check_row(review, "", "", spell=homograph)
    ambiguous = [i for i in issues if i.kind == "ascii_turkish"]
    assert ambiguous
    assert "İnceleme gerekli: surat" in ambiguous[0].message
    assert plan_fixes([review], issues, ["ascii_turkish"], spell=homograph).unfixed == 1


def test_five_thousand_rows_check_quickly() -> None:
    rows = [_row("Thanks", f"cok guzel kitap {i % 7} xyzzy Iste") for i in range(5000)]

    def check_all() -> None:
        for row in rows:
            check_row(row, "", "", spell=SPELL)

    assert best_time(lambda: check_all, under=3.0) < 3.0


def test_real_dictionary_smoke() -> None:
    spell = load_spell_checker()
    assert spell is not None
    assert repair_ascii_turkish("Hi", "Tesekkur ederim", spell).text == "Teşekkür ederim"
    assert repair_ascii_turkish("Hi", "bu degil icin", spell).text == "bu değil için"
    homograph = repair_ascii_turkish("Hi", "cok", spell)  # çok / çök: sözlükte iki aday
    assert homograph.text == "cok"
    assert homograph.ambiguous == ("cok",)


def test_hyphenated_word_parts_are_judged_separately() -> None:
    spell = SpellChecker(BloomFilter.build(["hızlı", "mün", "mermi"], error_rate=0.00001))
    # "mun" orijinalde de geçer: dokunulmaz; öteki parça kendi kuralıyla düzelir.
    assert repair_ascii_turkish("A mun shot", "mun-hizli mermi", spell).text == "mun-hızlı mermi"
    # Orijinalde geçmiyorsa "mun" kendi başına aday arar (burada tek aday: mün).
    assert repair_ascii_turkish("Hi", "mun-hizli mermi", spell).text == "mün-hızlı mermi"
    assert repair_ascii_turkish("Hi", "mermi-hizli", spell).text == "mermi-hızlı"
    assert (
        repair_ascii_turkish("Hi", "Bu Mun-hizli", spell).text == "Bu Mun-hizli"
    )  # cümle ortasında büyük harf: özel ad


def test_choices_carry_candidates_for_ambiguous_words() -> None:
    homograph = SpellChecker(BloomFilter.build(["sürat", "şurat", "burada"], error_rate=0.00001))
    result = repair_ascii_turkish("Hi", "Iste surat-burada", homograph)
    assert result.choices == (("surat", ("sürat", "şurat")),)
    assert result.ambiguous == ("surat",)


def test_apply_choice_replaces_word_keeping_case_pattern() -> None:
    assert apply_choice("Hi", "surat. Surat SURAT surat-x", "surat", "sürat") == "sürat. Sürat SÜRAT sürat-x"
    assert apply_choice("Hi", "Isik ISIK", "isik", "ışık") == "Işık IŞIK"
    assert apply_choice("Hi", "isik", "isik", "ışık") == "ışık"


def test_apply_choice_skips_source_words_mid_sentence_names_and_partial_matches() -> None:
    assert apply_choice("A surat", "surat ve surat", "surat", "sürat") == "surat ve surat"  # orijinalde geçiyor
    assert apply_choice("Hi", "Ali Surat gitti", "surat", "sürat") == "Ali Surat gitti"  # özel ad
    assert apply_choice("Hi", "Surat gitti", "surat", "sürat") == "Sürat gitti"  # cümle başı
    assert apply_choice("Hi", "⟦1⟧surat⟦2⟧ suratlar", "surat", "sürat") == "⟦1⟧sürat⟦2⟧ suratlar"  # tam sözcük


def test_ascii_mistakes_listed_words_are_repaired_even_if_dictionary_knows_them() -> None:
    # `simdi` paketli sözlükte geçerli sayılıyor; yaygın yazım hatası listesinde olduğu için onarılır.
    spell = load_spell_checker()
    assert spell is not None
    assert spell.is_known("simdi")
    assert repair_ascii_turkish("Now", "simdi gel", spell).text == "şimdi gel"
    assert repair_ascii_turkish("Now", "Simdi gel", spell).text == "Şimdi gel"
    assert repair_ascii_turkish("Now", "SIMDI", spell).text == "ŞİMDİ"


def test_ascii_mistakes_respect_source_extra_and_real_words() -> None:
    spell = load_spell_checker()
    assert spell is not None
    # Orijinalde aynen geçen sözcüğe (özel ad) ve oyun sözlüğündekine dokunulmaz.
    assert repair_ascii_turkish("simdi", "simdi gel", spell).text == "simdi gel"
    assert repair_ascii_turkish("Now", "simdi gel", spell, extra={"simdi"}).text == "simdi gel"
    # Listede olmayan gerçek Türkçe sözcük (sürat/surat gibi) olduğu gibi kalır.
    assert repair_ascii_turkish("Hi", "surat", spell).text == "surat"


def test_english_function_words_are_never_unknown() -> None:
    checker = SpellChecker(BloomFilter.build(["burada", "merhaba"], error_rate=0.00001))
    checker.flag_copied = True
    text = "You the vs. of OK to and or is it a an burada"
    assert checker.unknown_words(text, text) == []


def test_real_untranslated_word_still_flagged_with_flag_copied() -> None:
    checker = SpellChecker(BloomFilter.build(["burada", "merhaba"], error_rate=0.00001))
    checker.flag_copied = True
    assert checker.unknown_words("you merhaba sword", "you hello sword") == ["sword"]
