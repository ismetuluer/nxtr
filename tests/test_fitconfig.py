"""Metin sığdırma proje ayarları ve orijinalden sınır öğrenme."""

from __future__ import annotations

import logging

import pytest

from nxceviri.core.project import Project, TranslationRow
from nxceviri.core.translate.codekinds import KIND_OTHER, KIND_PAGE_BREAK, CodeKinds
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import (
    SETTING_CONFIG,
    SETTING_KINDS,
    FitConfig,
    FitOptions,
    learn_group_rules,
    learn_rules,
    load_config,
    save_config,
)


def _row(source: str, labels: tuple[str, ...] = (), file: str = "a.msbt") -> TranslationRow:
    return TranslationRow(1, file, "k", source, "", "untranslated", "", labels, None)


def test_save_load_roundtrip() -> None:
    p = Project.new()
    config = FitConfig(
        default=FitRules(40, 3, 5),
        per_file={"b.msbt": FitRules(30, 2)},
        kinds=CodeKinds({"Kod 0x05": "page_break"}),
        options=FitOptions(spaces=False, space_before_punct=True, repeated_punct=False),
    )
    save_config(p, config)
    assert load_config(p) == config


def test_load_empty_project_gives_defaults(caplog: pytest.LogCaptureFixture) -> None:
    p = Project.new()
    with caplog.at_level(logging.WARNING):
        config = load_config(p)
    assert config == FitConfig()
    assert config.rules_for("x") is None
    assert not caplog.records


def test_load_corrupt_json_gives_defaults() -> None:
    p = Project.new()
    p.set_setting(SETTING_CONFIG, "{bozuk")
    p.set_setting(SETTING_KINDS, "[[[")
    assert load_config(p) == FitConfig()


def test_invalid_fields_skip_entry_and_warn(caplog: pytest.LogCaptureFixture) -> None:
    p = Project.new()
    p.set_setting(
        SETTING_CONFIG,
        '{"default": {"width": -1, "max_lines": 3}, "files": {"a": {"width": "x", "max_lines": 2},'
        ' "b": {"width": 20, "max_lines": 2}}}',
    )
    with caplog.at_level(logging.WARNING):
        config = load_config(p)
    assert config.default is None
    assert config.per_file == {"b": FitRules(20, 2)}
    assert len(caplog.records) == 2


def test_rules_for_prefers_file_override() -> None:
    config = FitConfig(default=FitRules(40, 3), per_file={"a.msbt": FitRules(20, 2)})
    assert config.rules_for("a.msbt") == FitRules(20, 2)
    assert config.rules_for("b.msbt") == FitRules(40, 3)


def test_disabled_config_keeps_rules_but_applies_none() -> None:
    config = FitConfig(default=FitRules(40, 3), per_file={"a.msbt": FitRules(20, 2)}, enabled=False)
    assert config.rules_for("a.msbt") is None
    assert config.rules_for("b.msbt") is None
    p = Project.new()
    save_config(p, config)
    loaded = load_config(p)
    assert loaded == config  # kapalıyken sınırlar saklanır, yeniden açınca geri gelir
    assert not loaded.enabled


def test_old_config_without_enabled_key_is_enabled(caplog: pytest.LogCaptureFixture) -> None:
    p = Project.new()
    p.set_setting(SETTING_CONFIG, '{"default": {"width": 20, "max_lines": 2}, "files": {}}')
    with caplog.at_level(logging.WARNING):
        config = load_config(p)
    assert config.enabled
    assert config.rules_for("x") == FitRules(20, 2)
    assert not caplog.records


def test_non_bool_enabled_is_enabled() -> None:
    p = Project.new()
    p.set_setting(SETTING_CONFIG, '{"default": {"width": 20, "max_lines": 2}, "enabled": "hayır"}')
    assert load_config(p).enabled


def test_kind_of_row_out_of_range_is_other() -> None:
    kind_of = FitConfig().kind_of_row(_row("a⟦1⟧b", ("Sayfa sonu",)))
    assert kind_of(1) == KIND_PAGE_BREAK
    assert kind_of(2) == KIND_OTHER
    assert kind_of(0) == KIND_OTHER


def test_learn_rules_from_sources() -> None:
    labels = ("Sayfa sonu",)
    rows = [
        _row("short\nline two\nthree", ()),
        _row("x" * 35 + "\nb", ()),
        _row("one\ntwo⟦1⟧" + "y" * 10, labels),
    ]
    assert learn_rules(rows, CodeKinds({})) == FitRules(width=35, max_lines=3)
    assert learn_rules([], CodeKinds({})) is None
    assert learn_rules([_row("")], CodeKinds({})) is None


def _grow(source: str, file: str = "a.msbt", context: str = "") -> TranslationRow:
    return TranslationRow(1, file, "k", source, "", "untranslated", "", (), None, context)


