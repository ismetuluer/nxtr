"""I2 Localization: tip ağacı silinmiş dosyadan okuma, geri yazma, round-trip ve aktarma akışı."""

from __future__ import annotations

from pathlib import Path

import pytest
import UnityPy

from nxceviri.core.export.layeredfs import LAYOUT_ATMOSPHERE, ExportInfo, ExportOptions, TextFileRef, export_mod
from nxceviri.core.formats.base import SOURCE_LANGUAGE, FormatError
from nxceviri.core.formats.scanner import DETAIL_LANGUAGES, base_detail, detail_languages
from nxceviri.core.formats.unity import UnityPlugin, i2
from nxceviri.core.keys import load_keys
from nxceviri.core.pipeline import Inputs, available_languages, extract_texts, scan_sources
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import Project
from tests import nxbuild
from tests.unitybuild import i2_source_raw, serialized_without_typetree

PLUGIN = UnityPlugin()
LANGS = [("Spanish", "es"), ("English", "en"), ("French", "fr"), ("Portuguese (Brazil)", "pt-BR")]
TERMS: list[tuple[str, int, list[str]]] = [
    ("UI/Yes", 0, ["Sí", "Yes", "Oui", "Sim"]),
    ("UI/Points", 0, ["Tienes {purgepoints} puntos", "You have {purgepoints} points", "", ""]),
    ("UI/Bold", 0, ["<b>Hola</b>", "<b>Hello</b>\nworld", "<b>Salut</b>", "<b>Olá</b>"]),
    ("UI/Font", 1, ["FontA", "FontA", "FontA", "FontA"]),  # metin değil: font başvurusu
    ("UI/Empty", 0, ["Vacío", "   ", "", ""]),  # İngilizce hücre boş: aktarılmaz
    ("UI/Yes", 0, ["Sí 2", "Yes again", "", ""]),  # yinelenen terim adı
]


def _assets(layout: str = "A") -> bytes:
    noise = b"\x05\x00\x00\x00" * 30  # I2 olmayan bir MonoBehaviour
    return serialized_without_typetree([i2_source_raw(TERMS, LANGS, layout), noise])


@pytest.fixture(params=["A", "B"])
def assets(request: pytest.FixtureRequest) -> bytes:
    return _assets(request.param)


def test_parse_source_and_identity(assets: bytes) -> None:
    raw = bytes(next(o for o in UnityPy.load(assets).objects if o.path_id == 100).get_raw_data())
    source = i2.parse_source(raw)
    assert source is not None
    assert [lang.code for lang in source.languages] == ["es", "en", "fr", "pt-BR"]
    assert [t.name for t in source.terms] == [t[0] for t in TERMS]
    assert i2.serialize(source) == raw  # değişiklik yoksa bayt bayt aynı


