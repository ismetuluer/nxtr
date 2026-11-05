"""Metin sığdırma: sayfa ayrıştırma, sorun bulma ve otomatik bölme testleri."""

from __future__ import annotations

import random
import time

import pytest

from nxceviri.core.translate import placeholders
from nxceviri.core.translate.codekinds import (
    KIND_LINE_BREAK,
    KIND_OTHER,
    KIND_PAGE_BREAK,
    KIND_SYMBOL,
    KIND_VARIABLE,
)
from nxceviri.core.translate.fit import (
    PROBLEM_BREAK,
    PROBLEM_LINE,
    PROBLEM_PAGE,
    FitResult,
    FitRules,
    PageProblem,
    find_problems,
    fit_text,
    split_pages,
    visible_width,
)

PAGE = {1: KIND_PAGE_BREAK, 2: KIND_PAGE_BREAK, 3: KIND_PAGE_BREAK}


def kind_of(n: int) -> str:
    return PAGE.get(n, KIND_OTHER)


RULES = FitRules(width=40, max_lines=3)

SAMPLE = (
    "Yalnız bir uyarı.⟦1⟧Bu ayar bazen garip\n"
    "sonuç verebilir. Örneğin başarısız olduğun\n"
    "hâlde başarılı hareket sesi duyabilirsin.⟦2⟧Kusura\n"
    "bakma; TV ayarını böyle değiştirdiğimizde\n"
    "bazen oluyor.⟦3⟧Aa! Ama elde\n"
    "taşınır modda hiç yaşanmamalı! Buna da şükür."
)


def test_rules_validation() -> None:
    with pytest.raises(ValueError, match="genişliği"):
        FitRules(width=0, max_lines=3)
    with pytest.raises(ValueError, match="satır sayısı"):
        FitRules(width=40, max_lines=0)


def test_split_pages_roundtrip() -> None:
    pages = split_pages(SAMPLE, kind_of)
    assert len(pages) == 4
    assert [sep for _, sep in pages] == ["⟦1⟧", "⟦2⟧", "⟦3⟧", ""]
    assert "".join(a + b for a, b in pages) == SAMPLE


@pytest.mark.parametrize("text", ["", "⟦1⟧⟦2⟧", "⟦1⟧"])
def test_split_pages_empty_and_codes_only(text: str) -> None:
    pages = split_pages(text, kind_of)
    assert "".join(a + b for a, b in pages) == text


def test_split_pages_ignores_other_codes() -> None:
    assert split_pages("a⟦9⟧b", kind_of) == [("a⟦9⟧b", "")]


def test_visible_width_counts_variable_and_symbol() -> None:
    kinds = {5: KIND_VARIABLE, 6: KIND_SYMBOL}
    rules = FitRules(width=40, max_lines=3)

    def kof(n: int) -> str:
        return kinds.get(n, KIND_OTHER)

    assert visible_width("Ad: ⟦5⟧", kof, rules) == 4 + 6
    assert visible_width("⟦6⟧ git", kof, rules) == 1 + 4
    assert visible_width("⟦7⟧abc", kof, rules) == 3
    assert visible_width("  abc  ", kof, rules) == 3
    assert visible_width("Ad: ⟦5⟧", kof, FitRules(40, 3, variable_width=2)) == 4 + 2


def test_find_problems_on_sample() -> None:
    assert find_problems(SAMPLE, kind_of, RULES) == [
        PageProblem(PROBLEM_BREAK, 2, 1, 19),
        PageProblem(PROBLEM_LINE, 2, 2, 42),
        PageProblem(PROBLEM_LINE, 2, 3, 41),
        PageProblem(PROBLEM_BREAK, 3, 1, 6),
        PageProblem(PROBLEM_LINE, 3, 2, 41),
        PageProblem(PROBLEM_BREAK, 4, 1, 12),
        PageProblem(PROBLEM_LINE, 4, 2, 45),
    ]


def test_page_too_tall() -> None:
    assert find_problems("bir.\niki.\nüç.\ndört.", kind_of, RULES) == [PageProblem(PROBLEM_PAGE, 1, 0, 4)]


def test_line_break_code_separates_lines() -> None:
    def kof(n: int) -> str:
        return KIND_LINE_BREAK if n == 8 else KIND_OTHER

    text = "bir.⟦8⟧iki.⟦8⟧üç.⟦8⟧dört."
    assert find_problems(text, kof, RULES) == [PageProblem(PROBLEM_PAGE, 1, 0, 4)]


