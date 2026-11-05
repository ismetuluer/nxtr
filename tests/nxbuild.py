"""Testler için elle üretilmiş, küçük Switch içerikleri.

Gerçek oyun dosyası veya gerçek anahtar kullanılmaz: her test oturumu rastgele
anahtarlar üretir ve NCA/NSP/NSZ/BKTR yapılarını bu anahtarlarla sıfırdan kurar.
Yapılar uygulamanın okuyucusunun beklediği alanları birebir doldurur; RomFS hash
tabloları ve IVFC hash katmanları okuyucu tarafından kullanılmadığından boş bırakılır.
"""

from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import dataclass, field
from pathlib import Path

import lz4.block
import zstandard

from nxceviri.core.container.crypto import aes_ctr, aes_ecb_encrypt, aes_xts_encrypt

NONE32 = 0xFFFFFFFF


def align(n: int, a: int) -> int:
    return (n + a - 1) // a * a


# --- anahtarlar ------------------------------------------------------------------------


@dataclass
class TestKeys:
    header_key: bytes
    key_area: dict[int, bytes]
    titlekek: dict[int, bytes]

    @classmethod
    def random(cls, generations: int = 3) -> TestKeys:
        return cls(
            os.urandom(32),
            {g: os.urandom(16) for g in range(generations)},
            {g: os.urandom(16) for g in range(generations)},
        )

    def lines(self) -> list[str]:
        out = [f"header_key = {self.header_key.hex()}"]
        for g, k in self.key_area.items():
            out.append(f"key_area_key_application_{g:02x} = {k.hex()}")
            out.append(f"key_area_key_ocean_{g:02x} = {os.urandom(16).hex()}")
            out.append(f"key_area_key_system_{g:02x} = {os.urandom(16).hex()}")
        for g, k in self.titlekek.items():
            out.append(f"titlekek_{g:02x} = {k.hex()}")
        out.append(f"master_key_00 = {os.urandom(16).hex()}")
        return out

    def write(self, path: Path) -> Path:
        path.write_text("\n".join(self.lines()) + "\n", encoding="utf-8")
        return path

    def all_secret_hex(self) -> list[str]:
        values = [self.header_key, *self.key_area.values(), *self.titlekek.values()]
        return [v.hex() for v in values]


# --- RomFS / PFS0 ------------------------------------------------------------------------


def build_romfs(files: dict[str, bytes]) -> bytes:
    """Verilen yol → içerik sözlüğünden geçerli bir RomFS görüntüsü üretir."""
    dirs: dict[str, list[str]] = {"": []}  # dizin → alt dizin adları
    dir_files: dict[str, list[str]] = {"": []}
    for path in sorted(files):
        parts = path.split("/")
        cur = ""
        for part in parts[:-1]:
            nxt = f"{cur}/{part}" if cur else part
            if nxt not in dirs:
                dirs[nxt] = []
                dir_files[nxt] = []
                dirs[cur].append(part)
            cur = nxt
        dir_files[cur].append(parts[-1])

    def entry_len(name: str, fixed: int) -> int:
        return fixed + align(len(name.encode()), 4)

    # Dizin ofsetlerini önceden hesapla (BFS sırası).
    order = [""]
    i = 0
    while i < len(order):
        d = order[i]
        order.extend(f"{d}/{c}" if d else c for c in sorted(dirs[d]))
        i += 1
    dir_off: dict[str, int] = {}
    pos = 0
    for d in order:
        dir_off[d] = pos
        pos += entry_len(d.rsplit("/", 1)[-1] if d else "", 0x18)
    file_order = [f"{d}/{f}" if d else f for d in order for f in sorted(dir_files[d])]
    file_off: dict[str, int] = {}
    pos = 0
    for f in file_order:
        file_off[f] = pos
        pos += entry_len(f.rsplit("/", 1)[-1], 0x20)

    data = bytearray()
    data_pos: dict[str, int] = {}
    for f in file_order:
        data_pos[f] = len(data)
        data += files[f]
        data += b"\0" * (align(len(data), 16) - len(data))

    dir_table = bytearray()
    for d in order:
        name = (d.rsplit("/", 1)[-1] if d else "").encode()
        parent = d.rsplit("/", 1)[0] if "/" in d else ""
        siblings = sorted(dirs[parent]) if d else []
        my = d.rsplit("/", 1)[-1]
        sib = NONE32
        if d and siblings.index(my) + 1 < len(siblings):
            nxt = siblings[siblings.index(my) + 1]
            sib = dir_off[f"{parent}/{nxt}" if parent else nxt]
        children = sorted(dirs[d])
        child = dir_off[f"{d}/{children[0]}" if d else children[0]] if children else NONE32
        fl = sorted(dir_files[d])
        first_file = file_off[f"{d}/{fl[0]}" if d else fl[0]] if fl else NONE32
        dir_table += struct.pack("<6I", dir_off[parent] if d else 0, sib, child, first_file, NONE32, len(name))
        dir_table += name + b"\0" * (align(len(name), 4) - len(name))

    file_table = bytearray()
    for f in file_order:
        d = f.rsplit("/", 1)[0] if "/" in f else ""
        names = sorted(dir_files[d])
        my = f.rsplit("/", 1)[-1]
        k = names.index(my)
        sib = file_off[f"{d}/{names[k + 1]}" if d else names[k + 1]] if k + 1 < len(names) else NONE32
        name = my.encode()
        file_table += struct.pack("<IIQQII", dir_off[d], sib, data_pos[f], len(files[f]), NONE32, len(name))
        file_table += name + b"\0" * (align(len(name), 4) - len(name))

    dh_off = 0x50
    dm_off = dh_off + 4
    fh_off = dm_off + len(dir_table)
    fm_off = fh_off + 4
    data_off = align(fm_off + len(file_table), 16)
    header = struct.pack("<10Q", 0x50, dh_off, 4, dm_off, len(dir_table), fh_off, 4, fm_off, len(file_table), data_off)
    body = header + struct.pack("<I", NONE32) + dir_table + struct.pack("<I", NONE32) + file_table
    body += b"\0" * (data_off - len(body))
    return bytes(body + data)


