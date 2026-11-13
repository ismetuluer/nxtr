"""M5: font denetimi, harf dönüştürme, QA denetimleri ve LayeredFS dışa aktarma."""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path
from typing import Any

import pytest

from nxceviri.core.archives import nested
from nxceviri.core.errors import OperationCancelled
from nxceviri.core.export.addressables import CatalogError, patch_catalog_crc
from nxceviri.core.export.layeredfs import (
    INFO_FILE,
    LAYOUT_ATMOSPHERE,
    LAYOUT_EMULATOR,
    ExportError,
    ExportInfo,
    ExportOptions,
    ExportResult,
    TextFileRef,
    _recover_leftover_backups,
    collect_translations,
    export_mod,
    safe_mod_name,
)
from nxceviri.core.formats.base import FormatError
from nxceviri.core.formats.msbt import MsbtPlugin
from nxceviri.core.formats.unity import UnityPlugin
from nxceviri.core.keys import load_keys
from nxceviri.core.pipeline import Inputs, extract_texts, opened_view, scan_sources, version_warnings
from nxceviri.core.progress import CancelToken, TaskContext
from nxceviri.core.project import Project, SourceRecord, TranslationRow
from nxceviri.core.qa import transliterate
from nxceviri.core.qa.checks import check_row, run_checks
from nxceviri.core.qa.fonts import KIND_TMP_DYNAMIC, KIND_TMP_STATIC, FontInfo, FontReport, scan_fonts
from nxceviri.core.translate.status import Status
from tests import nxbuild
from tests.conftest import BASE_TID, UPDATE_FILES, GameFiles
from tests.unitybuild import (
    addressables_catalog,
    build_bundle,
    bundle_record,
    catalog_records,
    string_table,
    tmp_font,
)

NESTED_COMMON = "Mals/TRtr.Product.sarc.zs>TRtr.Product.sarc>Msg/Ortak.msbt"


# --- harf dönüştürme ve QA ----------------------------------------------------------------


def test_transliterate() -> None:
    text = "Şimdi ⟦1⟧ığdır Çağrı İzmir ⟦2⟧"
    assert transliterate.apply(text, "ğıİşĞŞ") == "Simdi ⟦1⟧igdir Çagri Izmir ⟦2⟧"
    assert transliterate.apply(text, "") == text
    assert transliterate.letters_for(transliterate.MODE_ALL, "") == "çğıİöşüÇĞÖŞÜ"
    assert transliterate.letters_for(transliterate.MODE_MISSING, "ğş") == "ğş"
    assert transliterate.letters_for(transliterate.MODE_NONE, "ğş") == ""


LONG_TR = "Bu çok çok çok uzun bir Türkçe cümle oldu maalesef evet, gerçekten uzun"


def _row(source: str, translation: str, status: str = Status.APPROVED, **kw: Any) -> TranslationRow:
    return TranslationRow(1, "f", "k", source, translation, status, kw.get("note", ""), (), kw.get("max_length"))


@pytest.mark.parametrize(
    ("row", "kinds"),
    [
        (_row("Hello", ""), ["untranslated"]),
        (_row("", ""), []),
        (_row("Hello ⟦1⟧", "Merhaba", Status.ERROR, note="Eksik kontrol kodu: ⟦1⟧"), ["placeholder"]),
        (_row("Hello", "Merhaba şey"), ["glyph"]),
        (_row("Short", "Kısa", max_length=3), ["max_length", "glyph"]),
        (
            _row(
                "A fairly long english sentence here.",
                "Bu çok çok çok uzun bir Türkçe cümle oldu maalesef evet, gerçekten uzun",
            ),
            ["overflow"],
        ),
        (_row("Line\nTwo", "Satır İki"), ["glyph", "newlines"]),
        (_row(" Hello", "Merhaba"), ["spaces"]),
        (_row("Hello", "Merhaba"), []),
    ],
)
def test_check_row(row: TranslationRow, kinds: list[str]) -> None:
    assert [i.kind for i in check_row(row, "ğıİşĞŞ", "")] == kinds


def test_transliteration_silences_glyph_warning() -> None:
    assert check_row(_row("Hello", "Merhaba şey"), "ğıİşĞŞ", "ğıİşĞŞ") == []
    issues = run_checks([_row("a", ""), _row("b", "ş")], "ş", "")
    assert [i.severity for i in issues] == ["info", "warning"]


