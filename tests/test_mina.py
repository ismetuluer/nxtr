"""Mina the Hollower (Yacht Club YCD): okuma eklentisi ve topluluk yamasını içe aktarma."""

from __future__ import annotations

from pathlib import Path

import pytest

from nxceviri.core.errors import NxError
from nxceviri.core.formats import detection
from nxceviri.core.formats.base import FormatError
from nxceviri.core.formats.mina import MinaPlugin, ycd
from nxceviri.core.formats.registry import plugin_for_kind
from nxceviri.core.progress import CancelToken, TaskContext
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.translate.port import (
    PortError,
    is_mina_patch,
    port_translations,
    read_mina_translations,
    read_ready_translations,
)
from nxceviri.core.translate.status import Status
from tests.ycdbuild import DIALOGUE_HEADER, NAMES_HEADER, UI_HEADER, table
from tests.ycdbuild import ycd as build

UI_ROWS = [
    ["yes", "Yes", "Oui", "Sì", "Ja", "Sí"],
    ["confirm", "Are you sure?", "Sûr ?", "Sicuro?", "Sicher?", "¿Seguro?"],
    ["blank", "", "", "", "", ""],  # çevrilecek metin yok
    ["palette", "palettes/menus/art.pal.yc", "", "", "", ""],  # başka dosyaya yol
    ["shared", "Same", "Same", "Same", "Same", "Same"],  # ortak havuzdan gösterilen dizgi
    ["dup", "First", "", "", "", ""],
    ["dup", "Second", "", "", "", ""],
    [
        "codes",
        "<f cn=mina>Mina</f> says {0} <w>hi</w>",
        "Texte français assez long pour laisser de la place",
        "b",
        "c",
        "d",
    ],
]
DIALOGUE_ROWS = [
    ["1", "Lionel", "", "", "Welcome, Mina.", "Bienvenue, Mina, dans la tour.", "", "", ""],
    ["2", "", "", "", "A very long line " + "x" * 300, "", "", "", ""],
]
NAME_ROWS = [["ID5", "<f cn=lion>Robed Figure</f>", "", "<f cn=lion>Robed Figure</f>", "", "", "", ""]]


def _game() -> bytes:
    return build(
        table(UI_HEADER, UI_ROWS),
        table(DIALOGUE_HEADER, DIALOGUE_ROWS),
    )


def test_read_tables() -> None:
    tables = ycd.read_tables(_game())
    assert [t.kind for t in tables] == ["ui", "dialogue"]
    ui = tables[0]
    assert ui.header == tuple(UI_HEADER)
    assert len(ui.rows) == len(UI_ROWS)
    assert ui.rows[0].cells == tuple(UI_ROWS[0])
    assert ui.rows[4].cells == ("shared", "Same", "Same", "Same", "Same", "Same")
    assert tables[1].rows[1].cells[4].endswith("x" * 300)  # 255 baytı aşan uzunluk


def test_names_table_kind() -> None:
    (names,) = ycd.read_tables(build(table(NAMES_HEADER, [["ID5", "Robed", "", "Robed", "", "", "", ""]])))
    assert names.kind == "names"


def test_read_tables_rejects_other_files_and_ignores_files_without_tables() -> None:
    with pytest.raises(FormatError):
        ycd.read_tables(b"PK\x03\x04" + b"\0" * 64)
    assert ycd.read_tables(build(b"\0" * 128)) == []


def test_extract_keys_codes_and_filters() -> None:
    plugin = MinaPlugin()
    entries = {e.key: e for e in plugin.extract(_game())}
    assert set(entries) == {
        "ui/yes",
        "ui/confirm",
        "ui/shared",
        "ui/dup",
        "ui/dup#2",
        "ui/codes",
        "dialogue/1",
        "dialogue/2",
    }
    assert entries["ui/yes"].source == "Yes"
    assert entries["ui/dup#2"].source == "Second"
    assert entries["ui/codes"].source == "⟦1⟧Mina⟦2⟧ says ⟦3⟧ ⟦4⟧hi⟦5⟧"
    assert [c.raw for c in entries["ui/codes"].codes] == [b"<f cn=mina>", b"</f>", b"{0}", b"<w>", b"</w>"]
    assert entries["dialogue/1"].context == "Lionel"
    assert entries["dialogue/1"].source == "Welcome, Mina."


def test_extract_uses_first_table_of_each_kind() -> None:
    patched = build(table(UI_HEADER, [["yes", "Yes"] + [""] * 4]), table(UI_HEADER, [["yes", "Evet"] + [""] * 4]))
    (entry,) = MinaPlugin().extract(patched)
    assert entry.source == "Yes"


def test_inject_without_translations_returns_same_bytes() -> None:
    data = _game()
    assert MinaPlugin().inject(data, {}) is data


