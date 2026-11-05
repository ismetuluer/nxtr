"""Dosya türü tespiti: imza (magic) ve ad/uzantıya göre tahmin.

Bu modül yalnızca *tahmin* eder; metnin gerçekten çıkarılması ilgili format
eklentisinin (MSBT, Unity, Unreal…) işidir.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from enum import StrEnum

from nxceviri.core.archives import cpk, nni, sarc, wad, yaz0, zstd


class FileKind(StrEnum):
    MSBT = "msbt"
    GFMSG = "gfmsg"
    MINA = "mina"
    DMC1 = "dmc1"
    M2TEXT = "m2text"
    YSORIGIN = "ysorigin"
    FMSB = "fmsb"
    SRT = "srt"
    DANGANRONPA = "danganronpa"
    UNITY = "unity"
    UNREAL = "unreal"
    TEXT = "text"
    ARCHIVE = "archive"
    OTHER = "other"


KIND_LABELS = {
    FileKind.MSBT: "MSBT",
    FileKind.GFMSG: "Game Freak mesajı",
    FileKind.MINA: "Yacht Club YCD",
    FileKind.DMC1: "Devil May Cry mesajı",
    FileKind.M2TEXT: "M2 PSB metni",
    FileKind.YSORIGIN: "Ys Origin metni",
    FileKind.FMSB: "Vanillaware MsgSheet",
    FileKind.SRT: "SubRip altyazısı",
    FileKind.DANGANRONPA: "Danganronpa metni",
    FileKind.UNITY: "Unity",
    FileKind.UNREAL: "Unreal",
    FileKind.TEXT: "Düz metin / JSON / CSV",
    FileKind.ARCHIVE: "Arşiv",
    FileKind.OTHER: "Bilinmeyen / metin dışı",
}


class TextLikelihood(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    NONE = "none"


LIKELIHOOD_LABELS = {TextLikelihood.HIGH: "Yüksek", TextLikelihood.MEDIUM: "Olası", TextLikelihood.NONE: "—"}

#: M2 arşivinin (`alldata.psb.m` gibi mdf kodlu PSB dizini) tespit ayrıntısı.
M2_ARCHIVE_DETAIL = "M2 arşivi (mdf)"
#: Falcom NNI arşivinin (`data-en.ni` dizini + `.na` verisi) ve CRI CPK arşivinin tespit ayrıntıları.
NNI_ARCHIVE_DETAIL = "Falcom NNI arşivi"
CPK_ARCHIVE_DETAIL = "CRI CPK arşivi"
WAD_ARCHIVE_DETAIL = "Spike Chunsoft WAD arşivi"
#: Ys Origin'in arayüz dizgeleri: `ys_data/data/loc/strings/english.xml`.
_YS_STRINGS = re.compile(r"(?:^|/)loc/strings/[^/]+\.xml$", re.IGNORECASE)
_UTF8_BOM = bytes.fromhex("efbbbf")
#: SubRip dosya başı (isteğe bağlı BOM, sıra numarası, zaman satırı).
_SRT_HEAD = re.compile(rb"\A(?:\xef\xbb\xbf)?\s*\d+[ \t]*\r?\n\d\d:\d\d:\d\d[,.]\d{3} --> \d\d:\d\d:\d\d[,.]\d{3}")

#: Tespit için okunan baş kısım uzunluğu.
HEAD_SIZE = 64

_LOCRES_MAGIC = bytes.fromhex("0E147475674A03FC4A15909DC3377F1B")
_UASSET_MAGIC = b"\xc1\x83\x2a\x9e"
_IL2CPP_MAGIC = b"\xaf\x1b\xb1\xfa"

_TEXT_EXTENSIONS = {
    ".txt": "Düz metin",
    ".json": "JSON",
    ".csv": "CSV",
    ".tsv": "TSV",
    ".xml": "XML",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".ini": "INI",
    ".cfg": "Yapılandırma metni",
    ".po": "Gettext PO",
    ".pot": "Gettext POT",
    ".lua": "Lua betiği",
    ".srt": "Altyazı (SRT)",
    ".md": "Markdown",
    ".html": "HTML",
    ".htm": "HTML",
    ".dsc": "Düz metin",
}

_UNITY_SERIALIZED_NAMES = re.compile(
    r"(^|/)(globalgamemanagers|level\d+|mainData|unity default resources|unity_builtin_extra)$"
)


def is_gf_message(head: bytes) -> bool:
    """Game Freak mesaj dosyası başlığı: 1 bölüm, ilk anahtar 0, bölüm 0x10'da ve boyutu tutarlı."""
    if len(head) < 0x14:
        return False
    sections, count, total, key, offset = struct.unpack_from("<HHIII", head)
    if sections != 1 or key != 0 or offset != 0x10 or count == 0:
        return False
    return bool(struct.unpack_from("<I", head, 0x10)[0] == total and 4 + 8 * count <= total)


