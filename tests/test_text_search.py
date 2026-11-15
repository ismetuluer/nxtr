"""Arama kutusu için Türkçe harflerde büyük/küçük duyarsız katlama ve süzgeçteki etkisi."""

from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from nxceviri.core.project import TranslationRow
from nxceviri.core.translate.status import Status
from nxceviri.core.translate.textsearch import fold_search
from nxceviri.gui.translate_page import TranslatePage


@pytest.mark.parametrize(
    ("a", "b"),
    [("IŞIK", "ışık"), ("İstanbul", "istanbul"), ("ISTANBUL", "İstanbul"), ("ITEM", "item"), ("Işık", "işik")],
)
def test_fold_search_equates_dotted_and_dotless_i(a: str, b: str) -> None:
    assert fold_search(a) == fold_search(b)


def test_fold_search_keeps_other_letters_distinct() -> None:
    assert fold_search("ÇIĞ") == fold_search("çığ")
    assert fold_search("kar") != fold_search("kâr")
    assert fold_search("") == ""


def _row(i: int, source: str, translation: str) -> TranslationRow:
    return TranslationRow(
        id=i,
        file="a.msbt",
        key=f"k{i}",
        source=source,
        translation=translation,
        status=Status.MACHINE,
        note="",
        code_labels=(),
        max_length=None,
        context=f"k{i}",
    )


def test_search_box_finds_turkish_letters_case_insensitively(qtbot: QtBot) -> None:
    page = TranslatePage()
    qtbot.addWidget(page)
    page.set_rows([_row(1, "x", "IŞIK burada"), _row(2, "y", "İSTANBUL yolu"), _row(3, "ITEM", "z"), _row(4, "q", "r")])
    for query, expected in (
        ("ışık", {1}),
        ("istanbul", {2}),
        ("Istanbul", {2}),
        ("item", {3}),
        ("ıtem", {3}),
        ("İTEM", {3}),
    ):
        page.search.setText(query)
        shown = {
            page.model.rows[page.proxy.mapToSource(page.proxy.index(i, 0)).row()].id
            for i in range(page.proxy.rowCount())
        }
        assert shown == expected, query
