"""Devil May Cry (Switch): mesaj tablosu, karakter kodlaması, fsd kapsayıcısı ve eklenti."""

from __future__ import annotations

import struct

import pytest

from nxceviri.core.formats import detection
from nxceviri.core.formats.base import SOURCE_PATH, FormatError
from nxceviri.core.formats.dmc1 import Dmc1Plugin, codec, fsd
from nxceviri.core.formats.registry import plugin_for_kind
from tests.dmc1build import ENGLISH_SLOT, message, table, text
from tests.dmc1build import fsd as build_fsd

ENGLISH = [
    "The gate has been opened. You can go now!",
    "I need 45 Red Orbs to open it.\nIt's a long way, and you are not ready.",
    "Do you have the key?",
]
FRENCH = ["Le portail est ouvert.", "Il me faut 45 orbes.", "As-tu la cle?"]
CTX: dict[object, object] = {SOURCE_PATH: "data/dmc1/fsd/r100.fsd"}
MSG_CTX: dict[object, object] = {SOURCE_PATH: "data/dmc1/etc_e/common.msg"}


def _file() -> bytes:
    return build_fsd(
        table([message(s) for s in ENGLISH]),
        others={24: table([message(s) for s in FRENCH]), 25: b"\x99" * 100},
    )


def test_decode_and_encode_round_trip() -> None:
    raw = text("Press R2 to jump!") + b"\x7e\x0a\x00" + text("Yes") + b"\x7e\x0e\x00\x78" + b"\0\0\0"
    msg = codec.decode(raw)
    assert msg.text == "Press R2 to jump!⟦1⟧Yes"
    assert [c.raw for c in msg.codes] == [b"\x7e\x0a\x00"]
    assert msg.tail == b"\x7e\x0e\x00\x78\0\0\0"
    assert codec.encode(msg) == raw
    assert codec.encode(msg, "Press R2!⟦1⟧No") == text("Press R2!") + b"\x7e\x0a\x00" + text("No") + msg.tail


def test_unknown_bytes_are_kept_as_codes() -> None:
    raw = bytes([0x50]) + text("Jackpot") + bytes([0x51]) + b"\x7e\x0e\x00\x00"
    msg = codec.decode(raw)
    assert msg.text == "⟦1⟧Jackpot⟦2⟧"
    assert codec.encode(msg) == raw


def test_digits_and_zero_padding_are_not_confused() -> None:
    raw = text("at 9:00.") + b"\x7e\x0e\x00\x50" + b"\0\0\0\0"
    msg = codec.decode(raw)
    assert msg.text == "at 9:00."
    assert msg.tail == b"\x7e\x0e\x00\x50\0\0\0\0"


def test_every_turkish_letter_is_written_as_a_pair() -> None:
    msg = codec.decode(text("Yes") + b"\x7e\x0e\x00\x50")
    sentence = "Çok güzel şölen: ığ İŞĞ ç ö ü Ö Ü; bitti"
    raw = codec.encode(msg, sentence, pad_to=4)
    assert len(raw) % 4 == 0
    assert codec.decode(raw).text == sentence
    for code, letter in codec.PAIR_CHARS.items():
        assert bytes([0x72, code]) in codec.encode(msg, letter, pad_to=1)  # PC yamasındaki düzen
    # PC yamasından alınan gerçek baytlar: "kapattık", "üzgünüm", "Doğru"
    assert codec.decode(bytes.fromhex("32283728 3b3b 7274 32".replace(" ", ""))).text == "kapattık"
    assert codec.decode(bytes.fromhex("726c41 2e 726c 35 726c 34".replace(" ", ""))).text == "üzgünüm"
    assert codec.decode(bytes.fromhex("11 36 7273 39 3c".replace(" ", ""))).text == "Doğru"
    assert set(codec.UNSUPPORTED_LETTERS) == set("ğĞıİşŞ")  # özgün fontta glifi olmayanlar


def test_quotes_and_punctuation() -> None:
    msg = codec.decode(bytes([0x0B]) + text("Jackpot") + bytes([0x0C, 0x4C, 0x0A, 0x4D]) + b"\x7e\x0e\x00\x50")
    assert msg.text == "“Jackpot”(/)"


@pytest.mark.parametrize("letter", ["€", "ß", "你", "Ж"])  # ASCII karşılığı olmayanlar reddedilir
def test_encode_rejects_letters_missing_from_the_font(letter: str) -> None:
    with pytest.raises(FormatError):
        codec.encode(codec.decode(text("Yes")), f"Evet {letter}")


