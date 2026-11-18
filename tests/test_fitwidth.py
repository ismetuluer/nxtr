"""Fontla genişlik denetimi: kapsam ayarı (JSON), kutu (kapsam / satır), tolerans, QA bulgusu, ölçüm fontu seçimi."""

from __future__ import annotations

import json
import logging

import pytest

from nxceviri.core.project import Project, TranslationRow
from nxceviri.core.qa.checks import KIND_LABELS, SEVERITY_WARNING, check_row, run_checks
from nxceviri.core.qa.fonts import KIND_TMP_DYNAMIC, KIND_TMP_STATIC, KIND_TTF, FontInfo, FontReport
from nxceviri.core.qa.live import KIND_HINTS, LIVE_KINDS
from nxceviri.core.translate import widths
from nxceviri.core.translate.fit import FitRules
from nxceviri.core.translate.fitconfig import (
    BOX_GROUP,
    BOX_ROW,
    GROUP_PREFIX,
    KEY_PREFIX,
    SETTING_CONFIG,
    FitConfig,
    WidthRules,
    load_config,
    save_config,
)
from nxceviri.core.translate.fitwidth import (
    KIND_TOO_WIDE,
    SETTING_WIDTHS,
    build_measure,
    load_table,
    width_message,
)
from nxceviri.core.translate.status import Status

#: Her harf 1 birim: ölçüm karakter sayısına eşit olur, beklenen oranlar elle hesaplanabilir.
UNIT = widths.WidthTable(dict.fromkeys("abcdefghijklmnopqrstuvwxyzçğıöşü ", 1.0), name="Birim", approximate=False)


def _row(row_id: int, source: str, translation: str = "", file: str = "menu.msbt", key: str = "k") -> TranslationRow:
    status = Status.MACHINE if translation else Status.UNTRANSLATED
    return TranslationRow(row_id, file, key, source, translation, status, "", (), None)


# --- ayar (JSON) ------------------------------------------------------------------------------------------------


def test_width_rules_roundtrip_with_all_scopes() -> None:
    p = Project.new()
    config = FitConfig(
        default=FitRules(40, 3),
        width_default=WidthRules(True, 0.2, BOX_ROW),
        width_files={"menu.msbt": WidthRules()},
        width_groups={"Menu": WidthRules(False, 0.15, BOX_GROUP)},
        width_keys={"btn_*": WidthRules(True, 0.3, BOX_GROUP)},
    )
    save_config(p, config)
    assert load_config(p) == config
    data = json.loads(p.setting(SETTING_CONFIG))
    assert data["widths"]["default"] == {"enabled": True, "tolerance": 0.2, "box": "row"}
    assert data["widths"]["keys"] == {"btn_*": {"enabled": True, "tolerance": 0.3, "box": "group"}}


def test_old_project_without_widths_loads_unchanged() -> None:
    p = Project.new()
    old = '{"enabled": true, "default": {"width": 30, "max_lines": 2}, "files": {}}'
    p.set_setting(SETTING_CONFIG, old)
    config = load_config(p)
    assert config.default == FitRules(30, 2)
    assert config.width_default is None
    assert config.width_files == config.width_groups == config.width_keys == {}
    save_config(p, config)
    assert "widths" not in json.loads(p.setting(SETTING_CONFIG))  # genişlik yoksa JSON eskisi gibi kalır


def test_width_only_scope_needs_no_char_limits() -> None:
    p = Project.new()
    save_config(p, FitConfig(width_files={"menu.msbt": WidthRules()}))
    config = load_config(p)
    row = _row(1, "Start", "Başla")
    assert config.rules_for_row(row) is None  # karakter sınırı yok
    assert config.width_for_row(row) == (WidthRules(), "menu.msbt")


def test_corrupt_width_entries_are_logged_and_skipped(caplog: pytest.LogCaptureFixture) -> None:
    p = Project.new()
    p.set_setting(
        SETTING_CONFIG,
        json.dumps(
            {
                "default": None,
                "widths": {
                    "default": {"enabled": "evet"},
                    "files": {
                        "a": {"tolerance": -1},
                        "b": {"box": "piksel"},
                        "c": [1, 2],
                        "d": {"enabled": True, "tolerance": 0.25},
                    },
                    "groups": "bozuk",
                },
            }
        ),
    )
    with caplog.at_level(logging.WARNING):
        config = load_config(p)
    assert config.width_default is None
    assert config.width_files == {"d": WidthRules(True, 0.25, BOX_GROUP)}
    assert config.width_groups == {}
    assert len(caplog.records) >= 5