def test_font_report_math() -> None:
    latin = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
    report = FontReport(
        fonts=[
            FontInfo("A", "f", KIND_TMP_STATIC, latin | set("çöüÇÖÜ"), False),
            FontInfo("B", "f", KIND_TMP_STATIC, latin | set("çöüÇÖÜğ"), False),
            FontInfo("C", "f", KIND_TMP_STATIC, latin, False),
            FontInfo("Japonca", "fonts-japanese", KIND_TMP_STATIC, latin, True),
            FontInfo("Dinamik", "f", KIND_TMP_DYNAMIC, latin | set("çğıİöşüÇĞÖŞÜ"), False),
            FontInfo("Bilinmeyen", "f", KIND_TMP_STATIC, None, False),
        ]
    )
    assert report.coverage()["ç"] == (2, 3)
    assert report.coverage()["ğ"] == (1, 3)
    assert report.missing_letters() == "ğıİşĞŞ"
    assert report.dynamic_fallback_letters() == "ğıİşĞŞ"
    assert report.fonts[5].missing() == ""


# --- MSBT oyunu: iç içe arşiv ve dışa aktarma ---------------------------------------------


@pytest.fixture
def msbt_project(game: GameFiles) -> tuple[Inputs, Project]:
    inputs = Inputs((game.base_nsp, game.update_nsp), load_keys(game.keys_path))
    report = scan_sources(inputs, TaskContext())
    project = Project.new()
    project.import_texts(extract_texts(inputs, report, TaskContext()).files)
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations(
        [
            (rows["Menu_Start"].id, "Maceraya Başla"),
            (rows["Menu_Hello"].id, "Merhaba ⟦1⟧Link⟦2⟧! Şimdi"),
            (rows["No"].id, "Hayır"),
            (rows["Wait"].id, "Lütfen bekleyin"),  # ⟦1⟧ eksik → hatalı, yazılmaz
        ]
    )
    project.set_translations([(rows["Yes"].id, "Evet")], machine=True)
    return inputs, project


def _refs(project: Project) -> list[TextFileRef]:
    return [TextFileRef(*f) for f in project.text_files()]


INFO = ExportInfo("Deneme Oyunu", f"{BASE_TID:016X}", 0, 65536)


def test_collect_translations(msbt_project: tuple[Inputs, Project]) -> None:
    _inputs, project = msbt_project
    by_file, written, errors, untranslated = collect_translations(project.translation_rows(), "ş")
    assert written == 4
    assert errors == 1
    assert untranslated == 1  # Menu_New
    assert by_file["Message/Ana_Menü.msbt"]["Menu_Start"] == "Maceraya Basla"


def test_export_atmosphere(msbt_project: tuple[Inputs, Project], game: GameFiles, tmp_path: Path) -> None:
    inputs, project = msbt_project
    before = hashlib.sha256(game.base_nsp.read_bytes()).hexdigest()
    dest = tmp_path / "Modlarım ğüş" / "Deneme Türkçe"
    progress: list[int] = []
    result = export_mod(
        inputs,
        _refs(project),
        project.translation_rows(),
        options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "Deneme Türkçe", "ğıİşĞŞ"),
        info=INFO,
        ctx=TaskContext(lambda d, _t, _m: progress.append(d)),
    )
    root = Path("atmosphere", "contents", f"{BASE_TID:016X}", "romfs")
    assert sorted(result.files) == sorted(
        [(root / "Message/Ana_Menü.msbt").as_posix(), (root / "Mals/TRtr.Product.sarc.zs").as_posix()]
    )
    assert (result.rows_written, result.rows_error, result.rows_untranslated) == (4, 1, 1)
    menu = {e.key: e.source for e in MsbtPlugin().extract((dest / root / "Message/Ana_Menü.msbt").read_bytes())}
    assert menu == {"Menu_Start": "Maceraya Basla", "Menu_Hello": "Merhaba ⟦1⟧Link⟦2⟧! Simdi", "Menu_New": "New option"}
    packed = (dest / root / "Mals/TRtr.Product.sarc.zs").read_bytes()
    inner = nested.split(NESTED_COMMON)[1:]
    common = {e.key: e.source for e in MsbtPlugin().extract(nested.open_inner(packed, inner))}
    assert common == {"Yes": "Evet", "No": "Hayir", "Wait": "Please wait⟦1⟧"}  # hatalı satır orijinal kaldı
    # Aynı arşivdeki dokunulmayan dosya bayt bayt aynı.
    bozuk = ["TRtr.Product.sarc", "Msg/Bozuk.msbt"]
    assert nested.open_inner(packed, bozuk) == nested.open_inner(UPDATE_FILES["Mals/TRtr.Product.sarc.zs"], bozuk)
    info = (dest / INFO_FILE).read_text(encoding="utf-8")
    assert "v65536" in info
    assert "ğ ı İ ş Ğ Ş → g i I s G S" in info
    assert hashlib.sha256(game.base_nsp.read_bytes()).hexdigest() == before  # oyun dosyası değişmedi
    assert not [p for p in dest.parent.iterdir() if p.name.startswith(".")]  # geçici klasör kalmadı
    assert progress


