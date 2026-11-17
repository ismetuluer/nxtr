"""Biçim eklentisinin "satır sonu yasak" bildirimi (`forbids_newline`, TECH_DEBT 91).

Bildiren eklentide çeviride gerçek satır sonu (`\\n`, `\\r`) varsa Kontrol Et'te hata bulgusu çıkar ve dışa aktarmada o
satır yazılmaz (orijinal kalır, bildirilir). Satır sonu kodu (`⟦n⟧`) satır sonu sayılmaz. Bildirmeyen eklentide
davranış değişmez (satır sonu sayısı farkı yalnızca uyarıdır).
"""

from __future__ import annotations

import pytest

from nxceviri.core.formats import registry
from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.formats.unity import UnityPlugin
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.qa.autofix import local_fix
from nxceviri.core.qa.checks import SEVERITY_ERROR, SEVERITY_WARNING, check_row
from nxceviri.core.translate.status import Status

TSV_KEY = "TSV|7|en|2"


def _row(translation: str, *, forbidden: bool, source: str = "time ⟦1⟧ min⟦2⟧end") -> TranslationRow:
    return TranslationRow(
        1,
        "a.bundle",
        TSV_KEY,
        source,
        translation,
        Status.MACHINE,
        "",
        ("Değişken {}", "Satır sonu"),
        None,
        format="unity",
        newline_forbidden=forbidden,
    )


def test_unity_forbids_newline_only_in_tsv_cells() -> None:
    plugin = UnityPlugin()
    assert plugin.forbids_newline(TSV_KEY)
    assert not plugin.forbids_newline("SRT|7|en|0")  # altyazıda satır sonu metnin parçası
    assert not plugin.forbids_newline("UI_en/1")  # String Table
    assert not plugin.forbids_newline("I2|3|0|1")


def test_builtin_declarations() -> None:
    """Yalnızca yazıcısı satır sonunu kesinlikle taşıyamayan eklenti bildirir (koddan ve biçim notlarından)."""
    declared = {p.name for p in registry.BUILTIN_PLUGINS if hasattr(p, "forbids_newline")}
    assert declared == {"unity"}


def test_registry_asks_the_plugin_and_tolerates_missing_or_broken_hooks(monkeypatch: pytest.MonkeyPatch) -> None:
    assert registry.forbids_newline("unity", TSV_KEY)
    assert not registry.forbids_newline("unity", "UI_en/1")
    assert not registry.forbids_newline("msbt", "Menu_Start")  # bildirmeyen eklenti
    assert not registry.forbids_newline("bilinmeyen", "x")

    class Broken:
        name = "kirik"

        def forbids_newline(self, key: str) -> bool:
            raise RuntimeError("eklenti hatası")

    monkeypatch.setattr(registry, "plugin_for_kind", lambda kind, title_id=None: Broken())
    registry.reset_user_plugins()
    try:
        assert not registry.forbids_newline("kirik", "x")  # hata projeyi açtırmamazlık etmez; kural yok sayılır
    finally:
        registry.reset_user_plugins()


def test_project_rows_carry_the_rule() -> None:
    project = Project.new()
    codes = (ControlCode(b"{}", "Değişken {}"), ControlCode(b"\\n", "Satır sonu"))
    project.import_texts(
        [
            ImportedFile(
                "a.bundle",
                "0100AAAA00000000",
                "unity",
                "base",
                (
                    TextEntry(TSV_KEY, 0, "time ⟦1⟧ min⟦2⟧end", codes),
                    TextEntry("UI_en/1", 1, "Hello", ()),
                ),
            )
        ]
    )
    rows = {r.key: r for r in project.translation_rows()}
    assert rows[TSV_KEY].newline_forbidden
    assert not rows["UI_en/1"].newline_forbidden


def test_check_row_reports_forbidden_newline_as_error() -> None:
    issues = [i for i in check_row(_row("süre ⟦1⟧ dk\n⟦2⟧son", forbidden=True), "", "") if i.kind == "newlines"]
    assert [i.severity for i in issues] == [SEVERITY_ERROR]
    assert "satır sonu" in issues[0].message
    # Satır sonu kodu (⟦2⟧) satır sonu sayılmaz.
    assert not [i for i in check_row(_row("süre ⟦1⟧ dk⟦2⟧son", forbidden=True), "", "") if i.kind == "newlines"]
    assert [i for i in check_row(_row("a\r⟦1⟧⟦2⟧", forbidden=True), "", "") if i.severity == SEVERITY_ERROR]


def test_without_the_rule_behaviour_is_unchanged() -> None:
    issues = [i for i in check_row(_row("süre ⟦1⟧ dk\n⟦2⟧son", forbidden=False), "", "") if i.kind == "newlines"]
    assert [i.severity for i in issues] == [SEVERITY_WARNING]


def test_fix_joins_the_lines() -> None:
    assert local_fix(_row("süre ⟦1⟧ dk\n⟦2⟧son", forbidden=True), kinds=["newlines"]) == "süre ⟦1⟧ dk ⟦2⟧son"
