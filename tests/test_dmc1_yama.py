"""Devil May Cry HD Collection (PC) topluluk Türkçe yaması: okuma ve projeye aktarma."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from nxceviri.core.formats.base import SOURCE_PATH, FormatError
from nxceviri.core.formats.dmc1 import Dmc1Plugin, codec, yama
from nxceviri.core.project import ImportedFile, Project
from nxceviri.core.translate.port import (
    PortError,
    is_dmc1_patch,
    port_translations,
    read_dmc1_translations,
    read_ready_translations,
)
from tests.dmc1build import fsd as build_fsd
from tests.dmc1build import message, table


def _tr(sentence: str) -> bytes:
    """Yamadaki gibi çiftli Türkçe harflerle bir dizgi."""
    return codec.encode(codec.decode(message("x")), sentence, pad_to=4)


def _yama(files: dict[str, list[bytes]]) -> bytes:
    out = bytearray(b"D1FS" + struct.pack("<I", len(files)))
    for name, blocks in files.items():
        raw = name.encode("ascii")
        out += struct.pack("<H", len(raw)) + raw + struct.pack("<I", len(blocks))
        for offset, block in enumerate(blocks):
            out += struct.pack("<II", 0x1000 * (offset + 1), len(block)) + block
    return bytes(out)


TURKISH = ["Doğru mu söylüyorum?", "Şimdi git!", "Tuvalet mi? İşte orada."]
ENGLISH = ["Am I correct?", "Now go!", "Is it the toilet? Right there."]


def _tr_table() -> bytes:
    return table([_tr(s) for s in TURKISH])


def test_read_yama_finds_the_table_even_when_the_block_starts_earlier() -> None:
    shifted = bytes(0x20) + _tr_table()  # PC dosyasında tablo 0x20 bayt sonra başlıyor
    data = _yama({"Fsd/r002.fsd": [shifted], "Fsd/r100.fsd": [_tr_table(), b"\x01" * 40]})
    tables = yama.read_yama(data)
    assert [t.file for t in tables] == ["r002.fsd", "r100.fsd"]
    assert tables[0].texts == tuple(TURKISH)
    assert tables[1].texts == tuple(TURKISH)


def test_read_yama_skips_patches_without_tables_and_rejects_bad_files() -> None:
    assert yama.read_yama(_yama({"Fsd/r209.fsd": [b"\x09" * 64]})) == []
    with pytest.raises(FormatError):
        yama.read_yama(b"XXXX" + bytes(8))
    with pytest.raises(FormatError):
        yama.read_yama(b"D1FS" + struct.pack("<I", 5) + b"\x01")  # kesik dosya


def test_read_message_file() -> None:
    result = yama.read_message_file(_tr_table(), "common.msg")
    assert result.file == "common.msg"
    assert result.texts == tuple(TURKISH)
    with pytest.raises(FormatError):
        yama.read_message_file(b"\0" * 64, "x.msg")


def _project() -> Project:
    plugin = Dmc1Plugin()
    english = build_fsd(table([message(s) for s in ENGLISH]))
    entries = tuple(plugin.extract(english, {SOURCE_PATH: "data/dmc1/fsd/r002.fsd"}))
    msg = table([message(s) for s in ENGLISH])
    msg_entries = tuple(plugin.extract(msg, {SOURCE_PATH: "data/dmc1/etc_e/common.msg"}))
    project = Project.new()
    project.import_texts(
        [
            ImportedFile("data/dmc1/fsd/r002.fsd", "0100E8000D5B8000", "dmc1", "base", entries),
            ImportedFile("data/dmc1/etc_e/common.msg", "0100E8000D5B8000", "dmc1", "base", msg_entries),
        ]
    )
    return project


def _patch_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "DMC_HD_Turkce_Yama"
    (folder / "_yama" / "dmc1" / "ekler" / "Etc_e").mkdir(parents=True)
    (folder / "_yama" / "dmc1" / "fsd_tr.yama").write_bytes(_yama({"Fsd/r002.fsd": [bytes(0x20) + _tr_table()]}))
    (folder / "_yama" / "dmc1" / "ekler" / "Etc_e" / "common.msg").write_bytes(_tr_table())
    (folder / "OKU_BENI.txt").write_text("not a package", encoding="utf-8")
    return folder


def test_port_matches_rows_by_file_name_and_line_number(tmp_path: Path) -> None:
    folder = _patch_folder(tmp_path)
    assert is_dmc1_patch(folder)
    assert not is_dmc1_patch(tmp_path / "yok")
    project = _project()
    ready = read_ready_translations(folder)
    assert set(ready.texts) >= {"r002.fsd|0", "common.msg|2"}
    report = port_translations(project, ready)
    assert (report.matched, report.applied, len(report.code_problems), report.unmatched_rows) == (6, 6, 0, 0)
    by_file = {(r.file.rsplit("/", 1)[-1], r.source): r.translation for r in project.translation_rows()}
    assert by_file[("r002.fsd", "Am I correct?")] == "Doğru mu söylüyorum?"
    assert by_file[("common.msg", "Is it the toilet? Right there.")] == "Tuvalet mi? İşte orada."


def test_port_errors(tmp_path: Path) -> None:
    empty = tmp_path / "bos"
    empty.mkdir()
    assert not is_dmc1_patch(empty)
    (empty / "fsd_tr.yama").write_bytes(_yama({"Fsd/r209.fsd": [b"\x09" * 64]}))
    with pytest.raises(PortError):
        read_dmc1_translations(empty)


def test_read_status_file() -> None:
    import struct as _struct

    tbl = _tr_table()
    data = _struct.pack("<II", 1, 16) + bytes(8) + tbl
    assert yama.read_status_file(data, "st_init.dat").texts == tuple(TURKISH)
    with pytest.raises(FormatError):
        yama.read_status_file(b"\0" * 16, "st_init.dat")