def test_widths_not_a_dict_is_ignored(caplog: pytest.LogCaptureFixture) -> None:
    p = Project.new()
    p.set_setting(SETTING_CONFIG, '{"default": {"width": 30, "max_lines": 2}, "widths": [1]}')
    with caplog.at_level(logging.WARNING):
        config = load_config(p)
    assert config.default == FitRules(30, 2)
    assert config.width_default is None
    assert caplog.records


def test_width_scope_precedence_and_disabled_override() -> None:
    config = FitConfig(
        width_default=WidthRules(),
        width_files={"off.msbt": WidthRules(enabled=False)},
        width_keys={"btn_*": WidthRules(tolerance=0.5)},
    )
    assert config.width_for_row(_row(1, "a", file="x.msbt")) == (WidthRules(), "")
    # Kapalı dosya girdisi proje ayarını o dosyada geçersiz kılar.
    assert config.width_for_row(_row(2, "a", file="off.msbt")) is None
    # Anahtar deseni dosyadan önce gelir.
    assert config.width_for_row(_row(3, "a", file="off.msbt", key="btn_ok")) == (
        WidthRules(tolerance=0.5),
        KEY_PREFIX + "btn_*",
    )


def test_group_scope_id_and_fit_disabled() -> None:
    config = FitConfig(width_groups={"menu.msbt": WidthRules()})
    assert config.width_for_row(_row(1, "a")) == (WidthRules(), GROUP_PREFIX + "menu.msbt")
    off = FitConfig(enabled=False, width_default=WidthRules())
    assert off.width_for_row(_row(1, "a")) is None  # sığdırma kapalıyken genişlik de denetlenmez


# --- kutu ve tolerans -------------------------------------------------------------------------------------------


def test_group_box_is_widest_single_line_source_in_scope() -> None:
    rows = [
        _row(1, "New Game", "Yeni Oyun"),  # 8 → 9: kutu 10 (en geniş), sorun yok
        _row(2, "Load", "Kayıtlı Oyunu Yükle"),  # 19 > 10 × 1.15
        _row(3, "Exit game!", "Çık"),
        _row(4, "Line one\nline two", "çok uzun bir satır ki kutuya sığmaz"),  # çok satırlı: kutuya girmez
        _row(5, "Unrelated very long source text", "x", file="other.msbt"),  # başka kapsam
    ]
    config = FitConfig(width_files={"menu.msbt": WidthRules()})
    measure = build_measure(rows, config, UNIT)
    assert measure.boxes == {"menu.msbt": pytest.approx(10.0)}  # "Exit game!" (ünlem tabloda yok → ortalama 1)
    assert measure.problem(rows[0]) is None
    found = measure.problem(rows[1])
    assert found is not None
    assert found.ratio == pytest.approx(19 / 10)
    assert measure.problem(rows[3]) is None  # çok satırlı orijinal denetlenmez
    assert measure.problem(rows[4]) is None  # kapsam dışı


def test_row_box_uses_own_source() -> None:
    rows = [_row(1, "New Game", "Yeni Oyun"), _row(2, "Exit game!", "Çık")]
    measure = build_measure(rows, FitConfig(width_default=WidthRules(box=BOX_ROW)), UNIT)
    found = measure.problem(rows[0])  # 9 / 8 = %112.5 ≤ %115 → sorun yok
    assert found is None
    longer = _row(1, "New Game", "Yeni Oyunlar")  # 12 / 8 = %150
    found = measure.problem(longer)
    assert found is not None
    assert found.ratio == pytest.approx(1.5)


def test_tolerance_controls_the_limit() -> None:
    row = _row(1, "abcdefghij", "abcdefghijkl")  # %120
    loose = build_measure([row], FitConfig(width_default=WidthRules(tolerance=0.25)), UNIT)
    strict = build_measure([row], FitConfig(width_default=WidthRules(tolerance=0.1)), UNIT)
    assert loose.problem(row) is None
    assert strict.problem(row) is not None


def test_reading_reports_ratio_even_under_the_limit() -> None:
    row = _row(1, "abcdefghij", "abcdefghijk")
    measure = build_measure([row], FitConfig(width_default=WidthRules()), UNIT)
    reading = measure.reading(row, row.translation)
    assert reading is not None
    assert reading.ratio == pytest.approx(1.1)
    assert reading.limit == pytest.approx(1.15)
    assert not reading.over
    assert measure.reading(row, "abcdefghijklm") is not None
    assert measure.reading(row, "abcdefghijklm").over  # type: ignore[union-attr]


def test_no_width_rules_means_no_work() -> None:
    rows = [_row(1, "a", "b")]
    measure = build_measure(rows, FitConfig(default=FitRules(10, 1)), UNIT)
    assert not measure.active
    assert measure.boxes == {}
    assert measure.reading(rows[0], "b") is None


