"""Satırları yeniden bölme (`reflow_text`): mevcut satır sonlarını kaldırıp dengeli yerleştirme."""

from __future__ import annotations

from nxceviri.core.translate import placeholders
from nxceviri.core.translate.codekinds import KIND_LINE_BREAK, KIND_OTHER, KIND_PAGE_BREAK
from nxceviri.core.translate.fit import FitRules, find_problems, reflow_text

KINDS = {1: KIND_LINE_BREAK, 2: KIND_PAGE_BREAK}


def kind_of(n: int) -> str:
    return KINDS.get(n, KIND_OTHER)


def test_newline_with_rules_is_balanced_not_greedy() -> None:
    rules = FitRules(width=20, max_lines=3)
    text = "Bir\nçok güzel bir gün geçirdik bugün burada"
    out = reflow_text(text, kind_of, rules)
    lines = out.split("\n")
    assert " ".join(lines) == "Bir çok güzel bir gün geçirdik bugün burada"
    assert len(lines) == 3 or len(lines) == 2
    assert not find_problems(out, kind_of, rules)
    assert max(len(line) for line in lines) - min(len(line) for line in lines) <= 8  # açgözlü değil dengeli


def test_line_break_codes_are_kept_and_redistributed() -> None:
    rules = FitRules(width=28, max_lines=2)
    text = "Merhaba⟦1⟧dostlarım bugün çok güzel bir gün geçirdik"
    out = reflow_text(text, kind_of, rules)
    assert placeholders.tokens_in(out) == placeholders.tokens_in(text) == [1]
    first, second = out.split("⟦1⟧")
    assert len(first) > len("Merhaba")  # kod kaydı
    assert f"{first} {second}".split() == text.replace("⟦1⟧", " ").split()
    assert not find_problems(out, kind_of, rules)


def test_page_breaks_stay_and_pages_are_reflowed_separately() -> None:
    rules = FitRules(width=18, max_lines=2)
    text = "ilk\nsayfa metni burada⟦2⟧ikinci sayfa da\nburada olsun"
    out = reflow_text(text, kind_of, rules)
    assert out.count("⟦2⟧") == 1
    first, second = out.split("⟦2⟧")
    assert " ".join(first.split()) == "ilk sayfa metni burada"
    assert " ".join(second.split()) == "ikinci sayfa da burada olsun"
    assert not find_problems(out, kind_of, rules)


def test_without_rules_uses_source_line_count() -> None:
    source = "One two three four\nfive six seven eight"
    out = reflow_text("bir\niki üç dört beş altı yedi sekiz", kind_of, None, source)
    lines = out.split("\n")
    assert len(lines) == 2
    assert abs(len(lines[0]) - len(lines[1])) <= 6
    one_line = reflow_text("bir\niki üç", kind_of, None, "Single line source")
    assert one_line == "bir iki üç"


def test_without_rules_code_representation_keeps_line_count() -> None:
    text = "bir iki üç⟦1⟧dört beş altı yedi sekiz"
    out = reflow_text(text, kind_of, None, "a⟦1⟧b")
    assert placeholders.tokens_in(out) == [1]
    first, second = out.split("⟦1⟧")
    assert abs(len(first) - len(second)) <= 6


def test_turkish_words_are_not_split() -> None:
    rules = FitRules(width=21, max_lines=3)
    out = reflow_text("Çok güzel öğrenciler şöyle ığdır İstanbul'a gitti", kind_of, rules)
    assert " ".join(out.split("\n")).split() == ["Çok", "güzel", "öğrenciler", "şöyle", "ığdır", "İstanbul'a", "gitti"]
    assert not find_problems(out, kind_of, rules)


def test_unfittable_page_is_left_alone() -> None:
    rules = FitRules(width=5, max_lines=2)
    text = "çokuzunbirsözcük\nvar"
    assert reflow_text(text, kind_of, rules) is text


def test_mixed_newline_and_code_page_is_left_alone() -> None:
    text = "bir\niki⟦1⟧üç dört"
    assert reflow_text(text, kind_of, FitRules(40, 3)) is text


def test_blank_line_paragraphs_are_left_alone() -> None:
    text = "birinci paragraf\n\nikinci paragraf"
    assert reflow_text(text, kind_of, FitRules(40, 3)) is text


def test_idempotent_and_unchanged_returns_same_object() -> None:
    rules = FitRules(width=20, max_lines=3)
    once = reflow_text("a b c d e f g h i j k l m n o p q r s t u v", kind_of, rules)
    assert reflow_text(once, kind_of, rules) == once
    single = "kısa"
    assert reflow_text(single, kind_of, rules) is single


def test_trailing_newline_is_preserved() -> None:
    out = reflow_text("bir iki\nüç dört beş altı yedi sekiz dokuz on\n", kind_of, FitRules(20, 4))
    assert out.endswith("\n")
    assert placeholders.tokens_in(out) == []


def test_rule_less_reflow_keeps_non_breaking_spaces() -> None:
    text = "Merhaba\xa0! nasılsın\nbugün çok güzel\nbir gün geçirdik\u3000evet"
    out = reflow_text(text, kind_of, None)
    assert out.count("\xa0") == 1
    assert "\u3000" in out
    assert "Merhaba\xa0!" in out
    assert out.replace("\n", " ") == text.replace("\n", " ")
