"""Despelote `Locoliser`: TSV tablolarının oyuna gömülü kopyası (oyun metni buradan okur)."""

from __future__ import annotations

import struct

import UnityPy

from nxceviri.core.formats.base import SOURCE_LANGUAGE
from nxceviri.core.formats.unity import UnityPlugin, locoliser
from tests.unitybuild import i2_source_raw, locoliser_raw, serialized_without_typetree, text_asset_raw

PLUGIN = UnityPlugin()
DIALOGUE_ID, UI_ID, LOCO_ID = 100, 101, 102

DIALOGUE_TSV = (
    "path\tvoice name\tvoice type\tsub index\tsub timestamp\t[es]\t[en]\r\n"
    "01_Kids\\Talk\tNina1_01\tconversation\t1\t0:00:00,292 --> 0:00:04,000\tHola amigos\tHello friends\r\n"
    "01_Kids\\Talk\tNina1_01\tconversation\t2\t0:00:04,167 --> 0:00:09,334\tUno\\ndos\tOne\\ntwo\r\n"
)
UI_TSV = "ID\tes\ten\r\n0\tcomenzar\tstart\r\n1\tmes\\nfin\tmonth\\nend\r\n2\tsalir\tquit\r\n"
# Önbellekte diyalog metni ekrana sığsın diye satırlara bölünmüş olabilir ("Hello\nfriends").
ENTRIES = [("01_kids/talk/nina1_01", [(1, ["Hola\namigos", "Hello\nfriends"]), (2, ["Uno\ndos", "One\ntwo"])])]
UI_ROWS = [["comenzar", "start"], ["mes\\nfin", "month\\nend"], ["salir (eski)", "quit (old)"]]


def _file(ui_rows: list[list[str]] = UI_ROWS) -> bytes:
    loco = locoliser_raw(DIALOGUE_ID, ENTRIES, UI_ID, ui_rows)
    return serialized_without_typetree(
        [
            text_asset_raw("despelote_loc_monsterFile", DIALOGUE_TSV),
            text_asset_raw("despelote_loc_UI", UI_TSV),
            loco,
        ],
        [49, 49, 114],
    )


def _cache(data: bytes) -> locoliser.Locoliser:
    obj = next(o for o in UnityPy.load(data).objects if o.path_id == LOCO_ID)
    loc = locoliser.parse(bytes(obj.get_raw_data()))
    assert loc is not None
    return loc


def test_parse_and_serialize_are_exact() -> None:
    raw = locoliser_raw(DIALOGUE_ID, ENTRIES, UI_ID, UI_ROWS)
    loc = locoliser.parse(raw)
    assert loc is not None
    assert loc.keys == ("01_kids/talk/nina1_01",)
    assert (loc.dialogue_file, loc.ui_file, loc.language_count) == (DIALOGUE_ID, UI_ID, 2)
    assert loc.entries[0][1].texts == ("Uno\ndos", "One\ntwo")
    assert loc.ui_rows[2] == ("salir (eski)", "quit (old)")
    assert locoliser.serialize(loc) == raw


def test_other_objects_are_not_mistaken_for_a_locoliser() -> None:
    raw = locoliser_raw(DIALOGUE_ID, ENTRIES, UI_ID, UI_ROWS)
    assert locoliser.parse(raw[: len(raw) // 2]) is None  # kesik
    assert locoliser.parse(i2_source_raw([("a", 0, ["x", "y"])], [("English", "en"), ("Spanish", "es")])) is None
    assert locoliser.parse(b"\0" * 200) is None
    uneven = locoliser_raw(DIALOGUE_ID, [("k", [(1, ["a", "b"]), (2, ["a"])])], UI_ID, UI_ROWS)
    assert locoliser.parse(uneven) is None  # dil sayısı tutarsız


def test_changed_text_keeps_alignment_and_other_fields() -> None:
    raw = locoliser_raw(DIALOGUE_ID, ENTRIES, UI_ID, UI_ROWS, tail=b"\x05\0\0\0" + b"\xab" * 12)
    loc = locoliser.parse(raw)
    assert loc is not None
    new = locoliser.with_texts(
        loc, {(0, 0): ("Merhaba arkadaşlar ğüşı", "Merhaba arkadaşlar ğüşı")}, {0: ("başla", "başla")}
    )
    out = locoliser.serialize(new)
    again = locoliser.parse(out)
    assert again is not None
    assert again.entries[0][0].texts == ("Merhaba arkadaşlar ğüşı",) * 2
    assert again.entries[0][0].timing == struct.pack("<ff", 1.5, 2.25)  # zamanlar aynen
    assert again.entries[0][1] == loc.entries[0][1]
    assert again.ui_rows[0] == ("başla", "başla")
    assert again.tail == loc.tail
    assert out.endswith(loc.tail)


def test_only_tsv_rows_are_offered_for_translation() -> None:
    entries = PLUGIN.extract(_file(), {SOURCE_LANGUAGE: None})
    assert sorted(e.source for e in entries) == sorted(["Hello friends", "One⟦1⟧two", "start", "month⟦1⟧end", "quit"])


def test_roundtrip_without_changes_is_identical() -> None:
    data = _file()
    originals = {e.key: e.source for e in PLUGIN.extract(data, {SOURCE_LANGUAGE: None})}
    assert PLUGIN.inject(data, originals) == data


def test_translation_reaches_only_the_source_language_slot_of_the_cache() -> None:
    data = _file()
    by_source = {e.source: e.key for e in PLUGIN.extract(data, {SOURCE_LANGUAGE: None})}
    out = PLUGIN.inject(
        data,
        {
            by_source["Hello friends"]: "Merhaba arkadaşlar",
            by_source["One⟦1⟧two"]: "Bir⟦1⟧iki",
            by_source["start"]: "başla",
            by_source["month⟦1⟧end"]: "ay⟦1⟧son",
            by_source["quit"]: "çık",
        },
    )
    loc = _cache(out)
    # Yalnızca İngilizce yuvası (ikinci sütun) değişir; İspanyolca özgün kalır, kullanıcı dili değiştirebilir.
    assert loc.entries[0][0].texts == ("Hola\namigos", "Merhaba arkadaşlar")
    assert loc.entries[0][1].texts == ("Uno\ndos", "Bir\niki")  # önbellekte gerçek satır sonu
    assert loc.ui_rows[0] == ("comenzar", "başla")
    assert loc.ui_rows[1] == ("mes\\nfin", "ay\\nson")  # bu hücre düz "\n" yazısıyla tutuluyordu
    # Önbellekteki özgün metni TSV'dekinden farklı olan menü satırına (sıra kaymış olabilir) yazılmaz.
    assert loc.ui_rows[2] == ("salir (eski)", "quit (old)")
    assert loc.entries[0][0].timing == _cache(data).entries[0][0].timing


def test_dialogue_matches_by_key_and_index_even_if_text_was_rewrapped() -> None:
    data = _file()
    key = next(e.key for e in PLUGIN.extract(data, {SOURCE_LANGUAGE: None}) if e.source == "Hello friends")
    loc = _cache(PLUGIN.inject(data, {key: "Selam"}))
    assert loc.entries[0][0].texts == ("Hola\namigos", "Selam")  # önbellekte "Hello\nfriends" idi
    assert loc.entries[0][1].texts == ("Uno\ndos", "One\ntwo")  # çevrilmeyen altyazı aynen
