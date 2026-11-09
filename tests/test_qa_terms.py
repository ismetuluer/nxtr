"""Terim tutarsızlığı: kanonik çeviri seçimi ve çeviride kanonik çevirinin aranması."""

from __future__ import annotations

import time

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import run_checks
from nxceviri.core.qa.terms import canonical_terms, term_issues
from nxceviri.core.translate.providers.base import GlossaryTerm
from nxceviri.core.translate.status import Status


def _row(i: int, source: str, translation: str, status: str = Status.MACHINE) -> TranslationRow:
    return TranslationRow(i, "f", f"k{i}", source, translation, status, "", (), None)


def test_canonical_is_most_frequent_translation_of_standalone_line() -> None:
    rows = [
        _row(1, "Silver Pines", "Gümüş Çamlar"),
        _row(2, "Silver Pines", "Gümüş Çamlar"),
        _row(3, "Silver Pines", "Gümüş Çam"),
    ]
    assert canonical_terms(rows, []) == {"Silver Pines": "Gümüş Çamlar"}


def test_canonical_tie_prefers_approved() -> None:
    rows = [
        _row(1, "Old Mill", "Eski Değirmen"),
        _row(2, "Old Mill", "Kocamış Değirmen", Status.APPROVED),
    ]
    assert canonical_terms(rows, []) == {"Old Mill": "Kocamış Değirmen"}


def test_canonical_only_short_capitalised_standalone_translated_lines() -> None:
    rows = [
        _row(1, "start game", "oyunu başlat"),  # küçük harfle başlıyor
        _row(2, "One Two Three Four Five", "bir iki üç dört beş"),  # 5 sözcük
        _row(3, "Welcome back.", "Tekrar hoş geldin."),  # cümle
        _row(4, "Press ⟦1⟧", "⟦1⟧ tuşuna bas"),  # kod var
        _row(5, "Mara", ""),  # çevirisi yok
        _row(6, "Mara", "Mara"),
    ]
    assert canonical_terms(rows, []) == {"Mara": "Mara"}


def test_glossary_beats_rows_and_ignored_are_dropped() -> None:
    rows = [_row(1, "Silver Pines", "Gümüş Çam"), _row(2, "Mara", "Mara")]
    glossary = [GlossaryTerm("silver pines", "Gümüş Çamlar"), GlossaryTerm("Sheriff", "Şerif")]
    canon = canonical_terms(rows, glossary, ignored=["mara"])
    assert canon == {"silver pines": "Gümüş Çamlar", "Sheriff": "Şerif"}


def test_canonical_row_itself_gives_no_issue() -> None:
    rows = [_row(1, "Silver Pines", "Gümüş Çamlar")]
    assert term_issues(rows, {"Silver Pines": "Gümüş Çamlar"}) == []


def test_matching_ignores_suffix_case_breaks_codes_and_spaces() -> None:
    canon = {"Silver Pines": "Gümüş Çamlar"}
    ok = [
        _row(1, "Welcome to Silver Pines.", "Gümüş Çamlar'a hoş geldin."),
        _row(2, "Welcome to Silver Pines.", "Gümüş Çamlar’a hoş geldin."),
        _row(3, "The people of Silver Pines.", "Gümüş Çamlarda yaşayanlar."),
        _row(4, "Silver Pines is home.", "GÜMÜŞ ÇAMLAR yuvam."),
        _row(5, "Silver Pines is home.", "gümüş çamlar yuvam."),
        _row(6, "Go to Silver Pines.", "Gümüş\nÇamlar'a git."),
        _row(7, "Go to Silver Pines.", "Gümüş ⟦1⟧ Çamlar'a git."),
        _row(8, "Go to Silver Pines.", "Gümüş   Çamlar'a git."),
        _row(9, "SILVER PINES rocks", "Gümüş Çamlar harika"),
        _row(10, "In silver pines", "Gümüş Çamlar'daki ev"),
    ]
    assert term_issues(ok, canon) == []


def test_turkish_dotted_and_dotless_i() -> None:
    canon = {"Isle": "Işık Adası"}
    rows = [_row(1, "Go to the Isle.", "IŞIK ADASI'na git."), _row(2, "Go to the Isle.", "İşik adası")]
    found = term_issues(rows, canon)
    assert [i.row_id for i in found] == [2]  # İ→i, I→ı: "işik" ≠ "ışık"


def test_different_translation_reports_with_count() -> None:
    canon = {"Silver Pines": "Gümüş Çamlar"}
    rows = [_row(i, "See Silver Pines.", "Gümüş Çamlar'ı gör.") for i in range(14)]
    rows.append(_row(100, "Welcome to Silver Pines.", "Gümüş Çam'a hoş geldin."))
    rows.append(_row(101, "Welcome to Silver Pines.", "Silver Pines'a hoş geldin."))
    found = term_issues(rows, canon)
    assert [i.row_id for i in found] == [100, 101]
    first = found[0]
    assert (first.kind, first.severity) == ("term", "warning")
    assert first.message == "‘Silver Pines’ burada çevrilmemiş ya da farklı çevrilmiş; 14 satırda ‘Gümüş Çamlar’."


def test_prefix_of_a_longer_word_is_not_a_match() -> None:
    canon = {"Home": "Ev"}
    rows = [_row(1, "Go Home now", "Evcilleştirilmiş olarak git")]
    assert [i.row_id for i in term_issues(rows, canon)] == [1]