def test_clean_text_has_no_problems() -> None:
    assert find_problems("Merhaba dünya, nasılsın?\nİyiyim, sağ ol.⟦1⟧Görüşürüz.", kind_of, RULES) == []


def test_bad_break_needs_all_three_conditions() -> None:
    # Üç koşul da var: kısa, sonraki kelime sığar, noktalamasız.
    assert find_problems("kısa satır\ndevam eder", kind_of, RULES) == [PageProblem(PROBLEM_BREAK, 1, 1, 10)]
    # Noktalamayla bitiyor.
    assert find_problems("kısa satır.\ndevam eder", kind_of, RULES) == []
    # Yarıdan uzun.
    assert find_problems("a" * 20 + "\ndevam", kind_of, RULES) == []
    # Sonraki kelime sığmıyor.
    assert find_problems("kısa satır\n" + "b" * 35, kind_of, RULES) == []
    # Son satır hiçbir zaman bad_break olmaz.
    assert find_problems("tek kısa satır", kind_of, RULES) == []
    # Boş satır bilinçli boşluktur.
    assert find_problems("\ndevam eder", kind_of, RULES) == []


# --- Bölme algoritması (fit_text) ---------------------------------------------------------------------------------


def _words_per_page(text: str) -> list[list[str]]:
    return [page.split() for page, _ in split_pages(text, kind_of)]


def _line_kind_of(n: int) -> str:
    return KIND_LINE_BREAK if n == 4 else kind_of(n)


def test_fit_sample_properties() -> None:
    result = fit_text(SAMPLE, kind_of, RULES)
    assert result.failed == ()
    assert find_problems(result.text, kind_of, RULES) == []
    assert placeholders.tokens_in(result.text) == placeholders.tokens_in(SAMPLE)
    assert [sep for _, sep in split_pages(result.text, kind_of)] == ["⟦1⟧", "⟦2⟧", "⟦3⟧", ""]
    # Kelime dizisi aynı (boşluk ve satır sonu dışında hiçbir şey değişmedi): kelime bölünmedi.
    assert _words_per_page(result.text) == _words_per_page(SAMPLE)


def test_fit_sample_expected_layout() -> None:
    assert fit_text(SAMPLE, kind_of, RULES).text == (
        "Yalnız bir uyarı.⟦1⟧Bu ayar bazen garip sonuç verebilir.\n"
        "Örneğin başarısız olduğun hâlde başarılı\n"
        "hareket sesi duyabilirsin.⟦2⟧Kusura bakma; TV ayarını böyle\n"
        "değiştirdiğimizde bazen oluyor.⟦3⟧Aa! Ama elde taşınır modda hiç\n"
        "yaşanmamalı! Buna da şükür."
    )


def test_prefers_sentence_boundary() -> None:
    text = "Bu ayar bazen garip sonuç verebilir. Örneğin başarısız olduğun hâlde başarılı hareket sesi duyabilirsin."
    result = fit_text(text, kind_of, FitRules(width=40, max_lines=3))
    assert result.failed == ()
    assert result.text.split("\n")[0].endswith("Bu ayar bazen garip sonuç verebilir.")


def test_clause_boundary_when_no_sentence_end() -> None:
    text = "Eğer bu kapıyı şimdi açarsan bile, o içeride seni kimse beklemiyor olacak"
    result = fit_text(text, kind_of, RULES)
    assert result.failed == ()
    assert result.text.split("\n")[0] == "Eğer bu kapıyı şimdi açarsan bile,"


def test_never_splits_inside_word() -> None:
    text = "a" * 30
    result = fit_text(text, kind_of, FitRules(width=20, max_lines=3))
    assert result == FitResult(text, (1,))


def test_too_many_lines_fails() -> None:
    text = "Yalnız.⟦1⟧" + " ".join(["uzunkelimeler"] * 10)
    result = fit_text(text, kind_of, FitRules(width=20, max_lines=3))
    assert result.failed == (2,)
    assert result.text == text


def test_untouched_when_ok() -> None:
    text = "Merhaba dünya, nasılsın?\nİyiyim, sağ ol.⟦1⟧Görüşürüz."
    result = fit_text(text, kind_of, RULES)
    assert result.text is text
    assert result.failed == ()


def test_only_problem_pages_change() -> None:
    first = "Kısa ve özel.\nİkinci   biçimli satır."
    text = first + "⟦1⟧" + "kelime " * 12
    result = fit_text(text, kind_of, RULES)
    assert result.failed == ()
    assert result.text.startswith(first + "⟦1⟧")


