"""Yazım raporu: bilinmeyen sözcüklerin satır sayısıyla dökümü ve toplu sözcük değiştirme."""

from __future__ import annotations

from collections.abc import Collection

from nxceviri.core.project import TranslationRow
from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.spell.checker import SpellChecker
from nxceviri.core.spell.report import UnknownWordCache, WordUse, replace_unknown, unknown_words
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


def test_replace_unknown_respects_boundaries_and_case() -> None:
    assert replace_unknown(
        "Vurp güzel. vurp güzel. Vurpa. vurpa", "Hi", _spell(), frozenset(), word="vurp", new="yuva"
    ) == ("Yuva güzel. yuva güzel. Vurpa. vurpa")


def test_replace_unknown_turkish_case_forms() -> None:
    assert replace_unknown("Ilık güzel. ılık güzel.", "Hi", _spell(), frozenset(), word="ılık", new="ilik") == (
        "İlik güzel. ilik güzel."
    )


def test_replace_unknown_leaves_codes_and_apostrophe_words_untouched() -> None:
    spell = _spell()
    assert replace_unknown("⟦1⟧ vurp ⟦2⟧", "Hi", spell, frozenset(), word="vurp", new="yuva") == "⟦1⟧ yuva ⟦2⟧"
    assert replace_unknown("⟦12⟧", "Hi", spell, frozenset(), word="12", new="x") == "⟦12⟧"
    assert replace_unknown("Eddie'ye vurp", "Hi", spell, frozenset(), word="eddie", new="x") == "Eddie'ye vurp"


def test_replace_unknown_no_match_returns_same_text() -> None:
    assert replace_unknown("merhaba dünya", "Hi", _spell(), frozenset(), word="ev", new="yuva") == "merhaba dünya"


# --- Ö5: yalnızca bilinmeyen sözcük olarak bulunan geçişler değiştirilir --------------------------


def test_replace_unknown_skips_source_words_all_caps_and_proper_names() -> None:
    spell = _spell()
    text = "Oyun başlatt. BAŞLATT burada. Mara başlatt dedi. Sonra başlatt!"
    # "BAŞLATT" tamamı büyük, "Mara" özel ad: listelenen geçişler yalnızca küçük harfli üç tanesidir
    assert replace_unknown(text, "Start the game", spell, frozenset(), word="başlatt", new="başla") == (
        "Oyun başla. BAŞLATT burada. Mara başla dedi. Sonra başla!"
    )


def test_replace_unknown_leaves_row_alone_when_word_is_in_source_or_copy() -> None:
    spell = _spell()
    assert replace_unknown("başlatt oyun", "Başlatt", spell, frozenset(), word="başlatt", new="başla") == "başlatt oyun"
    assert replace_unknown("başlatt", "Başlatt", spell, frozenset(), word="başlatt", new="başla") == "başlatt"


def test_replace_unknown_count_equals_word_use_count() -> None:
    spell = _spell()
    rows = [
        TranslationRow(1, "f", "a", "Start", "Oyun başlatt", "machine", "", (), None),
        TranslationRow(2, "f", "b", "Başlatt", "Başlatt oyun", "machine", "", (), None),
        TranslationRow(3, "f", "c", "Begin", "başlatt", "machine", "", (), None),
        TranslationRow(4, "f", "d", "Play", "Sonra başlatt!", "machine", "", (), None),
    ]
    use = next(u for u in unknown_words(rows, spell) if u.word == "başlatt")
    changed = [
        r.id
        for r in rows
        if replace_unknown(r.translation, r.source, spell, frozenset(), word="başlatt", new="x") != r.translation
    ]
    assert changed == list(use.row_ids)


# --- Ö7: artımlı önbellek -------------------------------------------------------------------------


class _CountingSpell(SpellChecker):
    calls = 0

    def unknown_words(self, text: str, source: str = "", extra: Collection[str] = frozenset()) -> list[str]:
        type(self).calls += 1
        return super().unknown_words(text, source, extra)


def test_cache_rescans_only_changed_rows_and_matches_unknown_words() -> None:
    spell = _CountingSpell(BloomFilter.build(WORDS, error_rate=0.0001))
    cache = UnknownWordCache()
    assert len(cache.stale(ROWS)) == len(ROWS)
    cache.store(cache.scan(ROWS, spell, frozenset()))
    assert cache.words(ROWS) == unknown_words(ROWS, spell)
    assert cache.stale(ROWS) == []
    _CountingSpell.calls = 0
    changed = [*ROWS[:3], _row(4, "Hello", "merhaba blip"), *ROWS[4:]]
    stale = cache.stale(changed)
    assert [r.id for r in stale] == [4]
    cache.store(cache.scan(stale, spell, frozenset()))
    assert _CountingSpell.calls == 1
    assert [w.word for w in cache.words(changed)] == ["vurp", "blip", "çörk"]
    assert cache.words(changed, ignored=["vurp"])[0].word == "blip"
