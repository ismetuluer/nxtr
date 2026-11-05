"""Game Freak mesaj dosyaları (Pokémon: Let's Go, Legends: Arceus…) — `.dat` + `.tbl`.

Yapı (ayrıntılar: docs/formats/gfmsg.md):

- Başlık 0x10: bölüm sayısı u16 (=1) | satır sayısı u16 | bölüm boyutu u32 |
  ilk anahtar u32 (=0) | bölüm ofseti u32 (=0x10).
- Bölüm: boyut u32 | satır tablosu {ofset u32 (bölüm başına göre), uzunluk u16 (karakter,
  sondaki 0 dahil), bayraklar u16}[] | satırlar (UTF-16LE, 4 bayta hizalı).
- Her satır XOR ile şifrelidir: anahtar 0x7C89 + 0x2983·satır_no ile başlar, her karakterden
  sonra 3 bit sola döndürülür.
- Kontrol kodu: 0x0010, ardından argüman sayısı n, ardından n adet u16 (ilki kod türü).
  Cinsiyet (0x1100) ve sayı (0x1101) seçimlerinin son argümanı, koddan hemen sonra gelen iki
  seçeneğin uzunluklarıdır (üst bayt ikinci, alt bayt birinci); seçenekler düz metindir.
- `.tbl` (AHTB): satır adları — {özet u64, uzunluk u16 (sondaki 0 dahil), ad}[]; sonda fazladan
  bir "_max" girdisi olabilir.

Seçimler üç yer tutucuyla gösterilir: `my ⟦1⟧boy⟦2⟧girl⟦3⟧` — çevirmen iki seçeneği de
değiştirebilir (boş bırakabilir); uzunluklar yazarken yeniden hesaplanır.
"""

from __future__ import annotations

import struct
from collections.abc import Mapping
from dataclasses import dataclass

from nxceviri.core.formats.base import SOURCE_PATH, Context, ControlCode, FormatError, TextEntry
from nxceviri.core.formats.detection import is_gf_message as is_message
from nxceviri.core.translate import placeholders

HEADER_SIZE = 0x10
AHTB_MAGIC = b"AHTB"
_KEY_START = 0x7C89
_KEY_STEP = 0x2983
_VARIABLE = 0x0010
_BRANCHES = {0x1100: "Cinsiyete göre seçim (erkek / kadın)", 0x1101: "Sayıya göre seçim (tekil / çoğul)"}
_MAX_BRANCH_LEN = 0xFF
#: Seçim ayracı ve sonu: dosyaya yazılmaz, yalnızca çeviri metnindeki yerleri belirler.
_BRANCH_SEP = b"gfmsg:secim-ayraci"
_BRANCH_END = b"gfmsg:secim-sonu"
_BRANCH_HEAD = " — başı"

_LABELS = {
    0xBE00: "Yeni paragraf (kaydır)",
    0xBE01: "Sayfa sonu (bekle, temizle)",
    0xBE02: "Bekleme",
    0xBDFF: "Boş kod",
    0xFF00: "Renk",
}


@dataclass
class Line:
    chars: list[int]  # sondaki 0 hariç
    terminated: bool
    flags: int


@dataclass
class GfMessage:
    line_count: int
    lines: list[Line]
    tail: bytes  # bölümden sonra kalan baytlar (normalde yok)


def _crypt(chars: list[int], index: int) -> list[int]:
    key = (_KEY_START + _KEY_STEP * index) & 0xFFFF
    out = []
    for c in chars:
        out.append(c ^ key)
        key = ((key << 3) | (key >> 13)) & 0xFFFF
    return out


def read(data: bytes) -> GfMessage:
    if not is_message(data[: HEADER_SIZE + 4]):
        raise FormatError("Game Freak mesaj dosyası değil veya başlığı bozuk.")
    _sections, count, total, _key, offset = struct.unpack_from("<HHIII", data)
    if offset + total > len(data):
        raise FormatError("Mesaj dosyası eksik: bölüm dosyanın sonunu aşıyor.")
    section = data[offset : offset + total]
    lines = []
    for i in range(count):
        line_off, length, flags = struct.unpack_from("<IHH", section, 4 + i * 8)
        if line_off < 4 + 8 * count or line_off + 2 * length > total:
            raise FormatError(f"Mesaj dosyası bozuk: {i}. satır bölümün dışına taşıyor.")
        chars = _crypt(list(struct.unpack_from(f"<{length}H", section, line_off)), i)
        terminated = bool(chars) and chars[-1] == 0
        lines.append(Line(chars[:-1] if terminated else chars, terminated, flags))
    return GfMessage(count, lines, data[offset + total :])