def _with_error_status(project: Project, *keys: str) -> list[TranslationRow]:
    """Verilen anahtarlı satırların durumunu "hatalı" yapar (çevirileri korunur)."""
    return [dataclasses.replace(r, status=Status.ERROR) if r.key in keys else r for r in project.translation_rows()]


def _common_texts(dest: Path) -> dict[str, str]:
    root = Path("atmosphere", "contents", f"{BASE_TID:016X}", "romfs")
    packed = (dest / root / "Mals/TRtr.Product.sarc.zs").read_bytes()
    inner = nested.split(NESTED_COMMON)[1:]
    return {e.key: e.source for e in MsbtPlugin().extract(nested.open_inner(packed, inner))}


def test_collect_translations_include_errors(msbt_project: tuple[Inputs, Project]) -> None:
    _inputs, project = msbt_project
    rows = _with_error_status(project, "No")
    soft: dict[str, set[str]] = {}
    by_file, written, errors, untranslated = collect_translations(rows, "ş", include_errors=True, soft=soft)
    assert (written, errors, untranslated) == (3, 2, 1)  # hatalı satırlar "yazılacak" sayısına katılmaz
    assert sorted(k for keys in soft.values() for k in keys) == ["No"]  # "Wait" kodu eksik: hiç denenmez
    assert sum(len(v) for v in by_file.values()) == 4
    # Kapalıyken eski davranış: hatalı satır tabloya girmez.
    off, written_off, errors_off, _u = collect_translations(rows, "ş")
    assert (written_off, errors_off) == (3, 2)
    assert sum(len(v) for v in off.values()) == 3


def test_export_skips_error_rows_by_default(msbt_project: tuple[Inputs, Project], tmp_path: Path) -> None:
    inputs, project = msbt_project
    dest = tmp_path / "kapali"
    result = export_mod(
        inputs,
        _refs(project),
        _with_error_status(project, "No"),
        options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "Deneme", ""),
        info=INFO,
    )
    assert (result.rows_written, result.rows_error) == (3, 2)
    assert (result.rows_error_written, result.rows_error_kept) == (0, 0)
    assert _common_texts(dest) == {"Yes": "Evet", "No": "No", "Wait": "Please wait⟦1⟧"}  # hatalı "No" yazılmadı
    info = (dest / INFO_FILE).read_text(encoding="utf-8")
    assert "Hatalı olduğu için yazılmayan satır: 2" in info
    assert "oyun çökebilir" not in info


def test_export_includes_error_rows_and_keeps_rejected_original(
    msbt_project: tuple[Inputs, Project], tmp_path: Path
) -> None:
    inputs, project = msbt_project
    dest = tmp_path / "acik"
    result = export_mod(
        inputs,
        _refs(project),
        _with_error_status(project, "No"),
        options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "Deneme", "", include_errors=True),
        info=INFO,
    )
    # "No": geçerli çeviri, hatalı işaretli → yazıldı. "Wait": ⟦1⟧ eksik → eklenti reddetti → orijinal.
    assert _common_texts(dest) == {"Yes": "Evet", "No": "Hayır", "Wait": "Please wait⟦1⟧"}
    assert (result.rows_error, result.rows_error_written, result.rows_error_kept) == (2, 1, 1)
    assert result.rows_written == 3
    info = (dest / INFO_FILE).read_text(encoding="utf-8")
    assert "çevirisiyle yazılan satır (oyun çökebilir): 1" in info
    assert "orijinal bırakılan satır: 1" in info
    assert not [p for p in dest.parent.iterdir() if p.name.startswith(".")]


