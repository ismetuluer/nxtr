"""Unity eklentisi: string tablolarını çıkarma, geri yazma, round-trip ve aktarma akışı."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import UnityPy

from nxceviri.core.formats.base import FormatError
from nxceviri.core.formats.unity import UnityPlugin
from nxceviri.core.formats.unity.unity import detokenize, tokenize
from nxceviri.core.keys import load_keys
from nxceviri.core.pipeline import (
    Inputs,
    available_languages,
    default_source_language,
    extract_texts,
    language_label,
    scan_sources,
)
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import Project
from tests import nxbuild
from tests.unitybuild import build_bundle, other_behaviour, shared_table, string_table

PLUGIN = UnityPlugin()

DIALOGUE = [
    (101, "<b>Hello</b>, {0}!"),
    (102, "Press {input_0} to <color=#FFCC00>open</color> the door."),
    (103, "Plain line\nwith a newline"),
    (104, '<sprite name="key"> Key found'),
    (105, ""),
    (106, "Smart {0:plural:one item|{} items} left"),
]


def _objects(locale: str = "en", shared_id: int = 1) -> list[tuple[str, dict[str, Any]]]:
    return [
        shared_table(
            "Dialogue",
            [(101, "Greet"), (102, "Door_Open"), (103, "Plain"), (104, "Key"), (105, "Empty"), (106, "Items_Left")],
        ),
        string_table(f"Dialogue_{locale}", locale, shared_id, DIALOGUE),
        other_behaviour("Ayarlar"),
        string_table(f"UI_{locale}", locale, 99, [(1, "Yes"), (2, "No")]),
    ]


@pytest.fixture(params=[True, False], ids=["lz4", "sıkıştırmasız"])
def bundle(request: pytest.FixtureRequest) -> bytes:
    return build_bundle(_objects(), compress=bool(request.param))


@pytest.mark.parametrize(
    ("text", "display", "labels"),
    [
        ("<b>Hi</b>", "⟦1⟧Hi⟦2⟧", ["Kalın başı", "Kalın sonu"]),
        ("{0} and {input_1}", "⟦1⟧ and ⟦2⟧", ["Değişken {0}", "Değişken {input_1}"]),
        ("{0:plural:{} a|{} b}", "⟦1⟧", ["Değişken {0:plural:{} a|{} b}"]),
        ("a < b and <3 and {unclosed", "a < b and <3 and {unclosed", []),
        ('<sprite name="x"><color=red>R</color>', "⟦1⟧⟦2⟧R⟦3⟧", ["Simge (sprite)", "Renk başı", "Renk sonu"]),
        ("<blink>x</blink>", "⟦1⟧x⟦2⟧", ["Biçim etiketi <blink>", "Biçim etiketi </blink>"]),
        ("", "", []),
    ],
)
def test_tokenize(text: str, display: str, labels: list[str]) -> None:
    shown, codes = tokenize(text)
    assert shown == display
    assert [c.label for c in codes] == labels
    assert detokenize(shown, codes) == text


def test_extract_with_shared_key_names(bundle: bytes) -> None:
    context = PLUGIN.collect_context(bundle)
    entries = PLUGIN.extract(bundle, context)
    by_key = {e.key: e for e in entries}
    assert [e.key for e in entries][:6] == [f"Dialogue_en/{i}" for i, _ in DIALOGUE]
    greet = by_key["Dialogue_en/101"]
    assert greet.source == "⟦1⟧Hello⟦2⟧, ⟦3⟧!"
    assert greet.context == "Dialogue/Greet"
    assert by_key["Dialogue_en/103"].source == "Plain line\nwith a newline"
    # Ortak veri bulunamayan tabloda bağlam boş kalır.
    assert by_key["UI_en/1"].context == ""
    assert PLUGIN.language(bundle) == "en"
    assert PLUGIN.detect("x.bundle", bundle[:64])


def test_context_falls_back_to_collection_name() -> None:
    data = build_bundle(_objects(shared_id=12345))  # işaretçi yanlış yeri gösteriyor
    entries = PLUGIN.extract(data, PLUGIN.collect_context(data))
    assert entries[0].context == "Dialogue/Greet"


def test_extract_without_context() -> None:
    entries = PLUGIN.extract(build_bundle(_objects()))
    assert all(e.context == "" for e in entries)
    assert len(entries) == len(DIALOGUE) + 2


def test_round_trip_is_byte_identical(bundle: bytes) -> None:
    """Zorunlu test: değişiklik yapmadan extract → inject çıktısı orijinalle bayt bayt aynı."""
    entries = PLUGIN.extract(bundle)
    assert PLUGIN.inject(bundle, {e.key: e.source for e in entries}) == bundle
    assert PLUGIN.inject(bundle, {}) == bundle


def test_objects_reserialize_identically(bundle: bytes) -> None:
    """Tip ağacıyla okunup değişmeden yazılan her nesnenin baytları orijinalle aynı."""
    env = UnityPy.load(bundle)
    for obj in env.objects:
        if obj.type.name == "MonoBehaviour":
            assert obj.save_typetree(obj.read_typetree()) == obj.get_raw_data()


def _raw_objects(data: bytes) -> dict[int, bytes]:
    return {o.path_id: o.get_raw_data() for o in UnityPy.load(data).objects}


def test_inject_translation(bundle: bytes) -> None:
    out = PLUGIN.inject(
        bundle,
        {
            "Dialogue_en/101": "⟦1⟧Merhaba⟦2⟧, ⟦3⟧!",
            "Dialogue_en/105": "Artık boş değil: ğüşıöçİ",
            "UI_en/1": "Evet",
        },
    )
    assert out != bundle
    got = {e.key: e.source for e in PLUGIN.extract(out)}
    assert got["Dialogue_en/101"] == "⟦1⟧Merhaba⟦2⟧, ⟦3⟧!"
    assert got["Dialogue_en/105"] == "Artık boş değil: ğüşıöçİ"
    assert got["UI_en/1"] == "Evet"
    assert got["Dialogue_en/102"] == "Press ⟦1⟧ to ⟦2⟧open⟦3⟧ the door."
    # Ham metin: etiketler orijinal hâliyle geri konur.
    raw = {
        e["m_Id"]: e["m_Localized"]
        for o in UnityPy.load(out).objects
        if o.type.name == "MonoBehaviour"
        for e in o.read_typetree().get("m_TableData", [])
    }
    assert raw[101] == "<b>Merhaba</b>, {0}!"
    # Dokunulmayan nesneler bayt bayt aynı; sıkıştırma ayarı korunur.
    before, after = _raw_objects(bundle), _raw_objects(out)
    for path_id in (1, 3):  # ortak veri ve diğer MonoBehaviour
        assert before[path_id] == after[path_id]
    new_file: Any = UnityPy.load(out).file
    old_file: Any = UnityPy.load(bundle).file
    assert new_file.dataflags == old_file.dataflags


@pytest.mark.parametrize(
    ("translation", "message"),
    [
        ("Merhaba!", "Eksik kontrol kodu"),
        ("⟦2⟧Merhaba⟦1⟧, ⟦3⟧!", "sırası"),
        ("⟦1⟧Merhaba⟦2⟧, ⟦3⟧ ⟦4⟧!", "olmayan kontrol kodu"),
    ],
)
def test_inject_rejects_broken_placeholders(bundle: bytes, translation: str, message: str) -> None:
    with pytest.raises(FormatError, match=message):
        PLUGIN.inject(bundle, {"Dialogue_en/101": translation})


def test_inject_unknown_key(bundle: bytes) -> None:
    with pytest.raises(FormatError, match="olmayan girdiler"):
        PLUGIN.inject(bundle, {"Dialogue_en/999": "x"})


def test_verify_detects_mismatch(bundle: bytes) -> None:
    with pytest.raises(FormatError, match="doğrulanamadı"):
        PLUGIN._verify(bundle, {"Dialogue_en/101": "beklenmeyen"})


def test_non_table_bundle_and_corrupt_data() -> None:
    assert PLUGIN.extract(build_bundle([other_behaviour("a")])) == []
    assert PLUGIN.language(build_bundle([other_behaviour("a")])) is None
    with pytest.raises(FormatError, match="açılamadı"):
        PLUGIN.extract(b"UnityFS\0" + b"\xff" * 200)


def test_asset_tables_are_not_text() -> None:
    """AssetTable aynı yapıdadır ama değerleri varlık GUID'leridir; metin olarak alınmaz."""
    guids = [(1, "389fd902d0330504a9218b0bcdf2594a"), (2, ""), (3, "d1a147066daaaaa4e83ae89dd6dc866f")]
    data = build_bundle([string_table("Fonts_en", "en", 0, guids), string_table("UI_en", "en", 0, [(1, "Yes")])])
    assert [e.key for e in PLUGIN.extract(data)] == ["UI_en/1"]


