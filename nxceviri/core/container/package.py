"""NSP/NSZ paketini açma: meta veriler, biletler ve içerik NCA'ları.

Bir paket tam olarak bir başlık içerir (ana oyun, güncelleme veya DLC). Kullanıcının
dosyası yalnızca okunur; akış kipindeki NCZ'ler gerekiyorsa önbellek klasörüne açılır.
"""

from __future__ import annotations

import errno
import hashlib
import logging
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from nxceviri.core.container.metadata import (
    Cnmt,
    CnmtContentType,
    ContentRecord,
    MetaType,
    Nacp,
    parse_cnmt,
    parse_nacp,
    parse_ticket,
)
from nxceviri.core.container.nca import FsType, Nca
from nxceviri.core.container.ncz import is_block_mode, iter_ncz_as_nca, open_ncz_random_access, verify_nca_hash
from nxceviri.core.container.pfs0 import Pfs0, PfsEntry
from nxceviri.core.container.romfs import RomFs
from nxceviri.core.container.storage import FileStorage, Storage
from nxceviri.core.errors import ContainerError, NxError
from nxceviri.core.keys import KeySet
from nxceviri.core.progress import TaskContext

log = logging.getLogger(__name__)

KIND_BASE = "base"
KIND_UPDATE = "update"
KIND_DLC = "dlc"

KIND_LABELS = {KIND_BASE: "Ana oyun", KIND_UPDATE: "Güncelleme", KIND_DLC: "DLC"}

_KIND_BY_META = {
    MetaType.APPLICATION: KIND_BASE,
    MetaType.PATCH: KIND_UPDATE,
    MetaType.ADD_ON_CONTENT: KIND_DLC,
}


#: Önbelleğe açma sonrasında diskte bırakılacak en az boş alan.
_DISK_MARGIN = 1024**3


def _no_space(name: str, needed: int, free: int) -> ContainerError:
    gb = 1024**3
    return ContainerError(
        f"Diskte yer yok: {name} önbelleğe açılırken yaklaşık {needed / gb:.1f} GB gerekiyor, {free / gb:.1f} GB boş.",
        "Diskte yer açın veya Dosya → Önbelleği Temizle… ile eski oyunların önbelleğini silin. "
        "Bu dosya akış kipinde sıkıştırıldığı için tamamen açılması gerekir.",
    )


@dataclass
class GamePackage:
    path: Path
    kind: str
    cnmt: Cnmt
    nacp: Nacp | None
    _file: FileStorage
    _pfs: Pfs0
    _keys: KeySet
    _title_keys: dict[bytes, bytes]
    _cache_dir: Path | None
    _ncas: dict[str, Nca] = field(default_factory=dict)
    _extra: list[FileStorage] = field(default_factory=list)

    @property
    def title_id(self) -> str:
        return self.cnmt.title_id_hex

    @property
    def application_id(self) -> str:
        return self.cnmt.application_id_hex

    @property
    def version(self) -> int:
        return self.cnmt.version

    @property
    def display_name(self) -> str:
        return self.nacp.name if self.nacp and self.nacp.name else self.path.stem

    def close(self) -> None:
        for extra in self._extra:
            extra.close()
        self._file.close()

    def __enter__(self) -> GamePackage:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def record(self, content_type: CnmtContentType) -> ContentRecord | None:
        candidates = [c for c in self.cnmt.contents if c.content_type == content_type]
        candidates.sort(key=lambda c: c.id_offset)
        return candidates[0] if candidates else None

    def open_nca(self, record: ContentRecord, ctx: TaskContext | None = None) -> Nca:
        if record.content_id in self._ncas:
            return self._ncas[record.content_id]
        entry = _find_entry(self._pfs, record.content_id)
        if entry is None:
            raise ContainerError(
                f"{self.path.name} eksik: {record.content_id} içeriği pakette yok.",
                "Paket eksik veya bozuk. Dosyayı kendi konsolunuzdan yeniden çıkarın.",
            )
        storage = self._entry_storage(entry, record.size, ctx or TaskContext())
        nca = Nca(storage, self._keys, self._title_keys, entry.name)
        self._ncas[record.content_id] = nca
        return nca

    def _entry_storage(self, entry: PfsEntry, nca_size: int, ctx: TaskContext) -> Storage:
        raw = self._pfs.open(entry)
        if not entry.name.lower().endswith(".ncz"):
            return raw
        if is_block_mode(raw):
            return open_ncz_random_access(raw)
        if self._cache_dir is None:
            raise ContainerError(
                f"{entry.name} akış kipinde sıkıştırılmış ve önbellek klasörü yok.",
                "Bu dosya okunmadan önce önbelleğe açılmalıdır.",
            )
        target = self._cache_dir / (entry.name[:-4] + ".nca")
        if not target.exists():
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            free = shutil.disk_usage(self._cache_dir).free
            if free < nca_size + _DISK_MARGIN:
                raise _no_space(entry.name, nca_size, free)
            tmp = target.with_name(target.name + ".yaziliyor")
            try:
                hasher = hashlib.sha256()
                with open(tmp, "wb") as out:
                    written = 0
                    for chunk in iter_ncz_as_nca(raw, ctx):
                        hasher.update(chunk)
                        out.write(chunk)
                        written += len(chunk)
                        ctx.report(written, 0, f"{entry.name} önbelleğe açılıyor")
                verify_nca_hash(target.name, hasher.digest())
                os.replace(tmp, target)
            except OSError as exc:
                if exc.errno != errno.ENOSPC:
                    raise
                raise _no_space(entry.name, nca_size, shutil.disk_usage(self._cache_dir).free) from None
            finally:
                tmp.unlink(missing_ok=True)
        fs = FileStorage(target)
        self._extra.append(fs)
        return fs

    def program_nca(self, ctx: TaskContext | None = None) -> Nca | None:
        rec = self.record(CnmtContentType.PROGRAM)
        return self.open_nca(rec, ctx) if rec else None

    def data_nca(self, ctx: TaskContext | None = None) -> Nca | None:
        rec = self.record(CnmtContentType.DATA)
        return self.open_nca(rec, ctx) if rec else None


