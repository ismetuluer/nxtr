"""Unicorn Overlord: CRI CPK arşivi, CRILAYLA, FMSB MsgSheet, tarama ve dışa aktarma (elle üretilmiş örneklerle)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nxceviri.core.archives import cpk
from nxceviri.core.archives.access import MemberReader, is_cpk_path, is_member_path
from nxceviri.core.container.romfs import RomFs
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.container.view import ContentTree, GameView, LayeredRomFs, RomFsLayer
from nxceviri.core.errors import ArchiveError, UnsupportedFormatError
from nxceviri.core.export.layeredfs import ExportError, ExportResult, TextFileRef, _export_member_archive
from nxceviri.core.formats.base import FormatError
from nxceviri.core.formats.detection import CPK_ARCHIVE_DETAIL, detect
from nxceviri.core.formats.fmsb import FmsbPlugin
from nxceviri.core.formats.scanner import scan_view
from nxceviri.core.pipeline import path_language
from tests.nxbuild import build_romfs
from tests.ysuobuild import build_cpk, build_fmsb, layla_compress

TID = "010069401ADB8000"
PLUGIN = FmsbPlugin()

SYS = [
    "##(START)",
    "",
    "Starting Position",
    "This unit is already full.\nAdd them anyway?",
    "Acquired #c(15)#(102)#/c x #c(15)%d#/c.",
    "I don't care #iwho#/i you are.",
    "^1/Alain^ seized the ^2/#FN(C5北の町)^.",
    "",
    "…",
]
JA = ["開始位置", "このユニットは満員です。", "なし", "アイテム"]
#: CRILAYLA'nın sıkıştırmadığı 0x100 baytlık baş kısmı aşan, tekrar içeren bir sayfa.
LONG = SYS + [f"Line {i}: the Liberation marches on, and on, and on." for i in range(20)]


def _tree(extra: dict[str, bytes] | None = None) -> ContentTree:
    files = {
        "Unicorn_US.CPK": build_cpk(
            {
                "Debug/_Enum.inc": b"enum {}",
                "MsgSheet/UcSysMsg.fms": build_fmsb(LONG),
                "MsgSheet/UcNameList.fms": build_fmsb(["Alain", "Scarlett"]),
            },
            compressed=frozenset({"MsgSheet/UcSysMsg.fms"}),
        ),
        "Unicorn.CPK": build_cpk({"MsgSheet/UcSysMsg.fms": build_fmsb(JA)}),
        **(extra or {}),
    }
    romfs = RomFs(MemoryStorage(build_romfs(files)))
    return ContentTree(TID, "Ana oyun", LayeredRomFs([RomFsLayer("base", romfs)]), lambda: None)


def test_layla_round_trip() -> None:
    data = bytes(range(256)) + b"abcabcabcabc" * 50 + b"tail-xyz"
    packed = layla_compress(data)
    assert len(packed) < len(data)
    assert cpk.decompress_layla(packed) == data


def test_layla_rejects_corrupt_data() -> None:
    with pytest.raises(ArchiveError):
        cpk.decompress_layla(b"CRILAYLA" + b"\xff" * 8)
    packed = bytearray(layla_compress(bytes(range(256)) + b"q" * 400))
    packed[16:20] = b"\xff\xff\xff\xff"  # geri başvuruları anlamsızlaştır
    with pytest.raises(ArchiveError):
        cpk.decompress_layla(bytes(packed))


@pytest.mark.parametrize("masked", [True, False])
def test_cpk_reads_members(masked: bool) -> None:
    sheet = build_fmsb(LONG)
    data = build_cpk(
        {"MsgSheet/A.fms": sheet, "X/b.bin": b"raw"}, compressed=frozenset({"MsgSheet/A.fms"}), masked=masked
    )
    arc = cpk.CpkFile(MemoryStorage(data), "Unicorn_US.CPK")
    assert set(arc.entries) == {"MsgSheet/A.fms", "X/b.bin"}
    assert arc.entries["MsgSheet/A.fms"].size < arc.entries["MsgSheet/A.fms"].extract_size
    assert arc.read("MsgSheet/A.fms") == sheet
    assert arc.read("X/b.bin") == b"raw"
    assert arc.header.masked is masked


def test_cpk_rebuild_without_changes_is_identical() -> None:
    data = build_cpk({"MsgSheet/A.fms": build_fmsb(LONG), "X/b.bin": b"raw"}, compressed=frozenset({"MsgSheet/A.fms"}))
    assert cpk.CpkFile(MemoryStorage(data), "t").rebuild({}) == data


def test_cpk_rebuild_stores_changed_member_uncompressed() -> None:
    data = build_cpk(
        {"MsgSheet/A.fms": build_fmsb(LONG), "X/b.bin": b"raw", "Z/c.bin": b"z" * 3000},
        compressed=frozenset({"MsgSheet/A.fms"}),
    )
    arc = cpk.CpkFile(MemoryStorage(data), "t")
    bigger = build_fmsb([*LONG, "Yeni ve oldukça uzun bir Türkçe satır " * 100])
    rebuilt = cpk.CpkFile(MemoryStorage(arc.rebuild({"MsgSheet/A.fms": bigger})), "t")
    entry = rebuilt.entries["MsgSheet/A.fms"]
    assert entry.size == entry.extract_size == len(bigger)
    assert rebuilt.read("MsgSheet/A.fms") == bigger
    assert rebuilt.read("Z/c.bin") == b"z" * 3000
    assert all(e.offset % 0x800 == 0 for e in rebuilt.entries.values())
    assert rebuilt.header.get(0, "EnabledDataSize") == sum(e.size for e in rebuilt.entries.values())
    etoc = rebuilt.header.get(0, "EtocOffset")
    assert isinstance(etoc, int)
    assert rebuilt.storage.read(etoc, 4) == b"ETOC"


def test_cpk_rejects_bad_header_and_unknown_member() -> None:
    data = build_cpk({"A/b.bin": b"x"})
    with pytest.raises(ArchiveError):
        cpk.CpkFile(MemoryStorage(b"CPK " + b"\0" * 60), "t")
    arc = cpk.CpkFile(MemoryStorage(data), "t")
    with pytest.raises(ArchiveError, match="yok"):
        arc.read("A/yok.bin")
    with pytest.raises(ArchiveError, match="olmayan"):
        arc.rebuild({"A/yok.bin": b""})


def test_cpk_refuses_to_rebuild_huge_archive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cpk, "MAX_REBUILD", 100)
    arc = cpk.CpkFile(MemoryStorage(build_cpk({"A/b.bin": b"x"})), "Unicorn.CPK")
    with pytest.raises(UnsupportedFormatError, match="çok büyük"):
        arc.rebuild({"A/b.bin": b"y"})


def test_fmsb_round_trip_and_tokens() -> None:
    data = build_fmsb(SYS)
    entries = {e.key: e for e in PLUGIN.extract(data)}
    assert set(entries) == {"2", "3", "4", "5", "6"}  # bölüm işareti, boş ve harfsiz satırlar alınmaz
    assert entries["3"].source == "This unit is already full.\nAdd them anyway?"
    assert entries["4"].source == "Acquired ⟦1⟧⟦2⟧⟦3⟧ x ⟦4⟧⟦5⟧⟦6⟧."
    assert entries["5"].source == "I don't care ⟦1⟧who⟦2⟧ you are."
    assert [c.raw for c in entries["6"].codes] == [
        b"^1/",
        b"^",
        b"^2/",
        b"#FN(C5\xe5\x8c\x97\xe3\x81\xae\xe7\x94\xba)",
        b"^",
    ]
    assert PLUGIN.inject(data, {k: e.source for k, e in entries.items()}) == data


def test_fmsb_inject_changes_size_and_keeps_slots() -> None:
    data = build_fmsb(SYS)
    out = PLUGIN.inject(
        data, {"2": "Başlangıç Noktası — çok daha uzun bir çeviri", "5": "Kim olduğun ⟦1⟧umurumda⟦2⟧ değil."}
    )
    got = {e.key: e.source for e in PLUGIN.extract(out)}
    assert got["2"] == "Başlangıç Noktası — çok daha uzun bir çeviri"
    assert got["5"] == "Kim olduğun ⟦1⟧umurumda⟦2⟧ değil."
    assert len(out) % 16 == 0
    assert out.endswith(data[-16:])
    assert out[0x20 : 0x20 + 8 * len(SYS)] == bytes(8 * len(SYS))


def test_fmsb_inject_rejects_bad_tokens_and_unknown_keys() -> None:
    data = build_fmsb(SYS)
    with pytest.raises(FormatError, match="yazılamadı"):
        PLUGIN.inject(data, {"5": "eğik yazı kodu yok"})
    with pytest.raises(FormatError, match="olmayan"):
        PLUGIN.inject(data, {"0": "x"})  # bölüm işareti
    with pytest.raises(FormatError, match="olmayan"):
        PLUGIN.inject(data, {"1": "x"})  # boş yuva


def test_fmsb_corrupt_files() -> None:
    data = build_fmsb(SYS)
    with pytest.raises(FormatError, match="FEOC"):
        PLUGIN.extract(data[:-16] + b"XXXX" + data[-12:])
    with pytest.raises(FormatError):
        PLUGIN.extract(data[:-20])


def test_fmsb_language_detection() -> None:
    assert PLUGIN.language(build_fmsb([*JA, "PlayStation", "Nintendo Switch"])) == "ja"
    assert PLUGIN.language(build_fmsb(SYS)) is None  # `#FN(…町)` kodları sayılmaz


def test_detection_and_paths() -> None:
    data = build_cpk({"A/b.bin": b"x"})
    assert detect("Unicorn_US.CPK", data[:64]).detail == CPK_ARCHIVE_DETAIL
    assert path_language("Unicorn_US.CPK>MsgSheet/UcSysMsg.fms") == "en"
    assert path_language("Unicorn_DE.CPK>MsgSheet/UcSysMsg.fms") == "de"
    assert path_language("Unicorn.CPK>MsgSheet/UcSysMsg.fms") is None
    assert is_cpk_path("Unicorn_US.CPK>MsgSheet/UcSysMsg.fms")
    assert is_member_path("Unicorn_US.CPK>MsgSheet/UcSysMsg.fms")


def test_scan_lists_message_sheets() -> None:
    report = scan_view(GameView(TID, "Unicorn Overlord", 0, None, [_tree()]))
    sheets = sorted(e.path for e in report.entries if e.kind == "fmsb")
    assert sheets == [
        "Unicorn.CPK>MsgSheet/UcSysMsg.fms",
        "Unicorn_US.CPK>MsgSheet/UcNameList.fms",
        "Unicorn_US.CPK>MsgSheet/UcSysMsg.fms",
    ]
    assert report.engine.engine == "vanillaware"
    reader = MemberReader(_tree().view)
    assert PLUGIN.language(reader.read("Unicorn.CPK>MsgSheet/UcSysMsg.fms")) == "ja"


def test_export_rebuilds_language_archive() -> None:
    tree = _tree()
    path = "Unicorn_US.CPK>MsgSheet/UcSysMsg.fms"
    translations = {path: {"2": "Başlangıç Noktası", "3": "Bu birlik zaten dolu.\nYine de eklensin mi?"}}
    result = ExportResult(Path("x"))
    outputs = _export_member_archive(
        tree,
        "Unicorn_US.CPK",
        [TextFileRef(path, TID, "fmsb")],
        translations=translations,
        root=Path("romfs"),
        result=result,
    )
    assert [rel.as_posix() for rel, _ in outputs] == ["romfs/Unicorn_US.CPK"]
    arc = cpk.CpkFile(MemoryStorage(outputs[0][1]), "Unicorn_US.CPK")
    got = {e.key: e.source for e in PLUGIN.extract(arc.read("MsgSheet/UcSysMsg.fms"))}
    assert got["2"] == "Başlangıç Noktası"
    assert arc.read("MsgSheet/UcNameList.fms") == build_fmsb(["Alain", "Scarlett"])
    assert arc.read("Debug/_Enum.inc") == b"enum {}"


def test_export_reports_unreadable_archive() -> None:
    tree = _tree({"Broken_US.CPK": b"CPK " + b"\0" * 100})
    path = "Broken_US.CPK>MsgSheet/A.fms"
    with pytest.raises(ExportError, match="okunamadı"):
        _export_member_archive(
            tree,
            "Broken_US.CPK",
            [TextFileRef(path, TID, "fmsb")],
            translations={path: {"0": "x"}},
            root=Path("r"),
            result=ExportResult(Path("x")),
        )
