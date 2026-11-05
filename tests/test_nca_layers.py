"""NCA'nın ek katmanları: sıkıştırma (LZ4), seyrek (sparse) bölümler ve çok bölümlü NCZ."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from nxceviri.core.container.compression import CompressedStorage, CompressionEntry
from nxceviri.core.container.nca import FsType, Nca
from nxceviri.core.container.ncz import _parse_sections
from nxceviri.core.container.package import open_package
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.container.view import build_game_view
from nxceviri.core.errors import ContainerError
from nxceviri.core.keys import KeySet, load_keys
from tests import nxbuild
from tests.conftest import BASE_FILES, BASE_TID, UPDATE_FILES, UPDATE_TID, GameFiles

# Sıkışabilen, birkaç bloğa yayılan bir dosya: LZ4 blokları gerçekten oluşur.
BIG_FILES = {**BASE_FILES, "Data/uzun_metin.txt": ("Merhaba dünya, çğıİöşü. " * 600).encode()}


@pytest.fixture
def keys(game: GameFiles) -> KeySet:
    return load_keys(game.keys_path)


def _files(view_tree: object) -> dict[str, bytes]:
    tree = view_tree.view  # type: ignore[attr-defined]
    return {p: tree.open(p).read_all() for p in tree.files}


def test_compressed_romfs_section_reads_all_files(game: GameFiles, keys: KeySet) -> None:
    section = nxbuild.compressed_romfs_section(nxbuild.build_romfs(BIG_FILES))
    built = nxbuild.build_nca(game.keys, 0, BASE_TID, [section])
    nca = Nca(MemoryStorage(built.data), keys)
    fs = nca.find_section(FsType.ROMFS)
    assert fs is not None
    assert fs.compression.present
    data = nca.data_storage(fs)
    assert isinstance(data, CompressedStorage)
    kinds = {e.kind for e in data._entries}
    assert kinds == {0, 1, 3}  # ham, sıfır ve LZ4 blokları hepsi sınanıyor
    from nxceviri.core.container.romfs import RomFs

    romfs = RomFs(data)
    assert {p: romfs.open(p).read_all() for p in romfs.files} == BIG_FILES


def test_compressed_base_in_package(game: GameFiles, keys: KeySet, tmp_path: Path) -> None:
    program = nxbuild.build_nca(
        game.keys, 0, BASE_TID, [nxbuild.compressed_romfs_section(nxbuild.build_romfs(BIG_FILES))]
    )
    pkg = nxbuild.build_package(
        game.keys, kind="base", title_id=BASE_TID, application_id=BASE_TID, version=0, program=program
    )
    path = tmp_path / "sıkıştırılmış.nsp"
    path.write_bytes(pkg.nsp)
    with open_package(path, keys) as p:
        view = build_game_view([p])
        assert _files(view.trees[0]) == BIG_FILES


def _compressed(virtual: bytes, block: int, physical: bytes, entries: list[CompressionEntry]) -> CompressedStorage:
    return CompressedStorage(MemoryStorage(physical), entries, len(virtual))


def test_compressed_storage_unaligned_reads_and_span() -> None:
    import lz4.block

    a, b, c = b"A" * 0x100, bytes(0x100), bytes(range(256)) * 1
    packed = lz4.block.compress(c, store_size=False)
    physical = a + packed
    entries = [
        CompressionEntry(0, 0, 0, nxbuild.NONE32),
        CompressionEntry(0x100, 0, 1, 0),
        CompressionEntry(0x200, 0x100, 3, len(packed)),
    ]
    store = _compressed(a + b + c, 0x100, physical, entries)
    assert store.read_all() == a + b + c
    assert store.read(0xF0, 0x120) == (a + b + c)[0xF0:0x210]
    assert store.physical_span(0x10, 0x20) == (0x10, 0x20)  # ham blok: birebir
    assert store.physical_span(0x250, 4) == (0x100, len(packed))  # LZ4: bloğun tamamı
    assert store.physical_span(0x120, 4) == (0, 0)  # yalnızca sıfır blok: fiziksel karşılık yok


def test_compressed_storage_rejects_bad_tables() -> None:
    with pytest.raises(ContainerError, match="sıfırdan"):
        CompressedStorage(MemoryStorage(b"x" * 16), [CompressionEntry(4, 0, 0, 0)], 16)
    with pytest.raises(ContainerError, match="dışına"):
        CompressedStorage(MemoryStorage(b"x" * 16), [CompressionEntry(0, 0, 3, 64)], 32)
    from nxceviri.core.errors import UnsupportedFormatError

    with pytest.raises(UnsupportedFormatError):
        CompressedStorage(MemoryStorage(b"x" * 16), [CompressionEntry(0, 0, 2, 4)], 16)
    store = CompressedStorage(MemoryStorage(b"\xff" * 16), [CompressionEntry(0, 0, 3, 16)], 64)
    with pytest.raises(ContainerError, match="açılamadı"):
        store.read(0, 4)


@pytest.fixture
def sparse_game(game: GameFiles, tmp_path: Path) -> tuple[Path, Path]:
    base_romfs = nxbuild.build_romfs(BASE_FILES)
    new_romfs = nxbuild.build_romfs(UPDATE_FILES)
    program = nxbuild.build_sparse_base_nca(game.keys, BASE_TID, base_romfs, new_romfs)
    base = nxbuild.build_package(
        game.keys, kind="base", title_id=BASE_TID, application_id=BASE_TID, version=0, program=program
    )
    patch = nxbuild.build_patch_nca(game.keys, BASE_TID, program, new_romfs)
    update = nxbuild.build_package(
        game.keys,
        kind="update",
        title_id=UPDATE_TID,
        application_id=BASE_TID,
        version=65536,
        program=patch,
    )
    base_path = tmp_path / "seyrek base.nsp"
    update_path = tmp_path / "seyrek update.nsp"
    base_path.write_bytes(base.nsp)
    update_path.write_bytes(update.nsp)
    return base_path, update_path


def test_sparse_base_with_update(sparse_game: tuple[Path, Path], keys: KeySet) -> None:
    base_path, update_path = sparse_game
    # Güncellemenin değiştirdiği bloklar base dosyada yok; birleşik görünüm yine tam olmalı.
    with open_package(base_path, keys) as base, open_package(update_path, keys) as update:
        program = base.program_nca()
        assert program is not None
        fs = program.find_section(FsType.ROMFS)
        assert fs is not None
        assert fs.is_sparse
        view = build_game_view([base, update])
        assert _files(view.trees[0]) == UPDATE_FILES


def test_sparse_base_alone_asks_for_update(sparse_game: tuple[Path, Path], keys: KeySet) -> None:
    base_path, _ = sparse_game
    with open_package(base_path, keys) as base, pytest.raises(ContainerError, match="güncelleme"):
        build_game_view([base])


def test_ncz_with_many_sections(game: GameFiles, keys: KeySet, tmp_path: Path) -> None:
    pkg = nxbuild.build_package(
        game.keys, kind="base", title_id=BASE_TID, application_id=BASE_TID, version=0, romfs_files=BASE_FILES
    )
    assert pkg.program is not None
    ncz = nxbuild.nca_to_ncz(pkg.program, section_chunk=0x40)
    sections, _ = _parse_sections(MemoryStorage(ncz))
    assert len(sections) > 64  # eski sabit sınır bu dosyayı reddediyordu
    files = [
        (pkg.program.content_id + ".ncz", ncz) if name == pkg.program.content_id + ".nca" else (name, data)
        for name, data in pkg.files
    ]
    path = tmp_path / "çok bölümlü.nsz"
    path.write_bytes(nxbuild.build_pfs0(files))
    with open_package(path, keys) as p:
        assert _files(build_game_view([p]).trees[0]) == BASE_FILES


def test_ncz_section_count_must_fit_file() -> None:
    head = bytearray(0x4000) + b"NCZSECTN" + struct.pack("<Q", 1000) + bytes(0x40)
    with pytest.raises(ContainerError, match="bölüm sayısı"):
        _parse_sections(MemoryStorage(bytes(head)))