@pytest.mark.parametrize(
    "text",
    [
        SAMPLE,
        "kısa satır\ndevam eder ve biter",
        "a\nb\nc\n",
        "Bir iki üç dört beş altı yedi sekiz dokuz on on bir on iki on üç on dört on beş on altı on yedi",
        "a" * 30 + " b",
        "Satır bir.\nSatır iki.\n\nSatır dört.⟦2⟧son",
    ],
)
def test_idempotent(text: str) -> None:
    once = fit_text(text, kind_of, RULES)
    twice = fit_text(once.text, kind_of, RULES)
    assert twice.text == once.text
    assert twice.failed == once.failed


def test_trailing_newline_counts_as_line_and_is_dropped() -> None:
    # Sondaki "\n" boş bir son satır sayılır; sayfa max_lines'ı aşıyorsa yeniden bölünür ve boş satır kalkar.
    rules = FitRules(width=40, max_lines=3)
    text = "bir.\niki.\nüç.\n"
    assert find_problems(text, kind_of, rules) == [PageProblem(PROBLEM_PAGE, 1, 0, 4)]
    result = fit_text(text, kind_of, rules)
    assert result == FitResult("bir. iki. üç.", ())
    assert find_problems(result.text, kind_of, rules) == []
    assert fit_text(result.text, kind_of, rules) == result
    # Sorun yoksa sondaki "\n" olduğu gibi kalır.
    assert fit_text("bir.\niki.\n", kind_of, rules).text == "bir.\niki.\n"


@pytest.mark.parametrize(
    "text",
    [
        "Başlık\n\n\tBu ayar bazen garip sonuç verebilir ve o zaman ne yaparız bilmiyorum",
        "Başlık\n\nBu ayar bazen garip sonuç verebilir ve o zaman ne yaparız bilmiyorum",
        "\nBu ayar bazen garip sonuç verebilir ve o zaman ne yaparız bilmiyorum",
        "Başlık\n\tBu ayar bazen garip sonuç verebilir ve o zaman ne yaparız bilmiyorum",
    ],
)
def test_paragraph_gap_or_tab_page_left_unchanged(text: str) -> None:
    # Başlık + boş satır + girintili paragraf birleştirilmez; sayfa olduğu gibi kalır ve onarılamadı sayılır.
    assert find_problems(text, kind_of, RULES)
    assert fit_text(text, kind_of, RULES) == FitResult(text, (1,))


def test_paragraph_gap_only_blocks_its_own_page() -> None:
    text = "Başlık\n\nBu ayar bazen garip sonuç verebilir ve o zaman ne yaparız bilmiyorum⟦1⟧" + "kelime " * 12
    result = fit_text(text, kind_of, RULES)
    assert result.failed == (1,)
    assert result.text.startswith(text.split("⟦1⟧", maxsplit=1)[0] + "⟦1⟧")
    assert find_problems(split_pages(result.text, kind_of)[1][0], kind_of, RULES) == []


def test_balanced_and_no_orphan() -> None:
    # Açgözlü bölme 37 + 22 karakter verirdi ("… al ve" / "hemen kapıdan geri dön").
    text = "Masanın üstündeki eski haritayı al ve hemen kapıdan geri dön"
    result = fit_text(text, kind_of, FitRules(width=40, max_lines=3))
    assert result.failed == ()
    lines = result.text.split("\n")
    assert len(lines) == 2
    assert len(lines[-1].split()) > 1
    assert abs(len(lines[0]) - len(lines[1])) <= 10
    assert result.text == "Masanın üstündeki eski haritayı al\nve hemen kapıdan geri dön"


def test_last_line_counts_toward_balance() -> None:
    # İlk satır ağzına kadar doldurulup "o zaman" ikiye bölünmez.
    text = "Bu ayar bazen garip sonuç verebilir ve o zaman ne yaparız bilmiyorum"
    result = fit_text(text, kind_of, FitRules(width=40, max_lines=3))
    assert result.failed == ()
    assert not result.text.split("\n")[0].endswith(" o")
    assert result.text == "Bu ayar bazen garip sonuç verebilir\nve o zaman ne yaparız bilmiyorum"


def test_orphan_avoided() -> None:
    # Açgözlü bölme son satıra tek kelime ("bul") bırakırdı.
    text = "Bu uzun yolun sonunda seni bekleyen bir kapıyı açmak için önce o eski anahtarı bul"
    result = fit_text(text, kind_of, FitRules(width=40, max_lines=3))
    assert result.failed == ()
    assert len(result.text.split("\n")[-1].split()) > 1