def test_export_include_errors_all_rejected_still_exports_rest(
    msbt_project: tuple[Inputs, Project], tmp_path: Path
) -> None:
    inputs, project = msbt_project
    result = export_mod(
        inputs,
        _refs(project),
        project.translation_rows(),
        options=ExportOptions(LAYOUT_ATMOSPHERE, tmp_path / "hepsi", "Deneme", "", include_errors=True),
        info=INFO,
    )
    assert (result.rows_error_written, result.rows_error_kept) == (0, 1)
    assert _common_texts(tmp_path / "hepsi") == {"Yes": "Evet", "No": "Hayır", "Wait": "Please wait⟦1⟧"}


def test_export_include_errors_prefilters_broken_codes_without_inject(
    msbt_project: tuple[Inputs, Project], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Kontrol kodu bozuk satır inject'e hiç verilmez (eklenti zaten reddedeceği için boşuna deneme olmasın)."""
    inputs, project = msbt_project
    seen: list[dict[str, str]] = []
    real = MsbtPlugin.inject

    def spy(self: MsbtPlugin, data: bytes, translations: Any) -> bytes:
        seen.append(dict(translations))
        return real(self, data, translations)

    monkeypatch.setattr(MsbtPlugin, "inject", spy)
    result = export_mod(
        inputs,
        _refs(project),
        _with_error_status(project, "No"),
        options=ExportOptions(LAYOUT_ATMOSPHERE, tmp_path / "onsuz", "Deneme", "", include_errors=True),
        info=INFO,
    )
    assert all("Lütfen bekleyin" not in t.values() for t in seen)
    assert len(seen) == 2  # dosya başına tek inject
    assert (result.rows_error_written, result.rows_error_kept) == (1, 1)


def test_export_include_errors_counts_only_processed_files(
    msbt_project: tuple[Inputs, Project], tmp_path: Path
) -> None:
    """Dosyası dışa aktarmaya hiç girmeyen hatalı satır "yazıldı" sayılmaz."""
    inputs, project = msbt_project
    refs = [f for f in _refs(project) if f.path != "Message/Ana_Menü.msbt"]
    result = export_mod(
        inputs,
        refs,
        _with_error_status(project, "Menu_Start"),
        options=ExportOptions(LAYOUT_ATMOSPHERE, tmp_path / "eksik", "Deneme", "", include_errors=True),
        info=INFO,
    )
    assert result.rows_error_written == 0
    assert result.rows_error_kept == result.rows_error


def test_export_include_errors_bisection_is_cancellable(
    msbt_project: tuple[Inputs, Project], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inputs, project = msbt_project
    token = CancelToken()
    real = MsbtPlugin.inject
    after_cancel: list[int] = []

    def reject(self: MsbtPlugin, data: bytes, translations: Any) -> bytes:
        if token.cancelled:
            after_cancel.append(1)
        if "Hayır" in translations.values() and "Evet" in translations.values():
            token.cancel()
            raise FormatError("reddedildi")
        return real(self, data, translations)

    monkeypatch.setattr(MsbtPlugin, "inject", reject)
    with pytest.raises(OperationCancelled):
        export_mod(
            inputs,
            _refs(project),
            _with_error_status(project, "No"),
            options=ExportOptions(LAYOUT_ATMOSPHERE, tmp_path / "iptal", "Deneme", "", include_errors=True),
            info=INFO,
            ctx=TaskContext(token=token),
        )
    assert not (tmp_path / "iptal").exists()
    assert not after_cancel  # iptalden sonra yeni inject denenmez


def test_export_include_errors_unrelated_failure_is_not_swallowed(
    msbt_project: tuple[Inputs, Project], tmp_path: Path
) -> None:
    """Hatalı olmayan bir satır yazılamıyorsa hata yutulmaz (yalnızca hatalı satırlar orijinale düşer)."""
    inputs, project = msbt_project
    rows = [dataclasses.replace(r, translation="Yok ⟦9⟧") if r.key == "No" else r for r in project.translation_rows()]
    with pytest.raises(ExportError):
        export_mod(
            inputs,
            _refs(project),
            rows,
            options=ExportOptions(LAYOUT_ATMOSPHERE, tmp_path / "bozuk", "Deneme", "", include_errors=True),
            info=INFO,
        )
    assert not (tmp_path / "bozuk").exists()


def test_export_emulator_layout(msbt_project: tuple[Inputs, Project], tmp_path: Path) -> None:
    inputs, project = msbt_project
    dest = tmp_path / "emu"
    result = export_mod(
        inputs,
        _refs(project),
        project.translation_rows(),
        options=ExportOptions(LAYOUT_EMULATOR, dest, 'Türkçe: "Yama"?', ""),
        info=INFO,
    )
    assert all(f.startswith(f"{BASE_TID:016X}/Türkçe Yama/romfs/") for f in result.files)
    assert safe_mod_name("  ") == "Turkce Ceviri"


def test_export_refuses_non_empty_destination(msbt_project: tuple[Inputs, Project], tmp_path: Path) -> None:
    inputs, project = msbt_project
    dest = tmp_path / "dolu"
    dest.mkdir()
    (dest / "benim.txt").write_text("dokunma", encoding="utf-8")
    with pytest.raises(ExportError, match="boş değil"):
        export_mod(
            inputs,
            _refs(project),
            project.translation_rows(),
            options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "x"),
            info=INFO,
        )
    assert (dest / "benim.txt").read_text(encoding="utf-8") == "dokunma"


def test_export_cancel_leaves_nothing(msbt_project: tuple[Inputs, Project], tmp_path: Path) -> None:
    inputs, project = msbt_project
    token = CancelToken()
    dest = tmp_path / "iptal"
    with pytest.raises(OperationCancelled):
        export_mod(
            inputs,
            _refs(project),
            project.translation_rows(),
            options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "x"),
            info=INFO,
            ctx=TaskContext(lambda *_: token.cancel(), token),
        )
    assert list(tmp_path.iterdir()) == []