def test_phrase_needs_word_boundary_in_source_and_untranslated_rows_skipped() -> None:
    canon = {"Mill": "Değirmen"}
    rows = [
        _row(1, "The Millennium", "Binyıl"),  # sözcük sınırı yok
        _row(2, "Old Mill.", ""),  # çevrilmemiş
        _row(3, "Old Mill.", "Eski değirmen."),
        _row(4, "Old. See Mill", "Eski Mill"),
    ]
    assert [i.row_id for i in term_issues(rows, canon)] == [4]


def test_multi_word_phrase_needs_whitespace_between_words_in_source() -> None:
    canon = {"Silver Pines": "Gümüş Çamlar"}
    rows = [
        _row(1, "Go to Silver\nPines now", "Bilinmeyen"),
        _row(2, "Go to Silver ⟦1⟧ Pines now", "Bilinmeyen"),
        _row(3, "Go to Silver. Pines now", "Bilinmeyen"),
    ]
    assert [i.row_id for i in term_issues(rows, canon)] == [1, 2]


def test_run_checks_includes_term_issues_and_respects_ignored() -> None:
    rows = [
        _row(1, "Silver Pines", "Gümüş Çamlar"),
        _row(3, "Silver Pines", "Gümüş Çamlar"),
        _row(2, "Welcome to Silver Pines.", "Gümüş Çam'a hoş geldin."),
    ]
    kinds = [i.kind for i in run_checks(rows, "", "")]
    assert kinds.count("term") == 1
    assert [i.kind for i in run_checks(rows, "", "", ignored_terms=["silver pines"])].count("term") == 0
    glossary = [GlossaryTerm("Silver Pines", "Gümüş Çam")]
    assert [i.kind for i in run_checks(rows, "", "", glossary)].count("term") == 0  # sözlük "Gümüş Çam" der


def test_term_issues_is_fast_on_50k_rows_and_2k_terms() -> None:
    canon = {f"Place{n} Hall": f"Yer{n} Salonu" for n in range(2000)}
    rows = [
        _row(i, f"Let us go to Place{i % 10000} Hall right now, my friend.", f"Şimdi Yer{i % 10000} Salonu'na gidelim.")
        for i in range(50_000)
    ]
    start = time.perf_counter()
    found = term_issues(rows, canon)
    assert time.perf_counter() - start < 2.0
    assert found == []


# --- Ö4: yanlış pozitifleri azaltan kurallar ---------------------------------------------------------


def test_o4_tek_satirda_gecen_ifade_kanonik_sayilmaz() -> None:
    rows = [_row(1, "Spear", "Mızrak"), _row(2, "Iron Sword", "Demir Kılıç"), _row(3, "Iron Sword", "Demir Kılıç")]
    assert canonical_terms(rows, []) == {"Iron Sword": "Demir Kılıç"}


def test_o4_ortak_arayuz_sozcukleri_cumle_icinde_uyari_uretmez() -> None:
    rows = [
        _row(1, "No", "Hayır"),
        _row(2, "No", "Hayır"),
        _row(3, "Yes", "Evet"),
        _row(4, "Yes", "Evet"),
        _row(5, "Back", "Geri"),
        _row(6, "Back", "Geri"),
        _row(7, "There is no way back.", "Çıkış yok."),
        _row(8, "Go back to the town.", "Kasabaya dön."),
        _row(9, "Yes, I know.", "Biliyorum."),
        _row(10, "Say Yes to the king.", "Krala olur de."),
    ]
    canon = canonical_terms(rows, [])
    assert canon == {"No": "Hayır", "Yes": "Evet", "Back": "Geri"}
    # küçük harfli "no/back", cümle başındaki "Yes" sayılmaz; yalnızca cümle ortasında büyük harfli geçiş denetlenir
    assert [i.row_id for i in term_issues(rows, canon)] == [10]


def test_o4_cumle_basi_eslesme_tek_sozcukte_sayilmaz_cok_sozcukte_sayilir() -> None:
    canon = {"Silver Pines": "Gümüş Çamlar", "Mara": "Mara"}
    rows = [
        _row(1, "Silver Pines is quiet.", "Sessiz bir yer."),
        _row(2, "Hi. Mara is here.", "Merhaba. Orada biri var."),
        _row(3, "Hi Mara is here.", "Merhaba. Orada biri var."),
    ]
    assert [i.row_id for i in term_issues(rows, canon)] == [1, 3]


def test_o4_kaynakta_kucuk_harfli_gecis_buyuk_harfli_ifadeyle_eslesmez() -> None:
    canon = {"Open": "Aç"}
    rows = [_row(1, "Please open the door.", "Kapıyı lütfen."), _row(2, "Please Open the door.", "Kapıyı lütfen.")]
    assert [i.row_id for i in term_issues(rows, canon)] == [2]


def test_o4_unsuz_yumusamasi_kabul_edilir() -> None:
    canon = {"Iron Sword": "Demir Kılıç", "Spear": "Mızrak"}
    ok = [
        _row(1, "You found an Iron Sword!", "Bir Demir Kılıcı buldun!"),
        _row(2, "Take the Spear.", "Mızrağı al."),
        _row(3, "Use the Spear well.", "Mızrağa dikkat et."),
    ]
    assert term_issues(ok, canon) == []
    # kök bozuksa yine uyarı verilir
    assert [i.row_id for i in term_issues([_row(4, "Take the Spear.", "Mızrabı al.")], canon)] == [4]


def test_o4_nk_ng_yumusamasi() -> None:
    canon = {"Bank": "Denk"}
    ok = [_row(1, "See the Bank now.", "Dengi gör.")]
    assert term_issues(ok, canon) == []


def test_o4_yumusama_ek_yoksa_gecerli_degildir() -> None:
    canon = {"Spear": "Mızrak"}
    assert [i.row_id for i in term_issues([_row(1, "Take the Spear.", "Mızrağ al.")], canon)] == [1]
