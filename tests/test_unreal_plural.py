"""Unreal biçim argümanının çoğul ifadesi: `{Count}|plural(one=cat,other=cats)`.

Değişken ile çoğul ifadesi tek bir bütündür: ifade aç/kapa çifti gibi okunur (`{Count}|plural(one=` … `)`),
seçenek ayracı (`,other=`) katıdır, seçeneklerdeki sözcükler düz metin olarak çevrilir. Bütün yer değiştirebilir
(uyarı). Yalnızca yalın biçim tanınır (tırnaksız, boşluksuz, boş olmayan değerler); başka biçimde ya da başka bir ek
(`|gender(…)`) geldiğinde değişken ve ekin başı tek, katı bir kod olur (yeri değişemez).
"""

from __future__ import annotations

import pytest

from nxceviri.core.formats import registry
from nxceviri.core.formats.base import FormatError
from nxceviri.core.formats.unreal import LocresPlugin, locres
from nxceviri.core.translate import placeholders
from tests.unrealbuild import build_locres

PLUGIN = LocresPlugin()
CATS = "There {N}|plural(one=is,other=are) {N} {N}|plural(one=cat,other=cats)."


def _raws(text: str) -> tuple[str, list[str]]:
    source, codes = locres.tokenize(text)
    return source, [c.raw.decode("utf-8") for c in codes]


def test_plural_expression_is_split_into_head_options_and_end() -> None:
    source, raws = _raws(CATS)
    assert source == "There ⟦1⟧is⟦2⟧are⟦3⟧ ⟦4⟧ ⟦5⟧cat⟦6⟧cats⟦7⟧."
    assert raws == ["{N}|plural(one=", ",other=", ")", "{N}", "{N}|plural(one=", ",other=", ")"]
    _s, codes = locres.tokenize(CATS)
    roles = registry.free_codes("unreal", codes)
    assert roles == frozenset({4})  # yalın değişken serbest
    assert placeholders.pairs_of(roles) == {
        1: ("plural", "open"),
        2: ("plural", "separator"),
        3: ("plural", "close"),
        5: ("plural", "open"),
        6: ("plural", "separator"),
        7: ("plural", "close"),
    }
    assert [c.label for c in codes[:3]] == ["Çoğul başı {N} (one=)", "Çoğul seçeneği (other=)", "Çoğul sonu"]


def test_whole_plural_expression_may_move_but_not_its_parts() -> None:
    source, codes = locres.tokenize(CATS)
    roles = registry.free_codes("unreal", codes)
    moved = placeholders.check(source, "⟦4⟧ ⟦5⟧kedi⟦6⟧kedi⟦7⟧ ⟦1⟧var⟦2⟧var⟦3⟧.", roles)
    assert not moved.errors
    assert moved.warnings == (placeholders.PAIR_REORDER_WARNING,)
    assert placeholders.check(source, "⟦1⟧var⟦3⟧ ⟦4⟧ ⟦5⟧kedi⟦2⟧⟦6⟧kedi⟦7⟧.", roles).errors  # ayraç taşındı
    assert placeholders.check(source, "⟦4⟧ ⟦1⟧var⟦2⟧var⟦3⟧ ⟦5⟧kedi⟦6⟧kedi⟦7⟧.", roles).warnings  # yalın değişken


def test_inject_writes_translated_and_moved_plural_options() -> None:
    data = build_locres([("Game", "Cats", CATS), ("Game", "Other", "Plain")])
    assert PLUGIN.inject(data, {e.key: e.source for e in PLUGIN.extract(data)}) == data
    moved = "⟦4⟧ ⟦5⟧kedi⟦6⟧kedi⟦7⟧ ⟦1⟧var⟦2⟧var⟦3⟧."
    with placeholders.tolerate_reorder():
        out = PLUGIN.inject(data, {"Game/Cats": moved})
    written = locres.read(out)
    texts = {locres._entry_key(e): written.strings[e.string_index] for e in written.entries}
    assert texts["Game/Cats"] == "{N} {N}|plural(one=kedi,other=kedi) {N}|plural(one=var,other=var)."
    again = {e.key: e.source for e in PLUGIN.extract(out)}
    assert again["Game/Cats"] == placeholders.renumber(moved)


@pytest.mark.parametrize("option", ["var, yok", "var)", "a=b", "{0}", "", "iki sözcük", 'tırnak"'])
def test_inject_rejects_option_text_that_would_break_the_expression(option: str) -> None:
    data = build_locres([("Game", "Cats", CATS)])
    with pytest.raises(FormatError):
        PLUGIN.inject(data, {"Game/Cats": f"Orada ⟦1⟧{option}⟦2⟧var⟦3⟧ ⟦4⟧ ⟦5⟧kedi⟦6⟧kedi⟦7⟧."})


def test_free_argument_moved_into_an_option_is_rejected_on_write() -> None:
    """Denetim serbest kodun çiftin içine girmesine izin verir (uyarı); seçeneğin içine giren argüman ifadeyi bozar,
    eklenti yazmayı reddeder (dışa aktarma o satırı orijinal bırakır)."""
    text = "{Name} has {N}|plural(one=cat,other=cats)"
    source, codes = locres.tokenize(text)
    assert source == "⟦1⟧ has ⟦2⟧cat⟦3⟧cats⟦4⟧"
    moved = "⟦2⟧kedi ⟦1⟧⟦3⟧kedi⟦4⟧"
    assert placeholders.check(source, moved, registry.free_codes("unreal", codes)).warnings
    data = build_locres([("Game", "K", text)])
    with placeholders.tolerate_reorder(), pytest.raises(FormatError):
        PLUGIN.inject(data, {"Game/K": moved})


def test_other_shapes_keep_the_head_strict() -> None:
    """Tanınmayan biçimde değişken ile ekin başı tek kod olur; serbest değildir, eklenti onu çift saymaz."""
    for text, head, rest in (
        ('{N}|plural(one="a cat",other="cats") left', "{N}|plural(", 'one="a cat",other="cats") left'),
        ("{N}|plural(one=,other=s) left", "{N}|plural(", "one=,other=s) left"),
        ("{G}|gender(he,she) left", "{G}|gender(", "he,she) left"),
    ):
        source, codes = locres.tokenize(text)
        assert source == f"⟦1⟧{rest}"
        assert codes[0].raw.decode() == head
        roles = registry.free_codes("unreal", codes)
        assert roles == frozenset()
        assert placeholders.pairs_of(roles) == {}
        data = build_locres([("Game", "K", text)])
        assert PLUGIN.inject(data, {"Game/K": source}) == data


def test_old_project_rows_fail_loudly() -> None:
    """Eski sürümde `|plural(…)` düz metindi; o satırın çevirisi yeni kodlarla yazılamaz, sessizce bozulmaz."""
    data = build_locres([("Game", "Cats", "{N}|plural(one=cat,other=cats)")])
    with pytest.raises(FormatError):
        PLUGIN.inject(data, {"Game/Cats": "⟦1⟧|plural(one=kedi,other=kediler)"})


def test_plain_arguments_and_rich_text_are_unchanged() -> None:
    source, raws = _raws('Hello {PlayerName}, <Bold>welcome</>! {0} {} <img id="A"/>')
    assert source == "Hello ⟦1⟧, ⟦2⟧welcome⟦3⟧! ⟦4⟧ ⟦5⟧ ⟦6⟧"
    assert raws == ["{PlayerName}", "<Bold>", "</>", "{0}", "{}", '<img id="A"/>']
