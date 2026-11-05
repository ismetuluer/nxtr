"""Ys Origin: NNI arşivi, XSO betik metinleri, arayüz XML'i, tarama ve dışa aktarma (elle üretilmiş örneklerle)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nxceviri.core.archives import nni
from nxceviri.core.archives.access import MemberReader, is_member_path, is_nni_path
from nxceviri.core.container.romfs import RomFs
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.container.view import ContentTree, GameView, LayeredRomFs, RomFsLayer
from nxceviri.core.errors import ArchiveError
from nxceviri.core.export.layeredfs import ExportResult, TextFileRef, _export_member_archive, fold_unsupported_letters
from nxceviri.core.formats.base import SOURCE_PATH, FormatError
from nxceviri.core.formats.detection import NNI_ARCHIVE_DETAIL, FileKind, detect
from nxceviri.core.formats.scanner import scan_view
from nxceviri.core.formats.ysorigin import YsOriginPlugin
from nxceviri.core.formats.ysorigin.plugin import build_xso as rebuild_xso
from nxceviri.core.formats.ysorigin.plugin import parse_xso
from nxceviri.core.pipeline import path_language
from tests.nxbuild import build_romfs
from tests.ysuobuild import build_nni, build_xso, build_ys_xml

TID = "0100F90010882000"
PLUGIN = YsOriginPlugin()

EN_STRINGS = [
    "V_180",
    "Yes. With the tower's influence cut off, Solomon\\nShrine has begun reascending.",
    "OPEN",
    "<color:0xffff3232>Well, well...<color:> a piece of %s ore.",
    "Yes",
    "@Flag_Inv",
    "Cancel",
]
JA_STRINGS = [
    "V_180",
    "はい。塔の影響が消えて…",
    "OPEN",
    "<color:0xffff3232>ほう…<color:>%s",
    "はい",
    "@Flag_Inv",
    "取消",
]
EN_ONLY = ["S_0003", "Who goes there?", "Hugo", "...!"]


def _archives() -> dict[str, bytes]:
    en_ni, en_na = build_nni(
        {
            "LOC/EN/DATA/MAP/S_00/S_0003/EVT_0001.XSO": build_xso(EN_STRINGS),
            "LOC/EN/DATA/MAP/S_00/S_0003/EVT_0002.XSO": build_xso(EN_ONLY),
            "EXTENSION/STORY/X.DDS": b"DDS ",
        },
        compressed=frozenset({"LOC/EN/DATA/MAP/S_00/S_0003/EVT_0001.XSO"}),
    )
    ja_ni, ja_na = build_nni({"LOC/JP/DATA/MAP/S_00/S_0003/EVT_0001.XSO": build_xso(JA_STRINGS)})
    xml = build_ys_xml({"TXT__OK": "OK", "TXT_HELP": "Press &amp; hold\nto run %d", "TXT__EMPTY": "", "TXT__NUM": "1"})
    return {
        "ys_data/archives/data-en.ni": en_ni,
        "ys_data/archives/data-en.na": en_na,
        "ys_data/archives/data-ja.ni": ja_ni,
        "ys_data/archives/data-ja.na": ja_na,
        "ys_data/data/loc/strings/english.xml": xml,
    }


def _tree() -> ContentTree:
    romfs = RomFs(MemoryStorage(build_romfs(_archives())))
    return ContentTree(TID, "Ana oyun", LayeredRomFs([RomFsLayer("base", romfs)]), lambda: None)


def test_scramble_round_trip_and_name_hash() -> None:
    data = bytes(range(256)) * 2
    assert nni.descramble(nni.scramble(data)) == data
    assert nni.scramble(data) != data
    assert nni.name_hash(b"A") == 33


def test_nni_reads_plain_and_compressed_members() -> None:
    ni, na = build_nni({"A/B.XSO": b"plain", "A/C.XSO": b"zipped" * 10}, compressed=frozenset({"A/C.XSO"}))
    arc = nni.NniArchive("data-en.ni", ni, MemoryStorage(na))
    assert arc.read("A/B.XSO") == b"plain"
    assert arc.read("A/C.XSO") == b"zipped" * 10
    assert arc.entries["A/C.XSO"].compressed


def test_nni_rebuild_appends_changed_members_and_keeps_others() -> None:
    ni, na = build_nni({"A/B.XSO": b"plain", "A/C.XSO": b"zipped" * 10}, compressed=frozenset({"A/C.XSO"}))
    arc = nni.NniArchive("data-en.ni", ni, MemoryStorage(na))
    index, data = arc.rebuild({"A/C.XSO": b"yeni ve daha uzun icerik"})
    assert data.startswith(na)  # orijinal veri olduğu gibi kalır
    new = nni.NniArchive("data-en.ni", index, MemoryStorage(data))
    assert new.read("A/C.XSO") == b"yeni ve daha uzun icerik"
    assert new.read("A/B.XSO") == b"plain"
    assert index[16 + 2 * 16 :] == ni[16 + 2 * 16 :]  # ad tablosu değişmez


def test_nni_rejects_corrupt_index_and_unknown_member() -> None:
    ni, na = build_nni({"A/B.XSO": b"x"})
    with pytest.raises(ArchiveError, match="NNI"):
        nni.NniArchive("x.ni", b"XXXX" + ni[4:], MemoryStorage(na))
    with pytest.raises(ArchiveError, match="uyuşmuyor"):
        nni.NniArchive("x.ni", ni + b"\0", MemoryStorage(na))
    arc = nni.NniArchive("x.ni", ni, MemoryStorage(na))
    with pytest.raises(ArchiveError, match="yok"):
        arc.read("A/YOK.XSO")
    with pytest.raises(ArchiveError, match="olmayan"):
        arc.rebuild({"A/YOK.XSO": b""})


def test_nni_detects_bad_checksum() -> None:
    ni, na = build_nni({"A/C.XSO": b"zipped" * 10}, compressed=frozenset({"A/C.XSO"}))
    broken = na[:4] + b"\0\0\0\0" + na[8:]  # CRC bozuk
    with pytest.raises(ArchiveError, match="denetim"):
        nni.NniArchive("x.ni", ni, MemoryStorage(broken)).read("A/C.XSO")


def test_xso_round_trip_is_byte_identical() -> None:
    data = build_xso(EN_STRINGS)
    entries = PLUGIN.extract(data)
    assert PLUGIN.inject(data, {e.key: e.source for e in entries}) == data
    strings, _table = parse_xso(data)
    assert rebuild_xso(data, strings) == data


def test_xso_tokens_and_newlines() -> None:
    entries = {e.key: e for e in PLUGIN.extract(build_xso(EN_STRINGS))}
    assert entries["1"].source == "Yes. With the tower's influence cut off, Solomon\nShrine has begun reascending."
    assert entries["3"].source == "⟦1⟧Well, well...⟦2⟧ a piece of ⟦3⟧ ore."
    assert [c.raw for c in entries["3"].codes] == [b"<color:0xffff3232>", b"<color:>", b"%s"]


def test_xso_uses_japanese_copy_to_skip_script_identifiers() -> None:
    ja_path = "ys_data/archives/data-ja.ni>LOC/JP/DATA/MAP/X.XSO"
    context: dict[object, object] = dict(PLUGIN.collect_context(build_xso(JA_STRINGS), ja_path))
    context[SOURCE_PATH] = "ys_data/archives/data-en.ni>LOC/EN/DATA/MAP/X.XSO"
    keys = [e.key for e in PLUGIN.extract(build_xso(EN_STRINGS), context)]
    assert keys == ["1", "3", "4", "6"]  # V_180, OPEN, @Flag_Inv aynı kaldığı için betik kimliği; "Yes" metin


def test_xso_without_japanese_copy_uses_heuristic() -> None:
    context: dict[object, object] = {SOURCE_PATH: "data-en.ni>LOC/EN/DATA/MAP/Y.XSO"}
    keys = [e.key for e in PLUGIN.extract(build_xso(EN_ONLY), context)]
    assert keys == ["1"]  # tek sözcüklü "Hugo" belirsiz: alınmaz; "...!" harf içermez
    sources = [e.source for e in PLUGIN.extract(build_xso(["S_0003", "...!", "Run!"]), context)]
    assert sources == ["Run!"]


def test_xso_inject_grows_and_shrinks_strings() -> None:
    data = build_xso(EN_STRINGS)
    out = PLUGIN.inject(data, {"1": "Evet.\nKule düştü — çok uzun bir Türkçe cümle.", "6": "İptal"})
    got = {e.key: e.source for e in PLUGIN.extract(out)}
    assert got["1"] == "Evet.\nKule düştü — çok uzun bir Türkçe cümle."
    assert got["6"] == "İptal"
    assert parse_xso(out)[0][1] == "Evet.\\nKule düştü — çok uzun bir Türkçe cümle.".encode()
    assert parse_xso(out)[0][0] == b"V_180"  # kimlikler yerinde
    assert len(out) % 4 == 0


def test_xso_inject_rejects_bad_tokens_and_unknown_keys() -> None:
    data = build_xso(EN_STRINGS)
    with pytest.raises(FormatError, match="yazılamadı"):
        PLUGIN.inject(data, {"3": "renk kodu yok"})
    with pytest.raises(FormatError, match="olmayan"):
        PLUGIN.inject(data, {"99": "x"})
    with pytest.raises(FormatError, match="olmayan"):
        PLUGIN.inject(build_xso(["...!"]), {"0": "x"})  # harf içermeyen dizge metin değil


def test_xso_corrupt_or_stringless() -> None:
    with pytest.raises(FormatError):
        PLUGIN.extract(b"XSR\0" + b"\xff" * 40)
    assert PLUGIN.extract(build_xso([])) == []


def test_xml_round_trip_entities_and_newlines() -> None:
    data = build_ys_xml({"TXT__OK": "OK", "TXT_HELP": "Press &amp; hold\nto run %d", "TXT__EMPTY": ""})
    entries = {e.key: e for e in PLUGIN.extract(data)}
    assert set(entries) == {"TXT__OK", "TXT_HELP"}
    assert entries["TXT_HELP"].source == "Press & hold\nto run ⟦1⟧"
    assert PLUGIN.inject(data, {k: e.source for k, e in entries.items()}) == data
    out = PLUGIN.inject(data, {"TXT_HELP": "Koşmak için <basılı> tut & ⟦1⟧\nkez"})
    assert b"Ko\xc5\x9fmak i\xc3\xa7in &lt;bas\xc4\xb1l\xc4\xb1&gt; tut &amp; %d\nkez" in out
    assert b"\\n" not in out  # XML'de ters bölü + n oyunda "¥n" görünür; satır sonu gerçek satır sonu olmalı
    assert {e.key: e.source for e in PLUGIN.extract(out)}["TXT_HELP"] == "Koşmak için <basılı> tut & ⟦1⟧\nkez"
    assert out.count(b"\r\n") == data.count(b"\r\n")


def test_xml_keeps_crlf_inside_strings_when_file_uses_it() -> None:
    data = build_ys_xml({"TXT_HELP": "One\nTwo"}).replace(b"One\nTwo", b"One\r\nTwo")
    entries = PLUGIN.extract(data)
    assert entries[0].source == "One\nTwo"
    out = PLUGIN.inject(data, {"TXT_HELP": "Bir\nİki\nÜç"})
    assert "Bir\r\nİki\r\nÜç".encode() in out


def test_detection_and_languages() -> None:
    ni, _ = build_nni({"A/B.XSO": b"x"})
    assert detect("ys_data/archives/data-en.ni", ni[:64]).detail == NNI_ARCHIVE_DETAIL
    xml = build_ys_xml({"A": "B"})
    assert detect("ys_data/data/loc/strings/english.xml", xml[:64]).kind == FileKind.YSORIGIN
    assert detect("other/english.xml", xml[:64]).kind == FileKind.TEXT
    assert path_language("ys_data/archives/data-ge.ni>LOC/DE/DATA/MAP/X.XSO") == "de"
    assert path_language("ys_data/archives/data-sp.ni>LOC/SP/DATA/MAP/X.XSO") == "es"
    assert path_language("ys_data/archives/data-ja.ni>LOC/JP/DATA/MAP/X.XSO") == "ja"
    assert path_language("ys_data/data/loc/strings/chinese-tw.xml") == "zh-hant"
    assert is_nni_path("ys_data/archives/data-en.ni>LOC/EN/X.XSO")
    assert is_member_path("ys_data/archives/data-en.ni>LOC/EN/X.XSO")
    assert not is_nni_path("ys_data/archives/data-en.ni")


def test_scan_lists_localized_scripts_only() -> None:
    report = scan_view(GameView(TID, "Ys Origin", 0, None, [_tree()]))
    texts = sorted(e.path for e in report.entries if e.kind == FileKind.YSORIGIN.value)
    assert texts == [
        "ys_data/archives/data-en.ni>LOC/EN/DATA/MAP/S_00/S_0003/EVT_0001.XSO",
        "ys_data/archives/data-en.ni>LOC/EN/DATA/MAP/S_00/S_0003/EVT_0002.XSO",
        "ys_data/archives/data-ja.ni>LOC/JP/DATA/MAP/S_00/S_0003/EVT_0001.XSO",
        "ys_data/data/loc/strings/english.xml",
    ]
    assert report.engine.engine == "falcom"
    assert not report.warnings


def test_scan_warns_when_data_file_missing() -> None:
    files = {k: v for k, v in _archives().items() if not k.endswith("data-en.na")}
    romfs = RomFs(MemoryStorage(build_romfs(files)))
    tree = ContentTree(TID, "Ana oyun", LayeredRomFs([RomFsLayer("base", romfs)]), lambda: None)
    report = scan_view(GameView(TID, "Ys Origin", 0, None, [tree]))
    assert any("data-en.na" in w for w in report.warnings)


def test_export_rebuilds_index_and_data() -> None:
    tree = _tree()
    path = "ys_data/archives/data-en.ni>LOC/EN/DATA/MAP/S_00/S_0003/EVT_0001.XSO"
    ref = TextFileRef(path, TID, "ysorigin")
    translations = {path: {"1": "Evet. Kulenin etkisi kesildi,\nSolomon yükseliyor.", "6": "Vazgeç"}}
    result = ExportResult(Path("x"))
    outputs = _export_member_archive(
        tree, "ys_data/archives/data-en.ni", [ref], translations=translations, root=Path("romfs"), result=result
    )
    files = {rel.as_posix(): blob for rel, blob in outputs}
    assert sorted(files) == ["romfs/ys_data/archives/data-en.na", "romfs/ys_data/archives/data-en.ni"]
    arc = nni.NniArchive(
        "n", files["romfs/ys_data/archives/data-en.ni"], MemoryStorage(files["romfs/ys_data/archives/data-en.na"])
    )
    got = {e.key: e.source for e in PLUGIN.extract(arc.read("LOC/EN/DATA/MAP/S_00/S_0003/EVT_0001.XSO"))}
    assert got["6"] == "Vazgeç"
    old = MemberReader(tree.view).nni("ys_data/archives/data-en.ni")
    assert arc.read("LOC/EN/DATA/MAP/S_00/S_0003/EVT_0002.XSO") == old.read("LOC/EN/DATA/MAP/S_00/S_0003/EVT_0002.XSO")


def test_export_unchanged_writes_nothing() -> None:
    tree = _tree()
    path = "ys_data/archives/data-en.ni>LOC/EN/DATA/MAP/S_00/S_0003/EVT_0002.XSO"
    same = {path: {e.key: e.source for e in PLUGIN.extract(MemberReader(tree.view).read(path))}}
    result = ExportResult(Path("x"))
    out = _export_member_archive(
        tree,
        "ys_data/archives/data-en.ni",
        [TextFileRef(path, TID, "ysorigin")],
        translations=same,
        root=Path("r"),
        result=result,
    )
    assert out == []
    assert result.unchanged_files == 1


def test_turkish_letters_are_kept_because_the_fonts_get_the_missing_glyphs() -> None:
    translations = {"a.xml": {"K": "Işığı göster, şimdi İlerle"}}
    folded = fold_unsupported_letters(translations, [TextFileRef("a.xml", TID, "ysorigin")])
    assert translations["a.xml"]["K"] == "Işığı göster, şimdi İlerle"
    assert folded == ""
    assert PLUGIN.unsupported_letters == ""
