"""Donkey Kong Country Returns HD: `Localization` SerializeReference kayıt defteri (elle üretilmiş örneklerle)."""

from __future__ import annotations

import struct

import pytest
import UnityPy

from nxceviri.core.formats.base import SOURCE_LANGUAGE, FormatError
from nxceviri.core.formats.unity import UnityPlugin, dklocal
from nxceviri.core.formats.unity import unity as unity_module
from tests.unitybuild import DkSlot, dk_localization_raw, serialized_without_typetree

PLUGIN = UnityPlugin()
PATH_ID = 100

#: İngilizce (0), Fransızca (1), ikinci İngilizce yuva (7); 5. yuva oyunda boştur.
EN: list[DkSlot] = [
    "Dixie Kong",  # 0
    "",  # 1: boş
    "<scale=0.8>Start a level\nwith Dixie.",  # 2: biçim etiketi
    ["Hit", "Hits", 0],  # 3: çoklu öğe: iki yeni çocuk + 0. yuvaya başvuru
    "\\3630bddf\\27b05a76",  # 4: ses kimliği, çevrilmez
    "...",  # 5: harfsiz
    "Continue?",  # 6
]
FR: list[DkSlot] = [
    "Dixie Kong",
    "",
    "<scale=0.8>Commencez un niveau.",
    ["Coup", "Coups", 0],
    "\\3630bddf\\27b05a76",
    "...",
    "Continuer ?",
]
EN_UK = [*EN[:6], "Continue ?"]  # 6. satır İngiliz yazımıyla farklı
LANGUAGES = [(0, EN), (1, FR), (7, EN_UK)]


@pytest.fixture(autouse=True)
def _small_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(unity_module, "_DK_MIN_SIZE", 0)


def _file(named: bool = False, languages: list[tuple[int, list[DkSlot]]] | None = None) -> bytes:
    raw = dk_localization_raw(languages or LANGUAGES, named=named)
    return serialized_without_typetree([b"\x00" * 64, raw], [114, 114])


def _doc(data: bytes) -> dklocal.Document:
    obj = next(o for o in UnityPy.load(data).objects if o.path_id == PATH_ID + 1)
    doc = dklocal.parse(bytes(obj.get_raw_data()))
    assert doc is not None
    return doc


def _texts(data: bytes, language: int) -> list[str]:
    doc = _doc(data)
    lang = next(lang for lang in doc.languages if lang.index == language)
    return [s.text for _slot, s in dklocal.unique_slots(doc, lang)]


# --- ayrıştırıcı ---------------------------------------------------------------------------------


@pytest.mark.parametrize("named", [False, True])
def test_parse_and_serialize_are_exact(named: bool) -> None:
    raw = dk_localization_raw(LANGUAGES, named=named)
    doc = dklocal.parse(raw)
    assert doc is not None
    assert doc.named is named
    assert [(lang.index, len(lang.slots)) for lang in doc.languages] == [(0, 7), (1, 7), (7, 7)]
    assert dklocal.serialize(doc) == raw


def test_unique_slots_deduplicate_shared_children() -> None:
    doc = dklocal.parse(dk_localization_raw(LANGUAGES))
    assert doc is not None
    slots = dklocal.unique_slots(doc, doc.languages[0])
    keys = [k for k, _s in slots]
    # 0. yuva çoklu öğenin üçüncü çocuğudur ama doğrudan yuvası da var: bir kez, ilk yerinde sayılır.
    assert keys == ["0", "1", "2", "3.0", "3.1", "4", "5", "6"]
    assert [s.text for _k, s in slots][3:5] == ["Hit", "Hits"]


def test_named_layout_keeps_names() -> None:
    doc = dklocal.parse(dk_localization_raw(LANGUAGES, named=True))
    assert doc is not None
    first = dklocal.unique_slots(doc, doc.languages[0])[0][1]
    assert first.name == "NewText_0"
    assert next(iter(doc.multiples.values())).name.startswith("Multi_")