def test_no_bad_break_in_output() -> None:
    # Sabit satır sayısında bile, geçerli bir düzen varsa gereksiz bölünmüş satır üretilmez.
    rules = FitRules(width=30, max_lines=3)
    text = "Kısa⟦4⟧ama bu ikinci satır gerçekten çok fazla uzun oldu"
    result = fit_text(text, _line_kind_of, rules)
    assert result.failed == ()
    assert find_problems(result.text, _line_kind_of, rules) == []


def test_line_break_code_page_keeps_codes() -> None:
    rules = FitRules(width=30, max_lines=3)
    text = "Bu çok uzun bir cümle ⟦4⟧ ve burası da çok uzun bir devam"
    result = fit_text(text, _line_kind_of, rules)
    assert result.failed == ()
    assert placeholders.tokens_in(result.text) == [4]
    assert "\n" not in result.text
    assert find_problems(result.text, _line_kind_of, rules) == []
    assert result.text == "Bu çok uzun bir cümle ve ⟦4⟧ burası da çok uzun bir devam"


def test_line_break_code_spacing_comes_from_text() -> None:
    rules = FitRules(width=30, max_lines=3)
    text = "Bu çok uzun bir cümle⟦4⟧ve burası da çok uzun bir devam"
    result = fit_text(text, _line_kind_of, rules)
    assert result.text == "Bu çok uzun bir cümle ve⟦4⟧burası da çok uzun bir devam"


def test_line_break_codes_more_than_max_lines_fail() -> None:
    rules = FitRules(width=30, max_lines=2)
    text = "bir⟦4⟧iki⟦4⟧üç " + "uzun " * 10
    assert fit_text(text, _line_kind_of, rules) == FitResult(text, (1,))


def test_mixed_separators_are_skipped() -> None:
    text = "Bu satır gerçekten çok ama çok uzun bir satır oldu\nikinci ⟦4⟧ üçüncü"
    assert fit_text(text, _line_kind_of, RULES) == FitResult(text, (1,))


def test_mixed_separators_without_problem_untouched() -> None:
    text = "bir.\niki.⟦4⟧üç."
    assert fit_text(text, _line_kind_of, RULES) == FitResult(text, ())


def test_non_break_code_stays_in_word() -> None:
    def kof(n: int) -> str:
        return KIND_VARIABLE if n == 7 else KIND_OTHER

    text = "Merhaba ⟦7⟧! Bugün seninle birlikte uzun bir yola çıkacağız, ⟦9⟧hazır ol⟦9⟧."
    result = fit_text(text, kof, RULES)
    assert result.failed == ()
    assert result.text.split() == text.split()
    assert placeholders.tokens_in(result.text) == placeholders.tokens_in(text)
    assert find_problems(result.text, kof, RULES) == []


@pytest.mark.parametrize("text", ["", "⟦1⟧⟦2⟧"])
def test_empty_and_codes_only_unchanged(text: str) -> None:
    assert fit_text(text, kind_of, RULES) == FitResult(text, ())


def test_turkish_chars() -> None:
    text = "Çağrı ışığı görünce öğüt verdi; İstanbul'a gidiş şüphesiz güç olacak ama çok güzel geçecek"
    rules = FitRules(width=30, max_lines=4)
    result = fit_text(text, kind_of, rules)
    assert result.failed == ()
    assert result.text.split() == text.split()
    assert all(len(line) <= 30 for line in result.text.split("\n"))


def test_5000_pages_fast() -> None:
    rows = [SAMPLE.replace("Kusura", f"Kusura{i % 7}") + "⟦1⟧" + "kelime " * (i % 15) + "son." for i in range(5000)]
    start = time.perf_counter()
    for row in rows:
        fit_text(row, kind_of, RULES)
    assert time.perf_counter() - start < 10.0


# --- Kontrol kodu bütünlüğü ---------------------------------------------------------------------------------------


def test_line_break_next_to_other_code_keeps_order() -> None:
    # Satır sonu kodu (1) yanındaki başka bir kodla (2) yer değiştirmemeli; değiştirecekse sayfa onarılmaz.
    def kof(n: int) -> str:
        return KIND_LINE_BREAK if n == 1 else KIND_OTHER

    text = "Eski sandıkta⟦1⟧⟦2⟧ altın para buldun, harika bir şey bu."
    result = fit_text(text, kof, FitRules(width=36, max_lines=2))
    assert placeholders.tokens_in(result.text) == placeholders.tokens_in(text)
    assert placeholders.problems(text, result.text) == []
    assert result == FitResult(text, (1,))


