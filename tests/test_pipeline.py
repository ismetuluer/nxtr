"""Arayüzün kullandığı iş akışı adımları."""

from __future__ import annotations

from pathlib import Path

import pytest

from nxceviri.core.errors import ContainerError, OperationCancelled
from nxceviri.core.keys import load_keys
from nxceviri.core.pipeline import (
    Inputs,
    check_sources,
    clear_cache,
    dir_size,
    extract_sources,
    read_source,
    scan_sources,
)
from nxceviri.core.progress import CancelToken, TaskContext
from nxceviri.core.project import SourceRecord
from tests.conftest import BASE_TID, UPDATE_FILES, GameFiles


def _rec(path: Path, kind: str, app: str = "A") -> SourceRecord:
    return SourceRecord(path, kind, app, app, 0, "", "", 0)


def test_read_source(game: GameFiles) -> None:
    keys = load_keys(game.keys_path)
    rec = read_source(game.update_nsz, keys)
    assert (rec.kind, rec.title_id, rec.version, rec.display_version) == (
        "update",
        f"{BASE_TID | 0x800:016X}",
        65536,
        "1.0.1",
    )
    assert rec.file_size == game.update_nsz.stat().st_size
    with pytest.raises(ContainerError, match="Desteklenmeyen"):
        read_source(game.keys_path, keys)


def test_check_sources(tmp_path: Path) -> None:
    f = tmp_path / "a.nsp"
    f.write_bytes(b"x")
    assert check_sources([]) == ["Henüz oyun dosyası eklenmedi."]
    assert check_sources([_rec(f, "base")]) == []
    assert any("ana oyunu" in p for p in check_sources([_rec(f, "update")]))
    assert any("Birden fazla" in p for p in check_sources([_rec(f, "base"), _rec(f, "base")]))
    assert any("farklı oyunlara" in p for p in check_sources([_rec(f, "base"), _rec(f, "dlc", "B")]))
    assert any("bulunamıyor" in p for p in check_sources([_rec(tmp_path / "yok.nsp", "base")]))


def test_scan_and_extract(game: GameFiles, tmp_path: Path) -> None:
    keys = load_keys(game.keys_path)
    inputs = Inputs((game.base_nsz_stream, game.update_nsp), keys, cache_dir=tmp_path / "proje_onbellek")
    report = scan_sources(inputs, TaskContext())
    assert {e.path.split(">")[0] for e in report.entries} == set(UPDATE_FILES)
    assert dir_size(tmp_path / "proje_onbellek") > 0  # akış kipindeki NCZ önbelleğe açıldı

    only = {e.path for e in report.text_candidates}
    outer = {p.split(">")[0] for p in only}
    n = extract_sources(inputs, tmp_path / "çıktı", only, TaskContext())
    assert n == len(outer)
    out = tmp_path / "çıktı" / f"{BASE_TID:016X}"
    for path in outer:
        assert (out / path).read_bytes() == UPDATE_FILES[path]

    clear_cache(tmp_path / "proje_onbellek")
    assert not (tmp_path / "proje_onbellek").exists()


def test_scan_cancelled(game: GameFiles) -> None:
    token = CancelToken()
    token.cancel()
    inputs = Inputs((game.base_nsp,), load_keys(game.keys_path))
    with pytest.raises(OperationCancelled):
        scan_sources(inputs, TaskContext(token=token))


def test_clear_cache_refuses_other_folders(tmp_path: Path) -> None:
    other = tmp_path / "belgelerim"
    other.mkdir()
    with pytest.raises(ContainerError):
        clear_cache(other)
    assert other.exists()
    clear_cache(tmp_path / "olmayan_onbellek")  # yoksa sessizce hiçbir şey yapmaz
    assert dir_size(tmp_path / "olmayan") == 0