def test_pad_to_recomputes_zero_padding() -> None:
    msg = codec.decode(message("Hello there"))
    short = codec.encode(msg, "Hi", pad_to=16)
    assert len(short) == 16
    assert short.startswith(text("Hi") + b"\x7e\x0e\x00\x50")
    assert codec.encode(msg, "Hi", pad_to=1) == text("Hi") + b"\x7e\x0e\x00\x50"


def test_parse_table_and_build_table_round_trip() -> None:
    strings = [message(s) for s in ENGLISH]
    data = table(strings)
    parsed = codec.parse_table(data, 0)
    assert parsed is not None
    assert parsed.count == 3
    assert codec.build_table(strings, first=parsed.first) == data
    assert codec.parse_table(b"\0" * 40, 0) is None
    assert codec.parse_table(b"", 0) is None


def test_fsd_directory_and_block_replacement() -> None:
    data = _file()
    offsets = fsd.read_directory(data)
    assert len([o for o in offsets if o]) == 7
    start, end = fsd.block_range(data, offsets[ENGLISH_SLOT])
    bigger = data[start:end] + b"\x01" * 40
    out = fsd.replace_blocks(data, {start: bigger})
    new_offsets = fsd.read_directory(out)
    assert new_offsets[ENGLISH_SLOT] == start
    assert new_offsets[24] > offsets[24]  # sonraki bölümler kaydı
    s2, e2 = fsd.block_range(out, new_offsets[24])
    assert out[s2:e2] == data[offsets[24] : fsd.block_range(data, offsets[24])[1]]
    with pytest.raises(FormatError):
        fsd.replace_blocks(data, {offsets[ENGLISH_SLOT] + 1: b"x"})
    with pytest.raises(FormatError):
        fsd.read_directory(b"\x01\0\0\0")


def test_extract_reads_the_english_slot_only() -> None:
    entries = Dmc1Plugin().extract(_file(), CTX)
    assert [e.source for e in entries] == ENGLISH
    assert len({e.key for e in entries}) == 3


def test_extract_standalone_msg() -> None:
    data = table([message("Yes", pad=13), message("", pad=0), message("Do you want to quit?", pad=1)])
    entries = Dmc1Plugin().extract(data, MSG_CTX)
    assert [(e.key, e.source) for e in entries] == [("0", "Yes"), ("2", "Do you want to quit?")]


def test_filler_strings_without_words_are_skipped() -> None:
    filler = b"\x7e\x09\x01\x00\x7e\x09\x00" * 3 + b"\x7e\x0e\x00\x00"
    data = build_fsd(table([message("You have the key."), filler, message("Do you want to go?")]))
    entries = Dmc1Plugin().extract(data, CTX)
    assert [e.source for e in entries] == ["You have the key.", "Do you want to go?"]


def test_extract_without_english_slot_returns_nothing() -> None:
    plugin = Dmc1Plugin()
    assert plugin.extract(b"\x01\0\0\0" + b"\0" * 64, CTX) == []
    broken = bytearray(_file())
    struct.pack_into("<Q", broken, 8 + 8 * ENGLISH_SLOT, 0)
    assert plugin.extract(bytes(broken), CTX) == []


def test_inject_without_translations_returns_same_bytes() -> None:
    data = _file()
    assert Dmc1Plugin().inject(data, {}) is data


def test_inject_grows_the_table_and_keeps_everything_else() -> None:
    plugin = Dmc1Plugin()
    data = _file()
    long_text = "Kapı açılmış oldu. Artık gidebilirsin, ama dikkatli ol çünkü yol uzun ve tehlikeli olabilir."
    translations = {
        f"{fsd.read_directory(data)[ENGLISH_SLOT]:x}/0": long_text.replace("ı", "i")
        .replace("ş", "s")
        .replace("ğ", "g"),
    }
    out = plugin.inject(data, translations)
    assert len(out) > len(data)
    entries = {e.key: e.source for e in plugin.extract(out, CTX)}
    key = next(iter(translations))
    assert entries[key] == translations[key]
    others = [k for k in entries if k != key]
    assert [entries[k] for k in others] == ENGLISH[1:]
    # diğer bölümler bayt bayt aynı ve dizin tutarlı
    before, after = fsd.read_directory(data), fsd.read_directory(out)
    for slot in (0, 1, 22, 24, 25, 30):
        b0, b1 = fsd.block_range(data, before[slot]), fsd.block_range(out, after[slot])
        assert data[b0[0] : b0[1]] == out[b1[0] : b1[1]]
    # tekrar yazmak (aynı çevirilerle) dosyayı değiştirmez
    assert plugin.inject(out, translations) == out