def test_mixed_languages_have_no_single_language() -> None:
    data = build_bundle([string_table("A_en", "en", 0, [(1, "a")]), string_table("A_ja", "ja", 0, [(1, "b")])])
    assert PLUGIN.language(data) is None


def test_large_table_round_trip() -> None:
    rows = [(i, f"Line {i}: <b>bold</b> {{0}}") for i in range(5000)]
    data = build_bundle([string_table("Big_en", "en", 0, rows)])
    entries = PLUGIN.extract(data)
    assert len(entries) == 5000
    assert PLUGIN.inject(data, {e.key: e.source for e in entries}) == data
    out = PLUGIN.inject(data, {"Big_en/4999": "Satır ⟦1⟧kalın⟦2⟧ ⟦3⟧"})
    assert PLUGIN.extract(out)[-1].source == "Satır ⟦1⟧kalın⟦2⟧ ⟦3⟧"


# --- oyundan projeye aktarma -------------------------------------------------------------

AA = "Data/StreamingAssets/aa/Switch/"


@pytest.fixture
def unity_game(tmp_path: Path) -> tuple[Inputs, Path]:
    keys = nxbuild.TestKeys.random()
    files = {
        "Data/globalgamemanagers": b"\0" * 8 + (22).to_bytes(4, "big") + b"\0" * 20,
        AA + "localization-assets-shared_assets_all.bundle": build_bundle([_objects()[0]]),
        AA + "localization-string-tables-english(en)_assets_all.bundle": build_bundle(_objects()[1:]),
        AA + "localization-string-tables-japanese(ja)_assets_all.bundle": build_bundle(
            [string_table("Dialogue_ja", "ja", 1, [(101, "こんにちは")])]
        ),
        AA + "animations-cat_assets_all.bundle": build_bundle([other_behaviour("kedi")]),
    }
    pkg = nxbuild.build_package(
        keys,
        kind="base",
        title_id=0x0100AAAA00000000,
        application_id=0x0100AAAA00000000,
        version=0,
        romfs_files=files,
        name="Unity Oyunu",
    )
    nsp = tmp_path / "Unity Oyunu ğüş.nsp"
    nsp.write_bytes(pkg.nsp)
    return Inputs((nsp,), load_keys(keys.write(tmp_path / "prod.keys"))), tmp_path


