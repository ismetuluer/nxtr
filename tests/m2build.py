"""Testler için küçük PSB, mdf ve NSO üreticileri (gerçek oyun verisi kullanılmaz)."""

from __future__ import annotations

import struct

import lz4.block

from nxceviri.core.archives import m2, psb
from nxceviri.core.archives.psb import PsbValue, int_array_bytes


def _name_trie(names: list[str]) -> tuple[list[int], list[int], list[int]]:
    """Adlar için çift dizili trie: (charset, tree, tails). Okuyucu `psb._decode_names`."""
    children: dict[int, dict[int, int]] = {0: {}}
    paths: list[list[int]] = []
    next_temp = 1
    for name in names:
        node, path = 0, []
        for c in [*name.encode("utf-8"), 0]:
            kids = children[node]
            if c not in kids:
                kids[c] = next_temp
                children[next_temp] = {}
                next_temp += 1
            node = kids[c]
            path.append(node)
        paths.append(path)
    ids = {0: 0}
    base: dict[int, int] = {}
    used = {0}
    queue = [0]
    while queue:
        node = queue.pop(0)
        kids = children[node]
        if not kids:
            continue
        b = 1
        while any(b + c in used for c in kids):
            b += 1
        base[ids[node]] = b
        for c, child in kids.items():
            ids[child] = b + c
            used.add(b + c)
            queue.append(child)
    size = max(used) + 1
    tree = [0] * size
    charset = [0] * size
    for node, kids in children.items():
        for child in kids.values():
            tree[ids[child]] = ids[node]
    for node_id, b in base.items():
        charset[node_id] = b
    tails = [ids[p[-1]] for p in paths]
    return charset, tree, tails


def _collect(value: PsbValue, names: set[str], strings: list[str]) -> None:
    if isinstance(value, str):
        if value not in strings:
            strings.append(value)
    elif isinstance(value, list):
        for v in value:
            _collect(v, names, strings)
    elif isinstance(value, dict):
        for k, v in value.items():
            names.add(k)
            _collect(v, names, strings)


def build_psb(root: PsbValue, chunks: list[bytes] | None = None, version: int = 2, chunk_align: int = 1) -> bytes:
    names_set: set[str] = set()
    strings: list[str] = []
    _collect(root, names_set, strings)
    names = sorted(names_set)
    chunks = chunks or []
    header_len = {2: 0x28, 3: 0x2C, 4: 0x38}[version]
    charset, tree, tails = _name_trie(names)
    names_blob = int_array_bytes(charset) + int_array_bytes(tree) + int_array_bytes(tails)
    root_blob = psb._Encoder(names, strings).encode(root, 0)  # uygulamanın kodlayıcısıyla aynı kurallar
    str_offsets, str_data = [], bytearray()
    for s in strings:
        str_offsets.append(len(str_data))
        str_data += s.encode("utf-8") + b"\0"
    c_offsets, c_data = [], bytearray()
    for c in chunks:
        c_offsets.append(len(c_data))
        c_data += c
    o_names = header_len
    o_root = o_names + len(names_blob)
    o_strings = o_root + len(root_blob)
    str_table = int_array_bytes(str_offsets)
    o_strdata = o_strings + len(str_table)
    # sürüm 4: dizge verisinden sonra boş ek parça bölümleri (ofsetler, boylar; veri yok)
    extra = int_array_bytes([]) + int_array_bytes([]) if version >= 4 else b""
    o_extra = o_strdata + len(str_data)
    o_coff = o_extra + len(extra)
    coff = int_array_bytes(c_offsets)
    o_clen = o_coff + len(coff)
    clen = int_array_bytes([len(c) for c in chunks])
    pad = b"\0" * (-(o_clen + len(clen)) % chunk_align)
    o_cdata = o_clen + len(clen) + len(pad)
    head = bytearray(psb.MAGIC + struct.pack("<HHI", version, 0, header_len if version >= 3 else 0))
    head += struct.pack("<7I", o_names, o_strings, o_strdata, o_coff, o_clen, o_cdata, o_root)
    if version >= 3:
        head += b"\0\0\0\0"
    if version >= 4:
        head += struct.pack("<3I", o_extra, o_extra + len(int_array_bytes([])), o_coff)
    if version >= 3:
        struct.pack_into("<I", head, 0x28, psb.checksum(bytes(head)))
    body = names_blob + root_blob + str_table + bytes(str_data) + extra + coff + clen + pad + bytes(c_data)
    return bytes(head) + body


def build_m2_archive(key: bytes, index_name: str, members: dict[str, bytes]) -> tuple[bytes, bytes]:
    """(`.psb.m` dizini, `.bin` verisi). Adı `.m` ile biten üyeler mdf olarak kodlanır."""
    data = bytearray()
    info: dict[str, PsbValue] = {}
    for path, content in members.items():
        stored = m2.encode(content, path, key) if path.endswith(".m") else content
        info[path] = [len(data), len(stored)]
        data += stored
        data += b"\0" * (-len(data) % 2048)
    index = build_psb({"expire_suffix_list": [], "file_info": info, "id": "archive", "version": 1.0}, version=3)
    return m2.encode(index, index_name, key), bytes(data)


def build_nso(segments: tuple[bytes, bytes, bytes], compressed: tuple[bool, bool, bool]) -> bytes:
    stored = [lz4.block.compress(s, store_size=False) if c else s for s, c in zip(segments, compressed, strict=True)]
    header = bytearray(0x100)
    header[:4] = b"NSO0"
    struct.pack_into("<I", header, 0x0C, sum(1 << i for i, c in enumerate(compressed) if c))
    pos, mem = len(header), 0
    for i, (seg, raw) in enumerate(zip(segments, stored, strict=True)):
        struct.pack_into("<IIII", header, 0x10 + i * 0x10, pos, mem, len(seg), 0)
        struct.pack_into("<I", header, 0x60 + i * 4, len(raw))
        pos += len(raw)
        mem += len(seg)
    return bytes(header) + b"".join(stored)
