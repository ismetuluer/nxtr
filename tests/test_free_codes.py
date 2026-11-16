"""Serbest kontrol kodları (ürün sahibinin kararı, 2026-11-16).

Yalnızca tek başına duran kodların (simge, adıyla bağlanan değişken) yeri değiştiyse satır hatalı sayılmaz: uyarıdır
ve dışa aktarılır. Konumsal kodlar (`%s`, `%d`), çiftler (renk aç/kapa) ve satır sonları katıdır. Hangi kodun serbest
olduğunu biçim eklentisi bildirir (`movable_code`); bildirmeyen eklentide hiçbir kod serbest değildir.
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

import pytest

from nxceviri.core.archives import cpk
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.export.layeredfs import (
    ExportInfo,
    ExportOptions,
    ExportResult,
    TextFileRef,
    _export_member_archive,
    _info_text,
    collect_translations,
    settle_rows,
)
from nxceviri.core.formats import registry
from nxceviri.core.formats.base import ControlCode, FormatError, TextEntry
from nxceviri.core.formats.fmsb import FmsbPlugin
from nxceviri.core.formats.fmsb import plugin as fmsb
from nxceviri.core.formats.gfmsg import gfmsg
from nxceviri.core.formats.nnitext import plugin as nnitext
from nxceviri.core.formats.pakyc import plugin as pakyc
from nxceviri.core.formats.psbtext import plugin as psbtext
from nxceviri.core.formats.srt import plugin as srt
from nxceviri.core.formats.unity import unity
from nxceviri.core.formats.unreal import locres
from nxceviri.core.formats.wadlin import plugin as wadlin
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import ImportedFile, Project, TranslationRow
from nxceviri.core.qa.autofix import plan_fixes, reorder_codes
from nxceviri.core.qa.checks import check_row
from nxceviri.core.translate import placeholders
from nxceviri.core.translate.csvio import prepare_correction
from nxceviri.core.translate.port import port_translations
from nxceviri.core.translate.replace import plan_replace
from nxceviri.core.translate.runner import MachineJob, run_machine_translation
from nxceviri.core.translate.status import SOURCE_CHANGED_NOTE, Status, evaluate
from tests.fake_ollama import FakeOllama
from tests.nnicpkbuild import build_cpk, build_fmsb
from tests.test_cpk_fmsb import TID, _tree

# fmsb: ⟦1⟧ = %d (konumsal), ⟦2⟧ = #FN(Bob) (ad değişkeni), ⟦3⟧ = #(56) (simge)
FREE_TEXT = "Gold: %d, name: #FN(Bob) #(56)"
# fmsb: ⟦1⟧ ⟦2⟧ renk çifti, ⟦3⟧ simge
PAIR_TEXT = "#c(12)Red#/c and #(56)"
# fmsb: iki konumsal değişken
POSITIONAL_TEXT = "%s has %d gold"
ARCHIVE = "Game_US.CPK"
SHEET = "MsgSheet/A.fms"
PATH = f"{ARCHIVE}>{SHEET}"


# --- tek karar işlevi ---------------------------------------------------------------------


def test_check_three_outcomes() -> None:
    src = "⟦1⟧Red⟦2⟧ and ⟦3⟧ by ⟦4⟧"  # 1-2 çift, 3 simge, 4 ad değişkeni
    free = frozenset({3, 4})
    assert placeholders.check(src, "⟦1⟧Kırmızı⟦2⟧ ve ⟦3⟧ ⟦4⟧", free) == placeholders.CodeCheck()
    swapped = placeholders.check(src, "⟦4⟧ ⟦3⟧ ve ⟦1⟧Kırmızı⟦2⟧", free)
    assert not swapped.errors
    assert swapped.warnings == (placeholders.FREE_REORDER_WARNING,)
    inside = placeholders.check(src, "⟦1⟧Kırmızı ⟦4⟧ ⟦3⟧⟦2⟧", free)  # serbest kod çiftin içine taşındı
    assert not inside.errors
    assert inside.warnings
    assert placeholders.check(src, "⟦2⟧Kırmızı⟦1⟧ ⟦3⟧ ⟦4⟧", free).errors  # çift ters
    assert placeholders.check(src, "⟦1⟧Kırmızı⟦2⟧ ⟦3⟧", free).errors  # eksik
    assert placeholders.check(src, "⟦1⟧Kırmızı⟦2⟧ ⟦3⟧ ⟦4⟧ ⟦5⟧", free).errors  # fazla
    assert placeholders.check(src, "⟦1⟧Kırmızı⟦2⟧ ⟦3⟧ ⟦3⟧ ⟦4⟧", free).errors  # yinelenen
    assert placeholders.check(src, "⟦4⟧ ⟦3⟧ ve ⟦1⟧Kırmızı⟦2⟧").errors  # serbest kod bildirilmemiş: katı


def test_evaluate_keeps_ok_status_for_free_reorder() -> None:
    src = "A ⟦1⟧ B ⟦2⟧"
    assert evaluate(src, "B ⟦2⟧ A ⟦1⟧", Status.MACHINE, frozenset({1, 2})) == (Status.MACHINE, "")
    status, note = evaluate(src, "B ⟦2⟧ A ⟦1⟧", Status.MACHINE)  # serbest kod bildirilmemiş
    assert status == Status.ERROR
    assert note


# --- eklenti bildirimleri ------------------------------------------------------------------


def _free(kind: str, codes: tuple[ControlCode, ...]) -> list[str]:
    return [codes[n - 1].raw.decode("utf-8") for n in sorted(registry.free_codes(kind, codes))]


def _gf(units: list[int], label: str) -> ControlCode:
    return ControlCode(struct.pack(f"<{len(units)}H", *units), label)


def test_builtin_free_code_table() -> None:
    """Her yerleşik eklenti için hangi kodların serbest olduğu (koddan okunarak belirlendi; emin olunmayan katı)."""
    _s, codes = fmsb.tokenize("%s %d #(56) #FN(Bob) #CN(Ann) #c(1)x#/c #w(40) <br> <1> ^1/x^ #s(0.8)y#/s")
    assert _free("fmsb", codes) == ["#(56)", "#FN(Bob)", "#CN(Ann)"]
    _s, codes = nnitext.tokenize("%s %d <ext:17> <color:0xffff3232>x<color:> <scale:1.3>")
    assert _free("nnitext", codes) == ["<ext:17>"]
    _s, codes = unity.tokenize('{0} {input_0} {0:plural:{} a|{} b} {} <sprite name="x"> <sprite=2> <b>x</b> <br>')
    assert _free("unity", codes) == ["{0}", "{input_0}", "{0:plural:{} a|{} b}", '<sprite name="x">', "<sprite=2>"]
    _s, codes = locres.tokenize('{PlayerName} {0} {} <img id="A"/> <Bold>x</>')
    assert _free("unreal", codes) == ["{PlayerName}", "{0}", '<img id="A"/>']
    gf = (
        _gf([0xE001], "Özel simge"),
        _gf([0], "Satır içi bitiş"),
        _gf([0x10, 2, 0x0100, 0], "Değişken (ad, eşya, hareket…) 0100"),
        _gf([0x10, 2, 0x0200, 0], "Sayı 0200"),
        _gf([0x10, 1, 0xFF00], "Renk"),
    )
    assert sorted(registry.free_codes("gfmsg", gf)) == [1]  # yalnızca simge; değişkenlerin bağlanışı belgelenmedi
    _s, codes = psbtext.tokenize("%s {x} #{color,FF0000FF}a <br> <size=24>b</size>")
    assert not registry.free_codes("psbtext", codes)
    _s, codes = pakyc.tokenize("{v} <f cn=a>x</f> <b action=attack></b>")
    assert not registry.free_codes("pakyc", codes)
    _s, codes = srt.tokenize("<i>x</i> {\\an8} <font color=red>y</font>")
    assert not registry.free_codes("srt", codes)
    _s, codes = wadlin.tokenize("<CLT 3>x<CLT>")
    assert not registry.free_codes("wadlin", codes)
    msbt = (ControlCode(b"\x0e\x00\x01\x00\x00\x00", "Oyun etiketi 1:0"), ControlCode(b"\x0e\x00\x03\x00", "Renk"))
    assert not registry.free_codes("msbt", msbt)
    fsd = (ControlCode(b"\xff\x08\x00\x00\x00", "Yazı kodu"), ControlCode(b"\xff\x0d\x00\x00", "Bekleme"))
    assert not registry.free_codes("fsdmsg", fsd)
    declared = {p.name for p in registry.BUILTIN_PLUGINS if hasattr(p, "movable_code")}
    assert declared == {"fmsb", "nnitext", "unity", "unreal", "gfmsg"}


def test_plugin_without_declaration_has_no_free_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    class UserPlugin:  # sözleşmenin isteğe bağlı bildirimini yapmayan kullanıcı eklentisi
        name = "kullanici"

    monkeypatch.setattr(registry, "plugin_for_kind", lambda kind, title_id=None: UserPlugin())
    registry.reset_user_plugins()
    codes = (ControlCode(b"{name}", "Değişken {name}"), ControlCode(b"<sprite=1>", "Simge (sprite)"))
    try:
        assert registry.free_codes("kullanici", codes) == frozenset()
    finally:
        registry.reset_user_plugins()
    monkeypatch.undo()
    assert registry.free_codes("bilinmeyen-bicim", codes) == frozenset()


# --- proje ---------------------------------------------------------------------------------


def _project(*texts: str, fmt: str = "fmsb", path: str = PATH) -> Project:
    tokenize = fmsb.tokenize if fmt == "fmsb" else nnitext.tokenize
    entries = []
    for i, text in enumerate(texts):
        source, codes = tokenize(text)
        entries.append(TextEntry(str(i), i, source, codes))
    project = Project.new()
    project.import_texts([ImportedFile(path, TID, fmt, "base", tuple(entries))])
    return project


def _write(project: Project, text: str, index: int = 0, **kw: Any) -> TranslationRow:
    row = project.translation_rows()[index]
    return project.set_translations([(row.id, text)], **kw)[0]


def test_rows_know_free_codes_from_plugin() -> None:
    project = _project(FREE_TEXT)
    assert project.translation_rows()[0].free_codes == frozenset({2, 3})


def test_free_reorder_is_not_an_error_and_checks_warn() -> None:
    project = _project(FREE_TEXT)
    row = _write(project, "Ad: ⟦3⟧ ⟦2⟧, altın: ⟦1⟧")
    assert (row.status, row.note) == (Status.APPROVED, "")
    issues = check_row(row, "", "")
    assert [(i.kind, i.severity) for i in issues if i.kind in ("placeholder", "code_order")] == [
        ("code_order", "warning")
    ]


def test_free_code_moved_around_a_pair_is_a_warning_but_reversed_pair_is_an_error() -> None:
    project = _project(PAIR_TEXT)
    assert _write(project, "⟦3⟧ ve ⟦1⟧Kırmızı⟦2⟧").status == Status.APPROVED
    assert _write(project, "⟦1⟧Kırmızı ⟦3⟧⟦2⟧").status == Status.APPROVED
    broken = _write(project, "⟦2⟧Kırmızı⟦1⟧ ve ⟦3⟧")
    assert broken.status == Status.ERROR
    assert [i.severity for i in check_row(broken, "", "") if i.kind == "placeholder"] == ["error"]


@pytest.mark.parametrize("fmt", ["fmsb", "nnitext"])
def test_positional_reorder_is_an_error(fmt: str) -> None:
    project = _project(POSITIONAL_TEXT, fmt=fmt, path=PATH if fmt == "fmsb" else "LOC/EN/A.XSO")
    row = _write(project, "⟦2⟧ altını var: ⟦1⟧")
    assert row.free_codes == frozenset()
    assert row.status == Status.ERROR


def test_missing_extra_or_repeated_codes_stay_errors() -> None:
    project = _project(FREE_TEXT)
    for text in ("Ad: ⟦3⟧ ⟦2⟧", "Ad: ⟦3⟧ ⟦2⟧ ⟦1⟧ ⟦4⟧", "Ad: ⟦3⟧ ⟦2⟧ ⟦1⟧ ⟦1⟧"):
        assert _write(project, text).status == Status.ERROR


# --- dışa aktarma ----------------------------------------------------------------------------


def _sheet_project() -> tuple[Project, bytes, bytes]:
    sheet = build_fmsb(["##(START)", FREE_TEXT, POSITIONAL_TEXT, "Plain line"])
    plugin = FmsbPlugin()
    entries = tuple(plugin.extract(sheet))
    project = Project.new()
    project.import_texts([ImportedFile(PATH, TID, "fmsb", "base", entries)])
    return project, sheet, build_cpk({SHEET: sheet})


def _export(
    project: Project, archive: bytes, *, include_errors: bool = False
) -> tuple[ExportResult, bytes, list[TranslationRow]]:
    rows = project.translation_rows()
    soft: dict[str, set[str]] = {}
    reordered: dict[str, set[str]] = {}
    translations, written, errors, untranslated = collect_translations(
        rows, "", include_errors=include_errors, soft=soft, reordered=reordered
    )
    result = ExportResult(Path("x"), rows_written=written, rows_error=errors, rows_untranslated=untranslated)
    result.soft_keys = {p: frozenset(k) for p, k in soft.items()}
    result.reordered_keys = {p: frozenset(k) for p, k in reordered.items()}
    outputs = _export_member_archive(
        _tree({ARCHIVE: archive}),
        ARCHIVE,
        [TextFileRef(PATH, TID, "fmsb")],
        translations=translations,
        root=Path("romfs"),
        result=result,
    )
    settle_rows(result, rows, include_errors=include_errors)
    written_sheet = cpk.CpkFile(MemoryStorage(outputs[0][1]), ARCHIVE).read(SHEET)
    return result, written_sheet, rows


def _by_key(project: Project) -> dict[str, TranslationRow]:
    return {r.key: r for r in project.translation_rows()}


def test_default_export_writes_free_reorder_and_reads_back() -> None:
    project, _sheet, archive = _sheet_project()
    rows = _by_key(project)
    project.set_translations([(rows["1"].id, "Ad: ⟦3⟧ ⟦2⟧, altın: ⟦1⟧"), (rows["3"].id, "Düz satır")])
    result, written, _rows = _export(project, archive)
    entries = {e.key: e.source for e in FmsbPlugin().extract(written)}
    assert placeholders.renumber(entries["1"]) == placeholders.renumber("Ad: ⟦3⟧ ⟦2⟧, altın: ⟦1⟧")
    assert "Ad: #(56) #FN(Bob), altın: %d".encode() in written
    assert entries["3"] == "Düz satır"
    assert result.rows_written == 2
    assert not result.dropped_keys.get(PATH)
    assert result.reorder_dropped_ids == []


@pytest.mark.parametrize("include_errors", [False, True])
def test_positional_reorder_is_never_exported(include_errors: bool) -> None:
    project, _sheet, archive = _sheet_project()
    rows = _by_key(project)
    project.set_translations([(rows["2"].id, "⟦2⟧ altını var: ⟦1⟧"), (rows["3"].id, "Düz satır")])
    assert _by_key(project)["2"].status == Status.ERROR
    _result, written, _rows = _export(project, archive, include_errors=include_errors)
    entries = {e.key: e.source for e in FmsbPlugin().extract(written)}
    assert entries["2"] == fmsb.tokenize(POSITIONAL_TEXT)[0]  # orijinal kaldı
    assert entries["3"] == "Düz satır"


def test_rejected_free_reorder_goes_back_to_original_and_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    project, _sheet, archive = _sheet_project()
    rows = _by_key(project)
    reordered = "Ad: ⟦3⟧ ⟦2⟧, altın: ⟦1⟧"
    project.set_translations([(rows["1"].id, reordered), (rows["3"].id, "Düz satır")])
    inject = FmsbPlugin.inject

    def picky(self: FmsbPlugin, data: bytes, translations: dict[str, str]) -> bytes:
        if translations.get("1") == reordered:
            raise FormatError("Bu oyun kod sırasını kabul etmiyor.")
        return inject(self, data, translations)

    monkeypatch.setattr(FmsbPlugin, "inject", picky)
    result, written, _rows = _export(project, archive)
    entries = {e.key: e.source for e in FmsbPlugin().extract(written)}
    assert entries["1"] == fmsb.tokenize(FREE_TEXT)[0]  # orijinal kaldı
    assert entries["3"] == "Düz satır"  # dosyanın geri kalanı yazıldı
    assert result.dropped_keys[PATH] == frozenset({"1"})
    assert result.reorder_dropped_ids == [rows["1"].id]
    assert result.rows_written == 1
    assert any("kod sırası" in w for w in result.warnings)
    info = _info_text(ExportInfo("Oyun", TID, 0, None), ExportOptions("atmosphere", Path("x"), "Mod"), result)
    assert "Kod sırası oyun dosyasına yazılamadığı için orijinal bırakılan satır: 1" in info


# --- diğer yollar aynı kararı verir -----------------------------------------------------------


def test_machine_translation_accepts_free_reorder_and_rejects_positional() -> None:
    project = _project(FREE_TEXT, POSITIONAL_TEXT)
    answers = {
        fmsb.tokenize(FREE_TEXT)[0]: "Ad: ⟦3⟧ ⟦2⟧, altın: ⟦1⟧",
        fmsb.tokenize(POSITIONAL_TEXT)[0]: "⟦2⟧ altını var: ⟦1⟧",
    }
    server = FakeOllama(translate=lambda text: answers[text])
    rows = project.translation_rows()
    written: list[tuple[int, str]] = []
    run_machine_translation(
        server.provider(), MachineJob(rows=rows, source_lang="en", all_rows=rows), TaskContext(), written.extend
    )
    # Kodu bozuk sonuç bir kez yeniden istenir (yalnızca konumsal satır); yine bozuksa "Hatalı" olarak yazılır.
    assert len(server.requests) == 2
    project.set_translations(written, machine=True)
    assert [r.status for r in project.translation_rows()] == [Status.MACHINE, Status.ERROR]


def test_import_paths_accept_free_reorder_and_reject_positional() -> None:
    project = _project(FREE_TEXT, POSITIONAL_TEXT)
    free_row, positional_row = project.translation_rows()
    assert prepare_correction(free_row, "Ad: ⟦3⟧ ⟦2⟧, altın: ⟦1⟧")[1] == []
    assert prepare_correction(positional_row, "⟦2⟧ altını var: ⟦1⟧")[1]
    report = port_translations(project, {"0": "Ad: ⟦3⟧ ⟦2⟧, altın: ⟦1⟧", "1": "⟦2⟧ altını var: ⟦1⟧"})
    assert report.applied == 1
    assert [key for key, _s, _i in report.code_problems] == ["1"]
    assert {r.key: r.status for r in project.translation_rows()} == {"0": Status.MACHINE, "1": Status.UNTRANSLATED}


def test_replace_accepts_free_reorder_and_skips_positional() -> None:
    project = _project(FREE_TEXT, POSITIONAL_TEXT)
    rows = project.translation_rows()
    project.set_translations([(rows[0].id, "Altın: ⟦1⟧, ad: ⟦2⟧ ⟦3⟧"), (rows[1].id, "⟦1⟧ adlı kişinin ⟦2⟧ altını")])
    plan = plan_replace(project.translation_rows(), r"(⟦1⟧)(.*)(⟦2⟧)", r"\3\2\1", regex=True)
    assert [row_id for row_id, _t in plan.changes] == [rows[0].id]
    assert plan.skipped == 1


# --- Düzeltmeler ve eski "Hatalı" satırlar ----------------------------------------------------


def test_reorder_codes_leaves_free_codes_where_the_translator_put_them() -> None:
    source = "A⟦1⟧B⟦2⟧C ⟦3⟧ ⟦4⟧"
    labels = ("Satır sonu <br>", "Satır sonu <br>", "Simge #(1)", "Ad değişkeni #FN(x)")
    free = frozenset({3, 4})
    assert reorder_codes(source, "⟦4⟧ ⟦3⟧ A⟦1⟧B⟦2⟧C", labels, free) is None  # yalnızca serbest fark: dokunulmaz
    assert reorder_codes(source, "⟦4⟧ ⟦3⟧ A⟦2⟧B⟦1⟧C", labels, free) == "⟦4⟧ ⟦3⟧ A⟦1⟧B⟦2⟧C"


def test_fix_clears_old_error_rows_that_only_moved_free_codes() -> None:
    project = _project(FREE_TEXT, POSITIONAL_TEXT)
    rows = project.translation_rows()
    project.set_translations([(rows[0].id, "Ad: ⟦3⟧ ⟦2⟧, altın: ⟦1⟧"), (rows[1].id, "⟦2⟧ altını var: ⟦1⟧")])
    # Eski sürümün kaydı: serbest kod sırası farkı yüzünden "Hatalı" duran satır.
    project._conn.execute(
        "UPDATE text_entries SET status = ?, note = ? WHERE id = ?", (Status.ERROR, "eski", rows[0].id)
    )
    old = project.translation_rows()
    assert old[0].status == Status.ERROR
    issues = [i for r in old for i in check_row(r, "", "")]
    plan = plan_fixes(old, issues, ["placeholder"])
    assert plan.changes == [(rows[0].id, "Ad: ⟦3⟧ ⟦2⟧, altın: ⟦1⟧")]
    assert plan.unfixed == 1  # konumsal sıra farkı düzeltilmez, hatalı kalır
    fixed = project.set_translations(plan.changes, machine=True)
    assert (fixed[0].status, fixed[0].note) == (Status.MACHINE, "")


def test_fix_leaves_error_rows_with_intact_codes_alone() -> None:
    """Orijinal metni değiştiği için "Hatalı" işaretlenen satırın kodları sağlamdır; Düzelt onu temizlememeli."""
    project = _project(FREE_TEXT)
    row = project.translation_rows()[0]
    project.set_translations([(row.id, "Altın: ⟦1⟧, ad: ⟦2⟧ ⟦3⟧")])
    project._conn.execute(
        "UPDATE text_entries SET status = ?, note = ? WHERE id = ?", (Status.ERROR, SOURCE_CHANGED_NOTE, row.id)
    )
    old = project.translation_rows()
    plan = plan_fixes(old, [i for r in old for i in check_row(r, "", "")], ["placeholder"])
    assert plan.changes == []
    assert plan.unfixed == 1


def _branch_codes() -> tuple[ControlCode, ...]:
    head = _gf([0x10, 2, 0x1100, 0x0403], "Cinsiyete göre seçim (erkek / kadın) — başı")
    return (head, ControlCode(gfmsg._BRANCH_SEP, "Seçenek ayracı"), ControlCode(gfmsg._BRANCH_END, "Seçim sonu"))


def test_gfmsg_rejects_a_symbol_moved_into_a_branch_option() -> None:
    """Seçenekler düz metin olarak okunur: içine taşınan simge geri okumada metne karışırdı; eklenti reddeder ve
    dışa aktarma o satırı orijinal bırakır."""
    codes = (*_branch_codes(), _gf([0xE001], "Özel simge"))
    source = "my ⟦1⟧boy⟦2⟧girl⟦3⟧ ⟦4⟧"
    assert registry.free_codes("gfmsg", codes) == frozenset({4})
    assert placeholders.check(source, "⟦4⟧ benim ⟦1⟧oğlan⟦2⟧kız⟦3⟧", frozenset({4})).warnings
    assert gfmsg._encode("⟦4⟧ benim ⟦1⟧oğlan⟦2⟧kız⟦3⟧", codes, "k")
    with pytest.raises(FormatError):
        gfmsg._encode("benim ⟦1⟧oğlan ⟦4⟧⟦2⟧kız⟦3⟧", codes, "k")
