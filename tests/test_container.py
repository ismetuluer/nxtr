"""Konteyner katmanı: PFS0, NCA, NCZ/NSZ, paket meta verileri, RomFS çıkarma."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import pytest

from nxceviri.core.container.ncz import nsz_to_nsp
from nxceviri.core.container.package import KIND_BASE, KIND_DLC, KIND_UPDATE, open_package
from nxceviri.core.container.pfs0 import Pfs0
from nxceviri.core.container.romfs import RomFs
from nxceviri.core.container.storage import FileStorage, MemoryStorage
from nxceviri.core.container.view import build_game_view, extract_tree, safe_relative_path
from nxceviri.core.errors import ContainerError, MissingKeyError, OperationCancelled
from nxceviri.core.keys import KeySet, load_keys
from nxceviri.core.progress import CancelToken, TaskContext
from tests import nxbuild
from tests.conftest import BASE_FILES, BASE_TID, DLC_TID, UPDATE_TID, GameFiles


@pytest.fixture
def keys(game: GameFiles) -> KeySet:
    return load_keys(game.keys_path)


def _digest(path: Path) -> tuple[str, int]:
    return hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns


def test_pfs0_roundtrip_and_corruption() -> None:
    data = nxbuild.build_pfs0([("a.txt", b"merhaba"), ("ğ.bin", b"\x01\x02")])
    pfs = Pfs0(MemoryStorage(data))
    assert [e.name for e in pfs.entries] == ["a.txt", "ğ.bin"]
    assert pfs.open(pfs.entries[0]).read_all() == b"merhaba"
    with pytest.raises(ContainerError, match="PFS0"):
        Pfs0(MemoryStorage(b"XXXX" + data[4:]))
    with pytest.raises(ContainerError, match="eksik"):
        Pfs0(MemoryStorage(data[:-1]))
    with pytest.raises(ContainerError, match="kısa"):
        Pfs0(MemoryStorage(b"PF"))


def test_romfs_roundtrip() -> None:
    files = {"a.txt": b"1", "klasör/b.bin": b"22", "klasör/alt/c": b"333", "z/d": b""}
    romfs = RomFs(MemoryStorage(nxbuild.build_romfs(files)))
    assert {p: romfs.open(p).read_all() for p in romfs.files} == files


def test_romfs_corrupt_header() -> None:
    data = bytearray(nxbuild.build_romfs({"a": b"x"}))
    data[0] = 0x40
    with pytest.raises(ContainerError, match="RomFS"):
        RomFs(MemoryStorage(bytes(data)))
    with pytest.raises(ContainerError):
        RomFs(MemoryStorage(b"\0" * 10))


def test_package_metadata(game: GameFiles, keys: KeySet) -> None:
    with open_package(game.base_nsp, keys) as base:
        assert base.kind == KIND_BASE
        assert base.title_id == f"{BASE_TID:016X}"
        assert base.version == 0
        assert base.nacp is not None
        assert base.nacp.name == "Deneme Oyunu"
        assert base.nacp.display_version == "1.0.0"
    with open_package(game.update_nsp, keys) as upd:
        assert upd.kind == KIND_UPDATE
        assert upd.title_id == f"{UPDATE_TID:016X}"
        assert upd.application_id == f"{BASE_TID:016X}"
        assert upd.version == 65536
        assert upd.nacp is not None
        assert upd.nacp.display_version == "1.0.1"
    with open_package(game.dlc_nsp, keys) as dlc:
        assert dlc.kind == KIND_DLC
        assert dlc.title_id == f"{DLC_TID:016X}"
        assert dlc.application_id == f"{BASE_TID:016X}"


def test_nsz_block_and_stream_give_same_files(game: GameFiles, keys: KeySet, tmp_path: Path) -> None:
    for nsz in (game.base_nsz_block, game.base_nsz_stream):
        with open_package(nsz, keys, cache_dir=tmp_path / "önbellek") as pkg:
            view = build_game_view([pkg])
            tree = view.trees[0].view
            assert {p: tree.open(p).read_all() for p in tree.files} == BASE_FILES


def test_stream_nsz_requires_cache(game: GameFiles, keys: KeySet) -> None:
    with open_package(game.base_nsz_stream, keys) as pkg, pytest.raises(ContainerError, match="önbellek"):
        pkg.program_nca()


def test_nsz_to_nsp_is_byte_identical(game: GameFiles, tmp_path: Path) -> None:
    before = {p: _digest(p) for p in (game.base_nsz_block, game.base_nsz_stream)}
    original = Pfs0(MemoryStorage(game.base_nsp.read_bytes()))
    originals = {e.name: original.open(e).read_all() for e in original.entries}
    for nsz in (game.base_nsz_block, game.base_nsz_stream):
        out = tmp_path / f"çıktı {nsz.stem}.nsp"
        progress: list[tuple[int, int]] = []

        def record(done: int, total: int, _msg: str, sink: list[tuple[int, int]] = progress) -> None:
            sink.append((done, total))

        nsz_to_nsp(nsz, out, TaskContext(record))
        converted = Pfs0(MemoryStorage(out.read_bytes()))
        assert {e.name: converted.open(e).read_all() for e in converted.entries} == originals
        assert progress
        assert progress[-1][0] == progress[-1][1]
        assert not list(tmp_path.glob("*.yaziliyor"))
        assert not list(tmp_path.glob("*.gecici"))
    # Kullanıcının dosyalarına asla yazılmaz.
    assert {p: _digest(p) for p in before} == before


def test_nsz_to_nsp_cancel_leaves_nothing(game: GameFiles, tmp_path: Path) -> None:
    token = CancelToken()

    def progress(done: int, total: int, _msg: str) -> None:
        if done > 0:
            token.cancel()

    out = tmp_path / "iptal.nsp"
    with pytest.raises(OperationCancelled):
        nsz_to_nsp(game.base_nsz_block, out, TaskContext(progress, token))
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []


def test_corrupt_ncz_block_detected(game: GameFiles, keys: KeySet, tmp_path: Path) -> None:
    data = bytearray(game.base_nsz_block.read_bytes())
    pfs = Pfs0(MemoryStorage(bytes(data)))
    ncz = next(e for e in pfs.entries if e.name.endswith(".ncz"))
    # Son sıkıştırılmış bloğun ortasını boz.
    pos = ncz.offset + ncz.size - 40
    data[pos : pos + 8] = b"\xff" * 8
    bad = tmp_path / "bozuk.nsz"
    bad.write_bytes(bytes(data))
    with pytest.raises(ContainerError):
        nsz_to_nsp(bad, tmp_path / "bozuk.nsp")
    assert not (tmp_path / "bozuk.nsp").exists()


def test_truncated_package(game: GameFiles, keys: KeySet, tmp_path: Path) -> None:
    data = game.base_nsp.read_bytes()
    short = tmp_path / "eksik.nsp"
    short.write_bytes(data[: len(data) // 2])
    with pytest.raises(ContainerError, match="eksik"):
        open_package(short, keys)


def test_not_a_package(keys: KeySet, tmp_path: Path) -> None:
    p = tmp_path / "oyun.nsp"
    p.write_bytes("bu bir oyun dosyası değil".encode() * 10)
    with pytest.raises(ContainerError, match="NSP/NSZ"):
        open_package(p, keys)


def test_nca_size_mismatch(game: GameFiles, keys: KeySet) -> None:
    from nxceviri.core.container.nca import Nca

    pfs = Pfs0(MemoryStorage(game.base_nsp.read_bytes()))
    entry = next(e for e in pfs.entries if e.name.endswith(".cnmt.nca"))
    data = pfs.open(entry).read_all()
    with pytest.raises(ContainerError, match="uyuşmuyor"):
        Nca(MemoryStorage(data + b"\0" * 0x200), keys)


def test_fs_header_hash_mismatch(game: GameFiles, keys: KeySet) -> None:
    from nxceviri.core.container.crypto import aes_xts_decrypt, aes_xts_encrypt
    from nxceviri.core.container.nca import Nca

    pfs = Pfs0(MemoryStorage(game.base_nsp.read_bytes()))
    entry = next(e for e in pfs.entries if e.name.endswith(".cnmt.nca"))
    data = bytearray(pfs.open(entry).read_all())
    header = bytearray(aes_xts_decrypt(game.keys.header_key, bytes(data[:0xC00])))
    header[0x400 + 0x150] ^= 0xFF
    data[:0xC00] = aes_xts_encrypt(game.keys.header_key, bytes(header))
    with pytest.raises(ContainerError, match="özeti"):
        Nca(MemoryStorage(bytes(data)), keys)


def test_missing_title_key(game: GameFiles, keys: KeySet, tmp_path: Path) -> None:
    pfs = Pfs0(MemoryStorage(game.base_nsp.read_bytes()))
    files = [(e.name, pfs.open(e).read_all()) for e in pfs.entries if not e.name.endswith(".tik")]
    p = tmp_path / "biletsiz.nsp"
    p.write_bytes(nxbuild.build_pfs0(files))
    with open_package(p, keys) as pkg, pytest.raises(MissingKeyError) as exc:
        build_game_view([pkg])
    assert "title.keys" in exc.value.hint


def test_title_keys_file_replaces_missing_ticket(game: GameFiles, keys: KeySet, tmp_path: Path) -> None:
    pfs = Pfs0(MemoryStorage(game.base_nsp.read_bytes()))
    tik = next(e for e in pfs.entries if e.name.endswith(".tik"))
    tik_data = pfs.open(tik).read_all()
    files = [(e.name, pfs.open(e).read_all()) for e in pfs.entries if e is not tik]
    p = tmp_path / "biletsiz.nsp"
    p.write_bytes(nxbuild.build_pfs0(files))
    title_keys = {tik_data[0x2A0:0x2B0]: tik_data[0x180:0x190]}
    with open_package(p, keys, title_keys) as pkg:
        assert build_game_view([pkg]).file_count == len(BASE_FILES)


def test_extract_tree_turkish_destination(game: GameFiles, keys: KeySet, tmp_path: Path) -> None:
    before = _digest(game.base_nsp)
    with open_package(game.base_nsp, keys) as pkg:
        tree = build_game_view([pkg]).trees[0]
        dest = tmp_path / "Çıkarılan RomFS ğüşİ"
        n = extract_tree(tree, dest)
    assert n == len(BASE_FILES)
    for path, data in BASE_FILES.items():
        assert (dest / path).read_bytes() == data
    assert _digest(game.base_nsp) == before


def test_extract_tree_refuses_non_empty_and_cancels_cleanly(game: GameFiles, keys: KeySet, tmp_path: Path) -> None:
    with open_package(game.base_nsp, keys) as pkg:
        tree = build_game_view([pkg]).trees[0]
        full = tmp_path / "dolu"
        full.mkdir()
        (full / "x").write_text("var olan", encoding="utf-8")
        with pytest.raises(ContainerError, match="boş değil"):
            extract_tree(tree, full)
        assert (full / "x").read_text(encoding="utf-8") == "var olan"

        token = CancelToken()
        dest = tmp_path / "iptal"
        with pytest.raises(OperationCancelled):
            extract_tree(tree, dest, TaskContext(lambda *_: token.cancel(), token))
        assert not dest.exists()
        assert [p.name for p in tmp_path.iterdir()] == ["dolu"]


@pytest.mark.parametrize("bad", ["../kaçış", "a/../../b", "C:/x", "a\\b", "con?", "ad.", ""])
def test_safe_relative_path_rejects(bad: str) -> None:
    with pytest.raises(ContainerError):
        safe_relative_path(bad)


def test_file_storage_is_read_only(game: GameFiles) -> None:
    with FileStorage(game.base_nsp) as fs:
        assert fs._fh.mode == "rb"
        assert fs.read(0, 4) == b"PFS0"
        with pytest.raises(ContainerError):
            fs.read(fs.size - 2, 4)


def test_bucket_tree_invalid_magic(game: GameFiles, keys: KeySet) -> None:
    from nxceviri.core.container.buckettree import read_bucket_tree
    from nxceviri.core.container.nca import BucketTreeHeader

    header = BucketTreeHeader.parse(struct.pack("<QQ4sIiI", 0, 0x4000, b"XXXX", 1, 1, 0))
    with pytest.raises(ContainerError, match="BKTR"):
        read_bucket_tree(MemoryStorage(b"\0" * 0x8000), header, 0x14)