def write(msg: GfMessage) -> bytes:
    table = bytearray()
    body = bytearray()
    pos = 4 + 8 * msg.line_count
    for i, line in enumerate(msg.lines):
        chars = line.chars + ([0] if line.terminated else [])
        table += struct.pack("<IHH", pos + len(body), len(chars), line.flags)
        body += struct.pack(f"<{len(chars)}H", *_crypt(chars, i))
        body += b"\0" * (-len(body) % 4)
    section_size = 4 + len(table) + len(body)
    header = struct.pack("<HHIII", 1, msg.line_count, section_size, 0, HEADER_SIZE)
    return header + struct.pack("<I", section_size) + bytes(table) + bytes(body) + msg.tail


def read_labels(data: bytes) -> list[str]:
    """`.tbl` (AHTB) dosyasındaki satır adları, sırayla."""
    if not data.startswith(AHTB_MAGIC) or len(data) < 8:
        raise FormatError("Etiket tablosu (AHTB) değil.")
    (count,) = struct.unpack_from("<I", data, 4)
    pos = 8
    names = []
    for _ in range(count):
        if pos + 10 > len(data):
            raise FormatError("Etiket tablosu bozuk: dosya beklenenden kısa.")
        (length,) = struct.unpack_from("<H", data, pos + 8)
        raw = data[pos + 10 : pos + 10 + length]
        names.append(raw.rstrip(b"\0").decode("utf-8", errors="replace"))
        pos += 10 + length
    return names


def _raw(chars: list[int]) -> bytes:
    return struct.pack(f"<{len(chars)}H", *chars)


def _label(kind: int) -> str:
    if kind in _LABELS:
        return _LABELS[kind]
    group = kind >> 8
    if group == 0x01:
        return f"Değişken (ad, eşya, hareket…) {kind:04X}"
    if group == 0x02:
        return f"Sayı {kind:04X}"
    if group in (0x10, 0x13):
        return f"Dilbilgisi kodu {kind:04X}"
    return f"Kontrol kodu {kind:04X}"


def _text(chars: list[int]) -> str:
    """UTF-16 karakterleri metne çevirir (vekil çiftler tek karakter olur)."""
    return _raw(chars).decode("utf-16-le", errors="surrogatepass")


def _segments(chars: list[int]) -> list[str | ControlCode]:
    """Satırı düz metin ve kontrol kodlarına ayırır; seçimler başı/ayracı/sonuyla açılır."""
    out: list[str | ControlCode] = []
    text: list[int] = []

    def flush() -> None:
        if text:
            out.append(_text(text))
            text.clear()

    i = 0
    while i < len(chars):
        c = chars[i]
        if c == _VARIABLE:
            if i + 2 >= len(chars) or i + 2 + chars[i + 1] > len(chars) or chars[i + 1] == 0:
                raise FormatError("Mesaj satırı bozuk: kontrol kodu yarıda kesilmiş.")
            n = chars[i + 1]
            seq = chars[i : i + 2 + n]
            kind = seq[2]
            i += 2 + n
            flush()
            if kind in _BRANCHES and n >= 2:
                first, second = seq[-1] & 0xFF, seq[-1] >> 8
                options = chars[i : i + first + second]
                if len(options) == first + second and _VARIABLE not in options:
                    out.append(ControlCode(_raw(seq), _BRANCHES[kind] + _BRANCH_HEAD))
                    out.append(_text(options[:first]))
                    out.append(ControlCode(_BRANCH_SEP, "Seçenek ayracı"))
                    out.append(_text(options[first:]))
                    out.append(ControlCode(_BRANCH_END, "Seçim sonu"))
                    i += first + second
                    continue
                # Beklenmeyen yapı: seçenekler dahil tek, dokunulmaz kod.
                out.append(ControlCode(_raw(seq + options), _BRANCHES[kind]))
                i += len(options)
                continue
            out.append(ControlCode(_raw(seq), _label(kind)))
            continue
        if c == 0 or 0xE000 <= c <= 0xF8FF:
            flush()
            out.append(ControlCode(_raw([c]), "Özel simge" if c else "Satır içi bitiş"))
            i += 1
            continue
        text.append(c)
        i += 1
    flush()
    return out