def test_inject_shrinks_and_standalone_msg() -> None:
    plugin = Dmc1Plugin()
    data = _file()
    key = f"{fsd.read_directory(data)[ENGLISH_SLOT]:x}/2"
    out = plugin.inject(data, {key: "Anahtar?"})
    assert len(out) <= len(data)
    assert {e.key: e.source for e in plugin.extract(out, CTX)}[key] == "Anahtar?"
    msg = table([message("Yes", pad=13), message("Do you want to quit?", pad=1)])
    out_msg = plugin.inject(msg, {"1": "Cikmak ister misin?"})
    parsed = codec.parse_table(out_msg, 0)
    assert parsed is not None
    assert parsed.strings[1][1] % 16 == 0
    entries = plugin.extract(out_msg, MSG_CTX)
    assert [e.source for e in entries] == ["Yes", "Cikmak ister misin?"]


def test_inject_errors() -> None:
    plugin = Dmc1Plugin()
    data = _file()
    base = f"{fsd.read_directory(data)[ENGLISH_SLOT]:x}"
    with pytest.raises(FormatError):
        plugin.inject(data, {f"{base}/99": "Merhaba"})
    with pytest.raises(FormatError):
        plugin.inject(data, {f"{base}/0": "Evet €"})


def test_detection_and_registry() -> None:
    assert detection.detect("data/dmc1/fsd/r002.fsd", b"").kind == detection.FileKind.DMC1
    assert detection.detect("data/dmc1/etc_e/common.msg", b"").kind == detection.FileKind.DMC1
    assert detection.detect("data/other/x.fsd", b"").kind != detection.FileKind.DMC1
    plugin = plugin_for_kind("dmc1")
    assert plugin is not None
    assert plugin.detect("data/dmc1/fsd/r002.fsd", b"")
    assert plugin.detect("data/dmc1/etc_e/common.msg", b"")
    assert not plugin.detect("data/dmc1/etc_f/common.msg", b"")  # Fransızca kopya
    assert not plugin.detect("data/dmc1/etc/common.msg", b"")  # Japonca kopya


def test_export_normalizes_text_and_adds_the_font_for_this_format_only() -> None:
    from pathlib import Path

    from nxceviri.core.export.layeredfs import TextFileRef, fold_unsupported_letters, support_files

    translations = {
        "a.fsd": {"1": "Işık, güzel \u2019yıl\u2019 \u2013 bitti\u2026"},
        "b.msbt": {"1": "Işık \u2019yıl\u2019"},
    }
    files = [TextFileRef("a.fsd", "T", "dmc1"), TextFileRef("b.msbt", "T", "msbt")]
    folded = fold_unsupported_letters(translations, files)
    assert folded == ""  # DMC için ğ ş ı İ dönüştürülmez: moda kendi yazı dokusu eklenir
    assert translations["a.fsd"]["1"] == "Işık, güzel 'yıl' - bitti..."  # fontta olmayan işaretler düzeltilir
    assert translations["b.msbt"]["1"] == "Işık \u2019yıl\u2019"  # başka biçime dokunulmaz
    extra = support_files(files, "atmosphere", "Mod")
    assert [str(p).replace("\\", "/") for p, _d in extra] == ["atmosphere/contents/T/romfs/data/dmc1/etc_e/msg_tex.t32"]
    assert len(extra[0][1]) == 0xC0 + 512 * 256 * 4 + 256
    assert isinstance(extra[0][0], Path)


def test_extract_works_without_a_file_path() -> None:
    """Dışa aktarma doğrulaması `extract`i bağlamsız çağırır; `.msg` dosyası yine tanınmalıdır."""
    data = table([message("Yes"), message("Do you want to quit?")])
    entries = Dmc1Plugin().extract(data)
    assert [(e.key, e.source) for e in entries] == [("0", "Yes"), ("1", "Do you want to quit?")]


