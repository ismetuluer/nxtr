"""Unity TextAsset yerelleştirmesi: SRT altyazıları ve dil sütunlu TSV tabloları (Despelote biçimi)."""

from __future__ import annotations

import pytest
import UnityPy

from nxceviri.core.formats.base import SOURCE_LANGUAGE, FormatError, TextEntry
from nxceviri.core.formats.unity import UnityPlugin, loctext
from tests.unitybuild import build_bundle, text_asset

PLUGIN = UnityPlugin()

SRT_EN = (
    "﻿1\r\n00:00:00,000 --> 00:00:04,1\r\nHello, <i>neighbor</i>!\r\n\r\n"
    "2\r\n00:00:05,0 --> 00:00:06,5\r\nOne line\nTwo lines {0}\r\n\r\n"
    "3\r\n00:00:07,000 --> 00:00:08,000\r\nBefore\r\n\r\nafter blank line\r\n"
)
SRT_ES = "1\r\n00:00:00,000 --> 00:00:04,100\r\nHola, vecino!\r\n"
UI_TSV = (
    "ID\tes\ten\tfr\r\n"
    "0\tcomenzar\tstart\tcommencer\r\n"
    "1\ttiempo {} min\\nfin\ttime {} min\\nend\ttemps {} min\\nfin\r\n"
    "2\t\t\t\r\n"
)
DIALOGUE_TSV = (
    "path\tvoice name\tvoice type\tsub index\tsub timestamp\t[es]\t[en]\t[fr]\r\n"
    "01_Kids\\Talk\tNina1\tconversation\t1\t0:00:00,292 --> 0:00:04,000\tHola\tHi\tSalut\r\n"
    "01_Kids\\Talk\tNino1\tconversation\t2\t0:00:04,167 --> 0:00:09,334\tUno\\ndos\tOne\\ntwo\tUn\\ndeux\r\n"
)
NOT_TABLE = '{\r\n  "name": "com.example.package"\r\n}'


def _bundle() -> bytes:
    return build_bundle(
        [
            text_asset("Nina1[en]", SRT_EN),
            text_asset("Nina1[es]", SRT_ES),
            text_asset("loc_UI", UI_TSV),
            text_asset("loc_dialogue", DIALOGUE_TSV),
            text_asset("package", NOT_TABLE),
        ]
    )


def _by_context(entries: list[TextEntry]) -> dict[str, TextEntry]:
    return {e.context: e for e in entries}


# --- ayrıştırıcı ------------------------------------------------------------------------------


def test_srt_cues_keep_exact_spans() -> None:
    cues = loctext.parse_srt(SRT_EN)
    assert [c.text for c in cues] == [
        "Hello, <i>neighbor</i>!",
        "One line\nTwo lines {0}",
        "Before\r\n\r\nafter blank line",
    ]
    for cue in cues:
        assert SRT_EN[cue.start : cue.end] == cue.text


def test_srt_detection_and_language_tag() -> None:
    assert loctext.is_srt(SRT_EN)
    assert loctext.is_srt(SRT_ES)
    assert not loctext.is_srt(UI_TSV)
    assert not loctext.is_srt(NOT_TABLE)
    assert loctext.srt_language("Nina1[en]") == "en"
    assert loctext.srt_language("[ES]shop convo_x") == "es"
    assert loctext.srt_language("credits") == ""


def test_replace_spans_only_touches_given_ranges() -> None:
    cues = loctext.parse_srt(SRT_EN)
    out = loctext.replace_spans(SRT_EN, [(cues[0].start, cues[0].end, "Merhaba!")])
    assert out == SRT_EN.replace("Hello, <i>neighbor</i>!", "Merhaba!")


def test_tsv_languages_rows_and_label() -> None:
    table = loctext.parse_tsv(DIALOGUE_TSV)
    assert table is not None
    assert table.languages == {"es": 5, "en": 6, "fr": 7}
    assert [line for line, _ in table.rows] == [1, 2]
    assert table.label(table.rows[0][1]) == "01_Kids\\Talk/Nina1/conversation/1"
    assert loctext.parse_tsv(NOT_TABLE) is None
    assert loctext.parse_tsv("a\tb\tc\r\n1\t2\t3") is None  # dil sütunu yok