def _find_entry(pfs: Pfs0, content_id: str) -> PfsEntry | None:
    for suffix in (".nca", ".ncz", ".cnmt.nca", ".cnmt.ncz"):
        entry = pfs.find(content_id + suffix)
        if entry is not None:
            return entry
    return None


def open_package(
    path: Path,
    keys: KeySet,
    title_keys: Mapping[bytes, bytes] | None = None,
    cache_dir: Path | None = None,
) -> GamePackage:
    """Paketi açar ve TitleID, sürüm ve (varsa) oyun adını okur."""
    file = FileStorage(path)
    try:
        pfs = Pfs0(file, path.name)
        merged_keys: dict[bytes, bytes] = {}
        for entry in pfs.entries:
            if entry.name.lower().endswith(".tik"):
                ticket = parse_ticket(pfs.open(entry).read_all())
                if not ticket.personalized:
                    merged_keys[ticket.rights_id] = ticket.title_key_block
        for rid, tkey in (title_keys or {}).items():
            merged_keys.setdefault(rid, tkey)

        meta_entry = next((e for e in pfs.entries if e.name.lower().endswith((".cnmt.nca", ".cnmt.ncz"))), None)
        if meta_entry is None:
            raise ContainerError(
                f"{path.name} içinde içerik meta verisi (.cnmt.nca) yok.",
                "Dosya eksik veya bozuk bir NSP/NSZ. Kendi konsolunuzdan yeniden çıkarın.",
            )
        meta_storage = pfs.open(meta_entry)
        if meta_entry.name.lower().endswith(".ncz"):
            meta_storage = open_ncz_random_access(meta_storage)
        meta_nca = Nca(meta_storage, keys, merged_keys, meta_entry.name)
        meta_fs = meta_nca.find_section(FsType.PFS0)
        if meta_fs is None:
            raise ContainerError(f"{meta_entry.name} bozuk: meta bölümü yok.")
        meta_pfs = meta_nca.open_pfs0(meta_fs)
        cnmt_entry = next((e for e in meta_pfs.entries if e.name.endswith(".cnmt")), None)
        if cnmt_entry is None:
            raise ContainerError(f"{meta_entry.name} bozuk: .cnmt dosyası yok.")
        cnmt = parse_cnmt(meta_pfs.open(cnmt_entry).read_all())

        pkg = GamePackage(
            path=path,
            kind=_KIND_BY_META[MetaType(cnmt.meta_type)],
            cnmt=cnmt,
            nacp=None,
            _file=file,
            _pfs=pfs,
            _keys=keys,
            _title_keys=merged_keys,
            _cache_dir=cache_dir,
        )
        control = pkg.record(CnmtContentType.CONTROL)
        if control is not None:
            pkg.nacp = _read_nacp(pkg, control)
        log.info("Paket açıldı: %s (%s, %s, v%d)", path.name, pkg.kind, pkg.title_id, pkg.version)
        return pkg
    except BaseException:
        file.close()
        raise


def _read_nacp(pkg: GamePackage, record: ContentRecord) -> Nacp | None:
    try:
        nca = pkg.open_nca(record)
        fs = nca.find_section(FsType.ROMFS)
        if fs is None:
            return None
        romfs = RomFs(nca.data_storage(fs), nca.name)
        if "control.nacp" not in romfs.files:
            return None
        return parse_nacp(romfs.open("control.nacp").read_all())
    except NxError as exc:
        # Oyun adı yalnızca bilgi amaçlıdır; okunamaması paketi kullanılmaz kılmaz.
        log.warning("Oyun bilgisi okunamadı (%s): %s", pkg.path.name, exc.message)
        return None