def test_export_without_translations(game: GameFiles, tmp_path: Path) -> None:
    inputs = Inputs((game.base_nsp,), load_keys(game.keys_path))
    project = Project.new()
    project.import_texts(extract_texts(inputs, scan_sources(inputs, TaskContext()), TaskContext()).files)
    with pytest.raises(ExportError, match="çeviri yok"):
        export_mod(
            inputs,
            _refs(project),
            project.translation_rows(),
            options=ExportOptions(LAYOUT_ATMOSPHERE, tmp_path / "m", "x"),
            info=INFO,
        )


def test_export_detects_missing_game_file(
    msbt_project: tuple[Inputs, Project], game: GameFiles, tmp_path: Path
) -> None:
    _inputs, project = msbt_project
    other = nxbuild.build_package(
        game.keys, kind="base", title_id=BASE_TID, application_id=BASE_TID, version=0, romfs_files={"x.txt": b"1"}
    )
    path = tmp_path / "farkli_surum.nsp"
    path.write_bytes(other.nsp)
    inputs = Inputs((path,), load_keys(game.keys_path))
    with pytest.raises(ExportError, match="bulunamadı"):
        export_mod(
            inputs,
            _refs(project),
            project.translation_rows(),
            options=ExportOptions(LAYOUT_ATMOSPHERE, tmp_path / "m", "x"),
            info=INFO,
        )
    assert not (tmp_path / "m").exists()


def test_version_warnings(tmp_path: Path) -> None:
    from nxceviri.core.formats.scanner import EngineGuess, ScanReport

    report = ScanReport("x", "0", 0, 65536, EngineGuess("unknown", "", "none", ()), [])
    base = SourceRecord(tmp_path / "b.nsp", "base", "0", "0", 0, "", "", 1)
    upd = SourceRecord(tmp_path / "u.nsp", "update", "1", "0", 65536, "", "", 1)
    newer = SourceRecord(tmp_path / "u2.nsp", "update", "1", "0", 131072, "", "", 1)
    assert version_warnings([base, upd], report) == []
    assert "güncellemesiz" in version_warnings([base], report)[0]
    assert "v131072" in version_warnings([base, newer], report)[0]
    assert version_warnings([base], None)


# --- Unity oyunu: font denetimi ve dışa aktarma -------------------------------------------

AA = "Data/StreamingAssets/aa/Switch/"