def is_unity_serialized(path: str, head: bytes) -> bool:
    """Unity serileştirilmiş dosyası mı (resources.assets, sharedassetsN.assets, levelN…)?"""
    is_serialized_name = path.lower().endswith(".assets") or _UNITY_SERIALIZED_NAMES.search(path)
    return bool(is_serialized_name) and len(head) >= 12 and 9 <= struct.unpack_from(">I", head, 8)[0] <= 40


#: Ad içinde geçtiğinde metin olasılığını yükselten sözcükler (kelime sınırlarıyla).
_TEXT_HINT = re.compile(
    r"(?<![a-z])(string[-_ ]?tables?|strings?|locali[sz]ation|locale?s?|loc|lang(uage)?s?|texts?|"
    r"dialog(ue)?s?|subtitles?|captions?|i18n|l10n|translations?|messages?|msg|talk|story)(?![a-z])"
)


@dataclass(frozen=True)
class Detection:
    kind: FileKind
    detail: str
    likelihood: TextLikelihood


def _ext(path: str) -> str:
    name = path.rsplit("/", 1)[-1].lower()
    return name[name.rfind(".") :] if "." in name else ""


def _looks_textual(head: bytes) -> bool:
    if head.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
        return True
    if b"\0" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as exc:
        # Baş kısım çok baytlı bir karakterin ortasında kesilmiş olabilir.
        return exc.start >= len(head) - 3
    return True


def has_text_hint(path: str) -> bool:
    return bool(_TEXT_HINT.search(path.lower()))