def test_other_objects_are_not_mistaken_for_a_localization() -> None:
    raw = dk_localization_raw(LANGUAGES)
    assert dklocal.parse(raw[: len(raw) // 2]) is None  # kesik
    assert dklocal.parse(raw + b"\0\0\0\0") is None  # kayıt defterinden sonra artık bayt
    assert dklocal.parse(b"\0" * 300) is None
    assert (
        dklocal.parse(raw.replace(b"SingleLanguageDataItem", b"SingleLanguageDataItex", 1)) is None
    )  # bilinmeyen sınıf
    assert dklocal.parse(raw.replace(b"Localization", b"Localizatiox", 1)) is None
    wrong_namespace = raw.replace(b"dk3ds", b"dk3dx", 1)
    assert dklocal.parse(wrong_namespace) is None


def test_changed_text_keeps_alignment_and_other_fields() -> None:
    raw = dk_localization_raw(LANGUAGES)
    doc = dklocal.parse(raw)
    assert doc is not None
    rid = dklocal.unique_slots(doc, doc.languages[0])[0][1].rid
    out = dklocal.serialize(dklocal.with_texts(doc, {rid: "Dixie Kong'un Türkçe adı ğüşıİ"}))
    again = dklocal.parse(out)
    assert again is not None
    assert len(out) % 4 == len(raw) % 4
    assert again.singles[rid].text == "Dixie Kong'un Türkçe adı ğüşıİ"
    assert again.singles[rid].number == doc.singles[rid].number
    assert again.singles[rid].tag == doc.singles[rid].tag
    others = {r: s for r, s in again.singles.items() if r != rid}
    assert others == {r: s for r, s in doc.singles.items() if r != rid}
    assert again.multiples == doc.multiples
    assert again.languages == doc.languages


# --- eklenti: çıkarma ------------------------------------------------------------------------------


def test_extract_default_is_english_slot() -> None:
    entries = {e.key: e for e in PLUGIN.extract(_file(), {SOURCE_LANGUAGE: None})}
    assert list(entries) == [f"DK|{PATH_ID + 1}|0|{slot}" for slot in ("0", "2", "3.0", "3.1", "6")]
    assert entries[f"DK|{PATH_ID + 1}|0|2"].source == "⟦1⟧Start a level\nwith Dixie."
    assert entries[f"DK|{PATH_ID + 1}|0|2"].codes[0].raw == b"<scale=0.8>"
    assert "\\3630bddf" not in "".join(e.source for e in entries.values())  # ses kimliği çevrilmez


def test_extract_without_context_still_uses_english() -> None:
    assert {e.source for e in PLUGIN.extract(_file())} == {
        "Dixie Kong",
        "⟦1⟧Start a level\nwith Dixie.",
        "Hit",
        "Hits",
        "Continue?",
    }


def test_extract_selected_language_and_fallback() -> None:
    french = PLUGIN.extract(_file(), {SOURCE_LANGUAGE: "fr"})
    assert {e.source for e in french} >= {"Coup", "Continuer ?"}
    assert all("|1|" in e.key for e in french)
    assert all("|0|" in e.key for e in PLUGIN.extract(_file(), {SOURCE_LANGUAGE: "tr"}))  # olmayan dil → İngilizce


def test_extract_context_from_names() -> None:
    entries = PLUGIN.extract(_file(named=True), {SOURCE_LANGUAGE: "en"})
    assert entries[0].context == "NewText_0"


# --- eklenti: geri yazma ---------------------------------------------------------------------------


def test_roundtrip_without_changes_is_identical() -> None:
    data = _file()
    entries = PLUGIN.extract(data, {SOURCE_LANGUAGE: "en"})
    assert PLUGIN.inject(data, {e.key: e.source for e in entries}) == data
    assert PLUGIN.inject(data, {}) == data


def key(language: int, slot: int | str) -> str:
    return f"DK|{PATH_ID + 1}|{language}|{slot}"


def test_inject_writes_slot_and_mirrors_identical_twin() -> None:
    data = _file()
    out = PLUGIN.inject(
        data,
        {
            key(0, 0): "Dixie Kong (çeviri)",
            key(0, 2): "⟦1⟧Bir seviyeye Dixie ile başla.",
            key(0, "3.1"): "Vuruşlar",
            key(0, 6): "Devam edilsin mi? ğüşıİ",
        },
    )
    assert _texts(out, 0) == [
        "Dixie Kong (çeviri)",
        "",
        "<scale=0.8>Bir seviyeye Dixie ile başla.",
        "Hit",
        "Vuruşlar",
        "\\3630bddf\\27b05a76",
        "...",
        "Devam edilsin mi? ğüşıİ",
    ]
    uk = _texts(out, 7)
    assert uk[0] == "Dixie Kong (çeviri)"  # özdeş satır ikinci İngilizce yuvaya da yazıldı
    assert uk[3:5] == ["Hit", "Vuruşlar"]
    assert uk[-1] == "Continue ?"  # İngiliz yazımı farklıydı: dokunulmadı
    assert _texts(out, 1) == _texts(data, 1)  # Fransızca aynen


def test_inject_keeps_other_objects_and_rejects_bad_input() -> None:
    data = _file()
    entries = PLUGIN.extract(data, {SOURCE_LANGUAGE: "en"})
    out = PLUGIN.inject(data, {entries[0].key: "Değişti"})
    before = {o.path_id: bytes(o.get_raw_data()) for o in UnityPy.load(data).objects if o.path_id != PATH_ID + 1}
    after = {o.path_id: bytes(o.get_raw_data()) for o in UnityPy.load(out).objects if o.path_id != PATH_ID + 1}
    assert before == after
    with pytest.raises(FormatError, match="yazılamadı"):
        PLUGIN.inject(data, {entries[1].key: "kod silinmiş"})  # ⟦1⟧ eksik
    with pytest.raises(FormatError, match="olmayan"):
        PLUGIN.inject(data, {f"DK|{PATH_ID + 1}|0|99": "x"})
    with pytest.raises(FormatError, match="olmayan"):
        PLUGIN.inject(data, {f"DK|{PATH_ID + 9}|0|0": "x"})


def test_large_object_gate_skips_small_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(unity_module, "_DK_MIN_SIZE", 10**9)
    assert PLUGIN.extract(_file(), {SOURCE_LANGUAGE: "en"}) == []


def test_header_layout_constants() -> None:
    raw = dk_localization_raw(LANGUAGES)
    assert raw[32:44] == b"Localization"
    assert struct.unpack_from("<i", raw, 44)[0] == len(LANGUAGES)
