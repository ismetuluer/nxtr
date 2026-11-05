"""SubRip altyazı eklentisi (Ys Origin giriş videosu): tanıma, dil, aktarma, geri yazma (elle üretilmiş örneklerle)."""

from __future__ import annotations

import pytest

from nxceviri.core.formats.base import FormatError
from nxceviri.core.formats.detection import FileKind, detect
from nxceviri.core.formats.registry import plugin_for_kind
from nxceviri.core.formats.srt import SrtPlugin
from nxceviri.core.pipeline import path_language

PLUGIN = SrtPlugin()
CUES = [
    ("00:00:00,290 --> 00:00:06,000", "Once upon a time, lost within the tides\nof history, there existed a land."),
    ("00:00:18,500 --> 00:00:22,300", 'It was called "Ys".'),
    (
        "00:00:24,200 --> 00:00:34,000",
        "<i>Goddesses</i> and the Six Priests,\nwith a trailing space \n{\an8}and a code.",
    ),
]


def build_srt(*, eol: str = "\n", bom: bool = False, cues: list[tuple[str, str]] = CUES, tail: str = "\n") -> bytes:
    blocks = [f"{i}\n{time}\n{text}" for i, (time, text) in enumerate(cues, 1)]
    text = ("\n\n".join(blocks) + tail).replace("\n", eol)
    return (b"\xef\xbb\xbf" if bom else b"") + text.encode("utf-8")


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
@pytest.mark.parametrize("bom", [False, True])
def test_round_trip_is_byte_identical(eol: str, bom: bool) -> None:
    data = build_srt(eol=eol, bom=bom)
    entries = PLUGIN.extract(data)
    assert [e.key for e in entries] == ["1", "2", "3"]
    assert PLUGIN.inject(data, {e.key: e.source for e in entries}) == data
    assert PLUGIN.inject(data, {}) == data


def test_extract_shows_text_codes_and_time_context() -> None:
    entries = {e.key: e for e in PLUGIN.extract(build_srt(eol="\r\n"))}
    assert entries["1"].source == "Once upon a time, lost within the tides\nof history, there existed a land."
    assert entries["1"].context == "00:00:00,290 --> 00:00:06,000"
    assert entries["3"].source == "⟦1⟧Goddesses⟦2⟧ and the Six Priests,\nwith a trailing space \n⟦3⟧and a code."
    assert [c.raw for c in entries["3"].codes] == [b"<i>", b"</i>", b"{\an8}"]


@pytest.mark.parametrize("eol", ["\n", "\r\n"])
def test_inject_changes_only_the_text_and_keeps_line_endings(eol: str) -> None:
    data = build_srt(eol=eol, bom=True)
    out = PLUGIN.inject(
        data,
        {
            "1": "Bir zamanlar, tarihin\nakıntısında kaybolmuş bir diyar vardı.",
            "3": "⟦1⟧Tanrıçalar⟦2⟧\n⟦3⟧ve altı Rahip.",
        },
    )
    text = out.decode("utf-8-sig")
    assert text.startswith(
        "1" + eol + "00:00:00,290 --> 00:00:06,000" + eol + "Bir zamanlar, tarihin" + eol + "akıntısında"
    )
    assert "<i>Tanrıçalar</i>" + eol + "{\an8}ve altı Rahip." in text
    assert 'It was called "Ys".' in text  # dokunulmayan blok aynen
    assert out.startswith(b"\xef\xbb\xbf")
    assert [e.source for e in PLUGIN.extract(out)][1] == 'It was called "Ys".'
    assert text.count("-->") == 3


def test_inject_rejects_broken_placeholders_blank_lines_and_unknown_rows() -> None:
    data = build_srt()
    with pytest.raises(FormatError):
        PLUGIN.inject(data, {"3": "Kod yok"})
    with pytest.raises(FormatError, match="boş satır"):
        PLUGIN.inject(data, {"2": "Bir\n\nİki"})
    with pytest.raises(FormatError, match="olmayan"):
        PLUGIN.inject(data, {"99": "x"})


def test_cues_without_letters_are_skipped_and_duplicate_numbers_get_suffix() -> None:
    cues = [("00:00:01,000 --> 00:00:02,000", "♪ ♪"), ("00:00:03,000 --> 00:00:04,000", "Hello")]
    assert [e.key for e in PLUGIN.extract(build_srt(cues=cues))] == ["2"]
    data = b"1\n00:00:01,000 --> 00:00:02,000\nA\n\n1\n00:00:03,000 --> 00:00:04,000\nB\n"
    assert [e.key for e in PLUGIN.extract(data)] == ["1", "1#2"]


def test_file_without_final_newline_and_bad_encoding() -> None:
    data = build_srt(tail="")
    assert PLUGIN.inject(data, {e.key: e.source for e in PLUGIN.extract(data)}) == data
    with pytest.raises(FormatError, match="UTF-8"):
        PLUGIN.extract(b"1\n00:00:01,000 --> 00:00:02,000\n\xff\xfe\n")


def test_detection_registry_and_language() -> None:
    data = build_srt()
    assert detect("ys_data/data/extension/movies/yso_pro_en.srt", data[:64]).kind == FileKind.SRT
    assert detect("notes.srt", b"hello world").kind != FileKind.SRT
    assert detect("movies/yso_pro_en.txt", data[:64]).kind != FileKind.SRT
    assert plugin_for_kind("srt") is not None
    assert [path_language(f"movies/yso_pro_{c}.srt") for c in ("en", "sp", "de", "zh-hans", "zh-hant")] == [
        "en",
        "es",
        "de",
        "zh-hans",
        "zh-hant",
    ]
