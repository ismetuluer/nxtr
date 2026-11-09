"""Anahtar deseni kuralları (`FitConfig.per_key`) ve grup / anahtar istatistikleri (`core/translate/limits.py`)."""

from __future__ import annotations

from nxceviri.core.project import Project, TranslationRow
from nxceviri.core.translate.codekinds import KIND_LINE_BREAK, CodeKinds
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import FitConfig, load_config, save_config
from nxceviri.core.translate.limits import LimitStat, group_stats, key_stats, valid_pattern


def _row(
    key: str,
    source: str = "x",
    file: str = "a.msbt",
    context: str = "",
    labels: tuple[str, ...] = (),
) -> TranslationRow:
    return TranslationRow(1, file, key, source, "", "untranslated", "", labels, None, context)


def test_key_pattern_beats_group_file_and_project() -> None:
    config = FitConfig(
        default=FitRules(50, 4),
        per_file={"a.msbt": FitRules(40, 3)},
        per_group={"Dialogue": FitRules(30, 2)},
        per_key={"menu_*": FitRules(10, 1)},
    )
    row = _row("menu_start", file="Dialogue.tsv", context="Dialogue/menu_start")
    assert config.rules_for_row(row) == FitRules(10, 1)
    other = _row("talk_1", file="Dialogue.tsv", context="Dialogue/talk_1")
    assert config.rules_for_row(other) == FitRules(30, 2)


def test_key_pattern_beats_file_rule() -> None:
    config = FitConfig(per_file={"a.msbt": FitRules(40, 3)}, per_key={"*_title": FitRules(12, 1)})
    assert config.rules_for_row(_row("game_title")) == FitRules(12, 1)
    assert config.rules_for_row(_row("game_text")) == FitRules(40, 3)


def test_most_specific_pattern_wins() -> None:
    config = FitConfig(per_key={"menu_*": FitRules(10, 1), "menu_item_*": FitRules(20, 2), "*": FitRules(99, 9)})
    assert config.rules_for_row(_row("menu_item_3")) == FitRules(20, 2)
    assert config.rules_for_row(_row("menu_x")) == FitRules(10, 1)
    assert config.rules_for_row(_row("zzz")) == FitRules(99, 9)


def test_key_pattern_is_case_insensitive() -> None:
    config = FitConfig(per_key={"MENU_*": FitRules(10, 1)})
    assert config.rules_for_row(_row("Menu_Start")) == FitRules(10, 1)


def test_key_pattern_also_matches_context_tail() -> None:
    config = FitConfig(per_key={"hint_*": FitRules(10, 1)})
    assert config.rules_for_row(_row("0042", context="Dialogue/hint_3")) == FitRules(10, 1)
    assert config.rules_for_row(_row("0042", context="")) is None


def test_key_pattern_ignored_when_disabled() -> None:
    config = FitConfig(per_key={"*": FitRules(10, 1)}, enabled=False)
    assert config.rules_for_row(_row("a")) is None


def test_per_key_save_load_roundtrip() -> None:
    p = Project.new()
    config = FitConfig(default=FitRules(40, 3), per_key={"menu_*": FitRules(10, 1, 7)})
    save_config(p, config)
    assert load_config(p) == config


def test_old_project_without_keys_loads_empty() -> None:
    p = Project.new()
    p.set_setting("fit_config", '{"default": {"width": 40, "max_lines": 3}, "files": {}}')
    config = load_config(p)
    assert config.per_key == {}
    assert config.default == FitRules(40, 3)


def test_corrupt_key_rule_skipped() -> None:
    p = Project.new()
    p.set_setting("fit_config", '{"keys": {"a_*": {"width": 0, "max_lines": 1}, "b_*": {"width": 5, "max_lines": 2}}}')
    assert load_config(p).per_key == {"b_*": FitRules(5, 2)}


def test_valid_pattern() -> None:
    assert valid_pattern("menu_*")
    assert valid_pattern("exact_key")
    assert not valid_pattern("")
    assert not valid_pattern("   ")
    assert not valid_pattern("a\nb")


def test_group_stats_counts_and_longest_line() -> None:
    rows = [
        _row("1", "kısa", file="a.msbt"),
        _row("2", "bu satır epey uzun\nikinci", file="a.msbt"),
        _row("3", "üç\nsatır\nvar", file="b.msbt"),
    ]
    stats = {s.scope: s for s in group_stats(rows)}
    a = stats["group:a.msbt"]
    assert (a.rows, a.longest_source_line, a.max_source_lines) == (2, len("bu satır epey uzun"), 2)
    assert a.label == "a.msbt"
    b = stats["group:b.msbt"]
    assert (b.rows, b.longest_source_line, b.max_source_lines) == (1, 5, 3)


def test_group_stats_strips_codes_and_splits_on_line_break_codes() -> None:
    kinds = CodeKinds({"Satır": KIND_LINE_BREAK})
    rows = [_row("1", "⟦1⟧merhaba⟦2⟧dünya", labels=("Kod 0x05", "Satır"))]
    (stat,) = group_stats(rows, kinds)
    # satır sonu koduyla iki satıra bölünür; "Kod 0x05" görünen karakter sayılmaz
    assert (stat.longest_source_line, stat.max_source_lines) == (7, 2)


def test_group_stats_uses_context_group() -> None:
    rows = [_row("1", "ab", file="t.asset", context="Dialogue/k1"), _row("2", "abc", file="t.asset", context="Menu/k2")]
    assert {s.scope for s in group_stats(rows)} == {"group:Dialogue", "group:Menu"}


def test_group_stats_empty_and_blank_sources() -> None:
    assert group_stats([]) == []
    (stat,) = group_stats([_row("1", "")])
    assert (stat.rows, stat.longest_source_line, stat.max_source_lines) == (1, 0, 0)


def test_key_stats_matches_patterns() -> None:
    rows = [_row("menu_a", "uzun bir satır"), _row("MENU_b", "ab\ncd"), _row("talk", "zzz")]
    stats = {s.scope: s for s in key_stats(rows, ["menu_*", "yok_*"])}
    menu = stats["key:menu_*"]
    assert menu == LimitStat("key:menu_*", "menu_*", 2, len("uzun bir satır"), 2)
    assert stats["key:yok_*"].rows == 0
    assert stats["key:yok_*"].longest_source_line == 0
