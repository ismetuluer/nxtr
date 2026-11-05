"""Ys Origin (NNI, XSO, XML) ve Unicorn Overlord (CPK, CRILAYLA, FMSB) için elle üretilmiş küçük örnekler."""

from __future__ import annotations

import io
import struct
import zlib

from PIL import Image, ImageDraw

from nxceviri.core.archives import cpk, nni

# --- Ys Origin ---------------------------------------------------------------------------------


def build_nni(members: dict[str, bytes], *, compressed: frozenset[str] = frozenset()) -> tuple[bytes, bytes]:
    """(dizin, veri). `compressed` içindeki üyeler `.Z` ekli ve zlib'li yazılır."""
    toc = bytearray()
    names = bytearray()
    data = bytearray(b"PAD!")  # ilk üye 0 ofsetinde olmasın (0/0 boş kayıt sayılır)
    for name, content in members.items():
        raw_name = name.replace("/", "\\") + (".Z" if name in compressed else "")
        blob = content
        if name in compressed:
            blob = struct.pack("<II", zlib.crc32(content), len(content)) + zlib.compress(content)
        encoded = raw_name.encode("cp932")
        toc += struct.pack("<IIII", nni.name_hash(encoded), len(blob), len(data), len(names))
        names += encoded + b"\0"
        data += blob
    header = struct.pack("<4sIII", nni.MAGIC, len(members), len(names), 0)
    return header + nni.scramble(bytes(toc)) + nni.scramble(bytes(names)), bytes(data)