def build_pfs0(files: list[tuple[str, bytes]]) -> bytes:
    strtab = bytearray()
    offs = []
    for name, _ in files:
        offs.append(len(strtab))
        strtab += name.encode() + b"\0"
    strtab += b"\0" * (align(16 + 24 * len(files) + len(strtab), 0x20) - (16 + 24 * len(files) + len(strtab)))
    out = bytearray(struct.pack("<4sIII", b"PFS0", len(files), len(strtab), 0))
    pos = 0
    for (_, data), name_off in zip(files, offs, strict=True):
        out += struct.pack("<QQII", pos, len(data), name_off, 0)
        pos += len(data)
    out += strtab
    for _, data in files:
        out += data
    return bytes(out)


# --- NCA ---------------------------------------------------------------------------------

DATA_PAD = 0x400  # bölüm içinde asıl verinin başladığı ofset (hash katmanları yerine boşluk)


def ivfc_hash_data(data_offset: int, data_size: int) -> bytes:
    hd = bytearray(0xF8)
    struct.pack_into("<4sIII", hd, 0, b"IVFC", 0x20000, 0x20, 7)
    for lvl in range(5):
        struct.pack_into("<QQI", hd, 0x10 + lvl * 0x18, 0, 0, 14)
    struct.pack_into("<QQI", hd, 0x10 + 5 * 0x18, data_offset, data_size, 14)
    return bytes(hd)


def sha256_hash_data(data_offset: int, data_size: int) -> bytes:
    hd = bytearray(0xF8)
    struct.pack_into("<II", hd, 0x20, 0x1000, 2)
    struct.pack_into("<QQQQ", hd, 0x28, 0, 0x20, data_offset, data_size)
    return bytes(hd)


@dataclass
class Section:
    fs_type: int  # 0 RomFS, 1 PFS0
    plain: bytes  # bölümün tamamı (şifresiz), DATA_PAD dahil
    encryption: int = 3  # 1 yok, 3 CTR, 4 CTR_EX (yalnızca build_patch_nca)
    hash_data: bytes = b""
    generation: int = 0
    secure_value: int = field(default_factory=lambda: int.from_bytes(os.urandom(4), "little"))
    patch_info: bytes = b"\0" * 0x40
    # CTR_EX bölümler için önceden şifrelenmiş ham bayt (build_patch_nca doldurur)
    raw_override: bytes | None = None
    # Başlıktaki bölüm boyutu ham bayttan farklıysa (seyrek bölüm: sanal boyut)
    header_size: int | None = None
    sparse_info: bytes = b""  # FsHeader 0x148 (0x30 bayt)
    compression_info: bytes = b""  # FsHeader 0x178 (0x28 bayt)

    @property
    def upper(self) -> bytes:
        return self.secure_value.to_bytes(4, "big") + self.generation.to_bytes(4, "big")


