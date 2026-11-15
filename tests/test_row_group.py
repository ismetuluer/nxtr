"""Satır grubu (`row_group`): koleksiyon kuralı yalnızca bağlama "Koleksiyon/anahtar" yazan biçimlerde geçerlidir."""

from __future__ import annotations

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.project import ImportedFile, Project, TranslationRow, in_collection, row_group
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import FitConfig, learn_group_rules, separate_groups
from nxceviri.core.translate.uppercase import UppercaseRules


def _row(file: str, context: str, fmt: str, i: int = 1, key: str = "k") -> TranslationRow:
    return TranslationRow(i, file, key, "src", "çeviri", "approved", "", (), None, context, fmt)


def test_slash_context_of_plugin_format_groups_by_file_name() -> None:
    row = _row("a.pak>x/y~z.sprbin", "/(Aang)", "kitt")
    assert row_group(row) == "y~z.sprbin"
    assert not in_collection(row)


def test_m2text_page_context_groups_by_file_name() -> None:
    row = _row("data/msg_en.mdf", "sayfa 0 / text, sayfa 1 / text", "m2text")
    assert row_group(row) == "msg_en.mdf"


def test_unity_collection_unchanged() -> None:
    assert row_group(_row("a.bundle>tables", "Dialogue/Jade_Intro_01", "unity")) == "Dialogue"
    assert in_collection(_row("a.bundle>tables", "Dialogue/Jade_Intro_01", "unity"))
    assert row_group(_row("a.bundle>tables", "/Adsız", "unity")) == ""  # adsız koleksiyon bugünkü gibi
    assert row_group(_row("a.bundle>Party", "PartyTeen5[en]", "unity")) == "Party"


def test_unreal_namespace_is_collection() -> None:
    assert row_group(_row("Game/Content/Game.locres", "Menu/Start", "unreal")) == "Menu"


def test_row_without_context_or_format_groups_by_file_name() -> None:
    assert row_group(_row("a.pak>m/b.msbt", "", "msbt")) == "b.msbt"
    assert row_group(_row("b.msbt", "C/1", "")) == "b.msbt"  # biçimi bilinmeyen satır koleksiyon sayılmaz


def _project() -> Project:
    project = Project.new()
    project.import_texts(
        [
            ImportedFile(
                "a.pak>x/one.sprbin", "0100", "kitt", "base", (TextEntry("1", 0, "A", (), context="/(Aang)"),)
            ),
            ImportedFile(
                "a.pak>x/two.sprbin",
                "0100",
                "kitt",
                "base",
                (TextEntry("1", 0, "B", (), context="/(Katara)"), TextEntry("2", 1, "B2", (), context="/(Sokka)")),
            ),
            ImportedFile("m.mdf", "0100", "m2text", "base", (TextEntry("1", 0, "C", (), context="sayfa 0 / text"),)),
            ImportedFile("t.bundle", "0100", "unity", "base", (TextEntry("UI/1", 0, "D", (), context="UI/Start"),)),
        ]
    )
    return project


def test_project_rows_carry_format() -> None:
    project = _project()
    groups = {r.file: row_group(r) for r in project.translation_rows()}
    assert groups == {
        "a.pak>x/one.sprbin": "one.sprbin",
        "a.pak>x/two.sprbin": "two.sprbin",
        "m.mdf": "m.mdf",
        "t.bundle": "UI",
    }
    assert {r.format for r in project.translation_rows()} == {"kitt", "m2text", "unity"}


def test_legacy_uppercase_group_marks_still_apply_as_row_marks() -> None:
    """Eski sürümün verdiği grup adlarıyla ("" ve "sayfa 0 ") kaydedilmiş işaretler aynı satırlara uygulanır."""
    project = _project()
    saved = UppercaseRules(frozenset({"", "sayfa 0 ", "UI"}), excluded=frozenset({("a.pak>x/two.sprbin", "2")}))
    project.set_uppercase_rules(saved)
    rules = project.uppercase_rules()
    applied = {(r.file, r.key) for r in project.translation_rows() if rules.applies(r.file, r.key, row_group(r))}
    assert applied == {("a.pak>x/one.sprbin", "1"), ("a.pak>x/two.sprbin", "1"), ("m.mdf", "1"), ("t.bundle", "UI/1")}
    assert rules.groups == frozenset({"UI"})  # hiçbir satırın grubu olmayan eski adlar düşer; Unity grubu kalır
    # Satır işaretini kaldırmak kalıcıdır: kaydedip yeniden okuyunca geri gelmez.
    off = rules.with_row("a.pak>x/one.sprbin", "1", "one.sprbin", False)
    project.set_uppercase_rules(off)
    again = project.uppercase_rules()
    assert not again.applies("a.pak>x/one.sprbin", "1", "one.sprbin")
    assert again.applies("a.pak>x/two.sprbin", "1", "two.sprbin")


def test_unity_uppercase_rules_unchanged() -> None:
    project = _project()
    saved = UppercaseRules(frozenset({"UI"}), frozenset({("m.mdf", "1")}))
    project.set_uppercase_rules(saved)
    assert project.uppercase_rules() == saved


def test_stale_empty_group_rule_does_not_override_file_rule() -> None:
    file_rule, stale = FitRules(40, 2), FitRules(10, 1)
    config = FitConfig(per_file={"a.pak>x/one.sprbin": file_rule, "b.msbt": file_rule}, per_group={"": stale})
    assert config.rules_for_row(_row("a.pak>x/one.sprbin", "/(Aang)", "kitt")) == file_rule
    assert config.rules_for_row(_row("b.msbt", "", "msbt")) == file_rule
    unity = _row("t.bundle", "/Adsız", "unity")
    assert config.rules_for_row(unity) == stale  # adsız Unity koleksiyonunun kendi kuralı bugünkü gibi


def test_plugin_slash_context_is_not_a_separate_group() -> None:
    rows = [_row("a.pak>x/one.sprbin", "/(Aang)", "kitt", 1), _row("a.pak>x/two.sprbin", "/(Katara)", "kitt", 2)]
    assert separate_groups(rows) == []
    assert learn_group_rules(rows, FitConfig()) == {}
    unity = [_row("t.bundle", "UI/Start", "unity")]
    assert separate_groups(unity) == ["UI"]
