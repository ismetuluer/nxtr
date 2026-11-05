"""M2 PSB metin eklentisi, M2 taraması ve M2 dışa aktarma (elle üretilmiş küçük arşivlerle)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from nxceviri.core.archives import m2, psb
from nxceviri.core.archives.access import MemberReader, is_m2_path, is_member_path
from nxceviri.core.archives.psb import PsbValue
from nxceviri.core.container.romfs import RomFs
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.container.view import ContentTree, GameView, LayeredRomFs, RomFsLayer
from nxceviri.core.errors import ArchiveError
from nxceviri.core.export.layeredfs import ExportError, ExportResult, TextFileRef, _export_m2
from nxceviri.core.formats.base import SOURCE_PATH, FormatError
from nxceviri.core.formats.detection import M2_ARCHIVE_DETAIL, FileKind, detect
from nxceviri.core.formats.m2text import M2TextPlugin, is_text_member
from nxceviri.core.formats.scanner import scan_view
from nxceviri.core.translate import placeholders
from tests.m2build import build_m2_archive, build_psb
from tests.nxbuild import build_romfs

KEY = b"TestAnahtar01"  # testlere özgü uydurma anahtar
TID = "0100000000000000"

MENU: dict[str, PsbValue] = {
    "message": {
        "MenuItemText__COMMON_YES": {"eng": ["Yes"], "fra": ["Oui"], "ger": ["Ja"], "jpn": ["はい"]},
        "MenuItemText__COMMON_OK": {"eng": ["OK"], "fra": ["OK"], "ger": ["OK"]},
        "MenuItemText__COMMON_CONFIRM": {"eng": ["Confirm"], "fra": ["Confirmer"]},
        "MenuItemText__TITLE_TOP_GAME_SELECT": {"eng": ["Game Select"], "fra": ["Game Select"]},
        "MenuItemText__TITLE_TOP_OTHER": {"eng": ["Game Select"], "fra": ["Game Select"]},
        "NoticeMsg__SAVE": {"eng": ["Saving...\nDo not turn off #{color,FFFF00FF}%s#{color,clear} now."]},
        "NoticeMsg__EMPTY": {"eng": [""]},
        "NoticeMsg__NUMBER": {"eng": ["123"]},
    }
}
_RICH = "<b>Briefing</b><br><size=0><voffset=63.4px><br></voffset></size>Snake"
BOOK: dict[str, PsbValue] = {
    "data": [
        {"pageNo": 1, "pageTitle": "TOP", "text": "", "groupid": "g1"},
        {"pageNo": 2, "pageTitle": "Section 1: Briefing", "TextAreaA0": _RICH, "groupid": "g1"},
        {"pageNo": 3, "pageTitle": "TOP", "TextAreaA0": "<br><br>", "groupid": "g2"},
    ]
}


def _at(value: Any, *path: str | int) -> Any:
    for step in path:
        value = value[step]
    return value


def _tree(members: dict[str, bytes], *, key: bytes = KEY, code: bytes | None = None) -> ContentTree:
    index, data = build_m2_archive(key, "alldata.psb.m", members)
    romfs = RomFs(MemoryStorage(build_romfs({"alldata.psb.m": index, "alldata.bin": data, "other/x.txt": b"x"})))
    loaded = b"\0".join([b"nn::fs::MountRom", KEY, b"archive"]) if code is None else code
    return ContentTree(TID, "Ana oyun", LayeredRomFs([RomFsLayer("base", romfs)]), lambda: loaded)


MEMBERS = {
    "system/config/menu_item.psb.m": build_psb(MENU, version=4),
    "087/config/output_TextData_EN.psb.m": build_psb(BOOK, version=3),
    "087/config/output_TextData_JP.psb.m": build_psb(BOOK, version=3),  # Japonca kaynak: taranmaz
    "system/font/title_a.psb.m": build_psb({"code": {"a": {"w": 1}}, "id": "font"}),  # metin yok
    "system/roms/disc.BIN": b"\x00" * 100,
}


def test_string_refs_lists_paths_and_indexes() -> None:
    doc = psb.Psb(build_psb({"a": ["x", {"b": "y"}], "c": "x"}))
    refs = doc.string_refs()
    assert [(p, doc.strings[i]) for p, i in refs] == [(("a", 0), "x"), (("a", 1, "b"), "y"), (("c",), "x")]
    assert refs[0][1] == refs[2][1]  # aynı yazı tek dizge


def test_extract_language_table_rows_are_unique_strings() -> None:
    plugin = M2TextPlugin()
    entries = plugin.extract(build_psb(MENU))
    by_source = {e.source: e for e in entries}
    assert list(by_source) == ["Yes", "OK", "Confirm", "Game Select", "Saving...\nDo not turn off ⟦1⟧⟦2⟧⟦3⟧ now."]
    assert by_source["Yes"].key == "message/MenuItemText__COMMON_YES/eng/0"
    # aynı yazıyı kullanan iki anahtar tek satırda birleşir, bağlamda ikisi de görünür
    assert by_source["Game Select"].context == "MenuItemText__TITLE_TOP_GAME_SELECT, MenuItemText__TITLE_TOP_OTHER"
    assert [e.index for e in entries] == [0, 1, 2, 3, 4]  # boş ve yalnızca sayı olan metinler çıkmaz


def test_extract_control_codes() -> None:
    entry = M2TextPlugin().extract(build_psb(MENU))[-1]
    assert [c.raw for c in entry.codes] == [b"#{color,FFFF00FF}", b"%s", b"#{color,clear}"]
    assert entry.codes[1].label == "Değişken %s"
    assert entry.codes[0].label.startswith("Renk / biçim kodu")


def test_extract_book_pages() -> None:
    entries = M2TextPlugin().extract(build_psb(BOOK))
    assert [e.source for e in entries] == [
        "TOP",
        "Section 1: Briefing",
        "⟦1⟧Briefing⟦2⟧⟦3⟧⟦4⟧⟦5⟧⟦6⟧⟦7⟧⟦8⟧Snake",
    ]
    assert entries[0].key == "data/0/pageTitle"
    assert entries[0].context == "sayfa 0 / pageTitle, sayfa 2 / pageTitle"  # "TOP" iki sayfada
    assert entries[2].key == "data/1/TextAreaA0"
    assert [c.label for c in entries[2].codes][:3] == ["Biçim etiketi <b>", "Etiket sonu </b>", "Satır sonu <br>"]


def test_book_only_from_english_files() -> None:
    plugin = M2TextPlugin()
    data = build_psb(BOOK)
    assert plugin.extract(data, {SOURCE_PATH: "alldata.psb.m>087/config/output_TextData_EN.psb.m"})
    assert not plugin.extract(data, {SOURCE_PATH: "alldata.psb.m>087/config/output_TextData_JP.psb.m"})
    assert is_text_member("087/config/output_TextData_EN.psb.m", data)
    assert not is_text_member("087/config/output_TextData_JP.psb.m", data)
    assert not is_text_member("a.psb.m", b"not a psb")
    assert not is_text_member("a.psb.m", build_psb({"id": "font", "code": {"a": 1}}))


def test_string_used_as_identifier_is_not_extracted() -> None:
    # "On" hem metin (eng) hem de bir kimlik olarak kullanılıyor: değiştirmek mantığı bozar → çıkarılmaz
    data = build_psb({"message": {"K": {"eng": ["On"]}, "L": {"eng": ["Off"]}}, "layout": ["On", "x"]})
    assert [e.source for e in M2TextPlugin().extract(data)] == ["Off"]


def test_inject_round_trip_is_identical() -> None:
    plugin = M2TextPlugin()
    for tree in (MENU, BOOK):
        data = build_psb(tree, version=4)
        entries = plugin.extract(data)
        assert plugin.inject(data, {e.key: e.source for e in entries}) == data
        assert plugin.inject(data, {}) is data


def test_inject_translates_all_languages_sharing_the_string_and_keeps_the_rest() -> None:
    plugin = M2TextPlugin()
    data = build_psb(MENU, version=4)
    keys = {e.source: e.key for e in plugin.extract(data)}
    save = next(e for e in plugin.extract(data) if e.source.startswith("Saving"))
    out = plugin.inject(
        data,
        {
            keys["Yes"]: "Evet",
            keys["Game Select"]: "Oyun Seçimi",
            save.key: "Kaydediliyor...\nŞimdi ⟦1⟧⟦2⟧⟦3⟧ ğüşiçöı.",
        },
    )
    root = psb.Psb(out).root()
    assert _at(root, "message", "MenuItemText__COMMON_YES", "eng") == ["Evet"]
    assert _at(root, "message", "MenuItemText__COMMON_YES", "fra") == ["Oui"]  # başka dil: aynen
    assert _at(root, "message", "MenuItemText__TITLE_TOP_OTHER", "eng") == ["Oyun Seçimi"]
    assert _at(root, "message", "MenuItemText__TITLE_TOP_GAME_SELECT", "fra") == ["Oyun Seçimi"]  # aynı dizge
    saved = "Kaydediliyor...\nŞimdi #{color,FFFF00FF}%s#{color,clear} ğüşiçöı."
    assert _at(root, "message", "NoticeMsg__SAVE", "eng") == [saved]
    assert psb.Psb(out).names == psb.Psb(data).names


def test_inject_rejects_bad_placeholders_and_unknown_keys() -> None:
    plugin = M2TextPlugin()
    data = build_psb(MENU)
    save = next(e for e in plugin.extract(data) if e.source.startswith("Saving"))
    with pytest.raises(FormatError, match="Eksik kontrol kodu"):
        plugin.inject(data, {save.key: "Kaydediliyor"})
    swapped = "⟦3⟧ ⟦2⟧ ⟦1⟧"
    assert placeholders.problems(save.source, swapped)
    with pytest.raises(FormatError, match="sırası"):
        plugin.inject(data, {save.key: save.source.replace("⟦1⟧⟦2⟧⟦3⟧", "⟦3⟧⟦2⟧⟦1⟧")})
    with pytest.raises(FormatError, match="olmayan satırlar"):
        plugin.inject(data, {"message/yok/eng/0": "x"})


def test_detect_m2_archive_and_member_paths() -> None:
    index, _ = build_m2_archive(KEY, "alldata.psb.m", {"a.bin": b"x"})
    det = detect("alldata.psb.m", index[:64], b"")
    assert (det.kind, det.detail) == (FileKind.ARCHIVE, M2_ARCHIVE_DETAIL)
    assert detect("alldata.bin", b"\0" * 64, b"").kind != FileKind.ARCHIVE
    assert is_m2_path("alldata.psb.m>system/config/menu_item.psb.m")
    assert is_member_path("alldata.psb.m>a.psb.m")
    assert not is_m2_path("alldata.psb.m")
    assert not is_m2_path("a.sarc>b.psb.m")


def test_member_reader_reads_through_m2() -> None:
    tree = _tree(MEMBERS)
    reader = MemberReader(tree.view, tree.code)
    assert reader.read("alldata.psb.m>system/config/menu_item.psb.m") == MEMBERS["system/config/menu_item.psb.m"]
    assert reader.m2("alldata.psb.m") is reader.m2("alldata.psb.m")  # dizin bir kez açılır
    with pytest.raises(ArchiveError, match="bulunamadı"):
        reader.read("alldata.psb.m>yok.psb.m")


def test_member_reader_errors_without_key_or_data_file() -> None:
    tree = _tree(MEMBERS, code=b"anahtar yok")
    with pytest.raises(ArchiveError, match="anahtarı oyunun kodunda bulunamadı"):
        MemberReader(tree.view, tree.code).m2("alldata.psb.m")
    with pytest.raises(ArchiveError, match="anahtarı"):
        MemberReader(tree.view, None).m2("alldata.psb.m")
    index, _ = build_m2_archive(KEY, "alldata.psb.m", MEMBERS)
    lone = ContentTree(
        TID,
        "x",
        LayeredRomFs([RomFsLayer("base", RomFs(MemoryStorage(build_romfs({"alldata.psb.m": index}))))]),
        lambda: KEY,
    )
    with pytest.raises(ArchiveError, match="veri dosyası"):
        MemberReader(lone.view, lone.code).m2("alldata.psb.m")


def test_scan_lists_only_translatable_english_members() -> None:
    tree = _tree(MEMBERS)
    view = GameView(TID, "Oyun", 0, None, [tree])
    report = scan_view(view)
    kinds = {e.path: e.kind for e in report.entries}
    assert kinds["alldata.psb.m"] == "archive"
    assert kinds["alldata.psb.m>system/config/menu_item.psb.m"] == "m2text"
    assert kinds["alldata.psb.m>087/config/output_TextData_EN.psb.m"] == "m2text"
    assert not any("_JP" in p or "font" in p or "roms" in p for p in kinds if ">" in p)
    assert report.engine.engine == "m2"
    assert report.warnings == []


def test_scan_warns_when_key_is_missing() -> None:
    tree = _tree(MEMBERS, code=b"anahtar yok")
    report = scan_view(GameView(TID, "Oyun", 0, None, [tree]))
    assert [e.kind for e in report.entries if ">" in e.path] == []
    assert any("anahtarı oyunun kodunda bulunamadı" in w for w in report.warnings)


def _refs(tree: ContentTree) -> tuple[list[TextFileRef], dict[str, dict[str, str]]]:
    plugin = M2TextPlugin()
    reader = MemberReader(tree.view, tree.code)
    menu = "alldata.psb.m>system/config/menu_item.psb.m"
    book = "alldata.psb.m>087/config/output_TextData_EN.psb.m"
    keys = {e.source: e.key for e in plugin.extract(reader.read(menu))}
    book_keys = {e.source: e.key for e in plugin.extract(reader.read(book))}
    refs = [TextFileRef(menu, TID, "m2text"), TextFileRef(book, TID, "m2text")]
    translations = {menu: {keys["Yes"]: "Evet", keys["OK"]: "Tamam"}, book: {book_keys["TOP"]: "ÜST"}}
    return refs, translations


def test_export_m2_gives_changed_members_loose_and_trims_the_index() -> None:
    tree = _tree(MEMBERS)
    refs, translations = _refs(tree)
    result = ExportResult(Path("x"))
    outputs = _export_m2(tree, "alldata.psb.m", refs, translations=translations, root=Path("romfs"), result=result)
    files = {rel.as_posix(): blob for rel, blob in outputs}
    assert sorted(files) == [
        "romfs/087/config/output_TextData_EN.psb.m",
        "romfs/alldata.psb.m",
        "romfs/system/config/menu_item.psb.m",
    ]
    arc = MemberReader(tree.view, tree.code).m2("alldata.psb.m")
    new_arc = m2.M2Archive("alldata.psb.m", files["romfs/alldata.psb.m"], tree.view.open("alldata.bin"), KEY)
    assert set(arc.entries) - set(new_arc.entries) == {
        "system/config/menu_item.psb.m",
        "087/config/output_TextData_EN.psb.m",
    }
    assert all(new_arc.entries[k] == arc.entries[k] for k in new_arc.entries)  # kalan girdiler aynı konumda
    menu = psb.Psb(m2.decode(files["romfs/system/config/menu_item.psb.m"], "menu_item.psb.m", KEY))
    assert "Evet" in menu.strings
    assert "Yes" not in menu.strings
    book = psb.Psb(m2.decode(files["romfs/087/config/output_TextData_EN.psb.m"], "output_textdata_en.psb.m", KEY))
    assert [s for s in book.strings if s.startswith("ÜST")] == ["ÜST"]
    assert not any("tobject" in f for f in files)  # veri dosyası (.bin) verilmez


def test_export_m2_unchanged_translations_write_nothing() -> None:
    tree = _tree(MEMBERS)
    refs, _ = _refs(tree)
    reader = MemberReader(tree.view, tree.code)
    same = {
        r.path: {e.key: e.source for e in M2TextPlugin().extract(reader.read(r.path))} for r in refs
    }  # özgün metinlerin kendisi
    result = ExportResult(Path("x"))
    out = _export_m2(tree, "alldata.psb.m", refs, translations=same, root=Path("r"), result=result)
    assert out == []
    assert result.unchanged_files == 2


def test_export_m2_requires_key() -> None:
    tree = _tree(MEMBERS, code=b"anahtar yok")
    refs, translations = _refs(_tree(MEMBERS))
    with pytest.raises(ExportError, match="okunamadı"):
        _export_m2(
            tree, "alldata.psb.m", refs, translations=translations, root=Path("r"), result=ExportResult(Path("x"))
        )
