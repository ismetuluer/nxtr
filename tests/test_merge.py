"""Base + update (+ DLC) birleştirme mantığı."""

from __future__ import annotations

from pathlib import Path

import pytest

from nxceviri.core.container.package import KIND_BASE, KIND_DLC, KIND_UPDATE, open_package
from nxceviri.core.container.romfs import RomFs
from nxceviri.core.container.storage import MemoryStorage
from nxceviri.core.container.view import LayeredRomFs, RomFsLayer, build_game_view
from nxceviri.core.errors import ContainerError
from nxceviri.core.keys import KeySet, load_keys
from tests import nxbuild
from tests.conftest import BASE_TID, DLC_FILES, UPDATE_FILES, GameFiles


@pytest.fixture
def keys(game: GameFiles) -> KeySet:
    return load_keys(game.keys_path)


def _romfs(files: dict[str, bytes]) -> RomFs:
    return RomFs(MemoryStorage(nxbuild.build_romfs(files)))


def test_layered_override_semantics() -> None:
    base = _romfs({"a.txt": b"base-a", "b.txt": b"base-b", "klasör/c.txt": b"base-c"})
    update = _romfs({"b.txt": b"update-b", "yeni.txt": b"update-yeni"})
    view = LayeredRomFs([RomFsLayer(KIND_BASE, base), RomFsLayer(KIND_UPDATE, update)])
    assert view.open("a.txt").read_all() == b"base-a"
    assert view.open("b.txt").read_all() == b"update-b"  # update base'i geçersiz kılar
    assert view.open("yeni.txt").read_all() == b"update-yeni"
    assert view.open("klasör/c.txt").read_all() == b"base-c"
    origins = {p: f.origin for p, f in view.files.items()}
    assert origins == {"a.txt": "base", "b.txt": "update", "klasör/c.txt": "base", "yeni.txt": "update"}
    assert list(view.files) == sorted(view.files)
    with pytest.raises(ContainerError):
        view.open("olmayan.txt")


def test_three_layers_last_wins() -> None:
    layers = [RomFsLayer(o, _romfs({"x": o.encode()})) for o in (KIND_BASE, KIND_UPDATE, KIND_DLC)]
    view = LayeredRomFs(layers)
    assert view.open("x").read_all() == b"dlc"
    assert view.files["x"].origin == KIND_DLC


def test_bktr_update_applies_over_base(game: GameFiles, keys: KeySet) -> None:
    with open_package(game.base_nsp, keys) as base, open_package(game.update_nsp, keys) as upd:
        view = build_game_view([upd, base])  # sıra önemsiz
        assert view.base_version == 0
        assert view.update_version == 65536
        tree = view.trees[0].view
        assert {p: tree.open(p).read_all() for p in tree.files} == UPDATE_FILES


def test_bktr_update_from_nsz(game: GameFiles, keys: KeySet) -> None:
    with open_package(game.base_nsz_block, keys) as base, open_package(game.update_nsz, keys) as upd:
        tree = build_game_view([base, upd]).trees[0].view
        assert {p: tree.open(p).read_all() for p in tree.files} == UPDATE_FILES


def test_bktr_origin_marks_only_changed_files(tmp_path: Path) -> None:
    """Yalnızca içeriği değişen dosya "update", dokunulmayanlar "base" olarak işaretlenir."""
    keys_obj = nxbuild.TestKeys.random()
    keys = load_keys(keys_obj.write(tmp_path / "prod.keys"))
    # Dosyaların veri sırası yola göredir; değişen dosya en sonda ve aynı boyutta kalır,
    # böylece tablolar ve diğer dosyaların blokları birebir aynı olur.
    filler = bytes(range(256)) * 4
    base_files = {"a/ilk.bin": filler, "a/iki.bin": filler[::-1], "z/son.msbt": b"MsgStdBn" + b"\0" * 0x3F8}
    new_files = {**base_files, "z/son.msbt": b"MsgStdBn" + b"\x07" * 0x3F8}
    base = nxbuild.build_package(
        keys_obj, kind="base", title_id=BASE_TID, application_id=BASE_TID, version=0, romfs_files=base_files
    )
    assert base.program is not None
    patch = nxbuild.build_patch_nca(keys_obj, BASE_TID, base.program, nxbuild.build_romfs(new_files), block=0x10)
    upd = nxbuild.build_package(
        keys_obj, kind="update", title_id=BASE_TID | 0x800, application_id=BASE_TID, version=1 << 16, program=patch
    )
    (tmp_path / "b.nsp").write_bytes(base.nsp)
    (tmp_path / "u.nsp").write_bytes(upd.nsp)
    with open_package(tmp_path / "b.nsp", keys) as b, open_package(tmp_path / "u.nsp", keys) as u:
        tree = build_game_view([b, u]).trees[0].view
        assert {p: f.origin for p, f in tree.files.items()} == {
            "a/ilk.bin": "base",
            "a/iki.bin": "base",
            "z/son.msbt": "update",
        }
        assert tree.open("z/son.msbt").read_all() == new_files["z/son.msbt"]


def test_update_without_base_is_rejected(game: GameFiles, keys: KeySet) -> None:
    with open_package(game.update_nsp, keys) as upd, pytest.raises(ContainerError, match="tek başına") as exc:
        build_game_view([upd])
    assert "ana oyunu" in exc.value.hint


def test_update_of_other_game_is_rejected(game: GameFiles, keys: KeySet, tmp_path: Path) -> None:
    other_tid = 0x0100FFFF00000000
    other = nxbuild.build_package(
        game.keys,
        kind="update",
        title_id=other_tid | 0x800,
        application_id=other_tid,
        version=1,
        romfs_files={"x": b"1"},
    )
    p = tmp_path / "baska_oyun_update.nsp"
    p.write_bytes(other.nsp)
    with (
        open_package(game.base_nsp, keys) as base,
        open_package(p, keys) as upd,
        pytest.raises(ContainerError, match="bu oyuna ait değil"),
    ):
        build_game_view([base, upd])


def test_two_bases_rejected(game: GameFiles, keys: KeySet) -> None:
    with (
        open_package(game.base_nsp, keys) as a,
        open_package(game.base_nsz_block, keys) as b,
        pytest.raises(ContainerError, match="Birden fazla ana oyun"),
    ):
        build_game_view([a, b])


def test_empty_package_list_rejected() -> None:
    with pytest.raises(ContainerError, match="Hiç oyun"):
        build_game_view([])


def test_newest_update_is_used(game: GameFiles, keys: KeySet) -> None:
    with (
        open_package(game.base_nsp, keys) as base,
        open_package(game.update_nsp, keys) as u1,
        open_package(game.update_nsz, keys) as u2,
    ):
        view = build_game_view([base, u1, u2])
        assert view.update_version == 65536
        assert any("en yenisi" in w for w in view.warnings)


def test_dlc_is_separate_tree(game: GameFiles, keys: KeySet) -> None:
    with open_package(game.base_nsp, keys) as base, open_package(game.dlc_nsp, keys) as dlc:
        view = build_game_view([base, dlc])
        assert [t.label.split()[0] for t in view.trees] == ["Ana", "DLC"]
        dlc_tree = view.trees[1].view
        assert {p: dlc_tree.open(p).read_all() for p in dlc_tree.files} == DLC_FILES
        assert all(f.origin == KIND_DLC for f in dlc_tree.files.values())
