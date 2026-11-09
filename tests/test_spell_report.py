"""Yazım raporu: bilinmeyen sözcüklerin satır sayısıyla dökümü ve toplu sözcük değiştirme."""

from __future__ import annotations

from nxceviri.core.project import TranslationRow
from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.spell.report import WordUse, replace_word, unknown_words
from nxceviri.core.translate.status import Status

WORDS = ["merhaba", "oyun", "başlat", "ev", "yuva", "benim", "bu", "güzel", "bir", "çok"]


def _spell() -> SpellChecker:
    return SpellChecker(BloomFilter.build(WORDS, error_rate=0.0001))


def _row(i: int, source: str, translation: str) -> TranslationRow:
    return TranslationRow(i, "f", f"k{i}", source, translation, Status.MACHINE, "", (), None)


ROWS = [
    _row(1, "Hello", "merhaba vurp oyun"),
    _row(2, "Hello", "merhaba vurp çörk"),
    _row(3, "Hello", "benim vurp çörk blip"),
    _row(4, "Hello", "merhaba oyun"),
    _row(5, "Hello", ""),  # çevrilmemiş
    _row(6, "Hello", "Hello"),  # çeviri = kaynak: denetlenmez
]


def test_unknown_words_counts_rows_and_sorts_by_count_then_turkish_alphabet() -> None:
    found = unknown_words(ROWS, _spell())
    assert found == [
        WordUse("vurp", 3, (1, 2, 3)),
        WordUse("çörk", 2, (2, 3)),
        WordUse("blip", 1, (3,)),
    ]


def test_ties_use_turkish_alphabet_order() -> None:
    rows = [_row(1, "x", "çök cork dkl")]
    assert [w.word for w in unknown_words(rows, _spell())] == ["cork", "çök", "dkl"]


def test_each_word_counted_once_per_row() -> None:
    rows = [_row(1, "x", "vurp vurp vurp")]
    assert unknown_words(rows, _spell()) == [WordUse("vurp", 1, (1,))]


def test_ignored_and_extra_words_are_left_out() -> None:
    found = unknown_words(ROWS, _spell(), extra=frozenset({"vurp"}), ignored=["ÇÖRK"])
    assert [w.word for w in found] == ["blip"]


def test_no_unknown_words_gives_empty_list() -> None:
    assert unknown_words([_row(1, "x", "merhaba oyun")], _spell()) == []
    assert unknown_words([], _spell()) == []


def test_replace_word_respects_boundaries_and_case() -> None:
    assert replace_word("Ev güzel. EV güzel. ev güzel. Evet. Seven", "ev", "yuva") == (
        "Yuva güzel. YUVA güzel. yuva güzel. Evet. Seven"
    )


def test_replace_word_turkish_case_forms() -> None:
    assert replace_word("IŞIK ışık Işık", "ışık", "ilik") == "İLİK ilik İlik"


def test_replace_word_leaves_codes_untouched() -> None:
    assert replace_word("⟦1⟧ ev ⟦2⟧", "ev", "yuva") == "⟦1⟧ yuva ⟦2⟧"
    assert replace_word("⟦12⟧", "12", "x") == "⟦12⟧"


def test_replace_word_no_match_returns_same_text() -> None:
    assert replace_word("merhaba dünya", "ev", "yuva") == "merhaba dünya"
    assert replace_word("Eddie'ye ev", "eddie", "x") == "Eddie'ye ev"