def test_inject_rewrites_all_language_columns_in_place() -> None:
    plugin = MinaPlugin()
    data = _game()
    translations = {
        "ui/yes": "Evet",
        "ui/confirm": "Emin misiniz?",
        "ui/codes": "⟦1⟧Mina⟦2⟧ {0} diyor ⟦4⟧selam⟦5⟧",
        "dialogue/1": "Hoş geldin, Mina.",
    }
    translations["ui/codes"] = "⟦1⟧Mina⟦2⟧ ⟦3⟧ diyor ⟦4⟧selam⟦5⟧"
    out = plugin.inject(data, translations)
    assert len(out) == len(data)  # hiçbir şey taşınmaz
    got = {e.key: e.source for e in plugin.extract(out)}
    assert got["ui/yes"] == "Evet"
    assert got["ui/codes"] == translations["ui/codes"]
    assert got["dialogue/1"] == "Hoş geldin, Mina."
    assert got["ui/shared"] == "Same"  # çevirisi verilmeyen satır aynen kalır
    assert got["dialogue/2"] == "A very long line " + "x" * 300
    for tbl in ycd.read_tables(out):
        row = tbl.rows[0]
        languages = row.cells[tbl.column("English") :]
        assert len(set(languages)) == 1  # tüm dil sütunları aynı Türkçe metni gösterir
    assert plugin.inject(out, {}) == out


def test_inject_uses_spare_room_when_strings_are_shared() -> None:
    """A satırının tek dizgisi B ile paylaşılıyor: A'nın boşalttığı yer yok, B'nin artığına yazılır."""
    wide = "ö" * 40
    data = bytearray(
        build(table(UI_HEADER, [["a", "Yes", "Yes", "Yes", "Yes", "Yes"], ["b", "Maybe", wide, wide, wide, wide]]))
    )
    (tbl,) = ycd.read_tables(bytes(data))
    a_english, b_french = tbl.rows[0].offset + 16, tbl.rows[1].offset + 2 * 16
    import struct

    a_target = a_english + 8 + struct.unpack_from("<i", data, a_english + 12)[0]
    struct.pack_into("<i", data, b_french + 12, a_target - (b_french + 8))  # B'nin Fransızcası A'nın "Yes"i
    struct.pack_into("<I", data, b_french + 4, 3)
    plugin = MinaPlugin()
    long_text = "Belki evet belki hayır"
    out = plugin.inject(bytes(data), {"ui/a": long_text, "ui/b": "Belki"})
    got = {e.key: e.source for e in plugin.extract(out)}
    assert got == {"ui/a": long_text, "ui/b": "Belki"}
    assert len(out) == len(data)


def test_inject_errors() -> None:
    plugin = MinaPlugin()
    data = _game()
    with pytest.raises(FormatError):
        plugin.inject(data, {"ui/yok": "Evet"})
    with pytest.raises(FormatError):
        plugin.inject(data, {"ui/codes": "Kodsuz çeviri"})  # kontrol kodları eksik
    tight = build(table(UI_HEADER, [["a", "Yes", "Yes", "Yes", "Yes", "Yes"]]))
    with pytest.raises(FormatError):
        plugin.inject(tight, {"ui/a": "Bu metin tek dizginin yerine sığmaz"})


def test_detection_and_registry() -> None:
    head = b"YCD\0" + b"\0" * 60
    got = detection.detect("romfs/global.pak.yc", head)
    assert got.kind == detection.FileKind.MINA
    assert got.likelihood == detection.TextLikelihood.HIGH
    assert detection.detect("romfs/maps/area.yc", head).likelihood == detection.TextLikelihood.MEDIUM
    assert detection.detect("romfs/x.bin", head).kind != detection.FileKind.MINA
    plugin = plugin_for_kind("mina")
    assert plugin is not None
    assert plugin.detect("x.yc", head)
    assert not plugin.detect("x.yc", b"UnityFS\0")


def _project() -> Project:
    data = _game()
    entries = tuple(MinaPlugin().extract(data))
    project = Project.new()
    project.import_texts([ImportedFile("romfs/global.pak.yc", "0100DCD01F306000", "mina", "base", entries)])
    return project


def _patch(tmp_path: Path) -> Path:
    """Yama gibi: özgün tablolar yerinde, sonda Türkçe kopyaları (İngilizce sütununda Türkçe)."""
    folder = tmp_path / "tr yama"
    folder.mkdir()
    turkish_ui = [
        ["yes", "Evet"] + [""] * 4,
        ["confirm", "Emin misiniz?"] + [""] * 4,
        ["shared", "Aynı"] + [""] * 4,
        ["dup", "Birinci"] + [""] * 4,
        ["dup", "İkinci"] + [""] * 4,
        ["codes", "<f cn=mina>Mina</f> {0} diyor"] + [""] * 4,  # <w> kodları eksik
    ]
    original_ui = [[r[0], r[1]] + [""] * 4 for r in UI_ROWS]
    old_dialogue = [
        ["1", "Lionel", "", "", "Welcome, Mina.", "", "", "", ""],
        ["2", "", "", "", "An older line", "", "", "", ""],  # güncellemede metin değişmiş
    ]
    turkish_dialogue = [
        ["1", "Lionel", "", "", "Hoş geldin, Mina.", "", "", "", ""],
        ["2", "", "", "", "Eski satırın çevirisi", "", "", "", ""],
    ]
    (folder / "global.pak.yc").write_bytes(
        build(
            table(UI_HEADER, original_ui),
            table(DIALOGUE_HEADER, old_dialogue),
            table(UI_HEADER, turkish_ui),
            table(DIALOGUE_HEADER, turkish_dialogue),
        )
    )
    (folder / "Terimler.txt").write_text("not a package", encoding="utf-8")
    return folder


