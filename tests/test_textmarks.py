"""İşaretli metin üretimi: semboller, satır sonu boşluk vurgusu ve kontrol kodu çipleri."""

from __future__ import annotations

import re
import time
from typing import Any

from nxceviri.core.translate.codekinds import KIND_LINE_BREAK, KIND_OTHER, KIND_PAGE_BREAK
from nxceviri.gui.textmarks import KIND_GLYPHS, code_spans, marked_html, trailing_space_spans
from nxceviri.gui.theme import TOKENS

TOKENS_LIGHT = TOKENS["light"]
KINDS = {1: KIND_LINE_BREAK, 2: KIND_PAGE_BREAK}


def kind_of(n: int) -> str:
    return KINDS.get(n, KIND_OTHER)


def html(text: str, **kwargs: Any) -> str:
    options = {"symbols": False, "chips": False, **kwargs}
    return marked_html(text, kind_of, TOKENS_LIGHT, **options)


def plain(markup: str) -> str:
    return re.sub(r"<[^>]+>", "", markup)


def test_symbols_off_has_no_marks() -> None:
    out = html("a b")
    assert "·" not in out
    assert "¶" not in out


def test_symbols_on_marks_space_newline_tab_nbsp() -> None:
    out = html("a b\nc\td e", symbols=True)
    for mark in ("·", "¶", "→", "°"):
        assert out.count(mark) == 1, mark
    assert "<br>" in out  # satır sonu gerçek satır sonu olarak kalır


def test_single_line_keeps_newline_inline() -> None:
    out = html("a\nb", symbols=True, single_line=True)
    assert "¶" in out
    assert "<br>" not in out
    assert "<br>" not in html("a\nb", single_line=True)  # semboller kapalıyken satır sonu boşluğa döner


def test_trailing_space_is_highlighted_only_with_symbols() -> None:
    marker = f"background-color:{TOKENS_LIGHT['warning_bg']}"
    assert html("son  \nsatır", symbols=True).count(marker) == 2
    assert marker not in html("son  \nsatır")
    assert trailing_space_spans("son  \nx ") == [(3, 5), (7, 8)]


def test_chips_replace_codes_and_keep_numbers() -> None:
    out = html("Bas ⟦1⟧ ve ⟦2⟧", chips=True)
    assert "⟦" not in out
    assert KIND_GLYPHS[KIND_LINE_BREAK] in out
    assert KIND_GLYPHS[KIND_PAGE_BREAK] in out
    assert TOKENS_LIGHT["accent"] in out
    assert TOKENS_LIGHT["warning"] in out
    text = plain(out)
    assert "1" in text
    assert "2" in text
    assert "⟦1⟧" in html("Bas ⟦1⟧", chips=False)  # çipsiz hâlde ham kod görünür


def test_unknown_kind_is_other_chip() -> None:
    assert KIND_GLYPHS[KIND_OTHER] in html("x ⟦9⟧", chips=True)


def test_html_is_escaped() -> None:
    out = html("<div> & ⟦", chips=True)
    assert "&lt;div&gt;" in out
    assert "&amp;" in out
    assert "<div>" not in out
    assert "⟦" in plain(out)  # yarım kod çip olmaz, ham kalır


def test_empty_and_whitespace_only() -> None:
    for text in ("", "   ", "⟦1⟧⟦2⟧"):
        for symbols in (False, True):
            html(text, symbols=symbols, chips=True)


def test_code_spans() -> None:
    assert code_spans("a⟦1⟧b⟦12⟧") == [(1, 4, 1), (5, 9, 12)]
    assert code_spans("⟦ yarım") == []


def test_very_long_line_is_fast() -> None:
    text = ("kelime " * 1500)[:10_000]
    start = time.perf_counter()
    html(text, symbols=True, chips=True)
    assert time.perf_counter() - start < 0.5


def test_symbol_space_keeps_a_break_opportunity() -> None:
    out = html("a b", symbols=True)
    assert "·</span>\u200b" in out  # kaydırma sözcük sınırında kalsın
    assert "\u200b" not in html("a b", symbols=True, single_line=True)
    assert "\u200b" not in html("a b")


def test_crlf_is_one_line_break() -> None:
    assert html("a\r\nb", symbols=True).count("¶") == 1
    assert html("a\rb", symbols=True).count("¶") == 1
    assert html("a\r\nb").count("<br>") == 1


def test_wrong_ranges_are_underlined_and_text_unchanged() -> None:
    out = html("ab cd ef", wrong=[(3, 5)])
    underline = f"text-decoration:underline;text-decoration-color:{TOKENS_LIGHT['danger']}"
    assert out.count(underline) == 1
    assert plain(out) == "ab cd ef"
    assert "<span" not in html("ab cd ef")
