"""Taşınan oyun dosyalarının yeniden bağlanması (çekirdek, Qt'siz). Yalnızca elle üretilmiş küçük dosyalar."""

from __future__ import annotations

from pathlib import Path

from nxceviri.core.project import SourceRecord
from nxceviri.core.project.relink import apply_moved, find_moved


def _record(path: Path, size: int) -> SourceRecord:
    return SourceRecord(path, "base", "0100ABCD12340000", "0100ABCD12340000", 0, "1.0", "Deneme", size)


def _file(folder: Path, name: str, size: int) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(b"x" * size)
    return path


def test_same_name_and_size_is_found(tmp_path: Path) -> None:
    new = _file(tmp_path / "yeni", "oyun.nsp", 12)
    sources = [_record(tmp_path / "eski" / "oyun.nsp", 12)]
    assert find_moved(sources, [tmp_path / "yeni"]) == {0: new}


def test_one_sub_level_is_searched(tmp_path: Path) -> None:
    new = _file(tmp_path / "kök" / "alt", "oyun.nsz", 7)
    assert find_moved([_record(tmp_path / "eski" / "oyun.nsz", 7)], [tmp_path / "kök"]) == {0: new}


def test_different_size_is_never_matched(tmp_path: Path) -> None:
    _file(tmp_path / "yeni", "oyun.nsp", 13)
    assert find_moved([_record(tmp_path / "eski" / "oyun.nsp", 12)], [tmp_path / "yeni"]) == {}


def test_unknown_size_accepts_only_a_single_candidate(tmp_path: Path) -> None:
    one = _file(tmp_path / "a", "oyun.nsp", 5)
    sources = [_record(tmp_path / "eski" / "oyun.nsp", 0)]
    assert find_moved(sources, [tmp_path / "a"]) == {0: one}
    _file(tmp_path / "b", "oyun.nsp", 9)
    assert find_moved(sources, [tmp_path / "a", tmp_path / "b"]) == {}


def test_existing_files_are_untouched_and_missing_folder_is_ignored(tmp_path: Path) -> None:
    here = _file(tmp_path / "burada", "a.nsp", 4)
    _file(tmp_path / "yeni", "a.nsp", 4)
    assert find_moved([_record(here, 4)], [tmp_path / "yeni", tmp_path / "yok"]) == {}


def test_apply_moved_changes_only_paths(tmp_path: Path) -> None:
    old = _record(tmp_path / "eski" / "a.nsp", 4)
    other = _record(tmp_path / "b.nsp", 3)
    new = tmp_path / "yeni" / "a.nsp"
    out = apply_moved([old, other], {0: new})
    assert out[0] == _record(new, 4)
    assert out[1] is other