def romfs_section(romfs: bytes, encryption: int = 3) -> Section:
    plain = b"\0" * DATA_PAD + romfs
    plain += b"\0" * (align(len(plain), 0x200) - len(plain))
    return Section(0, plain, encryption, ivfc_hash_data(DATA_PAD, len(romfs)))


def pfs0_section(pfs: bytes, encryption: int = 3) -> Section:
    plain = b"\0" * DATA_PAD + pfs
    plain += b"\0" * (align(len(plain), 0x200) - len(plain))
    return Section(1, plain, encryption, sha256_hash_data(DATA_PAD, len(pfs)))


@dataclass
class BuiltNca:
    data: bytes
    content_key: bytes
    sections: list[tuple[int, Section]]  # (mutlak başlangıç, bölüm)
    rights_id: bytes
    enc_title_key: bytes | None

    @property
    def content_id(self) -> str:
        return hashlib.sha256(self.data).digest()[:16].hex()


def build_nca(
    keys: TestKeys,
    content_type: int,
    program_id: int,
    sections: list[Section],
    *,
    key_generation: int = 2,
    use_rights_id: bool = False,
) -> BuiltNca:
    content_key = os.urandom(16)
    gen_index = key_generation - 1 if key_generation > 0 else 0
    rights_id = b"\0" * 16
    enc_title_key = None
    if use_rights_id:
        rights_id = program_id.to_bytes(8, "big") + b"\0" * 7 + bytes([key_generation])
        enc_title_key = aes_ecb_encrypt(keys.titlekek[gen_index], content_key)

    body = bytearray()
    placed: list[tuple[int, Section]] = []
    pos = 0x4000
    body += b"\0" * (pos - 0xC00)
    for s in sections:
        start = pos
        raw = s.raw_override if s.raw_override is not None else s.plain
        if s.raw_override is None and s.encryption == 3:
            raw = aes_ctr(content_key, s.upper, start, s.plain)
        body += raw
        pos += len(raw)
        placed.append((start, s))

    header = bytearray(0xC00)
    header[:0x200] = os.urandom(0x200)
    header[0x200:0x204] = b"NCA3"
    header[0x205] = content_type
    header[0x206] = min(key_generation, 2)
    header[0x207] = 0
    struct.pack_into("<QQ", header, 0x208, 0xC00 + len(body), program_id)
    struct.pack_into("<I", header, 0x21C, 0x000C1100)
    header[0x220] = key_generation if key_generation > 2 else 0
    header[0x230:0x240] = rights_id
    for i, (start, s) in enumerate(placed):
        raw_len = len(s.raw_override) if s.raw_override is not None else len(s.plain)
        if s.header_size is not None:
            raw_len = s.header_size
        struct.pack_into("<II", header, 0x240 + i * 0x10, start // 0x200, (start + raw_len) // 0x200)
        fsh = bytearray(0x200)
        struct.pack_into("<HBBB", fsh, 0, 2, s.fs_type, 3 if s.fs_type == 0 else 2, s.encryption)
        fsh[0x8 : 0x8 + len(s.hash_data)] = s.hash_data
        fsh[0x100:0x140] = s.patch_info
        struct.pack_into("<II", fsh, 0x140, s.generation, s.secure_value)
        fsh[0x148 : 0x148 + len(s.sparse_info)] = s.sparse_info
        fsh[0x178 : 0x178 + len(s.compression_info)] = s.compression_info
        header[0x400 + i * 0x200 : 0x600 + i * 0x200] = fsh
        header[0x280 + i * 0x20 : 0x2A0 + i * 0x20] = hashlib.sha256(fsh).digest()
    key_area = bytes(0x20) + content_key + bytes(0x10)
    header[0x300:0x340] = aes_ecb_encrypt(keys.key_area[gen_index], key_area)
    enc_header = aes_xts_encrypt(keys.header_key, bytes(header))
    return BuiltNca(enc_header + bytes(body), content_key, placed, rights_id, enc_title_key)


# --- BKTR yama ---------------------------------------------------------------------------


def _bucket_tree(entries: list[bytes], entry_size: int, end_offset: int) -> bytes:
    node = 0x4000
    per_set = (node - 16) // entry_size
    sets = [entries[i : i + per_set] for i in range(0, len(entries), per_set)]
    l1 = bytearray(node)
    struct.pack_into("<iiq", l1, 0, 0, len(sets), end_offset)
    out = bytearray(l1)
    starts = []
    for i, chunk in enumerate(sets):
        first = struct.unpack_from("<q", chunk[0])[0]
        starts.append(first)
        set_end = struct.unpack_from("<q", sets[i + 1][0])[0] if i + 1 < len(sets) else end_offset
        n = bytearray(node)
        struct.pack_into("<iiq", n, 0, i, len(chunk), set_end)
        for j, e in enumerate(chunk):
            n[16 + j * entry_size : 16 + (j + 1) * entry_size] = e
        out += n
    for i, s in enumerate(starts):
        struct.pack_into("<q", out, 16 + i * 8, s)
    return bytes(out)


def build_patch_nca(
    keys: TestKeys,
    program_id: int,
    base: BuiltNca,
    new_romfs: bytes,
    block: int = 0x200,
) -> BuiltNca:
    """Base'in RomFS bölümünden `new_romfs`'e giden BKTR yamalı bir Program NCA üretir.

    Yama verisi üç bölgeye ayrılır: iki farklı sayaç nesliyle şifreli ve bir şifresiz
    bölge; böylece AesCtrEx'in tüm yolları sınanır.
    """
    _base_start, base_sec = next((st, s) for st, s in base.sections if s.fs_type == 0)
    base_plain = base_sec.plain
    virt = romfs_section(new_romfs).plain

    # Sanal bölümü bloklara ayırıp base'le aynı olanları base'e, farklı olanları yamaya eşle.
    runs: list[tuple[int, int, int]] = []  # (sanal başlangıç, kaynak, uzunluk)
    for off in range(0, len(virt), block):
        chunk = virt[off : off + block]
        same = base_plain[off : off + block] == chunk
        src = 0 if same else 1
        if runs and runs[-1][1] == src:
            v, s, n = runs[-1]
            runs[-1] = (v, s, n + len(chunk))
        else:
            runs.append((off, src, len(chunk)))
    patch_data = bytearray()
    indirect_entries = []
    for v, src, n in runs:
        if src == 0:
            indirect_entries.append(struct.pack("<qqi", v, v, 0))
        else:
            indirect_entries.append(struct.pack("<qqi", v, len(patch_data), 1))
            patch_data += virt[v : v + n]
    patch_data += b"\0" * (align(max(len(patch_data), 0x30), 0x30) - len(patch_data))
    third = len(patch_data) // 3 // 16 * 16
    regions = [(0, True, 5), (third, True, 9), (2 * third, False, 0)]
    ctr_end = align(len(patch_data), 0x4000)
    patch_data += b"\0" * (ctr_end - len(patch_data))

    sec = Section(0, b"", 4, ivfc_hash_data(DATA_PAD, len(new_romfs)), generation=3)
    content_key = os.urandom(16)
    gen_index = 1
    # Önce bölüm başlangıcını bilmeliyiz: build_nca bölümleri 0x4000'den başlatır.
    start = 0x4000
    raw = bytearray()
    for i, (roff, encrypted, gen) in enumerate(regions):
        rend = regions[i + 1][0] if i + 1 < len(regions) else ctr_end
        piece = bytes(patch_data[roff:rend])
        if encrypted:
            upper = sec.secure_value.to_bytes(4, "big") + gen.to_bytes(4, "big")
            piece = aes_ctr(content_key, upper, start + roff, piece)
        raw += piece
    ind_tree = _bucket_tree(indirect_entries, 0x14, len(virt))
    ctr_entries = [struct.pack("<qB3xi", roff, 0 if enc else 1, gen) for roff, enc, gen in regions]
    ctr_tree = _bucket_tree(ctr_entries, 0x10, ctr_end)
    ind_off = len(raw)
    ctr_off = ind_off + len(ind_tree)
    tables = ind_tree + ctr_tree
    raw += aes_ctr(content_key, sec.upper, start + ind_off, tables)
    raw += b"\0" * (align(len(raw), 0x200) - len(raw))

    patch_info = bytearray(0x40)
    struct.pack_into("<QQ4sIiI", patch_info, 0, ind_off, len(ind_tree), b"BKTR", 1, len(indirect_entries), 0)
    struct.pack_into("<QQ4sIiI", patch_info, 0x20, ctr_off, len(ctr_tree), b"BKTR", 1, len(ctr_entries), 0)
    sec.patch_info = bytes(patch_info)
    sec.raw_override = bytes(raw)
    sec.plain = b""

    built = build_nca(keys, 0, program_id, [sec], key_generation=2)
    # build_nca rastgele bir içerik anahtarı üretti; yamayı kendi anahtarımızla şifreledik.
    # Anahtar alanını bizim anahtarımızla yeniden kur.
    return _rekey(keys, built, content_key, gen_index)


def compressed_romfs_section(romfs: bytes, block: int = 0x1000) -> Section:
    """Veri bölgesi LZ4 sıkıştırma katmanlı bir RomFS bölümü.

    Açılmış veri = RomFS + sonda iki sıfır bloğu. İlk blok ham, sıfır blokları "sıfır",
    kalanlar LZ4 (sıkışmıyorsa ham) yazılır; böylece tüm blok türleri sınanır.
    """
    virt = romfs + b"\0" * (align(len(romfs), block) - len(romfs)) + b"\0" * (2 * block)
    phys = bytearray()
    entries = []
    for off in range(0, len(virt), block):
        chunk = virt[off : off + block]
        packed = lz4.block.compress(chunk, store_size=False)
        if off == 0 or len(packed) >= len(chunk):
            entries.append(struct.pack("<qqBb2xI", off, len(phys), 0, 0, NONE32))
            phys += chunk
        elif chunk == bytes(len(chunk)) and off >= len(romfs):
            entries.append(struct.pack("<qqBb2xI", off, 0, 1, 0, 0))
        else:
            entries.append(struct.pack("<qqBb2xI", off, len(phys), 3, 0, len(packed)))
            phys += packed
    phys += b"\0" * (align(len(phys), 0x10) - len(phys))
    table = _bucket_tree(entries, 0x18, len(virt))
    region = bytes(phys) + table
    info = struct.pack("<QQ4sIiI", len(phys), len(table), b"BKTR", 1, len(entries), 0) + bytes(8)
    plain = b"\0" * DATA_PAD + region
    plain += b"\0" * (align(len(plain), 0x200) - len(plain))
    return Section(0, plain, 3, ivfc_hash_data(DATA_PAD, len(region)), compression_info=info)


def build_sparse_base_nca(
    keys: TestKeys, program_id: int, base_romfs: bytes, new_romfs: bytes, block: int = 0x200
) -> BuiltNca:
    """Seyrek RomFS bölümlü bir base Program NCA: güncellemenin değiştirdiği bloklar dosyada yok.

    Bölümün `plain` alanı sanal (tam) veriyi tutar; build_patch_nca bunu base olarak kullanır.
    """
    sec = romfs_section(base_romfs)
    virt_new = romfs_section(new_romfs).plain
    content_key = os.urandom(16)
    start = 0x4000
    enc = aes_ctr(content_key, sec.upper, start, sec.plain)
    runs: list[tuple[int, int]] = []  # (sanal başlangıç, kaynak: 0 dosyada, 1 sıfır)
    for off in range(0, len(sec.plain), block):
        src = 0 if sec.plain[off : off + block] == virt_new[off : off + block] else 1
        if not runs or runs[-1][1] != src:
            runs.append((off, src))
    phys = bytearray()
    entries = []
    for i, (v, src) in enumerate(runs):
        end = runs[i + 1][0] if i + 1 < len(runs) else len(sec.plain)
        if src == 0:
            entries.append(struct.pack("<qqi", v, len(phys), 0))
            phys += enc[v:end]
        else:
            entries.append(struct.pack("<qqi", v, 0x7777000, 1))  # sıfır kaynağında ofset anlamsız
    phys += b"\0" * (align(len(phys), 0x10) - len(phys))
    table = _bucket_tree(entries, 0x14, len(sec.plain))
    gen = 7
    table_upper = sec.secure_value.to_bytes(4, "big") + (gen << 16).to_bytes(4, "big")
    raw = bytes(phys) + aes_ctr(content_key, table_upper, start + len(phys), table)
    raw += b"\0" * (align(len(raw), 0x200) - len(raw))
    sec.raw_override = raw
    sec.header_size = len(sec.plain)
    sec.sparse_info = struct.pack("<QQ4sIiI", len(phys), len(table), b"BKTR", 1, len(entries), 0) + struct.pack(
        "<QH6x", start, gen
    )
    built = build_nca(keys, 0, program_id, [sec], key_generation=2)
    return _rekey(keys, built, content_key, 1)


def _rekey(keys: TestKeys, built: BuiltNca, content_key: bytes, gen_index: int) -> BuiltNca:
    from nxceviri.core.container.crypto import aes_xts_decrypt

    header = bytearray(aes_xts_decrypt(keys.header_key, built.data[:0xC00]))
    header[0x300:0x340] = aes_ecb_encrypt(keys.key_area[gen_index], bytes(0x20) + content_key + bytes(0x10))
    data = aes_xts_encrypt(keys.header_key, bytes(header)) + built.data[0xC00:]
    return BuiltNca(data, content_key, built.sections, built.rights_id, None)


# --- meta veriler ve paket ------------------------------------------------------------------


def build_cnmt(
    title_id: int, version: int, meta_type: int, application_id: int, contents: list[tuple[str, int, int]]
) -> bytes:
    ext = struct.pack("<QI4x", application_id, 0) if meta_type in (0x80, 0x81, 0x82) else b""
    out = bytearray(struct.pack("<QIBB", title_id, version, meta_type, 0))
    out += b"\0" * (0x0E - len(out))
    out += struct.pack("<HHH", len(ext), len(contents), 0)
    out += b"\0" * (0x20 - len(out))
    out += ext
    for cid, size, ctype in contents:
        out += os.urandom(0x20) + bytes.fromhex(cid) + size.to_bytes(6, "little") + bytes([ctype, 0])
    out += os.urandom(0x20)  # özet
    return bytes(out)


def build_nacp(name: str, display_version: str, publisher: str = "Test Yayıncı") -> bytes:
    nacp = bytearray(0x4000)
    enc = name.encode()
    nacp[0 : len(enc)] = enc
    pub = publisher.encode()
    nacp[0x200 : 0x200 + len(pub)] = pub
    dv = display_version.encode()
    nacp[0x3060 : 0x3060 + len(dv)] = dv
    return bytes(nacp)


def build_ticket(rights_id: bytes, enc_title_key: bytes) -> bytes:
    tik = bytearray(0x2C0)
    struct.pack_into("<I", tik, 0, 0x010004)
    tik[0x180:0x190] = enc_title_key
    tik[0x281] = 0  # common
    tik[0x2A0:0x2B0] = rights_id
    return bytes(tik)


@dataclass
class BuiltPackage:
    nsp: bytes
    program: BuiltNca | None
    files: list[tuple[str, bytes]]


def build_package(
    keys: TestKeys,
    *,
    kind: str,
    title_id: int,
    application_id: int,
    version: int,
    name: str = "Deneme Oyunu",
    display_version: str = "1.0.0",
    romfs_files: dict[str, bytes] | None = None,
    program: BuiltNca | None = None,
    use_rights_id: bool = True,
) -> BuiltPackage:
    """Bir NSP üretir. `program` verilmezse `romfs_files`'tan bir Program/Data NCA kurulur."""
    meta_type = {"base": 0x80, "update": 0x81, "dlc": 0x82}[kind]
    files: list[tuple[str, bytes]] = []
    contents: list[tuple[str, int, int]] = []
    tickets: list[tuple[str, bytes]] = []

    if program is None and romfs_files is not None:
        ctype = 4 if kind == "dlc" else 0
        exefs = pfs0_section(build_pfs0([("main", b"\x00" * 64)]))
        sections = (
            [romfs_section(build_romfs(romfs_files))]
            if kind == "dlc"
            else [exefs, romfs_section(build_romfs(romfs_files))]
        )
        program = build_nca(keys, ctype, application_id, sections, use_rights_id=use_rights_id)
    if program is not None:
        files.append((program.content_id + ".nca", program.data))
        contents.append((program.content_id, len(program.data), 2 if kind == "dlc" else 1))
        if program.enc_title_key is not None:
            tickets.append((program.rights_id.hex() + ".tik", build_ticket(program.rights_id, program.enc_title_key)))

    if kind != "dlc":
        control = build_nca(
            keys, 2, application_id, [romfs_section(build_romfs({"control.nacp": build_nacp(name, display_version)}))]
        )
        files.append((control.content_id + ".nca", control.data))
        contents.append((control.content_id, len(control.data), 3))

    cnmt_name = {"base": "Application", "update": "Patch", "dlc": "AddOnContent"}[kind]
    cnmt = build_cnmt(title_id, version, meta_type, application_id, contents)
    meta = build_nca(keys, 1, title_id, [pfs0_section(build_pfs0([(f"{cnmt_name}_{title_id:016x}.cnmt", cnmt)]))])
    files.insert(0, (meta.content_id + ".cnmt.nca", meta.data))
    files.extend(tickets)
    return BuiltPackage(build_pfs0(files), program, files)


# --- NSZ ---------------------------------------------------------------------------------


def nca_to_ncz(
    built: BuiltNca, block_mode: bool = True, block_exp: int = 14, section_chunk: int | None = None
) -> bytes:
    """NCA'yı nsz'nin yaptığı gibi NCZ'ye çevirir (bölümleri çöz, sıkıştır).

    `section_chunk` verilirse her şifreli bölüm bu boyutta parçalara bölünüp ayrı NCZ
    bölümleri olarak yazılır (gerçek NCZ'lerde binlerce bölüm olabilir).
    """
    data = built.data
    plain = bytearray(data[0x4000:])
    sections = []
    for start, s in built.sections:
        raw_len = len(s.raw_override) if s.raw_override is not None else len(s.plain)
        if s.encryption in (3, 4):
            seg = data[start : start + raw_len]
            plain[start - 0x4000 : start - 0x4000 + raw_len] = aes_ctr(built.content_key, s.upper, start, seg)
            step = section_chunk or raw_len
            for off in range(start, start + raw_len, step):
                n = min(step, start + raw_len - off)
                sections.append(struct.pack("<QQQQ", off, n, 3, 0) + built.content_key + s.upper + b"\0" * 8)
        else:
            sections.append(struct.pack("<QQQQ", start, raw_len, 1, 0) + b"\0" * 32)
    out = bytearray(data[:0x4000])
    out += b"NCZSECTN" + struct.pack("<Q", len(sections)) + b"".join(sections)
    cctx = zstandard.ZstdCompressor(level=3)
    if not block_mode:
        out += cctx.compress(bytes(plain))
        return bytes(out)
    bs = 1 << block_exp
    blocks = [bytes(plain[i : i + bs]) for i in range(0, len(plain), bs)]
    comp = []
    for b in blocks:
        c = cctx.compress(b)
        comp.append(c if len(c) < len(b) else b)
    out += b"NCZBLOCK" + struct.pack("<BBBBIQ", 2, 1, 0, block_exp, len(blocks), len(plain))
    out += struct.pack(f"<{len(comp)}I", *(len(c) for c in comp))
    for c in comp:
        out += c
    return bytes(out)


def nsp_to_nsz(pkg: BuiltPackage, block_mode: bool = True) -> bytes:
    files = []
    for name, data in pkg.files:
        if pkg.program is not None and name == pkg.program.content_id + ".nca":
            files.append((pkg.program.content_id + ".ncz", nca_to_ncz(pkg.program, block_mode)))
        else:
            files.append((name, data))
    return build_pfs0(files)


# --- MSBT --------------------------------------------------------------------------------

MsbtSegment = str | tuple[str, int, int, bytes]


def _lbl_hash(label: str, buckets: int) -> int:
    h = 0
    for b in label.encode():
        h = (h * 0x492 + b) & 0xFFFFFFFF
    return h % buckets


def build_msbt(
    texts: list[tuple[str, list[MsbtSegment]]],
    *,
    encoding: int = 1,
    endian: str = "<",
    labels: bool = True,
    extra_sections: bool = True,
    pad_last: bool = True,
    tail: bytes = b"",
) -> bytes:
    """Elle MSBT üretir. Segment: düz metin veya ("tag", grup, tür, parametreler) /
    ("end", grup, tür, b"")."""
    e = endian
    width = 1 if encoding == 0 else 2
    codec = "utf-8" if encoding == 0 else ("utf-16-le" if e == "<" else "utf-16-be")

    def unit(v: int) -> bytes:
        return bytes([v]) if width == 1 else struct.pack(e + "H", v)

    blobs = []
    for _label, segs in texts:
        b = bytearray()
        for seg in segs:
            if isinstance(seg, str):
                b += seg.encode(codec)
            elif seg[0] == "tag":
                b += unit(0x0E) + struct.pack(e + "HHH", seg[1], seg[2], len(seg[3])) + seg[3]
            else:
                b += unit(0x0F) + struct.pack(e + "HH", seg[1], seg[2])
        b += unit(0) + tail
        blobs.append(bytes(b))
    n = len(blobs)
    offs = []
    pos = 4 + 4 * n
    for blob in blobs:
        offs.append(pos)
        pos += len(blob)
    txt2 = struct.pack(f"{e}I{n}I", n, *offs) + b"".join(blobs)

    sections: list[tuple[bytes, bytes]] = []
    if labels:
        nb = 7
        groups: dict[int, list[tuple[str, int]]] = {i: [] for i in range(nb)}
        for i, (label, _segs) in enumerate(texts):
            groups[_lbl_hash(label, nb)].append((label, i))
        table = bytearray(struct.pack(e + "I", nb))
        body = bytearray()
        base = 4 + nb * 8
        for i in range(nb):
            table += struct.pack(e + "II", len(groups[i]), base + len(body))
            for label, idx in groups[i]:
                lb = label.encode()
                body += bytes([len(lb)]) + lb + struct.pack(e + "I", idx)
        sections.append((b"LBL1", bytes(table + body)))
    if extra_sections:
        sections.append(
            (b"ATR1", struct.pack(e + "II", n, 4) + b"".join(struct.pack(e + "I", i * 3) for i in range(n)))
        )
    sections.append((b"TXT2", txt2))
    if extra_sections:
        sections.append((b"TSY1", b"".join(struct.pack(e + "I", 0) for _ in range(n))))

    out = bytearray(b"MsgStdBn" + struct.pack(e + "HHBBHH", 0xFEFF, 0, encoding, 3, len(sections), 0))
    out += b"\0" * (0x20 - len(out))
    for i, (magic, data) in enumerate(sections):
        out += magic + struct.pack(e + "I", len(data)) + b"\0" * 8 + data
        if pad_last or i + 1 < len(sections):
            out += b"\xab" * ((-len(data)) % 16)
    struct.pack_into(e + "I", out, 0x12, len(out))
    return bytes(out)


# --- SARC / Yaz0 ---------------------------------------------------------------------------


def yaz0_literal(data: bytes) -> bytes:
    """Yalnızca düz baytlardan oluşan (geri başvurusuz) geçerli Yaz0 verisi."""
    out = bytearray(b"Yaz0" + struct.pack(">I", len(data)) + b"\0" * 8)
    for i in range(0, len(data), 8):
        group = data[i : i + 8]
        out.append((0xFF << (8 - len(group))) & 0xFF)
        out += group
    return bytes(out)


def build_sarc(files: dict[str, bytes], big_endian: bool = False) -> bytes:
    e = ">" if big_endian else "<"
    names = bytearray()
    nodes = []
    data = bytearray()
    for name in sorted(files):
        name_off = len(names) // 4
        names += name.encode() + b"\0"
        names += b"\0" * (-len(names) % 4)
        start = len(data)
        data += files[name]
        nodes.append(struct.pack(e + "IIII", 0, 0x01000000 | name_off, start, len(data)))
        data += b"\0" * (-len(data) % 8)
    sfat = b"SFAT" + struct.pack(e + "HHI", 0xC, len(nodes), 0x65) + b"".join(nodes)
    sfnt = b"SFNT" + struct.pack(e + "HH", 8, 0) + bytes(names)
    data_offset = 0x14 + len(sfat) + len(sfnt)
    data_offset += -data_offset % 8
    head = b"SARC" + struct.pack(e + "HHIIHH", 0x14, 0xFEFF, data_offset + len(data), data_offset, 0x100, 0)
    body = head + sfat + sfnt
    return body + b"\0" * (data_offset - len(body)) + bytes(data)