@pytest.fixture
def unity_game(tmp_path: Path) -> tuple[Inputs, Path]:
    latin = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    keys = nxbuild.TestKeys.random()
    files = {
        "Data/globalgamemanagers": b"\0" * 8 + (22).to_bytes(4, "big") + b"\0" * 20,
        AA + "localization-string-tables-english(en)_assets_all.bundle": build_bundle(
            [string_table("UI_en", "en", 0, [(1, "Yes"), (2, "<b>No</b>")])]
        ),
        AA + "fonts_assets_all.bundle": build_bundle(
            [tmp_font("Ana SDF", latin + "çöüÇÖÜ"), tmp_font("Başlık SDF", latin + "çöüÇÖÜ")]
        ),
        AA + "fonts-japanese_assets_all.bundle": build_bundle([tmp_font("Mincho SDF", latin + "あい")]),
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
    nsp = tmp_path / "unity.nsp"
    nsp.write_bytes(pkg.nsp)
    return Inputs((nsp,), load_keys(keys.write(tmp_path / "prod.keys"))), tmp_path


def test_unity_fonts_and_export(unity_game: tuple[Inputs, Path]) -> None:
    inputs, tmp_path = unity_game
    report = scan_sources(inputs, TaskContext())
    with opened_view(inputs, TaskContext()) as view:
        fonts = scan_fonts(view, report)
    assert {f.name for f in fonts.fonts} == {"Ana SDF", "Başlık SDF", "Mincho SDF"}
    assert next(f for f in fonts.fonts if f.name == "Mincho SDF").language_specific
    assert fonts.missing_letters() == "ğıİşĞŞ"

    project = Project.new()
    project.import_texts(extract_texts(inputs, report, TaskContext(), "en").files)
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations([(rows["UI_en/1"].id, "Evet şimdi"), (rows["UI_en/2"].id, "⟦1⟧Hayır⟦2⟧")])
    dest = tmp_path / "mod"
    letters = transliterate.letters_for(transliterate.MODE_MISSING, fonts.missing_letters())
    result = export_mod(
        inputs,
        [TextFileRef(*f) for f in project.text_files()],
        project.translation_rows(),
        options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "x", letters),
        info=ExportInfo("Unity Oyunu", "0100AAAA00000000", 0, None),
    )
    bundle = (dest / result.files[0]).read_bytes()
    texts = {e.key: e.source for e in UnityPlugin().extract(bundle)}
    assert texts == {"UI_en/1": "Evet simdi", "UI_en/2": "⟦1⟧Hayir⟦2⟧"}


# --- Addressables: değiştirilen paketin katalog CRC'si --------------------------------------


def test_patch_catalog_crc_only_touches_matching_records() -> None:
    target = bundle_record(46548, 1109416191)
    other = bundle_record(100, 0)
    untouched = bundle_record(46524, 3958103526)
    catalog = addressables_catalog([target, other, untouched])

    patched, fixed = patch_catalog_crc(catalog, {46548})

    assert fixed == [46548]
    assert len(patched) == len(catalog)  # kayıt uzunlukları korunur (ofsetler bozulmaz)
    records = catalog_records(patched)
    assert [r["m_Crc"] for r in records] == [0, 0, 3958103526]
    assert records[0]["m_BundleSize"] == 46548
    assert records[2] == untouched

    again, fixed_again = patch_catalog_crc(patched, {46548})
    assert fixed_again == []
    assert again == patched


def test_patch_catalog_crc_no_match_leaves_catalog_unchanged() -> None:
    catalog = addressables_catalog([bundle_record(100, 42)])
    assert patch_catalog_crc(catalog, {999}) == (catalog, [])
    with pytest.raises(CatalogError):
        patch_catalog_crc(b'{"m_InternalIds":[]}', {100})


def test_export_patches_addressables_catalog(tmp_path: Path) -> None:
    keys = nxbuild.TestKeys.random()
    table = build_bundle([string_table("UI_en", "en", 0, [(1, "Yes")])])
    catalog = addressables_catalog([bundle_record(len(table), 1109416191)])
    files = {
        "Data/globalgamemanagers": b"\0" * 8 + (22).to_bytes(4, "big") + b"\0" * 20,
        AA + "localization-string-tables-english(en)_assets_all.bundle": table,
        "Data/StreamingAssets/aa/catalog.json": catalog,
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
    nsp = tmp_path / "unity.nsp"
    nsp.write_bytes(pkg.nsp)
    inputs = Inputs((nsp,), load_keys(keys.write(tmp_path / "prod.keys")))
    report = scan_sources(inputs, TaskContext())
    project = Project.new()
    project.import_texts(extract_texts(inputs, report, TaskContext(), "en").files)
    row = next(r for r in project.translation_rows() if r.key == "UI_en/1")
    project.set_translations([(row.id, "Evet")])

    dest = tmp_path / "mod"
    result = export_mod(
        inputs,
        [TextFileRef(*f) for f in project.text_files()],
        project.translation_rows(),
        options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "x"),
        info=ExportInfo("Unity Oyunu", "0100AAAA00000000", 0, None),
    )

    root = Path("atmosphere", "contents", "0100AAAA00000000", "romfs")
    catalog_rel = (root / "Data/StreamingAssets/aa/catalog.json").as_posix()
    assert catalog_rel in result.files
    assert result.catalog_crc_fixes == [len(table)]
    patched = (dest / catalog_rel).read_bytes()
    assert len(patched) == len(catalog)
    assert catalog_records(patched)[0]["m_Crc"] == 0
    info = (dest / INFO_FILE).read_text(encoding="utf-8")
    assert "katalog CRC düzeltmesi" in info


