"""Kontrol kodu türleri: etiketten tahmin ve proje eşlemesi."""

from __future__ import annotations

import pytest

from nxceviri.core.translate.codekinds import (
    BUILTIN_KINDS,
    KIND_LINE_BREAK,
    KIND_NAMES,
    KIND_OTHER,
    KIND_PAGE_BREAK,
    KIND_STYLE,
    KIND_SYMBOL,
    KIND_VARIABLE,
    CodeKinds,
    guess_kind,
)


def test_guess_from_label() -> None:
    assert guess_kind("Satır sonu") == KIND_LINE_BREAK
    for label in ("Sayfa sonu", "Bekle", "Ekranı temizle"):
        assert guess_kind(label) == KIND_PAGE_BREAK
    assert guess_kind("Renk") == KIND_STYLE
    for label in ("Oyuncu adı", "Sayı"):
        assert guess_kind(label) == KIND_VARIABLE
    for label in ("Özel simge", "Tuş"):
        assert guess_kind(label) == KIND_SYMBOL
    assert guess_kind("Kod 0x05") == KIND_OTHER
    assert guess_kind("SATIR SONU") == KIND_LINE_BREAK
    assert guess_kind("RENK") == KIND_STYLE
    assert guess_kind("SAYI") == KIND_VARIABLE
    assert guess_kind("TUŞ") == KIND_SYMBOL
    assert guess_kind("SATİR SONU") == KIND_LINE_BREAK
    assert guess_kind("satir sonu") == KIND_LINE_BREAK
    assert guess_kind("Oyuncu ADI") == KIND_VARIABLE


def test_builtin_constants() -> None:
    assert BUILTIN_KINDS == (
        KIND_LINE_BREAK,
        KIND_PAGE_BREAK,
        KIND_VARIABLE,
        KIND_SYMBOL,
        KIND_STYLE,
        KIND_OTHER,
    )
    assert KIND_NAMES[KIND_LINE_BREAK] == "Satır sonu"
    assert KIND_NAMES[KIND_OTHER] == "Diğer"
    assert set(KIND_NAMES) == set(BUILTIN_KINDS)


def test_mapping_overrides_guess() -> None:
    kinds = CodeKinds({"Kod 0x05": KIND_PAGE_BREAK})
    assert kinds.kind_of("Kod 0x05") == KIND_PAGE_BREAK
    assert kinds.kind_of("Satır sonu") == KIND_LINE_BREAK


def test_custom_kind_name_is_kept() -> None:
    assert CodeKinds({"X": "Yazı hızı"}).kind_of("X") == "Yazı hızı"


def test_roundtrip() -> None:
    k = CodeKinds({"Özel şey": KIND_SYMBOL, "İğne ı": "Yazı hızı"})
    assert CodeKinds.load(k.dump()) == k


@pytest.mark.parametrize("text", ["", "{bozuk", "[1,2]", '{"a": 5}'])
def test_load_bad_json_gives_empty(text: str) -> None:
    assert CodeKinds.load(text).mapping == {}


def test_load_keeps_only_str_pairs() -> None:
    assert CodeKinds.load('{"a": "b", "c": 5}').mapping == {"a": "b"}


def test_page_break_guess_needs_whole_word() -> None:
    # Duraklama ("Bekleme") satır ortasında olur; sayfa sonu sanılırsa sayfa yanlış yerden bölünür.
    assert guess_kind("Bekleme") == KIND_OTHER
    assert guess_kind("BEKLEME") == KIND_OTHER
    for label in (
        "Bekle",
        "Sayfa sonu",
        "Ekranı temizle",
        "Sayfa sonu (bekle, temizle)",
        "Konuşma süresi / sayfa sonu",
    ):
        assert guess_kind(label) == KIND_PAGE_BREAK