def _display(chars: list[int]) -> tuple[str, tuple[ControlCode, ...]]:
    parts: list[str] = []
    codes: list[ControlCode] = []
    for seg in _segments(chars):
        if isinstance(seg, str):
            parts.append(seg)
        else:
            codes.append(seg)
            parts.append(placeholders.token(len(codes)))
    return "".join(parts), tuple(codes)


def _units(text: str) -> list[int]:
    raw = text.encode("utf-16-le", errors="surrogatepass")
    return list(struct.unpack(f"<{len(raw) // 2}H", raw))


def _encode(display: str, codes: tuple[ControlCode, ...], key: str) -> list[int]:
    """Yer tutuculu metni karakterlere çevirir; seçimlerin uzunluklarını yeniden hesaplar."""
    out: list[int] = []
    branch: tuple[int, list[int]] | None = None  # (başlığın out içindeki yeri, seçenek uzunlukları)
    for piece in placeholders.split(display):
        if isinstance(piece, str):
            out += _units(piece)
            continue
        if not 1 <= piece <= len(codes):
            raise FormatError(f"'{key}': çeviride geçersiz kontrol kodu {placeholders.token(piece)}.")
        raw = codes[piece - 1].raw
        if raw in (_BRANCH_SEP, _BRANCH_END):
            if branch is None:
                raise FormatError(f"'{key}': seçim ayracı/sonu, seçim başından önce kullanılmış.")
            start, lengths = branch
            lengths.append(len(out) - start - sum(lengths))
            if raw == _BRANCH_END:
                first, second = lengths
                if first > _MAX_BRANCH_LEN or second > _MAX_BRANCH_LEN:
                    raise FormatError(f"'{key}': seçim seçeneği çok uzun (en çok {_MAX_BRANCH_LEN} karakter).")
                out[start - 1] = (second << 8) | first
                branch = None
            continue
        seq = list(struct.unpack(f"<{len(raw) // 2}H", raw))
        out += seq
        if codes[piece - 1].label.endswith(_BRANCH_HEAD):
            branch = (len(out), [])
    if branch is not None:
        raise FormatError(f"'{key}': seçim kapatılmamış.")
    return out


class GfMsgPlugin:
    name = "gfmsg"
    label = "Game Freak mesajları (Pokémon)"
    candidates_only = False
    path_suffixes: tuple[str, ...] = (".dat", ".tbl")

    def detect(self, path: str, head: bytes) -> bool:
        lower = path.lower()
        return (lower.endswith(".dat") and is_message(head)) or (lower.endswith(".tbl") and head.startswith(AHTB_MAGIC))

    def collect_context(self, data: bytes, path: str = "") -> dict[object, object]:
        if not path.lower().endswith(".tbl"):
            return {}
        try:
            return {("etiketler", path[: -len(".tbl")]): read_labels(data)}
        except FormatError:
            return {}

    def language(self, data: bytes) -> str | None:
        return None  # dil klasörden anlaşılır: bin/message/English/…

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        if data.startswith(AHTB_MAGIC):
            return []  # etiket tablosu: yalnızca bağlam
        msg = read(data)
        labels: object = None
        if context is not None:
            path = str(context.get(SOURCE_PATH) or "")
            if path.lower().endswith(".dat"):
                labels = context.get(("etiketler", path[: -len(".dat")]))
        names = labels if isinstance(labels, list) else []
        entries = []
        for i, line in enumerate(msg.lines):
            if not any(isinstance(seg, str) and seg.strip() for seg in _segments(line.chars)):
                continue  # boş veya yalnızca kod: çevrilecek metin yok
            source, codes = _display(line.chars)
            name = names[i] if i < len(names) else ""
            entries.append(TextEntry(str(i), i, source, codes, context=str(name)))
        return entries

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        if not translations:
            return data
        msg = read(data)
        lines = {str(i): line for i, line in enumerate(msg.lines)}
        unknown = [k for k in translations if k not in lines]
        if unknown:
            raise FormatError(f"Mesaj dosyasında olmayan satırlar için çeviri verildi: {', '.join(unknown[:5])}")
        changed = False
        for key, new in translations.items():
            line = lines[key]
            source, codes = _display(line.chars)
            issues = placeholders.problems(source, new)
            if issues:
                raise FormatError(f"'{key}' çevirisi yazılamadı: {' '.join(issues)}")
            chars = _encode(new, codes, key)
            if chars != line.chars:
                line.chars = chars
                changed = True
        return write(msg) if changed else data