def test_normalize_handles_typographic_marks_and_stray_accents() -> None:
    assert codec.normalize("hâlâ ’yıl’ – bitti… Î é Ç ğ") == "hala 'yıl' - bitti... I e Ç ğ"
    assert (
        codec.normalize("⟦1⟧ Doğru\nçok 12") == "⟦1⟧ Doğru\nçok 12"
    )  # yer tutucu, satır sonu, Türkçe harf ve rakam korunur
    assert codec.normalize("你好") == "你好"  # karşılığı olmayan olduğu gibi kalır (yazarken hata verir)


def _status(english: bytes) -> bytes:
    """`st_init.dat` gibi: u32 adet + u32 ofsetler; 0. bölüm mesaj tablosu, diğerleri veri."""
    blocks = [english, b"\x11" * 48, b"\x22" * 32]
    head = 4 + 4 * len(blocks)
    pos = (head + 15) & ~15
    offsets, body = [], bytearray()
    for block in blocks:
        body += bytes(-(pos + len(body)) % 16)
        offsets.append(pos + len(body))
        body += block
    out = struct.pack(f"<I{len(blocks)}I", len(blocks), *offsets)
    return out + bytes(pos - len(out)) + bytes(body)


def test_status_file_extract_and_inject() -> None:
    plugin = Dmc1Plugin()
    data = _status(table([message("Equip?"), message("You don't have enough Red Orbs.")]))
    assert detection.detect("data/dmc1/status_e/st_init.dat", b"").kind == detection.FileKind.DMC1
    assert plugin.detect("data/dmc1/status_e/st_init.dat", b"")
    assert not plugin.detect("data/dmc1/status_f/st_init.dat", b"")
    assert not plugin.detect("data/dmc1/status_u/st_init.dat", b"")  # Japonca metin; yalnızca resimleri değişir
    entries = plugin.extract(data)
    assert [(e.key, e.source) for e in entries] == [("0", "Equip?"), ("1", "You don't have enough Red Orbs.")]
    out = plugin.inject(data, {"1": "Yeterince Kırmızı Küren yok, üzgünüm."})
    assert [e.source for e in plugin.extract(out)] == ["Equip?", "Yeterince Kırmızı Küren yok, üzgünüm."]
    offsets = fsd.read_directory(out, wide=False)
    assert out[offsets[1] : offsets[1] + 48] == b"\x11" * 48  # sonraki bölümler kaydı, içerik aynı
    assert out[offsets[2] :] == b"\x22" * 32
    assert plugin.inject(data, {}) is data


def _atm(s: str) -> bytes:
    """`.atm` dizgisi: aynı harf tablosu, kaçış baytı 0x80 (boşluk 80 05, bitiş 80 0E)."""
    body = text(s).replace(b"\x7e", b"\x80") + b"\x80\x0e\x00\x50"
    return body + bytes(4 + -len(body) % 4)  # uzunluk 4'ün katı


def test_atm_files_use_the_0x80_escape() -> None:
    plugin = Dmc1Plugin()
    data = table([_atm("Yes"), _atm("Set brightness"), _atm("Unlock all\nentries")], align=False)
    assert detection.detect("data/dmc1/atm_e/new_common_nx.atm", b"").kind == detection.FileKind.DMC1
    assert plugin.detect("data/dmc1/atm_e/new_common_nx.atm", b"")
    assert not plugin.detect("data/dmc1/atm_f/new_common_nx.atm", b"")
    entries = plugin.extract(data)
    assert [e.source for e in entries] == ["Yes", "Set brightness", "Unlock all\nentries"]
    out = plugin.inject(data, {"1": "Parlaklığı ayarla", "2": "Tümünü\naç"})
    assert [e.source for e in plugin.extract(out)] == ["Yes", "Parlaklığı ayarla", "Tümünü\naç"]
    parsed = codec.parse_table(out, 0)
    assert parsed is not None
    seg = out[parsed.strings[1][0] : parsed.strings[1][0] + parsed.strings[1][1]]
    assert b"\x80\x05" in seg  # boşluk ve bitiş 0x80 ile yazılır
    assert b"\x7e" not in seg
    assert b"\x72" not in seg  # Türkçe harf çiftsiz, tek bayt: ğ → 0x73, ı → 0x74
    assert b"\x73" in seg
    assert b"\x74" in seg
    assert all(n % 4 == 0 for _o, n in parsed.strings)  # özgün dizgilerin dolgu katı korunur
    assert plugin.inject(data, {}) is data
