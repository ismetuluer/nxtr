"""Yazım önerisi: Türkçe harf değişimi (iki yön), tek düzenleme, harf büyüklüğü, sınırlar ve güvenli sınıf."""

from __future__ import annotations

import itertools

import pytest

from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.spell.suggest import MAX_SUGGESTIONS, suggest, suggestions

DICT = [
    "buradasın",
    "şakırdayarak",
    "şapkadır",
    "şırıl",
    "şımartılmış",
    "işte",
    "kış",
    "kis",
    "kitap",
    "kalen",
    "kaler",
    "kales",
    "kalef",
    "kalem",
    "şapkadıra",
    "şapka",
    "gelişigüzelin",
    "pirinçler",
    "pirinç",
    "gül",
    *("".join(p) for p in itertools.product("sş", repeat=4) if "".join(p) != "ssşs"),
    "şğüö",
]


def _bloom(words: list[str]) -> BloomFilter:
    """Küçük süzgeçte çift özetleme çevrimleri kısalır (uydurma isabet); dolgu sözcükleri boyutu büyütür."""
    return BloomFilter.build([*words, *(f"x{n}q" for n in range(5000))], error_rate=1e-9)


@pytest.fixture(scope="module")
def spell() -> SpellChecker:
    return SpellChecker(_bloom(DICT))


def test_turkish_letter_to_ascii_and_back(spell: SpellChecker) -> None:
    assert suggest("buradaşın", spell, frozenset()) == ["buradasın"]  # ş → s
    assert suggest("şakirdayarak", spell, frozenset()) == ["şakırdayarak"]  # i → ı
    assert suggest("şapkadir", spell, frozenset()) == ["şapkadır"]
    assert suggest("şiril", spell, frozenset()) == ["şırıl"]
    assert suggest("şımartilmiş", spell, frozenset()) == ["şımartılmış"]
    assert suggest("sapkadir", spell, frozenset()) == ["şapkadır"]  # ASCII → Türkçe, iki harf birden


def test_known_word_has_no_suggestion(spell: SpellChecker) -> None:
    assert suggest("şapkadır", spell, frozenset()) == []


def test_case_pattern_is_kept(spell: SpellChecker) -> None:
    assert suggest("Buradaşın", spell, frozenset()) == ["Buradasın"]
    assert suggest("Iste", spell, frozenset()) == ["İşte"]  # I → İ, s → ş
    assert suggest("İste", spell, frozenset()) == ["İşte"]
    assert suggest("Şiril", spell, frozenset()) == ["Şırıl"]


def test_abbreviations_and_non_words_get_no_suggestion(spell: SpellChecker) -> None:
    assert suggest("BURADAŞIN", spell, frozenset()) == []  # tamamı büyük: kısaltma
    assert suggest("hihihi", spell, frozenset()) == []  # ses efekti
    assert suggest("buradaşın2", spell, frozenset()) == []
    assert suggest("buradaşın-x", spell, frozenset()) == []
    assert suggest("", spell, frozenset()) == []


def test_extra_words_count_as_dictionary(spell: SpellChecker) -> None:
    assert suggest("sakirti", spell, frozenset()) == []
    assert suggest("sakirti", spell, frozenset({"şakırtı"})) == ["şakırtı"]


def test_several_letter_candidates_are_all_listed(spell: SpellChecker) -> None:
    result = suggestions("kıs", spell, frozenset())  # "kis" ve "kış" ikisi de sözlükte
    assert sorted(result.words) == ["kis", "kış"]
    assert result.letters
    assert not result.safe  # birden çok: toplu düzeltmeye girmez


def test_single_letter_candidate_is_safe_for_bulk_fix(spell: SpellChecker) -> None:
    result = suggestions("buradaşın", spell, frozenset())
    assert result.letters
    assert result.safe