def test_read_mina_translations(tmp_path: Path) -> None:
    got = read_mina_translations(_patch(tmp_path))
    assert got.texts["ui/yes"] == "Evet"
    assert got.texts["ui/dup#2"] == "İkinci"
    assert got.texts["dialogue/1"] == "Hoş geldin, Mina."
    assert got.sources is not None
    assert got.sources["ui/yes"] == frozenset({"Yes"})
    assert got.sources["dialogue/2"] == frozenset({"An older line"})


def test_read_ready_translations_picks_mina(tmp_path: Path) -> None:
    folder = _patch(tmp_path)
    assert is_mina_patch(folder)
    assert read_ready_translations(folder).texts["ui/confirm"] == "Emin misiniz?"
    assert not is_mina_patch(tmp_path / "yok")


def test_port_writes_only_matching_sources(tmp_path: Path) -> None:
    project = _project()
    ready = read_mina_translations(_patch(tmp_path))
    preview = port_translations(project, ready, apply=False)
    assert preview.applied == 6  # yes, confirm, shared, dup, dup#2, dialogue/1 (codes: kod sorunu)
    assert not any(r.translation for r in project.translation_rows())
    report = port_translations(project, ready)
    rows = {r.key: r for r in project.translation_rows()}
    assert report.applied == 6
    assert report.source_changed == 1  # dialogue/2: güncellemede özgün metin değişmiş
    assert [k for k, _s, _why in report.code_problems] == ["ui/codes"]
    assert rows["ui/yes"].translation == "Evet"
    assert rows["ui/dup#2"].translation == "İkinci"
    assert rows["dialogue/1"].translation == "Hoş geldin, Mina."
    assert rows["dialogue/2"].translation == ""
    assert rows["ui/yes"].status == Status.MACHINE
    assert report.unmatched_rows == 0


def test_read_mina_translations_errors(tmp_path: Path) -> None:
    empty = tmp_path / "bos"
    empty.mkdir()
    with pytest.raises(PortError):
        read_mina_translations(empty)
    only_english = tmp_path / "ingilizce"
    only_english.mkdir()
    (only_english / "global.pak.yc").write_bytes(_game())  # Türkçe kopya yok
    with pytest.raises(PortError):
        read_mina_translations(only_english)
    with pytest.raises(NxError):
        read_mina_translations(tmp_path / "yok")


def test_read_mina_translations_can_be_cancelled(tmp_path: Path) -> None:
    token = CancelToken()
    token.cancel()
    with pytest.raises(NxError):
        read_mina_translations(_patch(tmp_path), TaskContext(token=token))


def test_port_falls_back_to_identical_source_text(tmp_path: Path) -> None:
    """Güncellemede kimliği değişen satır, özgün metni yamadakiyle birebir aynıysa çevirisini alır."""
    pad = [""] * 4
    game = build(table(UI_HEADER, [["moved", "Hello there", "Salut vraiment long", "x", "y", "z"]]))
    project = Project.new()
    entries = tuple(MinaPlugin().extract(game))
    project.import_texts([ImportedFile("romfs/global.pak.yc", "0100DCD01F306000", "mina", "base", entries)])
    folder = tmp_path / "yama"
    folder.mkdir()
    (folder / "global.pak.yc").write_bytes(
        build(
            table(UI_HEADER, [["old", "Hello there", *pad], ["same", "Hello there", *pad]]),
            table(UI_HEADER, [["old", "Merhaba", *pad], ["same", "Merhaba", *pad]]),
        )
    )
    report = port_translations(project, read_mina_translations(folder))
    (row,) = project.translation_rows()
    assert (row.translation, report.matched_by_text, report.applied) == ("Merhaba", 1, 1)


def test_extra_json_translations_are_merged(tmp_path: Path) -> None:
    folder = _patch(tmp_path)
    (folder / "ek.json").write_text('{"dialogue/2": "Elle çevrildi", "ui/yeni": "Yeni"}', encoding="utf-8")
    got = read_mina_translations(folder)
    assert got.texts["dialogue/2"] == "Elle çevrildi"  # yamanınki özgün metni değişmiş olsa da elle yazılan geçer
    assert got.texts["ui/yeni"] == "Yeni"
    assert got.sources is not None
    assert "dialogue/2" not in got.sources
    (folder / "ek.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(PortError):
        read_mina_translations(folder)
    (folder / "ek.json").write_text("{bozuk", encoding="utf-8")
    with pytest.raises(PortError):
        read_mina_translations(folder)
