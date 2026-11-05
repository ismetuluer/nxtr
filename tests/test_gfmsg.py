"""Game Freak mesaj biçimi: şifre, kontrol kodları, seçimler, round-trip ve aktarma akışı."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from nxceviri.core.export.layeredfs import LAYOUT_ATMOSPHERE, ExportInfo, ExportOptions, TextFileRef, export_mod
from nxceviri.core.formats.base import SOURCE_PATH, FormatError
from nxceviri.core.formats.detection import FileKind, detect
from nxceviri.core.formats.gfmsg import GfMsgPlugin
from nxceviri.core.formats.gfmsg.gfmsg import read, read_labels, write
from nxceviri.core.keys import load_keys
from nxceviri.core.languages import same_language
from nxceviri.core.pipeline import Inputs, available_languages, extract_texts, path_language, scan_sources
from nxceviri.core.progress import TaskContext
from nxceviri.core.project import Project
from tests import nxbuild

PLUGIN = GfMsgPlugin()

Piece = str | list[int]  # düz metin veya ham karakterler (kontrol kodları)


def var(kind: int, *args: int) -> list[int]:
    return [0x10, 1 + len(args), kind, *args]


def _chars(pieces: list[Piece]) -> list[int]:
    out: list[int] = []
    for p in pieces:
        if isinstance(p, str):
            raw = p.encode("utf-16-le")
            out += struct.unpack(f"<{len(raw) // 2}H", raw)
        else:
            out += p
    return out


def build_message(lines: list[list[Piece]], flags: list[int] | None = None) -> bytes:
    """Bağımsız bir yazıcı: uygulamanın kodunu kullanmadan şifreli mesaj dosyası üretir."""
    table = bytearray()
    body = bytearray()
    start = 4 + 8 * len(lines)
    for i, pieces in enumerate(lines):
        chars = [*_chars(pieces), 0]
        key = (0x7C89 + 0x2983 * i) & 0xFFFF
        enc = []
        for c in chars:
            enc.append(c ^ key)
            key = ((key << 3) | (key >> 13)) & 0xFFFF
        table += struct.pack("<IHH", start + len(body), len(chars), (flags or [0] * len(lines))[i])
        body += struct.pack(f"<{len(enc)}H", *enc) + b"\0" * (len(enc) % 2 * 2)
    size = 4 + len(table) + len(body)
    return struct.pack("<HHIIII", 1, len(lines), size, 0, 0x10, size) + bytes(table) + bytes(body)


def build_ahtb(names: list[str]) -> bytes:
    out = b"AHTB" + struct.pack("<I", len(names))
    for i, name in enumerate(names):
        raw = name.encode() + b"\0"
        out += struct.pack("<QH", 0xCBF29CE484222325 ^ i, len(raw)) + raw
    return out


GENDER = var(0x1100, 0xFF, (4 << 8) | 3)  # "boy" (3) / "girl" (4)
PLURAL = var(0x1101, 1, (1 << 8) | 0)  # "" / "s"
LINES: list[list[Piece]] = [
    ["Are you alive, my ", GENDER, "boygirl", "?!", var(0xBE01)],
    ["You earned ", var(0x0202, 1), " Merit Point", PLURAL, "s!"],
    [var(0xFF00, 2), "Can learn", var(0xFF00, 0)],
    ["Pokémon ", [0xE300], " ♂ 🎮\nnew line"],
    [var(0xBE01)],  # yalnızca kod: aktarılmaz
    [],  # boş satır
]
MESSAGE = build_message(LINES, flags=[0, 4, 64, 0, 512, 0])
LABELS = ["msg_alive", "msg_merit", "msg_learn", "msg_symbol", "msg_wait", "msg_empty", "msg_max"]


def test_read_and_identity() -> None:
    msg = read(MESSAGE)
    assert len(msg.lines) == 6
    assert [line.flags for line in msg.lines] == [0, 4, 64, 0, 512, 0]
    assert write(msg) == MESSAGE  # değişiklik yoksa bayt bayt aynı


def test_extract_with_labels() -> None:
    context = PLUGIN.collect_context(build_ahtb(LABELS), "bin/message/English/common/test.tbl")
    entries = PLUGIN.extract(MESSAGE, {**context, SOURCE_PATH: "bin/message/English/common/test.dat"})
    by_key = {e.key: e for e in entries}
    assert list(by_key) == ["0", "1", "2", "3"]
    assert by_key["0"].source == "Are you alive, my ⟦1⟧boy⟦2⟧girl⟦3⟧?!⟦4⟧"
    assert [c.label for c in by_key["0"].codes] == [
        "Cinsiyete göre seçim (erkek / kadın) — başı",
        "Seçenek ayracı",
        "Seçim sonu",
        "Sayfa sonu (bekle, temizle)",
    ]
    assert by_key["1"].source == "You earned ⟦1⟧ Merit Point⟦2⟧⟦3⟧s⟦4⟧!"
    assert by_key["2"].source == "⟦1⟧Can learn⟦2⟧"
    assert by_key["3"].source == "Pokémon ⟦1⟧ ♂ 🎮\nnew line"  # vekil çift tek karakter
    assert by_key["3"].codes[0].label == "Özel simge"
    assert by_key["1"].context == "msg_merit"
    assert PLUGIN.extract(MESSAGE)[0].context == ""  # bağlamsız da çalışır


def test_round_trip_is_byte_identical() -> None:
    same = {e.key: e.source for e in PLUGIN.extract(MESSAGE)}
    assert PLUGIN.inject(MESSAGE, same) == MESSAGE
    assert PLUGIN.inject(MESSAGE, {}) == MESSAGE


def test_inject_turkish_and_branch_lengths() -> None:
    out = PLUGIN.inject(
        MESSAGE,
        {
            "0": "Yaşıyor musun ⟦1⟧evlat⟦2⟧kızım⟦3⟧?!⟦4⟧",
            "1": "⟦1⟧ Başarı Puanı kazandın⟦2⟧⟦3⟧⟦4⟧!",  # Türkçede çoğul eki yok: iki seçenek boş
            "3": "Pokémon ⟦1⟧ ♂ 🎮\nyeni satır çğıİöşü",
        },
    )
    msg = read(out)
    assert msg.lines[0].chars[14:18] == [0x10, 3, 0x1100, 0xFF]  # "Yaşıyor musun " = 14 karakter
    assert msg.lines[0].chars[18] == (5 << 8) | 5  # "evlat" (5) / "kızım" (5)
    head = msg.lines[1].chars.index(0x1101) - 2
    assert msg.lines[1].chars[head : head + 4] == [0x10, 3, 0x1101, 1]
    assert msg.lines[1].chars[head + 4] == 0  # iki seçenek de boş
    assert [line.flags for line in msg.lines] == [0, 4, 64, 0, 512, 0]  # bayraklar korunur
    after = {e.key: e.source for e in PLUGIN.extract(out)}
    assert after["0"] == "Yaşıyor musun ⟦1⟧evlat⟦2⟧kızım⟦3⟧?!⟦4⟧"
    assert after["1"] == "⟦1⟧ Başarı Puanı kazandın⟦2⟧⟦3⟧⟦4⟧!"
    assert after["2"] == "⟦1⟧Can learn⟦2⟧"  # çevrilmeyen satır aynen kalır
    assert after["3"].endswith("çğıİöşü")


@pytest.mark.parametrize(
    ("key", "translation", "message"),
    [
        ("2", "Öğrenebilir", "Eksik kontrol kodu"),
        ("2", "⟦2⟧Öğrenebilir⟦1⟧", "sıra"),
        ("0", "⟦1⟧" + "a" * 300 + "⟦2⟧b⟦3⟧⟦4⟧", "çok uzun"),
    ],
)
def test_inject_rejects_bad_translations(key: str, translation: str, message: str) -> None:
    with pytest.raises(FormatError, match=message):
        PLUGIN.inject(MESSAGE, {key: translation})


def test_inject_unknown_key() -> None:
    with pytest.raises(FormatError, match="olmayan"):
        PLUGIN.inject(MESSAGE, {"99": "x"})


def test_detection_and_corruption() -> None:
    assert detect("bin/message/English/common/test.dat", MESSAGE[:64]).kind == FileKind.GFMSG
    assert detect("bin/message/English/common/test.tbl", build_ahtb(LABELS)[:64]).kind == FileKind.GFMSG
    assert detect("bin/message/grammar/x.dat", b"\x01\x00\xff\xff" + b"\0" * 60).kind != FileKind.GFMSG
    assert PLUGIN.extract(build_ahtb(LABELS)) == []
    with pytest.raises(FormatError, match="eksik"):
        read(MESSAGE[:40])
    broken = build_message([[[0x10, 5, 0x0100]]])  # argümanları yarıda kesilmiş kod
    with pytest.raises(FormatError, match="yarıda"):
        PLUGIN.extract(broken)
    assert read_labels(build_ahtb(LABELS)) == LABELS
    with pytest.raises(FormatError):
        read_labels(b"XXXX")


def test_languages_from_folders() -> None:
    assert path_language("bin/message/English/common/bag.dat") == "en"
    assert path_language("bin/message/JPN_KANJI/script/a.dat") == "ja-jpan"
    assert path_language("bin/message/Simp_Chinese/common/a.dat") == "zh-hans"
    assert not same_language("ja", "ja-jpan")  # kana ve kanji ayrı dosyalar


def test_large_file_round_trip() -> None:
    lines: list[list[Piece]] = [[f"Line {i} ", var(0x0101, 0), " ok"] for i in range(5000)]
    data = build_message(lines)
    entries = PLUGIN.extract(data)
    assert len(entries) == 5000
    out = PLUGIN.inject(data, {e.key: f"Satır {e.key} ⟦1⟧ tamam" for e in entries})
    assert PLUGIN.extract(out)[4999].source == "Satır 4999 ⟦1⟧ tamam"


@pytest.fixture
def gf_game(tmp_path: Path) -> tuple[Inputs, Path]:
    keys = nxbuild.TestKeys.random()
    french = build_message([["Es-tu vivant, mon ", GENDER, "garfil", " ?"]])
    files = {
        "bin/message/English/common/test.dat": MESSAGE,
        "bin/message/English/common/test.tbl": build_ahtb(LABELS),
        "bin/message/French/common/test.dat": french,
        "bin/message/French/common/test.tbl": build_ahtb(["msg_alive", "msg_max"]),
        "bin/message/grammar/table.dat": b"\x02\x00\x10\x00" + b"\x07" * 60,
        "bin/pokemon/data.gfpak": b"GFLXPACK" + b"\0" * 40,
    }
    pkg = nxbuild.build_package(
        keys,
        kind="base",
        title_id=0x0100CCCC00000000,
        application_id=0x0100CCCC00000000,
        version=0,
        romfs_files=files,
        name="Pokémon Deneme",
    )
    nsp = tmp_path / "Pokémon Deneme.nsp"
    nsp.write_bytes(pkg.nsp)
    return Inputs((nsp,), load_keys(keys.write(tmp_path / "prod.keys"))), tmp_path


def test_gf_game_import_and_export(gf_game: tuple[Inputs, Path]) -> None:
    inputs, tmp_path = gf_game
    report = scan_sources(inputs, TaskContext())
    assert report.engine.engine == "gamefreak"
    assert available_languages(report) == ["en", "fr"]
    result = extract_texts(inputs, report, TaskContext(), "en")
    assert result.skipped_languages == {"fr": 2}  # mesaj + etiket tablosu
    assert [f.path for f in result.files] == ["bin/message/English/common/test.dat"]
    entries = {e.key: e for e in result.files[0].entries}
    assert entries["0"].context == "msg_alive"  # yan dosyadaki etiket adı

    project = Project.new()
    project.import_texts(result.files)
    rows = {r.key: r for r in project.translation_rows()}
    project.set_translations(
        [(rows["0"].id, "Yaşıyor musun ⟦1⟧evlat⟦2⟧kızım⟦3⟧?!⟦4⟧"), (rows["2"].id, "⟦1⟧Öğrenebilir⟦2⟧")]
    )
    dest = tmp_path / "mod"
    export = export_mod(
        inputs,
        [TextFileRef(*f) for f in project.text_files()],
        project.translation_rows(),
        options=ExportOptions(LAYOUT_ATMOSPHERE, dest, "x", ""),
        info=ExportInfo("Pokémon Deneme", "0100CCCC00000000", 0, None),
    )
    assert export.files == ["atmosphere/contents/0100CCCC00000000/romfs/bin/message/English/common/test.dat"]
    texts = {e.key: e.source for e in PLUGIN.extract((dest / export.files[0]).read_bytes())}
    assert texts["0"] == "Yaşıyor musun ⟦1⟧evlat⟦2⟧kızım⟦3⟧?!⟦4⟧"
    assert texts["2"] == "⟦1⟧Öğrenebilir⟦2⟧"