def test_tsv_ignores_short_rows_and_roundtrips() -> None:
    table = loctext.parse_tsv(UI_TSV)
    assert table is not None
    assert [line for line, _ in table.rows] == [1, 2, 3]  # son boş satır (tek hücre) yok sayılır
    assert loctext.replace_cells(table, {}) == UI_TSV
    out = loctext.replace_cells(table, {(1, 2): "başla"})
    assert out == UI_TSV.replace("\tstart\t", "\tbaşla\t")


# --- eklenti ----------------------------------------------------------------------------------


def test_extract_english_only_with_controls() -> None:
    entries = PLUGIN.extract(_bundle(), {SOURCE_LANGUAGE: None})
    got = _by_context(entries)
    assert "package" not in got
    assert sorted(e.source for e in entries if e.context == "Nina1[en]") == sorted(
        ["Hello, ⟦1⟧neighbor⟦2⟧!", "One line\nTwo lines ⟦1⟧", "Before\r\n\r\nafter blank line"]
    )
    ui = [e for e in entries if e.context.startswith("loc_UI/")]
    assert [e.source for e in ui] == ["start", "time ⟦1⟧ min⟦2⟧end"]  # boş hücre atlanır
    assert [c.label for c in ui[1].codes] == ["Değişken {}", "Satır sonu"]
    assert all(e.key.split("|")[2] == "en" for e in entries)  # İspanyolca altyazı/sütun yok


def test_extract_respects_chosen_source_language() -> None:
    es = PLUGIN.extract(_bundle(), {SOURCE_LANGUAGE: "es"})
    assert {e.source for e in es if e.context == "Nina1[es]"} == {"Hola, vecino!"}
    assert {e.key.split("|")[2] for e in es} == {"es"}
    fr = PLUGIN.extract(_bundle(), {SOURCE_LANGUAGE: "fr"})
    assert not [e for e in fr if e.context in {"Nina1[en]", "Nina1[es]"}]  # altyazıda fr yok
    assert {e.key.split("|")[2] for e in fr} == {"fr"}


def test_extract_without_context_reads_every_language() -> None:
    langs = {e.key.split("|")[2] for e in PLUGIN.extract(_bundle())}
    assert langs == {"en", "es", "fr"}


def test_inject_roundtrip_with_originals_is_identical() -> None:
    bundle = _bundle()
    originals = {e.key: e.source for e in PLUGIN.extract(bundle, {SOURCE_LANGUAGE: None})}
    assert PLUGIN.inject(bundle, originals) == bundle
    assert PLUGIN.inject(bundle, {}) == bundle


def test_inject_writes_turkish_into_source_language_only() -> None:
    bundle = _bundle()
    entries = PLUGIN.extract(bundle, {SOURCE_LANGUAGE: None})
    by_source = {e.source: e for e in entries}
    translations = {
        by_source["Hello, ⟦1⟧neighbor⟦2⟧!"].key: "Merhaba, ⟦1⟧komşu⟦2⟧! ğüşıöçİ",
        by_source["time ⟦1⟧ min⟦2⟧end"].key: "süre ⟦1⟧ dk⟦2⟧son",
        by_source["One⟦1⟧two"].key: "Bir⟦1⟧iki",
    }
    out = PLUGIN.inject(bundle, translations)
    assert out != bundle
    after = {e.key: e.source for e in PLUGIN.extract(out, {SOURCE_LANGUAGE: None})}
    for key, text in translations.items():
        assert after[key] == text
    untouched = {k: v for k, v in {e.key: e.source for e in entries}.items() if k not in translations}
    assert all(after[k] == v for k, v in untouched.items())
    # Diğer diller ve kontrol kodları yerinde kalır: Türkçe yalnızca kaynak dil yuvasına yazılır.
    everything = {e.key: e.source for e in PLUGIN.extract(out)}
    assert "Merhaba, ⟦1⟧komşu⟦2⟧! ğüşıöçİ" in everything.values()
    assert "Hola, vecino!" in everything.values()
    assert "Un⟦1⟧deux" in everything.values()
    assert "Salut" in everything.values()
    assert everything["TSV|4|es|2"] == "Uno⟦1⟧dos"
    # Kaynak metin korunur: <i> etiketi, değişken, TSV'deki düz \n.
    env_texts = _raw_scripts(out)
    assert "Merhaba, <i>komşu</i>! ğüşıöçİ" in env_texts["Nina1[en]"]
    assert "\tsüre {} dk\\nson\t" in env_texts["loc_UI"]
    assert env_texts["loc_UI"].count("\r\n") == UI_TSV.count("\r\n")
    assert env_texts["package"] == NOT_TABLE