def test_rules_for_row_priority_group_over_file_over_project() -> None:
    config = FitConfig(
        default=FitRules(40, 3),
        per_file={"a.msbt": FitRules(20, 2)},
        per_group={"Menu": FitRules(10, 1)},
    )
    assert config.rules_for_row(_grow("x", "a.msbt", "Menu/k")) == FitRules(10, 1)
    assert config.rules_for_row(_grow("x", "a.msbt", "Dialogue/k")) == FitRules(20, 2)
    assert config.rules_for_row(_grow("x", "b.msbt", "Dialogue/k")) == FitRules(40, 3)
    assert config.rules_for_row(_grow("x", "dir/Menu")) == FitRules(10, 1)  # bağlamsız satırda grup dosya adıdır
    assert config.rules_for_row(_grow("x", "dir/Other")) == FitRules(40, 3)
    assert config.rules_for("a.msbt", "Menu") == FitRules(10, 1)


def test_group_rules_disabled_applies_none() -> None:
    config = FitConfig(per_group={"Menu": FitRules(10, 1)}, enabled=False)
    assert config.rules_for_row(_grow("x", "a.msbt", "Menu/k")) is None


def test_group_rules_roundtrip_and_old_config_without_groups() -> None:
    p = Project.new()
    config = FitConfig(default=FitRules(40, 3), per_group={"Menu": FitRules(10, 1, 4)})
    save_config(p, config)
    assert load_config(p) == config
    p.set_setting(SETTING_CONFIG, '{"default": {"width": 20, "max_lines": 2}, "files": {}}')  # eski proje
    old = load_config(p)
    assert old.per_group == {}
    assert old.default == FitRules(20, 2)


def test_invalid_group_rules_skipped(caplog: pytest.LogCaptureFixture) -> None:
    p = Project.new()
    p.set_setting(
        SETTING_CONFIG,
        '{"groups": {"A": {"width": 0, "max_lines": 2}, "B": {"width": 9, "max_lines": 2}}}',
    )
    with caplog.at_level(logging.WARNING):
        config = load_config(p)
    assert config.per_group == {"B": FitRules(9, 2)}
    assert len(caplog.records) == 1
    p.set_setting(SETTING_CONFIG, '{"groups": [1]}')
    assert load_config(p).per_group == {}


def test_learn_group_rules_separate_limits() -> None:
    rows = [
        _grow("x" * 100, "a.msbt", "Long/1"),
        _grow("y" * 90, "a.msbt", "Long/2"),
        _grow("z" * 40, "a.msbt", "Short/1"),
    ]
    config = FitConfig(default=FitRules(100, 1))
    assert learn_group_rules(rows, config) == {"Short": FitRules(40, 1)}  # Long, proje sınırıyla aynı: kayıt yok


def test_learn_group_rules_uses_file_rules_as_parent_and_drops_redundant() -> None:
    rows = [_grow("x" * 40, "a.msbt", "G/1"), _grow("y" * 30, "b.msbt", "H/1")]
    config = FitConfig(
        default=FitRules(100, 1),
        per_file={"a.msbt": FitRules(40, 1)},
        per_group={"G": FitRules(5, 1)},  # eski, artık gereksiz kural silinmeli
    )
    assert learn_group_rules(rows, config) == {"H": FitRules(30, 1)}


def test_learn_group_rules_keeps_unmeasurable_group_and_variable_width() -> None:
    rows = [_grow("", "a.msbt", "E/1"), _grow("x" * 10, "a.msbt", "F/1")]
    config = FitConfig(default=FitRules(50, 2, 9), per_group={"E": FitRules(7, 1)})
    learned = learn_group_rules(rows, config)
    assert learned == {"E": FitRules(7, 1), "F": FitRules(10, 1, 9)}


def test_learn_group_rules_skips_single_file_basename_groups() -> None:
    rows = [_grow("x" * 11, "a/Talk.msbt"), _grow("y" * 50, "b/Talk.msbt"), _grow("z" * 5, "a/Solo.msbt")]
    config = FitConfig(
        per_file={"a/Talk.msbt": FitRules(40, 3), "b/Talk.msbt": FitRules(30, 2)},
        per_group={"Solo.msbt": FitRules(9, 1)},
    )
    learned = learn_group_rules(rows, config)
    assert learned == {}  # Talk.msbt'nin tüm dosyalarının kuralı var; Solo.msbt tek dosyalık: eski kural atılır


def test_learn_group_rules_multi_file_group_without_file_rules() -> None:
    rows = [_grow("x" * 11, "a/Talk.msbt"), _grow("y" * 50, "b/Talk.msbt")]
    config = FitConfig(default=FitRules(100, 1))
    assert learn_group_rules(rows, config) == {"Talk.msbt": FitRules(50, 1)}


def test_file_rule_beats_basename_group_rule() -> None:
    config = FitConfig(
        default=FitRules(100, 1),
        per_file={"a/Talk.msbt": FitRules(40, 3)},
        per_group={"Talk.msbt": FitRules(11, 2), "Menu": FitRules(7, 1)},
    )
    assert config.rules_for_row(_grow("x", "a/Talk.msbt")) == FitRules(40, 3)
    assert config.rules_for_row(_grow("x", "b/Talk.msbt")) == FitRules(11, 2)
    assert config.rules_for_row(_grow("x", "a/Talk.msbt", "Menu/k")) == FitRules(7, 1)  # bağlamdan gelen grup kazanır