def detect(path: str, head: bytes, tail: bytes = b"") -> Detection:
    """Dosyanın türünü tahmin eder. `tail` dosyanın son baytlarıdır (Unreal .pak için)."""
    ext = _ext(path)
    hinted = has_text_hint(path)
    high_if_hint = TextLikelihood.HIGH if hinted else TextLikelihood.NONE

    if head.startswith(b"MsgStdBn"):
        return Detection(FileKind.MSBT, "MSBT (Nintendo LMS metni)", TextLikelihood.HIGH)
    if ext == ".dat" and is_gf_message(head):
        return Detection(FileKind.GFMSG, "Game Freak mesaj dosyası", TextLikelihood.HIGH)
    if ext == ".tbl" and head.startswith(b"AHTB"):
        return Detection(FileKind.GFMSG, "Game Freak etiket tablosu (AHTB)", TextLikelihood.NONE)
    if ext == ".fsd" and "/dmc1/" in path.lower():
        return Detection(FileKind.DMC1, "Devil May Cry sahne dosyası (.fsd)", TextLikelihood.HIGH)
    if path.lower().endswith("/st_init.dat") and "/dmc1/" in path.lower():
        return Detection(FileKind.DMC1, "Devil May Cry durum ve eşya metinleri (st_init.dat)", TextLikelihood.MEDIUM)
    if path.lower().endswith("/etc_u/memicon.dat") and "/dmc1/" in path.lower():
        return Detection(FileKind.DMC1, "Devil May Cry kayıt ekranı mesajları (memicon.dat)", TextLikelihood.MEDIUM)
    if ext == ".atm" and "/dmc1/" in path.lower():
        return Detection(FileKind.DMC1, "Devil May Cry başarım/galeri metni (.atm)", TextLikelihood.MEDIUM)
    if ext == ".msg" and "/dmc1/" in path.lower():
        return Detection(FileKind.DMC1, "Devil May Cry mesaj dosyası (.msg)", TextLikelihood.MEDIUM)
    if head.startswith(b"YCD\0") and ext == ".yc":
        # Yacht Club paketi: dil tabloları genellikle adında "global" geçen paketlerdedir.
        likely = TextLikelihood.HIGH if "global" in path.lower() else TextLikelihood.MEDIUM
        return Detection(FileKind.MINA, "Yacht Club YCD paketi (Mina the Hollower)", likely)
    if head.startswith(b"mdf\0") and path.lower().endswith(".psb.m"):
        return Detection(FileKind.ARCHIVE, M2_ARCHIVE_DETAIL, TextLikelihood.NONE)
    if nni.is_index(path, head):
        return Detection(FileKind.ARCHIVE, NNI_ARCHIVE_DETAIL, TextLikelihood.NONE)
    if cpk.is_cpk(path, head):
        return Detection(FileKind.ARCHIVE, CPK_ARCHIVE_DETAIL, TextLikelihood.NONE)
    if wad.is_wad(path, head):
        return Detection(FileKind.ARCHIVE, WAD_ARCHIVE_DETAIL, TextLikelihood.NONE)
    if _YS_STRINGS.search(path) and head.startswith((b"<?xml", _UTF8_BOM + b"<?xml")) and b"<dict>" in head:
        return Detection(FileKind.YSORIGIN, "Ys Origin arayüz dizgeleri (XML)", TextLikelihood.HIGH)
    if ext == ".srt" and _SRT_HEAD.match(head):
        return Detection(FileKind.SRT, "SubRip altyazısı (.srt)", TextLikelihood.HIGH)
    if head.startswith(b"MsgPrjBn"):
        return Detection(FileKind.OTHER, "MSBP (LMS proje ayarları)", TextLikelihood.NONE)
    if head.startswith(b"MsgFlwBn"):
        return Detection(FileKind.OTHER, "MSBF (LMS diyalog akışı)", TextLikelihood.NONE)
    if head.startswith(sarc.MAGIC):
        return Detection(FileKind.ARCHIVE, "SARC arşivi", TextLikelihood.NONE)
    if head.startswith(yaz0.MAGIC):
        return Detection(FileKind.ARCHIVE, "Yaz0 sıkıştırma", TextLikelihood.NONE)
    if head.startswith(zstd.MAGIC):
        return Detection(FileKind.ARCHIVE, "ZSTD sıkıştırma", TextLikelihood.NONE)

    if head.startswith((b"UnityFS\0", b"UnityWeb\0", b"UnityRaw\0", b"UnityArchive")):
        return Detection(FileKind.UNITY, "Unity AssetBundle", high_if_hint)
    if head.startswith(_IL2CPP_MAGIC) and path.endswith("global-metadata.dat"):
        return Detection(FileKind.UNITY, "Unity IL2CPP meta verisi", TextLikelihood.NONE)
    if ext in (".ress", ".resource"):
        return Detection(FileKind.UNITY, "Unity kaynak verisi (doku/ses)", TextLikelihood.NONE)
    if is_unity_serialized(path, head):
        likely = TextLikelihood.HIGH if hinted else TextLikelihood.MEDIUM
        return Detection(FileKind.UNITY, "Unity serileştirilmiş dosya", likely)

    if head.startswith(_LOCRES_MAGIC) or ext == ".locres":
        return Detection(FileKind.UNREAL, "Unreal yerelleştirme (.locres)", TextLikelihood.HIGH)
    if ext == ".locmeta":
        return Detection(FileKind.UNREAL, "Unreal yerelleştirme meta verisi", TextLikelihood.NONE)
    if ext == ".pak" and b"\xe1\x12\x6f\x5a" in tail:
        return Detection(FileKind.UNREAL, "Unreal .pak arşivi", TextLikelihood.MEDIUM)
    if ext in (".utoc", ".ucas"):
        return Detection(FileKind.UNREAL, "Unreal IoStore kapsayıcısı", TextLikelihood.MEDIUM)
    if head.startswith(_UASSET_MAGIC) or ext in (".uasset", ".uexp"):
        return Detection(FileKind.UNREAL, "Unreal varlığı (.uasset)", high_if_hint)

    if ext in _TEXT_EXTENSIONS and _looks_textual(head):
        likely = TextLikelihood.HIGH if hinted else TextLikelihood.MEDIUM
        return Detection(FileKind.TEXT, _TEXT_EXTENSIONS[ext], likely)

    other = _other_detail(head, ext)
    if other is not None:
        return Detection(FileKind.OTHER, other, TextLikelihood.NONE)
    if not ext and head and _looks_textual(head):
        return Detection(FileKind.TEXT, "Düz metin (uzantısız)", high_if_hint)
    return Detection(FileKind.OTHER, "Bilinmeyen", TextLikelihood.NONE)


def _other_detail(head: bytes, ext: str) -> str | None:
    if head.startswith(b"RIFF") and head[8:12] == b"FEV ":
        return "FMOD ses bankası"
    signatures = (
        (b"\x89PNG", "PNG görüntü"),
        (b"BNTX", "BNTX doku"),
        (b"FRES", "BFRES model"),
        (b"FFNT", "BFFNT font"),
        (b"BWAV", "BWAV ses"),
        (b"FSTM", "BFSTM ses"),
        (b"BARS", "BARS ses arşivi"),
        (b"GDPC", "Godot paketi (.pck)"),
        (b"FORM", "GameMaker verisi"),
        (b"RPA-", "Ren'Py arşivi"),
        (b"OTTO", "OpenType font"),
        (b"BY\x00", "BYML veri"),
        (b"YB", "BYML veri"),
        (b"OggS", "Ogg ses"),
        (b"\x1aE\xdf\xa3", "WebM/Matroska video"),
        (b"MZ", "Windows/.NET ikili dosyası"),
    )
    for magic, label in signatures:
        if head.startswith(magic):
            return label
    if ext in (".ttf", ".otf"):
        return "Font"
    if ext in (".dll", ".so", ".nro", ".nso"):
        return "Program kodu"
    return None