# --- QA ---------------------------------------------------------------------------------------------------------


def test_check_row_reports_width_warning_with_numbers() -> None:
    rows = [_row(1, "New Game", "Yeni Oyun"), _row(2, "Load", "Kayıtlı Oyunu Yükle")]
    config = FitConfig(width_files={"menu.msbt": WidthRules()})
    measure = build_measure(rows, config, UNIT)
    issues = [i for i in check_row(rows[1], "", "", None, config, widths=measure) if i.kind == KIND_TOO_WIDE]
    assert len(issues) == 1
    assert issues[0].severity == SEVERITY_WARNING
    assert issues[0].message == width_message(19 / 8, 0.15, BOX_GROUP)
    assert "%238" in issues[0].message
    assert "%115" in issues[0].message
    assert "oyunda taşabilir" in issues[0].message
    assert KIND_TOO_WIDE in KIND_LABELS
    assert KIND_TOO_WIDE in LIVE_KINDS
    assert KIND_TOO_WIDE in KIND_HINTS


def test_width_message_names_the_box_kind() -> None:
    assert width_message(1.28, 0.15, BOX_GROUP) == (
        "Genişlik %128, sınır %115 (kapsamdaki en geniş orijinale göre); oyunda taşabilir."
    )
    assert "satırın kendi orijinaline göre" in width_message(1.28, 0.15, BOX_ROW)


def test_run_checks_uses_given_boxes_for_subset() -> None:
    """Birkaç satır yeniden denetlenirken kutu tüm projeden hesaplanmış ölçümden gelir (alt kümeden değil)."""
    rows = [_row(1, "A much longer item", "x"), _row(2, "Load", "Yükle bunu")]
    config = FitConfig(width_default=WidthRules())
    measure = build_measure(rows, config, UNIT)
    issues = run_checks([rows[1]], "", "", None, config, widths=measure, terms={})
    assert not [i for i in issues if i.kind == KIND_TOO_WIDE]


def test_width_warning_does_not_change_newline_check() -> None:
    row = _row(1, "Load", "Kayıtlı\nOyunu Yükle")
    config = FitConfig(width_default=WidthRules())
    kinds = {i.kind for i in check_row(row, "", "", None, config, widths=build_measure([row], config, UNIT))}
    assert "newlines" in kinds
    assert KIND_TOO_WIDE in kinds


# --- ölçüm tablosu ----------------------------------------------------------------------------------------------

LATIN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def _font(name: str, table_chars: str, kind: str = KIND_TMP_STATIC, lang: bool = False) -> FontInfo:
    table = widths.WidthTable(dict.fromkeys(table_chars, 10.0), name=name, approximate=False)
    return FontInfo(name, "fonts.bundle", kind, frozenset(LATIN + table_chars), lang, widths=table)


def test_measuring_table_prefers_latin_static_with_most_ascii_letters() -> None:
    report = FontReport(
        [
            _font("Kısmi", "abc"),
            _font("Tam", LATIN),
            _font("Tam Büyük", LATIN + "çğış"),
            _font("Japonca", LATIN + "あいう", lang=True),
            _font("Dinamik", LATIN + "あいうえお", kind=KIND_TMP_DYNAMIC),
        ]
    )
    table = report.measuring_table()
    assert table is not None
    assert table.name == "Tam Büyük"  # eşit ASCII kapsamında büyük tablo


def test_measuring_table_none_without_tables() -> None:
    no_table = FontInfo("Eski", "a.bundle", KIND_TTF, frozenset(LATIN), False)
    assert FontReport([no_table]).measuring_table() is None
    assert FontReport().measuring_table() is None


def test_ttf_widths_reads_latin_font_and_skips_cjk() -> None:
    from nxceviri.core.qa.fonts import _ttf_widths
    from tests.test_widths import make_ttf

    data = make_ttf(1000, dict.fromkeys("abc", 500))
    table = _ttf_widths(data, frozenset("abc "), "Latin")
    assert table is not None
    assert table.advances["a"] == pytest.approx(0.5)
    cjk = frozenset(chr(0x4E00 + i) for i in range(300))
    assert _ttf_widths(data, cjk, "Mincho") is None  # dile özgü büyük font açılmaz
    assert _ttf_widths(b"bozuk", frozenset("a"), "x") is None


def test_load_table_falls_back_to_approximate(caplog: pytest.LogCaptureFixture) -> None:
    assert load_table("").approximate
    with caplog.at_level(logging.WARNING):
        assert load_table("{bozuk").approximate
    stored = load_table(widths.dump(UNIT))
    assert stored.name == "Birim"
    assert not stored.approximate
    assert SETTING_WIDTHS == "fit_widths"