_RANDOM_KINDS = {1: KIND_PAGE_BREAK, 2: KIND_LINE_BREAK, 3: KIND_VARIABLE, 4: KIND_OTHER, 5: KIND_SYMBOL}


def _random_kind_of(n: int) -> str:
    return _RANDOM_KINDS.get((n - 1) % 5 + 1, KIND_OTHER)


def _random_text(rng: random.Random) -> str:
    words = ["bir", "iki", "çok", "uzun", "kelime", "şimdi", "geldi.", "ama,", "o", "zaman", "İstanbul'a", "ışık"]
    parts: list[str] = []
    for _ in range(rng.randint(1, 30)):
        roll = rng.random()
        if roll < 0.25:
            parts.append(placeholders.token(rng.randint(1, 5) + 5 * rng.randint(0, 3)))
        elif roll < 0.32:
            parts.append("\n")
        else:
            parts.append(rng.choice(words))
        parts.append(rng.choice([" ", " ", ""]))
    return "".join(parts)


def test_random_texts_keep_codes() -> None:
    rng = random.Random(20261031)
    for _ in range(400):
        text = _random_text(rng)
        rules = FitRules(width=rng.randint(8, 30), max_lines=rng.randint(1, 4))
        result = fit_text(text, _random_kind_of, rules)
        assert placeholders.tokens_in(result.text) == placeholders.tokens_in(text), text
        before = split_pages(text, _random_kind_of)
        after = split_pages(result.text, _random_kind_of)
        assert [sep for _, sep in after] == [sep for _, sep in before], text
        assert [placeholders.tokens_in(p) for p, _ in after] == [placeholders.tokens_in(p) for p, _ in before], text
        assert fit_text(result.text, _random_kind_of, rules).text == result.text, text


# --- Orijinalde de olan kısa bölünme ------------------------------------------------------------------------------


def test_bad_break_also_in_source_is_kept() -> None:
    # Menü, liste, şiir: orijinalde de aynı kısa bölünme varsa bilinçlidir.
    assert find_problems("Evet\nHayır", kind_of, RULES) == [PageProblem(PROBLEM_BREAK, 1, 1, 4)]
    assert find_problems("Evet\nHayır", kind_of, RULES, source_text="Yes\nNo") == []
    assert fit_text("Evet\nHayır", kind_of, RULES, source_text="Yes\nNo") == FitResult("Evet\nHayır", ())
    assert fit_text("Evet\nHayır", kind_of, RULES).text == "Evet Hayır"


def test_new_bad_break_still_fixed_with_source() -> None:
    source = "Yes, and no problem at all."
    text = "Evet\nhiç sorun yok."
    assert find_problems(text, kind_of, RULES, source_text=source) == [PageProblem(PROBLEM_BREAK, 1, 1, 4)]
    assert fit_text(text, kind_of, RULES, source_text=source) == FitResult("Evet hiç sorun yok.", ())
    # Orijinaldeki kısa bölünme başka bir satırdaysa bu satırdaki yeni bölünme yine bulunur.
    menu = "Evet⟦1⟧Tamam\niptal"
    assert find_problems(menu, kind_of, RULES, source_text="Yes\nNo⟦1⟧OK") == [PageProblem(PROBLEM_BREAK, 2, 1, 5)]


def test_source_bad_break_does_not_hide_other_problems() -> None:
    text = "Evet\n" + "uzun " * 10
    assert [p.kind for p in find_problems(text, kind_of, RULES, source_text="Yes\nNo")] == [PROBLEM_LINE]
    result = fit_text(text, kind_of, RULES, source_text="Yes\nNo")
    assert result.failed == ()
    assert find_problems(result.text, kind_of, RULES, source_text="Yes\nNo") == []
    assert fit_text(result.text, kind_of, RULES, source_text="Yes\nNo") == FitResult(result.text, ())


def test_non_breaking_space_is_kept() -> None:
    text = "Buradan köye tam 10 km yol var, hemen yürümeye başla yoksa geç kalırsın"
    result = fit_text(text, kind_of, FitRules(width=20, max_lines=4))
    assert result.failed == ()
    assert "10 km" in result.text
    assert all("10" not in line or "10 km" in line for line in result.text.split("\n"))
