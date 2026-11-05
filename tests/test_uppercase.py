"""Büyük harfle çizilen metinler: i → İ dönüşümü, proje kaydı ve dışa aktarma."""

from __future__ import annotations

from pathlib import Path

from nxceviri.core.export.layeredfs import (
    LAYOUT_ATMOSPHERE,
    ExportInfo,
    ExportOptions,
    ExportResult,
    _info_text,
    collect_translations,
)
from nxceviri.core.project import Project, TranslationRow
from nxceviri.core.translate.uppercase import UppercaseRules, dotted_capitals


def _row(i: int, key: str, translation: str, context: str, status: str = "approved") -> TranslationRow:
    return TranslationRow(i, "tables.bundle", key, "src", translation, status, "", (), None, context)


def test_dotted_capitals_only_touches_lowercase_i() -> None:
    assert dotted_capitals("Işık ve kitap ⟦1⟧ işi") == "Işık ve kİtap ⟦1⟧ İşİ"
    assert dotted_capitals("ıI") == "ıI"  # noktasız harfler zaten doğru büyür


def test_rules_apply_by_group_or_row() -> None:
    rules = UppercaseRules(frozenset({"World_Sign"}), frozenset({("tables.bundle", "UI_en/9")}))
    assert rules.applies("tables.bundle", "World_Sign_en/1", "World_Sign")
    assert rules.applies("tables.bundle", "UI_en/9", "UI")
    assert not rules.applies("tables.bundle", "UI_en/10", "UI")
    assert not UppercaseRules()


def test_rules_survive_dump_and_corrupt_values() -> None:
    rules = UppercaseRules(frozenset({"Menü"}), frozenset({("a>b", "k/1")}))
    assert UppercaseRules.load(*rules.dump()) == rules
    assert UppercaseRules.load("{bozuk", "[[1, 2]]") == UppercaseRules()
    assert UppercaseRules.load("", "") == UppercaseRules()


def test_collect_translations_converts_only_marked_rows() -> None:
    rows = [
        _row(1, "World_Sign_en/1", "Paris Sokakları ve Işık", "World_Sign/Streets"),
        _row(2, "Dialogue_en/2", "Nasılsın, iyi misin?", "Dialogue/Hello"),
    ]
    rules = UppercaseRules(frozenset({"World_Sign"}))
    by_file, written, _errors, _untranslated = collect_translations(rows, "", rules)
    assert written == 2
    assert by_file["tables.bundle"]["World_Sign_en/1"] == "Parİs Sokakları ve Işık"
    assert by_file["tables.bundle"]["Dialogue_en/2"] == "Nasılsın, iyi misin?"  # işaretsiz satır değişmez
    # İşaret yoksa hiçbir şey değişmez.
    plain = collect_translations(rows, "")[0]
    assert plain["tables.bundle"]["World_Sign_en/1"] == "Paris Sokakları ve Işık"
    # Harf dönüştürme açıksa önce İ yazılır, sonra büyük harf I'ya dönüştürülür.
    converted = collect_translations(rows, "İ", rules)[0]
    assert converted["tables.bundle"]["World_Sign_en/1"] == "ParIs Sokakları ve Işık"


def test_project_persists_rules(tmp_path: Path) -> None:
    project = Project.new()
    assert not project.uppercase_rules()
    rules = UppercaseRules(frozenset({"UI_Settings"}), frozenset({("f", "k")}))
    project.set_uppercase_rules(rules)
    path = tmp_path / "p.nxproj"
    project.save_as(path)
    project.close()
    reopened = Project.open(path)
    assert reopened.uppercase_rules() == rules
    reopened.close()


def test_info_file_reports_uppercase_rows() -> None:
    result = ExportResult(Path("x"), rows_written=3, rows_uppercase=2)
    info = _info_text(
        ExportInfo("Oyun", "0100DDDD00000000", 0, None), ExportOptions(LAYOUT_ATMOSPHERE, Path("x"), "x"), result
    )
    assert "Büyük harfle gösterilen satır (i → İ yazıldı): 2" in info


def test_row_exception_inside_marked_group() -> None:
    rules = UppercaseRules(frozenset({"UI"})).with_row("f", "UI_en/1", "UI", False)
    assert not rules.applies("f", "UI_en/1", "UI")  # istisna
    assert rules.applies("f", "UI_en/2", "UI")  # tablonun geri kalanı işaretli
    back = rules.with_row("f", "UI_en/1", "UI", True)
    assert back.applies("f", "UI_en/1", "UI")
    assert not back.excluded


def test_row_marked_outside_group_and_unmarked_again() -> None:
    rules = UppercaseRules().with_row("f", "Narr_en/5", "Narr", True)
    assert rules.applies("f", "Narr_en/5", "Narr")
    assert not rules.with_row("f", "Narr_en/5", "Narr", False).applies("f", "Narr_en/5", "Narr")
    assert not rules.with_row("f", "Narr_en/5", "Narr", False).excluded  # tablo işaretli değil: istisna gerekmez


def test_exceptions_persist_and_export_skips_them() -> None:
    rules = UppercaseRules(frozenset({"World_Sign"})).with_row("tables.bundle", "World_Sign_en/2", "World_Sign", False)
    assert UppercaseRules.load(*rules.dump()) == rules
    assert UppercaseRules.load("[]", "[]", "bozuk") == UppercaseRules()
    rows = [
        _row(1, "World_Sign_en/1", "Sokak", "World_Sign/A"),
        _row(2, "World_Sign_en/2", "Kitap", "World_Sign/B"),
    ]
    out = collect_translations(rows, "", rules)[0]["tables.bundle"]
    assert out == {"World_Sign_en/1": "Sokak", "World_Sign_en/2": "Kitap"}
    rows[1] = _row(2, "World_Sign_en/2", "Kitap Evi", "World_Sign/B")
    rows[0] = _row(1, "World_Sign_en/1", "Kitap Evi", "World_Sign/A")
    out = collect_translations(rows, "", rules)[0]["tables.bundle"]
    assert out == {"World_Sign_en/1": "Kİtap Evİ", "World_Sign_en/2": "Kitap Evi"}