def test_at_most_five_suggestions_fewest_swaps_first(spell: SpellChecker) -> None:
    result = suggest("ssşs", spell, frozenset())  # 14 sözlük adayı var
    assert len(result) == MAX_SUGGESTIONS
    assert all(sum(a != b for a, b in zip(w, "ssşs", strict=True)) == 1 for w in result[:4])  # tek harf önce
    assert all(len(w) == 4 for w in result)


def test_edit_distance_only_when_no_letter_candidate(spell: SpellChecker) -> None:
    result = suggestions("kitapp", spell, frozenset())  # fazla harf
    assert result.words == ("kitap",)
    assert not result.letters
    assert not result.safe  # tek düzenleme toplu düzeltmeye girmez
    assert suggest("kiatp", spell, frozenset()) == ["kitap"]  # yer değiştirmiş harf
    # eksik ve değişmiş harf aranmaz: aday sayısı çok, süzgecin uydurma isabeti gerçeğinden çok olur
    assert suggest("kitp", spell, frozenset()) == []
    assert suggest("kitaq", spell, frozenset()) == []


def test_letter_candidates_win_over_edit_distance(spell: SpellChecker) -> None:
    # "şapkadir": hem "şapkadır" (harf) hem "şapkadıra" (iki düzenleme) var; yalnızca harf sınıfı gelir
    assert suggest("şapkadir", spell, frozenset()) == ["şapkadır"]
    only_edit = suggestions("şapkadıraa", spell, frozenset())
    assert only_edit.words == ("şapkadıra",)
    assert not only_edit.letters


def test_edit_distance_skipped_when_too_many_neighbours() -> None:
    crowded = SpellChecker(_bloom(["acde", "abde", "abce", "abcd"]))
    assert suggest("abcde", crowded, frozenset()) == []  # dört komşu: belirsiz ya da gürültü


def test_edit_distance_keeps_first_letter_and_needs_four_letters(spell: SpellChecker) -> None:
    assert suggest("itap", spell, frozenset()) == []  # baştaki eksik harf önerilmez
    assert suggest("gül", spell, frozenset()) == []  # bilinen
    assert suggest("güx", spell, frozenset()) == []  # üç harften kısa-kısıt: düzenleme önerisi yok


def test_letter_swaps_are_limited(spell: SpellChecker) -> None:
    assert suggest("sguo", spell, frozenset()) == []  # "ğüşö" dört harf değişimi: sınırın ötesinde
    long_word = "scgosuiscgosui"  # 14 değişebilir konum
    bloom = _bloom(["scgösuiscgoşui"])
    assert suggest(long_word, SpellChecker(bloom), frozenset()) == []


def test_tried_candidate_count_is_reported(spell: SpellChecker) -> None:
    result = suggestions("buradaşın", spell, frozenset())
    assert 0 < result.tried <= 300


def test_bulk_safety_needs_few_candidates_or_a_known_root() -> None:
    word = "gelisiguzelin"  # 7 değişebilir harf: aday sayısı yüksek
    with_root = SpellChecker(_bloom(["gelişigüzelin", "gelişigüzel"]))
    result = suggestions(word, with_root, frozenset())
    assert result.words == ("gelişigüzelin",)
    assert result.tried > 7
    assert result.rooted
    assert result.safe
    no_root = SpellChecker(_bloom(["gelişigüzelin"]))
    result = suggestions(word, no_root, frozenset())
    assert result.words == ("gelişigüzelin",)  # öneri yine görünür
    assert not result.rooted
    assert not result.safe  # ama toplu düzeltmeye girmez


def test_long_edit_candidate_needs_a_known_root(spell: SpellChecker) -> None:
    assert suggest("pirinçlerr", spell, frozenset()) == ["pirinçler"]  # kök "pirinç" sözlükte
    lone = SpellChecker(_bloom(["pirinçler"]))
    assert suggest("pirinçlerr", lone, frozenset()) == []  # uzun aday, kökü yok: uydurma isabet olabilir


def test_doubled_letter_is_suggested(spell: SpellChecker) -> None:
    assert suggest("kalemm", spell, frozenset()) == ["kalem"]