def test_non_i2_data_is_not_a_source() -> None:
    assert i2.parse_source(b"") is None
    assert i2.parse_source(b"\x05\x00\x00\x00" * 64) is None
    raw = i2_source_raw(TERMS, LANGS)
    assert i2.parse_source(raw[: len(raw) // 2]) is None  # yarıda kesilmiş
    # Dil kodu geçersizse (ör. "No") kaynak sayılmaz.
    assert i2.parse_source(i2_source_raw([("A", 0, ["x"])], [("Bilinmez", "No")])) is None


def test_detect_and_language(assets: bytes) -> None:
    assert PLUGIN.detect("Data/resources.assets", assets[:64])
    assert not PLUGIN.detect("Data/resources.assets", b"\0" * 64)
    assert PLUGIN.language(assets) is None  # tüm diller tek nesnede


def test_extract_source_language_column(assets: bytes) -> None:
    entries = PLUGIN.extract(assets, {SOURCE_LANGUAGE: "en"})
    by_key = {e.key: e for e in entries}
    assert list(by_key) == [
        "I2|100|en|UI/Yes",
        "I2|100|en|UI/Points",
        "I2|100|en|UI/Bold",
        "I2|100|en|UI/Yes#2",
    ]
    assert by_key["I2|100|en|UI/Points"].source == "You have ⟦1⟧ points"
    assert by_key["I2|100|en|UI/Bold"].source == "⟦1⟧Hello⟦2⟧\nworld"
    assert by_key["I2|100|en|UI/Yes"].context == "UI/Yes"


@pytest.mark.parametrize(
    ("wanted", "column"),
    [("es", "es"), ("fr-fr", "fr"), ("pt-br", "pt-BR"), ("ja", "en"), (None, "en")],
)
def test_column_choice(wanted: str | None, column: str) -> None:
    keys = {e.key.split("|")[2] for e in PLUGIN.extract(_assets(), {SOURCE_LANGUAGE: wanted})}
    assert keys == {column}


def test_extract_without_context_reads_all_languages() -> None:
    keys = {e.key for e in PLUGIN.extract(_assets())}
    assert "I2|100|es|UI/Empty" in keys
    assert "I2|100|fr|UI/Yes" in keys
    assert not any("UI/Font" in k for k in keys)


def test_round_trip_is_byte_identical(assets: bytes) -> None:
    same = {e.key: e.source for e in PLUGIN.extract(assets)}
    assert PLUGIN.inject(assets, same) == assets
    assert PLUGIN.inject(assets, {}) == assets


def test_inject_translation(assets: bytes) -> None:
    out = PLUGIN.inject(
        assets,
        {
            "I2|100|en|UI/Yes": "Evet çğıİöşü",
            "I2|100|en|UI/Points": "⟦1⟧ puanın var",
            "I2|100|en|UI/Bold": "⟦1⟧Merhaba⟦2⟧\ndünya",
        },
    )
    after = {e.key: e.source for e in PLUGIN.extract(out)}
    assert after["I2|100|en|UI/Yes"] == "Evet çğıİöşü"
    assert after["I2|100|en|UI/Points"] == "⟦1⟧ puanın var"
    assert after["I2|100|es|UI/Yes"] == "Sí"  # diğer diller dokunulmadan kalır
    assert after["I2|100|en|UI/Yes#2"] == "Yes again"
    raw = bytes(next(o for o in UnityPy.load(out).objects if o.path_id == 100).get_raw_data())
    source = i2.parse_source(raw)
    assert source is not None
    assert source.terms[1].languages[1] == "{purgepoints} puanın var"  # kontrol kodu geri kondu
    assert source.terms[2].languages[1] == "<b>Merhaba</b>\ndünya"
    # Diğer nesne bayt bayt aynı.
    noise = [bytes(o.get_raw_data()) for o in UnityPy.load(out).objects if o.path_id == 101]
    assert noise == [b"\x05\x00\x00\x00" * 30]


@pytest.mark.parametrize(
    ("translation", "message"), [("puanın var", "Eksik kontrol kodu"), ("⟦1⟧ ⟦2⟧", "Orijinalde olmayan")]
)
def test_inject_rejects_broken_placeholders(translation: str, message: str) -> None:
    with pytest.raises(FormatError, match=message):
        PLUGIN.inject(_assets(), {"I2|100|en|UI/Points": translation})


def test_inject_unknown_key() -> None:
    with pytest.raises(FormatError, match="olmayan"):
        PLUGIN.inject(_assets(), {"I2|100|en|Yok/Böyle": "x"})


def test_large_source_round_trip() -> None:
    terms = [(f"Dialog/Line_{i}", 0, [f"Línea {i}", f"Line {i} {{name}}", ""]) for i in range(3000)]
    langs = [("Spanish", "es"), ("English", "en"), ("German", "de")]
    data = serialized_without_typetree([i2_source_raw(terms, langs)])
    entries = PLUGIN.extract(data, {SOURCE_LANGUAGE: "en"})
    assert len(entries) == 3000
    out = PLUGIN.inject(data, {e.key: f"Satır {i} ⟦1⟧" for i, e in enumerate(entries)})
    again = PLUGIN.extract(out, {SOURCE_LANGUAGE: "en"})
    assert again[2999].source == "Satır 2999 ⟦1⟧"


@pytest.fixture
def i2_game(tmp_path: Path) -> tuple[Inputs, Path]:
    keys = nxbuild.TestKeys.random()
    files = {
        "Data/globalgamemanagers": b"\0" * 8 + (22).to_bytes(4, "big") + b"\0" * 20,
        "Data/resources.assets": _assets(),
        "Data/sharedassets0.assets": serialized_without_typetree([b"\x01\x00\x00\x00" * 20]),
    }
    pkg = nxbuild.build_package(
        keys,
        kind="base",
        title_id=0x0100BBBB00000000,
        application_id=0x0100BBBB00000000,
        version=0,
        romfs_files=files,
        name="I2 Oyunu",
    )
    nsp = tmp_path / "I2 Oyunu ğüş.nsp"
    nsp.write_bytes(pkg.nsp)
    return Inputs((nsp,), load_keys(keys.write(tmp_path / "prod.keys"))), tmp_path


def test_i2_game_import_and_export(i2_game: tuple[Inputs, Path]) -> None:
    inputs, tmp_path = i2_game
    report = scan_sources(inputs, TaskContext())
    result = extract_texts(inputs, report, TaskContext(), None)  # dil seçilmedi → İngilizce
    assert [f.path for f in result.files] == ["Data/resources.assets"]
    assert {e.key for e in result.files[0].entries} == {
        "I2|100|en|UI/Yes",
        "I2|100|en|UI/Points",
        "I2|100|en|UI/Bold",
        "I2|100|en|UI/Yes#2",
    }
    project = Project.new()
    project.import_texts(result.files)
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations(
        [(rows["I2|100|en|UI/Yes"].id, "Evet şimdi"), (rows["I2|100|en|UI/Points"].id, "⟦1⟧ puan")]
    )
    dest = tmp_path / "mod"
    export = export_mod(
        inputs,
        [TextFileRef(*f) for f in project.text_files()],
        project.translation_rows(),
        options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "x", ""),
        info=ExportInfo("I2 Oyunu", "0100BBBB00000000", 0, None),
    )
    assert export.files == ["atmosphere/contents/0100BBBB00000000/romfs/Data/resources.assets"]
    texts = {e.key: e.source for e in PLUGIN.extract((dest / export.files[0]).read_bytes())}
    assert texts["I2|100|en|UI/Yes"] == "Evet şimdi"
    assert texts["I2|100|en|UI/Points"] == "⟦1⟧ puan"
    assert texts["I2|100|es|UI/Yes"] == "Sí"


# --- dosyanın içindeki dil listesi (tarama raporu → kaynak dil seçimi) -------------------------

LANGS_EN_JA = [("English", "en"), ("Japanese", "ja")]
TERMS_EN_JA: list[tuple[str, int, list[str]]] = [("UI/Yes", 0, ["Yes", "はい"]), ("UI/No", 0, ["No", "いいえ"])]


@pytest.fixture
def i2_two_languages(tmp_path: Path) -> Inputs:
    keys = nxbuild.TestKeys.random()
    files = {
        "Data/globalgamemanagers": b"\0" * 8 + (22).to_bytes(4, "big") + b"\0" * 20,
        "Data/resources.assets": serialized_without_typetree(
            [i2_source_raw(TERMS_EN_JA, LANGS_EN_JA), b"\x05\x00\x00\x00" * 30]
        ),
    }
    pkg = nxbuild.build_package(
        keys,
        kind="base",
        title_id=0x0100BBBB00000000,
        application_id=0x0100BBBB00000000,
        version=0,
        romfs_files=files,
        name="I2 Oyunu",
    )
    nsp = tmp_path / "iki dil.nsp"
    nsp.write_bytes(pkg.nsp)
    return Inputs((nsp,), load_keys(keys.write(tmp_path / "prod.keys")))


def test_plugin_languages_hook(assets: bytes) -> None:
    assert PLUGIN.languages(assets) == ["es", "en", "fr", "pt-BR"]
    assert PLUGIN.languages(serialized_without_typetree([b"\x05\x00\x00\x00" * 30])) == []


def test_scan_lists_i2_languages_and_selected_one_is_imported(i2_two_languages: Inputs) -> None:
    report = scan_sources(i2_two_languages, TaskContext())
    assert available_languages(report) == ["en", "ja"]
    result = extract_texts(i2_two_languages, report, TaskContext(), "ja")
    assert {e.key: e.source for e in result.files[0].entries} == {
        "I2|100|ja|UI/Yes": "はい",
        "I2|100|ja|UI/No": "いいえ",
    }


def test_detail_language_helpers() -> None:
    detail = "Unity serileştirilmiş dosya" + DETAIL_LANGUAGES + "en, pt-BR"
    assert detail_languages(detail) == ["en", "pt-BR"]
    assert base_detail(detail) == "Unity serileştirilmiş dosya"
    assert detail_languages("Unity serileştirilmiş dosya") == []
    assert base_detail("Font") == "Font"


def test_scan_detail_keeps_unity_container_name_for_font_scan(i2_two_languages: Inputs) -> None:
    report = scan_sources(i2_two_languages, TaskContext())
    entry = next(e for e in report.entries if e.path == "Data/resources.assets")
    assert detail_languages(entry.detail) == ["en", "ja"]
    assert base_detail(entry.detail) == base_detail(entry.detail.split(DETAIL_LANGUAGES)[0])
    assert DETAIL_LANGUAGES not in base_detail(entry.detail)


def test_i2_languages_survive_project_round_trip(i2_two_languages: Inputs) -> None:
    report = scan_sources(i2_two_languages, TaskContext())
    project = Project.new()
    project.save_scan(report)
    saved = project.latest_scan()
    assert saved is not None
    assert available_languages(saved) == ["en", "ja"]


def test_engine_guess_ignores_language_suffix() -> None:
    """Dil eki eklenmiş `detail` motor tahmininde kanıt sayılmaya devam eder."""
    from nxceviri.core.formats.scanner import DETAIL_LANGUAGES, ScanEntry, guess_engine

    plain = [
        ScanEntry("0100000000000000", "Data/a.assets", 1, "unity", "Unity serileştirilmiş dosya", "high", "base"),
        ScanEntry("0100000000000000", "Data/b.bundle", 1, "unity", "Unity AssetBundle", "high", "base"),
    ]
    tagged = [
        ScanEntry(e.title_id, e.path, e.size, e.kind, e.detail + DETAIL_LANGUAGES + "en, ja", e.likelihood, e.origin)
        for e in plain
    ]
    assert guess_engine(tagged).evidence == guess_engine(plain).evidence