def _export(project: Project, inputs: Inputs, dest: Path, **options: object) -> ExportResult:
    return export_mod(
        inputs,
        _refs(project),
        project.translation_rows(),
        options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "x", **options),  # type: ignore[arg-type]
        info=INFO,
    )


def test_overwrite_replaces_an_earlier_nxtr_mod(msbt_project: tuple[Inputs, Project], tmp_path: Path) -> None:
    inputs, project = msbt_project
    dest = tmp_path / "mod"
    _export(project, inputs, dest)
    (dest / "eski-kalinti.txt").write_text("eski", encoding="utf-8")
    result = _export(project, inputs, dest, overwrite=True)
    assert not (dest / "eski-kalinti.txt").exists()  # eski mod silindi, kalıntı karışmadı
    assert result.files
    assert (dest / INFO_FILE).is_file()
    assert not list(tmp_path.glob(".mod*"))  # yedek ve geçici klasör kalmadı


def test_overwrite_never_deletes_a_folder_nxtr_did_not_make(
    msbt_project: tuple[Inputs, Project], tmp_path: Path
) -> None:
    inputs, project = msbt_project
    dest = tmp_path / "Masaustu"
    dest.mkdir()
    (dest / "belge.txt").write_text("önemli", encoding="utf-8")
    with pytest.raises(ExportError, match="NXTR"):
        _export(project, inputs, dest, overwrite=True)
    assert (dest / "belge.txt").read_text(encoding="utf-8") == "önemli"


def _leftover(parent: Path, name: str, *, with_info: bool, tag: str = "ab12cd34") -> Path:
    folder = parent / f".{name}.{tag}.eski"
    folder.mkdir()
    (folder / "eski-mod.txt").write_text("eski", encoding="utf-8")
    if with_info:
        (folder / INFO_FILE).write_text("eski bilgi", encoding="utf-8")
    return folder


def test_leftover_backup_is_restored_when_destination_is_missing(
    msbt_project: tuple[Inputs, Project], tmp_path: Path
) -> None:
    inputs, project = msbt_project
    dest = tmp_path / "mod"
    leftover = _leftover(tmp_path, "mod", with_info=True)
    result = _export(project, inputs, dest, overwrite=True)
    assert not leftover.exists()
    assert not list(tmp_path.glob(".mod*"))
    assert result.files
    assert not (dest / "eski-mod.txt").exists()  # eski mod geri geldi, sonra yenisiyle değişti
    assert (dest / INFO_FILE).read_text(encoding="utf-8") != "eski bilgi"


def test_leftover_backup_is_restored_even_when_overwrite_is_off(
    msbt_project: tuple[Inputs, Project], tmp_path: Path
) -> None:
    inputs, project = msbt_project
    dest = tmp_path / "mod"
    leftover = _leftover(tmp_path, "mod", with_info=True)
    with pytest.raises(ExportError, match="boş değil"):
        _export(project, inputs, dest)
    assert not leftover.exists()
    assert (dest / "eski-mod.txt").read_text(encoding="utf-8") == "eski"
    assert (dest / INFO_FILE).read_text(encoding="utf-8") == "eski bilgi"


def test_leftover_backup_is_removed_when_destination_exists(
    msbt_project: tuple[Inputs, Project], tmp_path: Path
) -> None:
    inputs, project = msbt_project
    dest = tmp_path / "mod"
    _export(project, inputs, dest)
    leftover = _leftover(tmp_path, "mod", with_info=True)
    _export(project, inputs, dest, overwrite=True)
    assert not leftover.exists()
    assert (dest / INFO_FILE).is_file()


