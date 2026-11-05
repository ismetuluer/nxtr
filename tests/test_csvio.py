"""TXT/XLSX/CSV ile dışa/içe aktarma ve geri alma yığını (Ctrl+Z)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from nxceviri.core.formats.base import ControlCode, TextEntry
from nxceviri.core.project import (
    JOB_MANUAL,
    JOB_REVERT,
    JOB_UNAPPROVE,
    ImportedFile,
    Project,
    TranslationRow,
    row_group,
)
from nxceviri.core.project.store import UNDO_LIMIT
from nxceviri.core.translate.csvio import (
    TRANSLATION_COLUMNS,
    TXT_COLUMNS,
    CsvError,
    CsvRow,
    export_csv,
    export_translation_txt,
    export_translation_xlsx,
    export_txt,
    export_xlsx,
    parse_csv,
    parse_txt,
    parse_xlsx,
    plan_import,
    prepare_correction,
    read_csv,
    read_revision_file,
    revision_prompt,
    revision_prompt_txt,
    revision_prompt_xlsx,
    rows_csv,
    rows_translation_txt,
    rows_translation_xlsx,
    rows_txt,
    rows_xlsx,
    table_xlsx,
    translation_prompt_txt,
    translation_prompt_xlsx,
)
from nxceviri.core.translate.status import Status

LB = ControlCode(b"\n", "Satır sonu")


def _project() -> Project:
    p = Project.new()
    entries = (
        TextEntry("a", 0, 'Hello, "friend"!', ()),
        TextEntry("b", 1, "We could make⟦1⟧the goal.", (LB,)),
        TextEntry("c", 2, "Not me.", ()),
    )
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", entries)])
    rows = _rows(p)
    p.set_translations([(rows["a"].id, 'Merhaba, "dostum"!'), (rows["b"].id, "Kale yaparız.⟦1⟧")], machine=True)
    p.set_translations([(rows["c"].id, "Ben değil.")])  # onaylı
    return p


def _rows(p: Project) -> dict[str, TranslationRow]:
    return {r.key: r for r in p.translation_rows()}


def test_export_round_trips_through_parser(tmp_path: Path) -> None:
    p = _project()
    rows = p.translation_rows()
    paths = export_csv(rows, tmp_path / "oyun.csv")
    assert paths == [tmp_path / "oyun.csv"]
    raw = paths[0].read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM: Excel Türkçe karakterleri doğru açar
    parsed = read_csv(paths[0])
    assert [(c.entry_id, c.source, c.text) for c in parsed] == [(r.id, r.source, r.translation) for r in rows]
    assert plan_import(rows, parsed).changes == []  # değişmeden geri yükleme hiçbir şey yazmaz


def test_export_splits_into_numbered_parts(tmp_path: Path) -> None:
    rows = _project().translation_rows()
    paths = export_csv(rows, tmp_path / "oyun.csv", part_rows=2)
    assert [x.name for x in paths] == ["oyun_001.csv", "oyun_002.csv"]
    assert [len(read_csv(x)) for x in paths] == [2, 1]


def test_export_by_group_writes_one_file_per_group(tmp_path: Path) -> None:
    def row(i: int, file: str) -> TranslationRow:
        return TranslationRow(i, file, f"k{i}", "Hi", "Selam", "machine", "", (), None)

    rows = [row(1, "a.assets>Dialogue"), row(2, "a.assets>UI: Menü?"), row(3, "a.assets>Dialogue")]
    paths = export_csv(rows, tmp_path / "oyun.csv", by_group=True)
    assert [x.name for x in paths] == ["oyun_Dialogue.csv", "oyun_UI_ Menü.csv"]  # dosya adına uymayanlar atılır
    assert [c.entry_id for c in read_csv(paths[0])] == [1, 3]
    parts = export_csv(rows, tmp_path / "p.csv", part_rows=1, by_group=True)
    assert [x.name for x in parts] == ["p_Dialogue_001.csv", "p_Dialogue_002.csv", "p_UI_ Menü.csv"]


def test_parser_tolerates_chat_model_output() -> None:
    text = (
        "Here is the revised file you provided:\n"
        "```csv\n"
        "ID;Anahtar;Orijinal;Çeviri\n"
        '7;"a";"Hello";"Selam; dostum"\n'
        "\n"
        "8;b;Bye;Hoşça kal\n"
        "```\n"
    )
    assert parse_csv(text) == [CsvRow(7, "Hello", "Selam; dostum"), CsvRow(8, "Bye", "Hoşça kal")]
    assert parse_csv("id,translation\n3,Evet\n") == [CsvRow(3, None, "Evet")]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("a,b\n1,2\n", "sütunları bulunamadı"),
        ('id,ceviri\nX,"Evet"\n', "sayı değil"),
        ("id,anahtar,orijinal,ceviri\n1\n", "sütun eksik"),
    ],
)
def test_parser_rejects_broken_files(text: str, message: str) -> None:
    with pytest.raises(CsvError, match=message):
        parse_csv(text)


def test_read_csv_accepts_windows_turkish_encoding(tmp_path: Path) -> None:
    path = tmp_path / "excel.csv"
    path.write_bytes("id;çeviri\n5;Şişe ığdır\n".encode("cp1254"))
    assert read_csv(path) == [CsvRow(5, None, "Şişe ığdır")]


def test_plan_import_cleans_validates_and_skips() -> None:
    p = _project()
    rows = _rows(p)
    csv_rows = [
        CsvRow(rows["a"].id, rows["a"].source, "<b>Selam</b> dostum!"),  # fazla etiket temizlenir
        CsvRow(rows["b"].id, rows["b"].source, "Kale[1]yapabiliriz."),  # bozuk kod yazımı onarılır
        CsvRow(rows["c"].id, rows["c"].source, "Ben olmam."),  # onaylı satır da değişir
        CsvRow(999, "x", "y"),
    ]
    plan = plan_import(p.translation_rows(), csv_rows)
    assert dict(plan.changes) == {
        rows["a"].id: "Selam dostum!",
        rows["b"].id: "Kale⟦1⟧yapabiliriz.",
        rows["c"].id: "Ben olmam.",
    }
    assert (plan.cleaned, plan.approved, plan.unknown) == (2, 1, 1)

    bad = plan_import(
        p.translation_rows(),
        [
            CsvRow(rows["b"].id, None, "Kale yaparız."),  # kod yok
            CsvRow(rows["a"].id, "Something else", "Başka"),  # başka satırın/projenin orijinali
            CsvRow(rows["c"].id, None, "  "),
        ],
    )
    assert bad.changes == []
    assert [eid for eid, _ in bad.code_problems] == [rows["b"].id]
    assert bad.source_mismatch == [rows["a"].id]
    assert bad.empty == 1


def test_prepare_correction_repairs_cleans_and_validates() -> None:
    row = TranslationRow(1, "f", "k", "We could make⟦1⟧the goal.", "", "untranslated", "", ("Satır sonu",), None)
    # Kullanıcının elle yazdığı bozuk kod ve fazla etiket, içe aktarmadaki gibi onarılır/temizlenir.
    assert prepare_correction(row, "<b>Kale</b>[1]yapabiliriz.") == ("Kale⟦1⟧yapabiliriz.", [])
    text, issues = prepare_correction(row, "Kale yapabiliriz.")
    assert text == "Kale yapabiliriz."
    assert "Eksik kontrol kodu" in issues[0]
    assert prepare_correction(row, "   ") == ("", ["Çeviri boş."])


def test_csv_quotes_and_line_breaks_survive() -> None:
    row = TranslationRow(1, "f", "k", 'Say "hi"\nnow', 'De ki "selam"\nşimdi', "machine", "", (), None)
    assert parse_csv(rows_csv([row])) == [CsvRow(1, row.source, row.translation)]


def test_revision_prompt_lists_rules_and_instruction() -> None:
    prompt = revision_prompt("Şerif değil, Polis yaz.")
    assert "⟦1⟧" in prompt
    assert "Yalnızca “ceviri” sütununu" in prompt
    assert prompt.endswith("Şerif değil, Polis yaz.")
    assert "Ek talimat" not in revision_prompt()


# --- TXT (orijinal, çeviri, düzeltme, grup) ---------------------------------------------------------


def test_txt_export_round_trips_through_parser(tmp_path: Path) -> None:
    p = _project()
    rows = p.translation_rows()
    paths = export_txt(rows, tmp_path / "oyun.txt")
    assert paths == [tmp_path / "oyun.txt"]
    raw = paths[0].read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM: Notepad/Excel Türkçe karakterleri doğru açar
    text = paths[0].read_text(encoding="utf-8-sig")
    assert text.splitlines()[0].split("\t") == list(TXT_COLUMNS)
    parsed = parse_txt(text)
    assert parsed == [CsvRow(None, r.source, r.translation, "", row_group(r)) for r in rows]
    plan = plan_import(rows, parsed)
    assert plan.changes == []  # boş düzeltme: hiçbir şey yazılmaz
    assert plan.no_correction == len(rows)


def test_txt_export_splits_and_groups(tmp_path: Path) -> None:
    rows = _project().translation_rows()
    paths = export_txt(rows, tmp_path / "oyun.txt", part_rows=2)
    assert [x.name for x in paths] == ["oyun_001.txt", "oyun_002.txt"]
    assert [len(parse_txt(x.read_text(encoding="utf-8-sig"))) for x in paths] == [2, 1]

    def row(i: int, file: str) -> TranslationRow:
        return TranslationRow(i, file, f"k{i}", "Hi", "Selam", "machine", "", (), None)

    grouped = export_txt(
        [row(1, "a.assets>Dialogue"), row(2, "a.assets>UI"), row(3, "a.assets>Dialogue")],
        tmp_path / "oyun.txt",
        by_group=True,
    )
    assert [x.name for x in grouped] == ["oyun_Dialogue.txt", "oyun_UI.txt"]


def test_txt_correction_replaces_translation() -> None:
    p = _project()
    rows = _rows(p)
    text = (
        "orijinal\tçeviri\tdüzeltme\n"
        'Hello, "friend"!\tMerhaba, "dostum"!\tMerhaba, arkadaşım!\n'
        "We could make⟦1⟧the goal.\tKale yaparız.⟦1⟧\t\n"  # boş düzeltme: korunur
        "Not me.\tBen değilim.\tBen olmam.\n"
    )
    plan = plan_import(p.translation_rows(), parse_txt(text))
    assert dict(plan.changes) == {
        rows["a"].id: "Merhaba, arkadaşım!",
        rows["c"].id: "Ben olmam.",
    }
    assert (plan.no_correction, plan.unmatched, plan.unknown) == (1, 0, 0)
    # Boş düzeltmeli satır gerçekten yazılmaz.
    assert rows["b"].id not in dict(plan.changes)


def test_txt_matches_duplicate_pairs_in_order() -> None:
    def same(i: int) -> TranslationRow:
        return TranslationRow(i, "f", f"k{i}", "Yes", "Evet", "machine", "", (), None)

    rows = [same(1), same(2), same(3)]
    parsed = parse_txt("orijinal\tçeviri\tdüzeltme\nYes\tEvet\tEvet, lütfen.\nYes\tEvet\t\nYes\tEvet\tTamam.\n")
    plan = plan_import(rows, parsed)
    assert dict(plan.changes) == {1: "Evet, lütfen.", 3: "Tamam."}
    assert plan.no_correction == 1


def test_txt_matching_falls_back_to_unique_source_and_reports_ambiguous() -> None:
    rows = [
        TranslationRow(1, "f", "k1", "Open", "Aç", "machine", "", (), None),
        TranslationRow(2, "f", "k2", "Open", "Açık", "machine", "", (), None),
        TranslationRow(3, "f", "k3", "Close", "Kapat", "machine", "", (), None),
    ]
    # 1. ve 2. satırda orijinal aynı, çeviri farklı; çeviri değiştirilmişse orijinal tek başına belirsizdir.
    plan = plan_import(rows, parse_txt("Open\tDeğişmiş\tAç\n"))
    assert plan.changes == []
    assert plan.unmatched == 1
    # 3. satırın orijinali benzersiz: çeviri sütunu değişse de eşleşir.
    plan = plan_import(rows, parse_txt("Close\tDeğişmiş\tKapatma\n"))
    assert dict(plan.changes) == {3: "Kapatma"}


def test_txt_source_mismatch_and_code_problems_are_skipped() -> None:
    p = _project()
    rows = _rows(p)
    mismatch = plan_import(
        p.translation_rows(),
        parse_txt("orijinal\tçeviri\tdüzeltme\nSomething else\tKale yaparız.⟦1⟧\tKale yaparız.⟦1⟧\n"),
    )
    assert mismatch.changes == []
    assert mismatch.source_mismatch == [rows["b"].id]

    broken_codes = plan_import(
        p.translation_rows(),
        parse_txt(
            "orijinal\tçeviri\tdüzeltme\n"
            "We could make⟦1⟧the goal.\tKale yaparız.⟦1⟧\tKale yaparız.\n"  # kontrol kodu yok
        ),
    )
    assert broken_codes.changes == []
    assert [eid for eid, _ in broken_codes.code_problems] == [rows["b"].id]


def test_txt_escapes_tabs_newlines_and_backslashes(tmp_path: Path) -> None:
    row = TranslationRow(1, "f", "k", 'Say\t"hi"\nnow\\', 'De ki\t"selam"\nşimdi\\', "machine", "", (), None)
    text = rows_txt([row])
    body = text.split("\r\n")[1]
    assert body.count("\t") == 3  # yalnızca sütun ayraçları; metin içindeki sekme kaçışlandı
    assert "\\t" in body
    assert "\\n" in body
    assert parse_txt(text) == [CsvRow(None, row.source, row.translation, "", row_group(row))]
    path = export_txt([row], tmp_path / "kacis.txt")[0]
    assert parse_txt(path.read_text(encoding="utf-8-sig")) == [
        CsvRow(None, row.source, row.translation, "", row_group(row))
    ]


def test_txt_exports_group_as_read_only_context(tmp_path: Path) -> None:
    rows = [
        TranslationRow(1, "a.assets>UI", "k1", "Resume", "Devam", "machine", "", (), None),
        TranslationRow(2, "a.assets>Dialogue", "k2", "Resume", "Devam et", "machine", "", (), None),
    ]
    text = rows_txt(rows)
    assert text.splitlines()[0].split("\t") == list(TXT_COLUMNS)
    parsed = parse_txt(text)
    assert [(r.text, r.correction, r.group) for r in parsed] == [
        ("Devam", "", "UI"),
        ("Devam et", "", "Dialogue"),
    ]
    plan = plan_import(rows, parsed)
    assert (plan.no_correction, plan.changes) == (2, [])  # grup asla çeviriye yazılmaz


def test_txt_group_disambiguates_identical_pairs() -> None:
    rows = [
        TranslationRow(1, "a.assets>UI", "k1", "Yes", "Evet", "machine", "", (), None),
        TranslationRow(2, "a.assets>Dialogue", "k2", "Yes", "Evet", "machine", "", (), None),
    ]
    parsed = parse_txt("orijinal\tçeviri\tdüzeltme\tgrup\nYes\tEvet\t\tDialogue\nYes\tEvet\tTamam.\tUI\n")
    plan = plan_import(rows, parsed)
    # Grup olmasaydı dosya sırası gereği ikinci satır değişirdi; bağlam doğru satırı seçer.
    assert dict(plan.changes) == {1: "Tamam."}
    assert plan.no_correction == 1


def test_txt_old_three_column_files_still_parse_extra_tabs_as_correction() -> None:
    # Eski başlık üç sütunlu; fazladan sekme grup değil, düzeltmenin içidir.
    assert parse_txt("orijinal\tçeviri\tdüzeltme\nHello\tSelam\tMerhaba\tdostum\n") == [
        CsvRow(None, "Hello", "Selam", "Merhaba\tdostum", "")
    ]
    # Başlıksız eski dosyalar da aynı varsayılan düzenle okunur.
    assert parse_txt("Hello\tSelam\tMerhaba\n") == [CsvRow(None, "Hello", "Selam", "Merhaba", "")]


def test_txt_group_column_tolerates_renames_and_dropouts() -> None:
    assert parse_txt("orijinal\tçeviri\tdüzeltme\tGrup Adı\nHello\tSelam\tMerhaba\tUI\n")[0].group == "UI"
    assert parse_txt("orijinal\tçeviri\tdüzeltme\tnotes\nHello\tSelam\t\tUI\n")[0].group == "UI"
    # Model grup sütununu tümden silse de düzeltme doğru sütundan okunur.
    assert parse_txt("orijinal\tçeviri\tdüzeltme\tgrup\nHello\tSelam\tMerhaba\n") == [
        CsvRow(None, "Hello", "Selam", "Merhaba", "")
    ]


def test_txt_honours_header_column_order_and_group_position() -> None:
    parsed = parse_txt("Grup\tOrijinal\tÇeviri\tDüzeltme\nUI\tHello\tSelam\tMerhaba\n")
    assert parsed == [CsvRow(None, "Hello", "Selam", "Merhaba", "UI")]
    # Grup sonda değilken fazladan sekme yine düzeltmeye eklenir, sütunlar kaymaz.
    parsed = parse_txt("Grup\tOrijinal\tÇeviri\tDüzeltme\nUI\tHello\tSelam\tMerhaba\tdostum\n")
    assert parsed == [CsvRow(None, "Hello", "Selam", "Merhaba\tdostum", "UI")]


def test_txt_parser_tolerates_chat_model_output() -> None:
    text = (
        "İşte redakte edilmiş dosya:\n"
        "```txt\n"
        "Orijinal\tÇeviri\tDüzeltme\n"
        "Hello\tSelam\tMerhaba\n"
        "\n"
        "Bye\tHoşça kal\t\n"
        "```\n"
    )
    assert parse_txt(text) == [CsvRow(None, "Hello", "Selam", "Merhaba"), CsvRow(None, "Bye", "Hoşça kal", "")]
    with pytest.raises(CsvError, match="bulunamadı"):
        parse_txt("yalnızca açıklama\n")


@pytest.mark.parametrize("suffix", [".txt", ".csv"])
def test_read_revision_file_detects_format(tmp_path: Path, suffix: str) -> None:
    p = _project()
    rows = p.translation_rows()
    if suffix == ".txt":
        path = export_txt(rows, tmp_path / "r.txt")[0]
        assert parse_txt(path.read_text(encoding="utf-8-sig")) == read_revision_file(path)
    else:
        path = export_csv(rows, tmp_path / "r.csv")[0]
        assert read_csv(path) == read_revision_file(path)
    # Eski CSV biçimi .txt uzantısıyla da okunur.
    legacy = tmp_path / "eski.txt"
    legacy.write_text(rows_csv(rows), encoding="utf-8-sig")
    assert read_revision_file(legacy) == read_csv(legacy)
    # TXT içeriği yanlışlıkla .csv adıyla kaydedilse de okunur.
    wrong_name = tmp_path / "yanlis.csv"
    wrong_name.write_text(rows_txt(rows), encoding="utf-8-sig")
    assert read_revision_file(wrong_name) == parse_txt(wrong_name.read_text(encoding="utf-8-sig"))


def test_revision_prompt_txt_lists_rules_and_instruction() -> None:
    prompt = revision_prompt_txt("Şerif değil, Polis yaz.")
    assert "⟦1⟧" in prompt
    assert "Yalnızca “düzeltme” sütununu" in prompt
    assert "boş bırak" in prompt
    assert "grup" in prompt
    assert "UI" in prompt  # grup bağlamı menü/cümle ayrımı için açıklanır
    assert prompt.endswith("Şerif değil, Polis yaz.")
    assert "Ek talimat" not in revision_prompt_txt()


# --- XLSX (Excel) ----------------------------------------------------------------------------------


def test_xlsx_export_round_trips_through_parser(tmp_path: Path) -> None:
    p = _project()
    rows = p.translation_rows()
    paths = export_xlsx(rows, tmp_path / "oyun.xlsx")
    assert paths == [tmp_path / "oyun.xlsx"]
    raw = paths[0].read_bytes()
    assert raw.startswith(b"PK\x03\x04")  # Office Open XML paketi (ZIP)
    with zipfile.ZipFile(paths[0]) as z:
        assert "xl/worksheets/sheet1.xml" in z.namelist()
    assert parse_xlsx(raw) == [CsvRow(None, r.source, r.translation, "", row_group(r)) for r in rows]
    plan = plan_import(rows, parse_xlsx(raw))
    assert plan.changes == []  # boş düzeltme: hiçbir şey yazılmaz
    assert plan.no_correction == len(rows)


def test_xlsx_export_splits_and_groups(tmp_path: Path) -> None:
    rows = _project().translation_rows()
    paths = export_xlsx(rows, tmp_path / "oyun.xlsx", part_rows=2)
    assert [x.name for x in paths] == ["oyun_001.xlsx", "oyun_002.xlsx"]
    assert [len(parse_xlsx(x.read_bytes())) for x in paths] == [2, 1]

    def row(i: int, file: str) -> TranslationRow:
        return TranslationRow(i, file, f"k{i}", "Hi", "Selam", "machine", "", (), None)

    grouped = export_xlsx(
        [row(1, "a.assets>Dialogue"), row(2, "a.assets>UI"), row(3, "a.assets>Dialogue")],
        tmp_path / "oyun.xlsx",
        by_group=True,
    )
    assert [x.name for x in grouped] == ["oyun_Dialogue.xlsx", "oyun_UI.xlsx"]


def test_xlsx_correction_replaces_translation() -> None:
    p = _project()
    rows = _rows(p)
    data = table_xlsx(
        TXT_COLUMNS,
        [
            ('Hello, "friend"!', 'Merhaba, "dostum"!', "Merhaba, arkadaşım!"),
            ("We could make⟦1⟧the goal.", "Kale yaparız.⟦1⟧", ""),  # boş düzeltme: korunur
            ("Not me.", "Ben değilim.", "Ben olmam."),
        ],
    )
    plan = plan_import(p.translation_rows(), parse_xlsx(data))
    assert dict(plan.changes) == {
        rows["a"].id: "Merhaba, arkadaşım!",
        rows["c"].id: "Ben olmam.",
    }
    assert plan.no_correction == 1


def test_xlsx_keeps_newlines_and_quotes() -> None:
    row = TranslationRow(1, "f", "k", 'Say "hi"\nnow', 'De ki "selam"\nşimdi', "machine", "", (), None)
    assert parse_xlsx(rows_xlsx([row])) == [CsvRow(None, row.source, row.translation, "", row_group(row))]


def test_xlsx_group_column_is_read_only_context() -> None:
    data = table_xlsx(TXT_COLUMNS, [("Resume", "Devam", "", "UI"), ("Resume", "Devam et", "Devam et.", "Dialogue")])
    assert parse_xlsx(data) == [
        CsvRow(None, "Resume", "Devam", "", "UI"),
        CsvRow(None, "Resume", "Devam et", "Devam et.", "Dialogue"),
    ]


def test_read_revision_file_detects_xlsx(tmp_path: Path) -> None:
    p = _project()
    path = export_xlsx(p.translation_rows(), tmp_path / "r.xlsx")[0]
    assert read_revision_file(path) == parse_xlsx(path.read_bytes())
    # XLSX içeriği yanlışlıkla .txt adıyla kaydedilse de paket imzasından tanınır.
    misnamed = tmp_path / "yanlis.txt"
    misnamed.write_bytes(path.read_bytes())
    assert read_revision_file(misnamed) == parse_xlsx(misnamed.read_bytes())


def test_read_xlsx_rejects_broken_package(tmp_path: Path) -> None:
    path = tmp_path / "bozuk.xlsx"
    path.write_bytes(b"PK\x03\x04bozuk")
    with pytest.raises(CsvError, match="XLSX"):
        read_revision_file(path)


def test_revision_prompt_xlsx_lists_rules_and_instruction() -> None:
    prompt = revision_prompt_xlsx("Şerif değil, Polis yaz.")
    assert "⟦1⟧" in prompt
    assert "Yalnızca “düzeltme” sütununu" in prompt
    assert "XLSX" in prompt
    assert "grup" in prompt
    assert "UI" in prompt
    assert prompt.endswith("Şerif değil, Polis yaz.")
    assert "Ek talimat" not in revision_prompt_xlsx()


def test_redacted_status_overwrites_approved_only_when_allowed() -> None:
    p = _project()
    rows = _rows(p)
    updated = p.set_translations([(rows["c"].id, "Ben olmam.")], status=Status.REDACTED, overwrite_approved=True)
    assert [(r.id, r.status) for r in updated] == [(rows["c"].id, Status.REDACTED)]
    assert _rows(p)["c"].status == Status.REDACTED
    # Dış redaksiyon insan denetiminden geçmiş sayılır: bellekte makine çevirisinin önüne geçer.
    assert p.memory_lookup([rows["c"].source]) == {rows["c"].source: ("Ben olmam.", "human")}

    p.set_translations([(rows["c"].id, "Onaylı metin")])
    p.set_translations([(rows["c"].id, "İzinsiz redaksiyon")], status=Status.REDACTED)
    assert _rows(p)["c"].translation == "Onaylı metin"  # onaylı satıra izinsiz yazılmaz


def test_translation_txt_export_round_trips_and_keeps_current_column(tmp_path: Path) -> None:
    p = _project()
    rows = p.translation_rows()
    paths = export_translation_txt(rows, tmp_path / "oyun_ceviri.txt")
    assert paths == [tmp_path / "oyun_ceviri.txt"]
    assert paths[0].read_bytes().startswith(b"\xef\xbb\xbf")
    text = paths[0].read_text(encoding="utf-8-sig")
    assert text.splitlines()[0].split("\t") == list(TRANSLATION_COLUMNS)
    # Düzen redaksiyonla aynıdır: orijinal ve mevcut çeviri korunur, “yeni çeviri” boş gelir.
    assert parse_txt(text) == [CsvRow(None, r.source, r.translation, "", row_group(r)) for r in rows]
    plan = plan_import(rows, parse_txt(text))
    assert plan.changes == []
    assert plan.no_correction == len(rows)


def test_translation_xlsx_export_round_trips_and_keeps_current_column(tmp_path: Path) -> None:
    rows = _project().translation_rows()
    paths = export_translation_xlsx(rows, tmp_path / "oyun_ceviri.xlsx")
    assert paths == [tmp_path / "oyun_ceviri.xlsx"]
    data = paths[0].read_bytes()
    assert data.startswith(b"PK\x03\x04")
    assert parse_xlsx(data) == [CsvRow(None, r.source, r.translation, "", row_group(r)) for r in rows]
    plan = plan_import(rows, parse_xlsx(data))
    assert plan.changes == []
    assert plan.no_correction == len(rows)


def test_translation_new_column_replaces_and_blank_keeps_current() -> None:
    p = _project()
    rows = _rows(p)
    text = (
        "orijinal\tçeviri\tyeni çeviri\tgrup\n"
        'Hello, "friend"!\tMerhaba, "dostum"!\tMerhaba, arkadaşım!\tDialogue\n'
        "We could make⟦1⟧the goal.\tKale yaparız.⟦1⟧\t\tDialogue\n"  # boş: mevcut korunur
        "Not me.\tBen değilim.\tBen olmam.\tDialogue\n"
    )
    plan = plan_import(p.translation_rows(), parse_txt(text))
    assert dict(plan.changes) == {
        rows["a"].id: "Merhaba, arkadaşım!",
        rows["c"].id: "Ben olmam.",
    }
    assert (plan.no_correction, plan.unmatched, plan.unknown) == (1, 0, 0)


def test_translation_header_is_recognized_when_columns_are_reordered() -> None:
    parsed = parse_txt("Grup\tYeni Çeviri\tOrijinal\tÇeviri\nUI\tMerhaba\tHello\tSelam\n")
    assert parsed == [CsvRow(None, "Hello", "Selam", "Merhaba", "UI")]


def test_translation_new_column_without_current_column() -> None:
    p = _project()
    rows = _rows(p)
    parsed = parse_txt("orijinal\tyeni çeviri\tgrup\nNot me.\tBen olmam.\tDialogue\n")
    # Mevcut çeviri sütunu silinmişse “yeni çeviri” hem eşleşme metni hem düzeltmedir; grup ayrı kalır.
    assert parsed == [CsvRow(None, "Not me.", "Ben olmam.", "Ben olmam.", "Dialogue")]
    plan = plan_import(p.translation_rows(), parsed)
    assert dict(plan.changes) == {rows["c"].id: "Ben olmam."}


def test_translation_prompts_list_rules_and_instruction() -> None:
    for prompt in (translation_prompt_txt, translation_prompt_xlsx):
        text = prompt("Şerif değil, Polis yaz.")
        assert "⟦1⟧" in text
        assert "Yalnızca “yeni çeviri” sütununu" in text
        assert "boş bırak" in text
        assert "grup" in text
        assert text.endswith("Şerif değil, Polis yaz.")
        assert "Ek talimat" not in prompt()


def test_translation_rows_helpers_keep_group_and_escapes() -> None:
    row = TranslationRow(1, "f", "k", 'Say "hi"\nnow', 'De ki "selam"\nşimdi', "machine", "", (), None, "UI")
    assert rows_translation_txt([row]).startswith("orijinal\tçeviri\tyeni çeviri\tgrup")
    expected = [CsvRow(None, row.source, row.translation, "", row_group(row))]
    assert parse_txt(rows_translation_txt([row])) == expected
    assert parse_xlsx(rows_translation_xlsx([row])) == expected


# --- geri alma yığını -----------------------------------------------------------------------------


def test_undo_restores_text_and_status_step_by_step() -> None:
    p = _project()
    rows = _rows(p)
    p.set_translations([(rows["a"].id, "Selam!")])  # elle → onaylı
    p.set_translations([(rows["b"].id, "")])  # temizleme
    assert p.undo_job() == JOB_MANUAL
    job, undone = p.undo() or ("", [])
    assert (job, [r.key for r in undone]) == (JOB_MANUAL, ["b"])
    assert _rows(p)["b"].translation == "Kale yaparız.⟦1⟧"
    p.undo()
    after = _rows(p)["a"]
    assert (after.translation, after.status) == ('Merhaba, "dostum"!', Status.MACHINE)
    # Geri alma geçmişe yazılır; "Son İşin Değişiklikleri" geri alınanı artık göstermez.
    assert p.row_history(rows["a"].id)[0].job == JOB_REVERT


def test_undo_approval_and_unapprove() -> None:
    p = _project()
    rows = _rows(p)
    p.set_translations([(rows["a"].id, rows["a"].translation)])  # onaylama: metin aynı, durum değişir
    assert _rows(p)["a"].status == Status.APPROVED
    p.undo()
    assert _rows(p)["a"].status == Status.MACHINE
    p.unapprove([rows["c"].id])
    assert p.undo_job() == JOB_UNAPPROVE
    p.undo()
    assert _rows(p)["c"].status == Status.APPROVED


def test_machine_job_parts_undo_together_and_revert_is_undoable() -> None:
    p = _project()
    rows = _rows(p)
    p.set_translations([(rows["a"].id, "Bir")], machine=True, job="revise-1")
    p.set_translations([(rows["a"].id, "İki"), (rows["b"].id, "Üç⟦1⟧")], machine=True, job="revise-1")
    p.undo()
    assert _rows(p)["a"].translation == 'Merhaba, "dostum"!'  # işten önceki ilk hâl
    assert _rows(p)["b"].translation == "Kale yaparız.⟦1⟧"
    assert p.undo_job() == JOB_MANUAL  # sıradaki: _project()'teki onaylama

    p.set_translations([(rows["a"].id, "Dört")], machine=True, job="revise-2")
    p.revert(p.job_changes("revise-2"))
    assert _rows(p)["a"].translation == 'Merhaba, "dostum"!'
    p.undo()  # geri almayı geri al
    assert _rows(p)["a"].translation == "Dört"


def test_undo_stack_is_bounded_and_cleared_by_rescan() -> None:
    p = _project()
    a = _rows(p)["a"].id
    for i in range(UNDO_LIMIT + 5):
        p.set_translations([(a, f"Sürüm {i}")])
    steps = 0
    while p.undo() is not None:
        steps += 1
    assert steps == UNDO_LIMIT
    p.set_translations([(a, "Son")])
    p.import_texts([ImportedFile("Dialogue.tsv", "0100", "unity", "base", (TextEntry("a", 0, "Hi", ()),))])
    assert p.undo() is None