def _raw_scripts(data: bytes) -> dict[str, str]:
    return {o.read().m_Name: o.read().m_Script for o in UnityPy.load(data).objects if o.type.name == "TextAsset"}


def test_inject_rejects_broken_control_codes() -> None:
    bundle = _bundle()
    key = next(e.key for e in PLUGIN.extract(bundle, {SOURCE_LANGUAGE: None}) if e.source.startswith("time "))
    with pytest.raises(FormatError):
        PLUGIN.inject(bundle, {key: "süre dk son"})  # ⟦1⟧ ve ⟦2⟧ eksik


def test_inject_rejects_tab_or_newline_in_tsv_but_allows_srt_line_breaks() -> None:
    bundle = _bundle()
    entries = PLUGIN.extract(bundle, {SOURCE_LANGUAGE: None})
    tsv_key = next(e.key for e in entries if e.source == "start")
    with pytest.raises(FormatError, match="biçimi bozacak"):
        PLUGIN.inject(bundle, {tsv_key: "ba\tşla"})
    with pytest.raises(FormatError, match="biçimi bozacak"):
        PLUGIN.inject(bundle, {tsv_key: "ba\nşla"})
    srt_key = next(e.key for e in entries if e.source.startswith("One line"))
    out = PLUGIN.inject(bundle, {srt_key: "Bir satır\nİki satır ⟦1⟧"})
    assert "Bir satır\nİki satır {0}" in _raw_scripts(out)["Nina1[en]"]
    with pytest.raises(FormatError, match="biçimi bozacak"):
        PLUGIN.inject(bundle, {srt_key: "Bir\n\n2\n00:00:01,000 --> 00:00:02,000\nsahte ⟦1⟧"})


def test_inject_rejects_unknown_key() -> None:
    with pytest.raises(FormatError, match="olmayan girdiler"):
        PLUGIN.inject(_bundle(), {"TSV|9|en|1": "x"})


def test_invalid_utf8_in_game_data_is_shown_readable_and_left_untouched() -> None:
    # Gerçek oyunda kesilmiş "’" (E2 80 99 yerine E2 80) gibi bozuk baytlar var; UnityPy bunları
    # tek başına vekil karakter olarak okur ve SQLite'a yazılamaz.
    broken = "1\r\n00:00:00,000 --> 00:00:02,000\r\nthe whole dollarization\udce2\udc80\r\n"
    fine = "\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\nAll good\r\n"
    bundle = build_bundle([text_asset("Isabel[en]", broken + fine)])
    entries = PLUGIN.extract(bundle, {SOURCE_LANGUAGE: None})
    assert [e.source for e in entries] == ["the whole dollarization�", "All good"]
    for entry in entries:
        entry.source.encode("utf-8")  # vekil karakter kalmadı
    originals = {e.key: e.source for e in entries}
    assert PLUGIN.inject(bundle, originals) == bundle  # ekranda görünen metin geri verilince dosya değişmez
    out = PLUGIN.inject(bundle, {entries[1].key: "Hepsi iyi"})
    scripts = _raw_scripts(out)["Isabel[en]"]
    assert "dollarization\udce2\udc80" in scripts  # çevrilmeyen satırın bozuk baytları olduğu gibi
    assert "Hepsi iyi" in scripts
    out = PLUGIN.inject(bundle, {entries[0].key: "dolarizasyon"})
    assert "dolarizasyon" in _raw_scripts(out)["Isabel[en]"]
