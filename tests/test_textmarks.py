"""İşaretli metin üretimi: semboller, satır sonu boşluk vurgusu ve kontrol kodu çipleri."""

from __future__ import annotations

import re
import time
from typing import Any

from nxceviri.core.translate.codekinds import KIND_LINE_BREAK, KIND_OTHER, KIND_PAGE_BREAK, KIND_SYMBOL
from nxceviri.gui.textmarks import KIND_GLYPHS, code_spans, marked_html, pua_spans, trailing_space_spans
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


def found_spans(markup: str, color: str) -> list[str]:
    """Verilen arka plan rengiyle boyanmış parçaların düz metinleri."""
    pattern = rf'<span style="[^"]*background-color:{re.escape(color)};[^"]*">(.*?)</span>'
    return [plain(m) for m in re.findall(pattern, markup)]


def test_found_spans_get_selection_background() -> None:
    out = html("Bir iki üç", found=[(4, 7)])
    assert found_spans(out, TOKENS_LIGHT["selection"]) == ["iki"]
    assert plain(out).replace("\xa0", " ") == "Bir iki üç"  # metin değişmez


def test_current_found_span_is_stronger() -> None:
    out = html("Bir iki üç", found=[(4, 7)], found_current=True)
    assert found_spans(out, TOKENS_LIGHT["accent"]) == ["iki"]
    assert found_spans(out, TOKENS_LIGHT["selection"]) == []


def test_found_spans_use_text_offsets_with_symbols_and_chips() -> None:
    # Boşluk "·" olarak çizilse de aralıklar ham metin konumudur; çip de eşleşmeyle örtüşürse eşleşme zeminini alır.
    out = html("a b ⟦1⟧ cd", symbols=True, chips=True, found=[(2, 3), (4, 7)], found_current=True)
    painted = found_spans(out, TOKENS_LIGHT["accent"])
    assert painted[0] == "b"
    assert "↵1" in painted[1]
    assert not any("cd" in p for p in painted)


def test_found_and_wrong_spans_combine() -> None:
    out = html("abc def", wrong=[(0, 3)], found=[(2, 5)])
    assert plain(out) == "abc def"
    assert "text-decoration:underline" in out


def test_found_span_in_selected_row_is_distinct_from_selection_background() -> None:
    out = html("Bir iki üç", found=[(4, 7)], selected_row=True)
    assert found_spans(out, TOKENS_LIGHT["surface"]) == ["iki"]


PUA_TEXT = "＋ Start"


def test_pua_chars_are_drawn_as_neutral_marks_not_raw() -> None:
    for symbols in (False, True):
        for chips in (False, True):
            out = html(PUA_TEXT, symbols=symbols, chips=chips)
            assert "" not in out
            assert "" not in out
            assert out.count(KIND_GLYPHS[KIND_SYMBOL]) == 2
            assert "＋" in out
            assert "Start" in plain(out)


def test_pua_does_not_shift_found_and_wrong_offsets() -> None:
    text = " Start now"
    out = html(text, found=[(3, 8)], wrong=[(9, 12)], found_current=True)
    assert found_spans(out, TOKENS_LIGHT["accent"]) == ["Start"]
    assert "text-decoration:underline" in out
    assert re.search(r"underline[^>]*>now</span>", out)


def test_pua_in_found_span_is_painted_with_the_match() -> None:
    out = html("ab", found=[(1, 2)], found_current=True)
    assert found_spans(out, TOKENS_LIGHT["accent"]) == [KIND_GLYPHS[KIND_SYMBOL]]


def test_pua_spans_are_text_offsets() -> None:
    assert pua_spans("abc") == [1, 2, 4]
    assert pua_spans("plain ç") == []