def test_leftover_cleanup_touches_only_matching_nxtr_backups(
    msbt_project: tuple[Inputs, Project], tmp_path: Path
) -> None:
    inputs, project = msbt_project
    dest = tmp_path / "mod"
    _export(project, inputs, dest)
    no_info = _leftover(tmp_path, "mod", with_info=False)  # kalıba uyar ama NXTR modu değil
    other_mod = _leftover(tmp_path, "baska", with_info=True)  # başka modun yedeği
    wrong_tag = tmp_path / ".mod.xyz.eski"  # kalıba uymaz
    wrong_tag.mkdir()
    (wrong_tag / INFO_FILE).write_text("x", encoding="utf-8")
    neighbour = tmp_path / "mod2"
    neighbour.mkdir()
    (neighbour / INFO_FILE).write_text("x", encoding="utf-8")
    _export(project, inputs, dest, overwrite=True)
    for kept in (no_info, other_mod, wrong_tag, neighbour):
        assert kept.is_dir()
        assert any(kept.iterdir())


def test_leftover_restore_failure_is_logged_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    leftover = _leftover(tmp_path, "mod", with_info=True)

    def boom(src: object, dst: object) -> None:
        raise OSError("kilitli")

    monkeypatch.setattr("nxceviri.core.export.layeredfs.os.replace", boom)
    with caplog.at_level("WARNING"):
        _recover_leftover_backups(tmp_path / "mod")
    assert leftover.is_dir()
    assert "kilitli" in caplog.text


def test_extra_files_are_written_into_the_mod(msbt_project: tuple[Inputs, Project], tmp_path: Path) -> None:
    inputs, project = msbt_project
    dest = tmp_path / "fontlu"
    result = _export(project, inputs, dest, extra_files={f"{BASE_TID:016X}": {"Font/oyun.ttf": b"yeni-font"}})
    written = [f for f in result.files if f.endswith("Font/oyun.ttf")]
    assert len(written) == 1
    assert (dest / written[0]).read_bytes() == b"yeni-font"


def test_export_lists_which_error_rows_stayed_original(msbt_project: tuple[Inputs, Project], tmp_path: Path) -> None:
    """Orijinal kalan hatalı satırlar sonuçta kimliğiyle bulunur; çevirisiyle yazılan hatalı satır listede yoktur."""
    inputs, project = msbt_project
    rows = _with_error_status(project, "No", "Wait")
    result = export_mod(
        inputs,
        _refs(project),
        rows,
        options=ExportOptions(LAYOUT_ATMOSPHERE, tmp_path / "liste", "Deneme", "", include_errors=True),
        info=INFO,
    )
    by_key = {r.key: r.id for r in rows}
    assert result.error_kept_ids == [by_key["Wait"]]  # "No" yazıldı, "Wait" (kodu eksik) orijinal kaldı
    plain = export_mod(
        inputs,
        _refs(project),
        rows,
        options=ExportOptions(LAYOUT_ATMOSPHERE, tmp_path / "duz", "Deneme", ""),
        info=INFO,
    )
    assert sorted(plain.error_kept_ids) == sorted([by_key["No"], by_key["Wait"]])


def test_export_refuses_when_written_file_gains_or_loses_rows(
    msbt_project: tuple[Inputs, Project], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Yazılan dosya geri okununca satır kümesi orijinalinkinden farklıysa (ör. çeviriye karışan satır sonu satırı
    böldüyse) mod üretilmez; neden ve satır adı söylenir."""
    from nxceviri.core.formats.base import TextEntry

    inputs, project = msbt_project
    written: list[bytes] = []
    real_inject, real_extract = MsbtPlugin.inject, MsbtPlugin.extract

    def inject(self: MsbtPlugin, data: bytes, translations: Any) -> bytes:
        out = real_inject(self, data, translations)
        written.append(out)
        return out

    def extract(self: MsbtPlugin, data: bytes, context: Any = None) -> list[TextEntry]:
        entries = real_extract(self, data, context)
        if data in written:  # yazılmış dosya: fazladan bir satır belirmiş gibi
            entries = [*entries, TextEntry("/(ghost_key)", 99, "kalıntı", ())]
        return entries

    monkeypatch.setattr(MsbtPlugin, "inject", inject)
    monkeypatch.setattr(MsbtPlugin, "extract", extract)
    dest = tmp_path / "bozuk"
    with pytest.raises(ExportError) as caught:
        export_mod(
            inputs,
            _refs(project),
            project.translation_rows(),
            options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "Deneme", ""),
            info=INFO,
        )
    assert "satır kümesi" in caught.value.message
    assert "/(ghost_key)" in caught.value.message
    assert not dest.exists()  # hedefte hiçbir şey bırakılmadı
