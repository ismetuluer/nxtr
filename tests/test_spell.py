"""Türkçe yazım denetimi: Bloom süzgeci, sözcük ayıklama, kullanıcı sözlüğü ve QA bulgusu."""

from __future__ import annotations

from pathlib import Path

import pytest

from nxceviri.core.project import TranslationRow
from nxceviri.core.qa.checks import KIND_LABELS, SEVERITY_INFO, check_row, run_checks
from nxceviri.core.spell.bloom import BloomFilter
from nxceviri.core.spell.checker import SpellChecker, turkish_lower, words_of
from nxceviri.core.spell.userdict import UserDictionary
from nxceviri.core.translate.status import Status

WORDS = ["merhaba", "kitap", "kitaplarımızdan", "çocuk", "ışık", "iyi", "oyun", "başlat", "yükle"]


def _checker(extra: list[str] | None = None) -> SpellChecker:
    return SpellChecker(BloomFilter.build(WORDS, error_rate=0.0001))


def test_bloom_round_trip_has_no_false_negatives(tmp_path: Path) -> None:
    words = [f"sözcük{i}" for i in range(5000)]
    bloom = BloomFilter.build(words, error_rate=0.001)
    assert all(w in bloom for w in words)
    path = tmp_path / "t.bloom"
    path.write_bytes(bloom.to_bytes())
    again = BloomFilter.from_bytes(path.read_bytes())
    assert all(w in again for w in words)
    wrong = sum(f"yanlış{i}" in again for i in range(20000))
    assert wrong < 100  # hedef 0,001 → 20 000 sınamada ~20; geniş pay


def test_bloom_rejects_corrupt_files() -> None:
    with pytest.raises(ValueError, match="süzgeci"):
        BloomFilter.from_bytes(b"bozuk")


def test_turkish_lower_handles_dotted_and_dotless_i() -> None:
    assert turkish_lower("ISIK") == "ısık"
    assert turkish_lower("İSTANBUL") == "istanbul"
    assert turkish_lower("Işık") == "ışık"


def test_words_of_skips_codes_digits_and_apostrophe_names() -> None:
    text = "Merhaba ⟦1⟧ 12 kitaplarımızdan Eddie'ye x-ray 3D"
    assert [w for w, _ in words_of(text)] == ["Merhaba", "kitaplarımızdan", "x-ray"]


def test_is_known_uses_filter_user_words_and_extra() -> None:
    spell = _checker()
    assert spell.is_known("KİTAPLARIMIZDAN")
    assert spell.is_known("Işık")
    assert not spell.is_known("kitapplarımızdan")
    spell.add_user_words(["Elara"])
    assert spell.is_known("elara")
    assert spell.is_known("Silver", extra={"silver"})


def test_unknown_words_ignores_names_taken_from_the_source() -> None:
    spell = _checker()
    found = spell.unknown_words(
        "Silver Pines'a merhaba, oyun başlatt", source="Welcome to Silver Pines. Start the game"
    )
    assert found == ["başlatt"]  # "Silver" kaynaktan, "Pines'a" kesme işaretinden dolayı sayılmaz
    assert spell.unknown_words("Silver ışığı", source="Silver light") == ["ışığı"]


def test_unknown_words_skips_abbreviations_and_mid_sentence_names() -> None:
    spell = _checker()
    assert spell.unknown_words("Merhaba HP ve Mara", source="") == ["ve"]  # HP kısaltma, Mara cümle ortasında özel ad
    assert spell.unknown_words("Mara geldi", source="") == ["mara", "geldi"]  # cümle başı denetlenir
    assert spell.unknown_words("Evet. Mara iyi", source="") == ["evet", "mara"]


def test_unknown_words_skips_sound_effects() -> None:
    spell = _checker()
    assert spell.unknown_words("Hihihi, ehehehe ve ahhh başlatt", source="") == ["ve", "başlatt"]


def test_user_dictionary_persists_and_dedupes(tmp_path: Path) -> None:
    path = tmp_path / "sozluk" / "yazim.txt"
    user = UserDictionary(path)
    assert user.words() == frozenset()
    assert user.add(["Elara", "elara", "  Mara ", ""]) == 2
    assert user.add(["Mara"]) == 0
    assert UserDictionary(path).words() == frozenset({"elara", "mara"})
    assert user.remove(["mara"]) == 1
    assert UserDictionary(path).words() == frozenset({"elara"})


def test_user_dictionary_survives_missing_or_unreadable_file(tmp_path: Path) -> None:
    path = tmp_path / "yazim.txt"
    path.write_bytes(b"\xff\xfe bozuk bayt")
    assert UserDictionary(path).words() == frozenset()  # okunamayan dosya sözlüğü boş sayar, çökmez


def _row(source: str, translation: str) -> TranslationRow:
    return TranslationRow(1, "f", "k1", source, translation, Status.MACHINE, "", (), None, "C/1")


def test_check_row_reports_misspelled_words() -> None:
    spell = _checker()
    issues = check_row(_row("Load game", "Oyunu yükkle"), "", "", spell=spell)
    found = [i for i in issues if i.kind == "spelling"]
    assert len(found) == 1
    assert found[0].severity == SEVERITY_INFO  # liste gürültüsü olmasın: yalnızca süzgeçle görünür
    assert found[0].words == ("oyunu", "yükkle")
    assert found[0].message == "Sözlükte olmayan sözcükler: oyunu, yükkle"
    assert KIND_LABELS["spelling"] == "Yazım"
    assert not [i for i in check_row(_row("Load", "Yükle"), "", "", spell=spell) if i.kind == "spelling"]
    assert not [i for i in check_row(_row("Load", "Oyunu yükkle"), "", "") if i.kind == "spelling"]  # denetim yok


def test_run_checks_passes_spell_checker_through() -> None:
    issues = run_checks([_row("Start", "Başlatt")], "", "", spell=_checker())
    assert [i.kind for i in issues if i.kind == "spelling"] == ["spelling"]


def test_bundled_filter_matches_real_turkish() -> None:
    from nxceviri.core.spell.loader import load_spell_checker

    spell = load_spell_checker()
    assert spell is not None
    for word in ("merhaba", "kitaplarımızdan", "bilgisayarımdan", "çocukları", "gidelim", "İstanbul", "ışığı"):
        assert spell.is_known(word), word
    for word in ("yanlışş", "kitapplar", "gidelimm", "başlattt", "xyzqw"):
        assert not spell.is_known(word), word
    text = "Oyunu başlatmak için düğmeye basın, sonra gidelim."
    assert spell.unknown_words(text, "Press to start.") == []


def test_unknown_spans_give_positions() -> None:
    spell = _checker()
    assert spell.unknown_spans("kitap yanlışş iyi", "") == [(6, 13, "yanlışş")]