def test_unity_game_import(unity_game: tuple[Inputs, Path]) -> None:
    inputs, tmp_path = unity_game
    report = scan_sources(inputs, TaskContext())
    assert report.engine.engine == "unity"
    langs = available_languages(report)
    assert langs == ["en", "ja"]
    assert default_source_language(langs) == "en"
    assert language_label("ja") == "Japonca (ja)"

    result = extract_texts(inputs, report, TaskContext(), source_language="en")
    assert result.skipped_languages == {"ja": 1}
    assert [f.path for f in result.files] == [AA + "localization-string-tables-english(en)_assets_all.bundle"]
    entries = {e.key: e for e in result.files[0].entries}
    assert entries["Dialogue_en/102"].context == "Dialogue/Door_Open"  # başka bundle'daki anahtar adı

    japanese = extract_texts(inputs, report, TaskContext(), source_language="ja")
    assert japanese.files[0].entries[0].source == "こんにちは"

    project = Project.new()
    project.import_texts(result.files)
    rows = {r.key: r for r in project.translation_rows()}
    assert rows["Dialogue_en/101"].context == "Dialogue/Greet"
    assert rows["Dialogue_en/101"].code_labels == ("Kalın başı", "Kalın sonu", "Değişken {0}")
    project.save_as(tmp_path / "unity.nxproj")
    project.close()
    reopened = Project.open(tmp_path / "unity.nxproj")
    assert {r.key: r.context for r in reopened.translation_rows()}["Dialogue_en/106"] == "Dialogue/Items_Left"
    reopened.close()


@pytest.mark.gui
def test_gui_source_language_choice(qtbot: Any, unity_game: tuple[Inputs, Path]) -> None:
    from PySide6.QtCore import QSettings

    from nxceviri.gui.main_window import STEP_TRANSLATE, MainWindow

    inputs, tmp_path = unity_game
    window = MainWindow(QSettings(str(tmp_path / "ayarlar.ini"), QSettings.Format.IniFormat))
    window.show()
    try:
        assert window.load_keys_file(tmp_path / "prod.keys")
        window.add_files(list(inputs.paths))
        qtbot.waitUntil(lambda: window.task is None, timeout=20_000)
        window.start_scan()
        qtbot.waitUntil(lambda: window.task is None, timeout=20_000)
        report = window.scan_page.report
        assert report.language.isVisibleTo(window)
        assert [report.language.itemData(i) for i in range(report.language.count())] == ["en", "ja"]
        assert report.language.currentData() == "en"
        report.language.setCurrentIndex(report.language.findData("ja"))
        report.import_button.click()
        qtbot.waitUntil(lambda: window.task is None, timeout=20_000)
        assert window.pages.currentIndex() == STEP_TRANSLATE
        rows = window.translate_page.model.rows
        assert [(r.key, r.source) for r in rows] == [("Dialogue_ja/101", "こんにちは")]
        assert "1 dil dosyası atlandı" in window.translate_page.notice_text
    finally:
        window.dirty = False
        window.close()
        window.deleteLater()
