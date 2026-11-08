"""Doğal sıralama anahtarı: sayılar değerine, harfler Türkçe sıraya göre."""

from __future__ import annotations

from nxceviri.core.languages import natural_sort_key


def _sorted(items: list[str]) -> list[str]:
    return sorted(items, key=natural_sort_key)


def test_numbers_sort_by_value() -> None:
    items = ["10", "2", "100", "1", "11", "21"]
    assert _sorted(items) == ["1", "2", "10", "11", "21", "100"]


def test_numbers_inside_text() -> None:
    items = ["Dialogue/line10", "Dialogue/line2", "Dialogue/line1", "Dialogue/line100"]
    assert _sorted(items) == ["Dialogue/line1", "Dialogue/line2", "Dialogue/line10", "Dialogue/line100"]


def test_turkish_letters_keep_alphabet_order() -> None:
    assert _sorted(["dünya", "çilek", "cam", "şeker", "sarı", "ğ", "g"]) == [
        "cam",
        "çilek",
        "dünya",
        "g",
        "ğ",
        "sarı",
        "şeker",
    ]


def test_mixed_and_empty_do_not_crash() -> None:
    assert _sorted(["b2", "", "a10", "a2", "10"]) == ["", "10", "a2", "a10", "b2"]


def test_leading_zeros_are_stable() -> None:
    assert _sorted(["a7", "a07", "a6"]) == ["a6", "a07", "a7"]