def build_xso(strings: list[str], *, code: bytes = b"\x01\x61\x0b\x02" * 3) -> bytes:
    assert len(code) % 4 == 0
    header = struct.pack("<4sHH7I", b"XSR\0", 16, 0xCCCC, 1, 0, 0, 2, 0, len(code) // 4, len(strings))
    offsets = bytearray()
    pool = bytearray()
    for s in strings:
        offsets += struct.pack("<I", len(pool))
        pool += s.encode("utf-8") + b"\0"
    out = header + code + offsets + pool
    return out + bytes((-len(out)) % 4)


def build_ys_xml(strings: dict[str, str]) -> bytes:
    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<dict>", "  <!-- Menu -->"]
    for ident, text in strings.items():
        lines.append(f'  <string id="{ident}">{text}</string>' if text else f'  <string id="{ident}"/>')
    lines.append("</dict>")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


# --- Unicorn Overlord --------------------------------------------------------------------------


def build_fmsb(strings: list[str]) -> bytes:
    body = bytearray(struct.pack("<4s7I", b"FMSB", 0, 0x20, 0, 0, len(strings), 3, 0))
    body += bytes(8 * len(strings))
    for s in strings:
        body += s.encode("utf-8") + b"\0"
    body += bytes((-len(body)) % 16)
    body += b"FEOC" + struct.pack("<III", 0, 0x10, 0)
    struct.pack_into("<I", body, 4, len(body) - 0x30)
    return bytes(body)


_TYPES = {"u16": (2, ">H"), "u32": (4, ">I"), "u64": (6, ">Q"), "str": (0x0A, None)}


def build_utf(name: str, columns: list[tuple[str, str]], rows: list[dict[str, object]], *, masked: bool) -> bytes:
    """Yalnızca satırda saklanan (0x50) sütunlarla bir `@UTF` tablosu; değeri None olan sütun boştur (0x10)."""
    strings = bytearray(b"<NULL>\0")
    offsets: dict[str, int] = {}

    def string(s: str) -> int:
        if s not in offsets:
            offsets[s] = len(strings)
            strings.extend(s.encode("utf-8") + b"\0")
        return offsets[s]

    name_off = string(name)
    defs = bytearray()
    present = [c for c in columns if any(r.get(c[0]) is not None for r in rows)]
    for col, kind in columns:
        storage = 0x50 if (col, kind) in present else 0x10
        defs += bytes([storage | _TYPES[kind][0]]) + struct.pack(">I", string(col))
    row_bytes = bytearray()
    for r in rows:
        for col, kind in present:
            value = r[col]
            if kind == "str":
                assert isinstance(value, str)
                row_bytes += struct.pack(">I", string(value))
            else:
                fmt = _TYPES[kind][1]
                assert fmt is not None
                row_bytes += struct.pack(fmt, value)
    row_len = len(row_bytes) // max(len(rows), 1)
    rows_off = 24 + len(defs)
    str_off = rows_off + len(row_bytes)
    data_off = str_off + len(strings)
    body = struct.pack(">IIIIHHI", rows_off, str_off, data_off, name_off, len(columns), row_len, len(rows))
    body += bytes(defs) + bytes(row_bytes) + bytes(strings)
    table = b"@UTF" + struct.pack(">I", len(body)) + body
    return cpk._mask(table) if masked else table


def _chunk(magic: bytes, table: bytes) -> bytes:
    return struct.pack("<4sIQ", magic, 0xFF, len(table)) + table


def _align(buf: bytearray, n: int) -> None:
    buf.extend(bytes((-len(buf)) % n))


def build_cpk(files: dict[str, bytes], *, compressed: frozenset[str] = frozenset(), masked: bool = True) -> bytes:
    """TOC ve ETOC'lu küçük bir CPK. Hizalama 0x800; `compressed` üyeler CRILAYLA ile konur."""
    align = 0x800
    toc_offset = 0x800
    blobs = {m: (layla_compress(d) if m in compressed else d) for m, d in files.items()}
    toc_columns = [("DirName", "str"), ("FileName", "str"), ("FileSize", "u32"), ("ExtractSize", "u32")]
    toc_columns += [("FileOffset", "u64"), ("ID", "u32")]

    def toc_rows(offsets: dict[str, int]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for i, (member, data) in enumerate(files.items()):
            folder, _, fname = member.rpartition("/")
            rows.append(
                {
                    "DirName": folder,
                    "FileName": fname,
                    "FileSize": len(blobs[member]),
                    "ExtractSize": len(data),
                    "FileOffset": offsets[member],
                    "ID": i,
                }
            )
        return rows

    toc_chunk = _chunk(b"TOC ", build_utf("CpkTocInfo", toc_columns, toc_rows(dict.fromkeys(files, 0)), masked=masked))
    content_offset = toc_offset + len(toc_chunk) + (-(toc_offset + len(toc_chunk))) % align
    content = bytearray()
    offsets: dict[str, int] = {}
    for member in files:
        pos = content_offset + len(content)
        pos += (-pos) % align
        content.extend(bytes(pos - content_offset - len(content)))
        offsets[member] = pos - toc_offset
        content += blobs[member]
    etoc_offset = content_offset + len(content) + (-(content_offset + len(content))) % align
    header_columns = [("TocOffset", "u64"), ("ContentOffset", "u64"), ("ContentSize", "u64"), ("EtocOffset", "u64")]
    header_columns += [("ItocOffset", "u64"), ("EnabledPackedSize", "u64"), ("EnabledDataSize", "u64")]
    header_columns += [("Files", "u32"), ("Align", "u16"), ("Tvers", "str")]
    header: dict[str, object] = {
        "TocOffset": toc_offset,
        "ContentOffset": content_offset,
        "ContentSize": etoc_offset - content_offset,
        "EtocOffset": etoc_offset,
        "ItocOffset": None,
        "EnabledPackedSize": sum(len(d) for d in files.values()),
        "EnabledDataSize": sum(len(b) for b in blobs.values()),
        "Files": len(files),
        "Align": align,
        "Tvers": "test",
    }
    out = bytearray(_chunk(b"CPK ", build_utf("CpkHeader", header_columns, [header], masked=masked)))
    _align(out, toc_offset)
    out += _chunk(b"TOC ", build_utf("CpkTocInfo", toc_columns, toc_rows(offsets), masked=masked))
    _align(out, align)
    assert len(out) == content_offset
    out += content
    _align(out, align)
    etoc_rows: list[dict[str, object]] = [{"LocalDir": m.rpartition("/")[0]} for m in files]
    out += _chunk(b"ETOC", build_utf("CpkEtocInfo", [("LocalDir", "str")], etoc_rows, masked=masked))
    return bytes(out)


def layla_compress(data: bytes) -> bytes:
    """CRILAYLA kodlayıcı (test için): açgözlü geri başvuru araması, sondan başa."""
    prefix, body = data[:0x100], data[0x100:]
    bits: list[int] = []

    def emit(value: int, n: int) -> None:
        bits.extend((value >> (n - 1 - i)) & 1 for i in range(n))

    w = len(body) - 1
    while w >= 0:
        best_len, best_dist = 0, 0
        for dist in range(3, min(0x2000 + 3, len(body) - w)):
            length = 0
            while length <= w and body[w - length] == body[w - length + dist] and length < 300:
                length += 1
            if length > best_len:
                best_len, best_dist = length, dist
        if best_len >= 3:
            emit(1, 1)
            emit(best_dist - 3, 13)
            v = best_len - 3
            for width in (2, 3, 5):
                top = (1 << width) - 1
                emit(min(v, top), width)
                if v < top:
                    break
                v -= top
            else:
                while v >= 0xFF:
                    emit(0xFF, 8)
                    v -= 0xFF
                emit(v, 8)
            w -= best_len
        else:
            emit(0, 1)
            emit(body[w], 8)
            w -= 1
    bits.extend([0] * ((-len(bits)) % 8))
    packed = bytes(int("".join(map(str, bits[i : i + 8])), 2) for i in range(0, len(bits), 8))
    stream = packed[::-1]
    return b"CRILAYLA" + struct.pack("<II", len(body), len(stream)) + stream + prefix


# --- Ys Origin yazı tipi (BMFont) ve grafik (DDS) ----------------------------------------------


def _blob(w: int, h: int, *, outline: bool, parts: list[tuple[int, int, int, int]] | None = None) -> Image.Image:
    """Beyaz dolgulu (isteğe bağlı koyu 1 piksel dış çizgili) harf: `parts` (x, y, w, h) dikdörtgenlerinin birleşimi."""
    image = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for x, y, pw, ph in parts or [(0, 0, w, h)]:
        if outline:
            draw.rectangle((x, y, x + pw - 1, y + ph - 1), fill=(20, 20, 20, 255))
        else:
            draw.rectangle((x, y, x + pw - 1, y + ph - 1), fill=(255, 255, 255, 255))
    if outline:
        for x, y, pw, ph in parts or [(0, 0, w, h)]:
            if pw > 2 and ph > 2:
                draw.rectangle((x + 1, y + 1, x + pw - 2, y + ph - 2), fill=(255, 255, 255, 255))
            else:  # çok ince parça: yalnızca dolgu
                draw.rectangle((x, y, x + pw - 1, y + ph - 1), fill=(255, 255, 255, 255))
    return image


def latin_glyphs(*, outline: bool) -> dict[str, tuple[Image.Image, int, int]]:
    """Türkçe harf türetmeye yetecek küçük Latin glif kümesi: harf → (görüntü, xoffset, yoffset); taban çizgisi 14."""

    def b(w: int, h: int, parts: list[tuple[int, int, int, int]] | None = None) -> Image.Image:
        return _blob(w, h, outline=outline, parts=parts)

    return {
        # nokta (satır 0-2), boşluk (3-4), gövde (5-13)
        "i": (b(5, 14, [(1, 0, 3, 3), (1, 5, 3, 9)]), 1, 3),
        "n": (b(8, 9), 1, 8),
        "I": (b(5, 11), 1, 3),
        "s": (b(6, 9), 1, 8),
        "S": (b(7, 11), 1, 3),
        "c": (b(6, 9), 1, 8),
        "ç": (b(6, 12, [(0, 0, 6, 9), (2, 9, 2, 3)]), 1, 8),
        "C": (b(8, 11), 1, 3),
        "Ç": (b(8, 14, [(0, 0, 8, 11), (3, 11, 2, 3)]), 1, 3),
        "g": (b(7, 13, [(0, 0, 7, 9), (1, 9, 5, 4)]), 1, 8),
        "G": (b(8, 11), 1, 3),
        "ö": (b(7, 12), 1, 5),
    }


def build_bmfont(
    glyphs: dict[str, tuple[Image.Image, int, int]], *, atlas: tuple[int, int] = (96, 96), alpha_only: bool = False
) -> tuple[bytes, Image.Image]:
    """BMFont ikili (v3) dosyası ve atlas; glifler raflara dizilir. `alpha_only`: renk kanalları sıfır (arial gibi)."""
    sheet = Image.new("RGBA", atlas, (0, 0, 0, 0))
    chars = bytearray()
    x = y = shelf = 0
    for ch, (glyph, xo, yo) in glyphs.items():
        image = glyph
        if alpha_only:
            image = Image.merge("RGBA", (*(Image.new("L", glyph.size, 0),) * 3, glyph.getchannel("A")))
        if x + image.width + 2 > atlas[0]:
            x, y, shelf = 0, y + shelf + 2, 0
        assert y + image.height <= atlas[1], "test atlası dar"
        sheet.paste(image, (x, y))
        chars += struct.pack("<IHHHHhhhBB", ord(ch), x, y, image.width, image.height, xo, yo, image.width + 1, 0, 15)
        x, shelf = x + image.width + 2, max(shelf, image.height)
    info = struct.pack("<h", 12) + bytes(13) + b"Test\0"
    common = struct.pack("<5H5B", 20, 14, atlas[0], atlas[1], 1, 0, 0, 0, 0, 0)
    pages = b"test.png\0"
    blocks = [(1, info), (2, common), (3, pages), (4, bytes(chars))]
    out = b"BMF\x03" + b"".join(bytes([k]) + struct.pack("<I", len(b)) + b for k, b in blocks)
    return out, sheet


def build_dds(image: Image.Image, *, mips: int = 1, code: str = "BC3") -> bytes:
    """Oyundaki gibi DDS: BC3 için DX10 başlığı (DXGI 77), BC1 için eski DXT1 başlığı; ek mip seviyeleri sıfır verilidir
    (yalnızca boyut/başlık sınaması için)."""
    buf = io.BytesIO()
    image.save(buf, "DDS", pixel_format="BC3" if code == "BC3" else "DXT1")
    data = bytearray(buf.getvalue())
    if code == "BC3":
        assert data[84:88] == b"DX10"
        struct.pack_into("<I", data, 128, 77)  # Pillow TYPELESS (76) yazar; oyun BC3_UNORM (77) kullanır
    struct.pack_into("<I", data, 28, mips)
    block = 16 if code == "BC3" else 8
    for level in range(1, mips):
        w, h = max(1, image.width >> level), max(1, image.height >> level)
        data += bytes(max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * block)
    return bytes(data)
