"""Testler için elle üretilmiş Unreal .locres ve .pak dosyaları (gerçek oyun dosyası kullanılmaz).

Pak üreticisi uygulamanın yazıcısından bağımsızdır: eski dizin (v3, v7, v8 — sıkıştırma adlarıyla)
ve yeni dizin (v11 — kodlanmış girdiler, tam klasör dizini) biçimlerini, isteğe bağlı zlib
sıkıştırmasıyla üretir.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from collections import defaultdict

MAGIC = bytes.fromhex("0E147475674A03FC4A15909DC3377F1B")
PAK_MAGIC = 0x5A6F12E1


def fstring(text: str, force_utf16: bool = False) -> bytes:
    if not text:
        return struct.pack("<i", 0)
    if not force_utf16 and all(ord(c) < 0x80 for c in text):
        raw = text.encode("ascii") + b"\0"
        return struct.pack("<i", len(raw)) + raw
    raw = text.encode("utf-16-le") + b"\0\0"
    return struct.pack("<i", -(len(raw) // 2)) + raw


def build_locres(entries: list[tuple[str, str, str]], version: int = 2, share: bool = True) -> bytes:
    """entries: (ad alanı, anahtar, metin). `share`: aynı metinler dizide tek kez (gerçek dosyalar gibi)."""
    namespaces: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for ns, key, text in entries:
        namespaces[ns].append((key, text))
    if version == 0:
        out = bytearray(struct.pack("<I", len(namespaces)))
        for ns, keys in namespaces.items():
            out += fstring(ns) + struct.pack("<I", len(keys))
            for key, text in keys:
                out += fstring(key) + struct.pack("<I", len(text) * 7) + fstring(text)
        return bytes(out)
    strings: list[str] = []
    refs: list[int] = []
    body = bytearray(struct.pack("<I", len(namespaces)))
    for ns, keys in namespaces.items():
        if version >= 2:
            body += struct.pack("<I", hash(ns) & 0xFFFFFFFF)
        body += fstring(ns) + struct.pack("<I", len(keys))
        for key, text in keys:
            if version >= 2:
                body += struct.pack("<I", hash(key) & 0xFFFFFFFF)
            if share and text in strings:
                idx = strings.index(text)
                refs[idx] += 1
            else:
                idx = len(strings)
                strings.append(text)
                refs.append(1)
            body += fstring(key) + struct.pack("<Ii", (len(text) * 31) & 0xFFFFFFFF, idx)
    head_len = 16 + 1 + 8 + (4 if version >= 2 else 0)
    head = bytearray(MAGIC + bytes([version]) + struct.pack("<q", head_len + len(body)))
    if version >= 2:
        head += struct.pack("<I", len(entries))
    tail = bytearray(struct.pack("<I", len(strings)))
    for text, ref in zip(strings, refs, strict=True):
        tail += fstring(text)
        if version >= 2:
            tail += struct.pack("<i", ref)
    return bytes(head + body + tail)


def _entry_header(
    version: int, offset: int, size: int, usize: int, method: int, blocks: list[tuple[int, int]], digest: bytes
) -> bytes:
    out = struct.pack("<qqqI", offset, size, usize, method)
    if version < 2:
        out += struct.pack("<q", 0)
    out += digest
    if version >= 3:
        if method:
            out += struct.pack("<i", len(blocks)) + b"".join(struct.pack("<qq", s, e) for s, e in blocks)
        out += struct.pack("<BI", 0, 65536 if method else 0)
    return out


def _header_size(version: int, compressed: bool, blocks: int) -> int:
    size = 8 * 3 + 20 + 4
    if version >= 3:
        size += 5 + ((4 + 16 * blocks) if compressed else 0)
    if version < 2:
        size += 8
    return size


def build_pak(
    files: dict[str, bytes],
    *,
    version: int = 8,
    mount: str = "../../../",
    compress: bool = False,
    block_size: int = 1024,
    encrypted_index: bool = False,
) -> bytes:
    method = 1 if compress else 0
    body = bytearray()
    records: list[tuple[str, int, int, int, list[tuple[int, int]], bytes]] = []
    for name, data in files.items():
        offset = len(body)
        chunks = [data[i : i + block_size] for i in range(0, len(data), block_size)] if compress else []
        comp = [zlib.compress(c) for c in chunks]
        size = sum(len(c) for c in comp) if compress else len(data)
        header_size = _header_size(version, compress, len(comp))
        blocks: list[tuple[int, int]] = []
        pos = header_size if version >= 5 else offset + header_size
        for c in comp:
            blocks.append((pos, pos + len(c)))
            pos += len(c)
        digest = hashlib.sha1(data).digest()
        body += _entry_header(version, 0, size, len(data), method, blocks, digest)
        body += b"".join(comp) if compress else data
        records.append((name, offset, size, len(data), blocks, digest))

    if version >= 10:
        index, extra = _index_v10(version, mount, records, method, len(body))
    else:
        index = bytearray(fstring(mount) + struct.pack("<i", len(records)))
        for name, offset, size, usize, blocks, digest in records:
            index += fstring(name) + _entry_header(version, offset, size, usize, method, blocks, digest)
        extra = b""
    index_offset = len(body)
    out = bytearray(body + index + extra)
    footer = bytearray()
    if version >= 7:
        footer += b"\0" * 16
    if version >= 4:
        footer += b"\x01" if encrypted_index else b"\0"
    footer += struct.pack("<Iiqq", PAK_MAGIC, version, index_offset, len(index)) + hashlib.sha1(index).digest()
    if version == 9:
        footer += b"\0"
    if version >= 8:
        names = [b"Zlib", b"", b"", b"", b""]
        footer += b"".join(n.ljust(32, b"\0") for n in names)
    return bytes(out + footer)


def _index_v10(
    version: int,
    mount: str,
    records: list[tuple[str, int, int, int, list[tuple[int, int]], bytes]],
    method: int,
    body_len: int,
) -> tuple[bytearray, bytes]:
    encoded = bytearray()
    locations: dict[str, int] = {}
    for name, offset, size, usize, blocks, _digest in records:
        locations[name] = len(encoded)
        value = (1 << 31) | (1 << 30) | (1 << 29)  # ofset ve boyutlar 32 bite sığıyor
        value |= (method & 0x3F) << 23
        value |= (len(blocks) & 0xFFFF) << 6
        if method:
            value |= (65536 >> 11) & 0x3F
        encoded += struct.pack("<I", value) + struct.pack("<II", offset, usize)
        if method:
            encoded += struct.pack("<I", size)
            if len(blocks) != 1:
                encoded += b"".join(struct.pack("<I", e - s) for s, e in blocks)
    dirs: dict[str, dict[str, int]] = defaultdict(dict)
    for name, loc in locations.items():
        folder, _, file_name = name.rpartition("/")
        dirs[(folder + "/") if folder else "/"][file_name] = loc
    directory = bytearray(struct.pack("<i", len(dirs)))
    for folder, entries in dirs.items():
        directory += fstring(folder) + struct.pack("<i", len(entries))
        for file_name, loc in entries.items():
            directory += fstring(file_name) + struct.pack("<i", loc)
    index = bytearray(fstring(mount) + struct.pack("<iQ", len(records), 0))
    index += struct.pack("<I", 0)  # yol özeti dizini yok
    # Tam klasör dizini, dizinin hemen arkasına yazılır; ofseti şimdiden hesaplanabilir.
    tail_after_dir = struct.pack("<i", len(encoded)) + bytes(encoded) + struct.pack("<i", 0)
    dir_offset_field = len(index) + 4
    index_len = dir_offset_field + 8 + 8 + 20 + len(tail_after_dir)
    dir_offset = body_len + index_len
    index += struct.pack("<I", 1) + struct.pack("<qq", dir_offset, len(directory)) + hashlib.sha1(directory).digest()
    index += tail_after_dir
    return index, bytes(directory)
