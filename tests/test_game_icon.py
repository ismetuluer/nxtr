"""Oyun kartı verisi: control NCA'sından yayıncı ve simge okuma, projede önbellekleme, eski projelerin göçü."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from nxceviri.core.container.metadata import MAX_ICON_BYTES, pick_icon_name, valid_icon
from nxceviri.core.container.package import open_package
from nxceviri.core.keys import load_keys
from nxceviri.core.pipeline import read_source
from nxceviri.core.project import Project, SourceRecord
from nxceviri.core.project import store as store_module
from tests import nxbuild

BASE_TID = 0x0100000000010000
FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x01\x02\x03" * 50 + b"\xff\xd9"
OTHER_JPEG = b"\xff\xd8\xff\xe1" + b"\x09" * 20


def _nsp(
    tmp_path: Path, keys: nxbuild.TestKeys, control_extra: dict[str, bytes] | None, name: str = "Deneme Oyunu"
) -> Path:
    pkg = nxbuild.build_package(
        keys,
        kind="base",
        title_id=BASE_TID,
        application_id=BASE_TID,
        version=0,
        name=name,
        romfs_files={"Data/a.txt": b"x"},
        control_extra=control_extra,
    )
    path = tmp_path / "oyun.nsp"
    path.write_bytes(pkg.nsp)
    return path


@pytest.fixture
def keys(tmp_path: Path) -> nxbuild.TestKeys:
    test_keys = nxbuild.TestKeys.random()
    test_keys.write(tmp_path / "prod.keys")
    return test_keys


def test_pick_icon_name_prefers_american_english() -> None:
    names = ["control.nacp", "icon_Turkish.dat", "icon_French.dat", "icon_AmericanEnglish.dat"]
    assert pick_icon_name(names) == "icon_AmericanEnglish.dat"
    assert pick_icon_name(["icon_Turkish.dat", "icon_French.dat", "control.nacp"]) == "icon_French.dat"
    assert pick_icon_name(["control.nacp", "icon_x.png"]) is None


def test_valid_icon_rejects_non_jpeg_and_huge() -> None:
    assert valid_icon(FAKE_JPEG) == FAKE_JPEG
    assert valid_icon(b"PNG-degil") == b""
    assert valid_icon(b"") == b""
    assert valid_icon(b"\xff\xd8\xff" + b"\0" * MAX_ICON_BYTES) == b""


def test_package_reads_icon_and_publisher(tmp_path: Path, keys: nxbuild.TestKeys) -> None:
    path = _nsp(tmp_path, keys, {"icon_AmericanEnglish.dat": FAKE_JPEG, "icon_Turkish.dat": OTHER_JPEG})
    key_set = load_keys(tmp_path / "prod.keys")
    with open_package(path, key_set) as pkg:
        assert pkg.icon == FAKE_JPEG
        assert pkg.nacp is not None
        assert pkg.nacp.publisher == "Test Yayıncı"
    record = read_source(path, key_set)
    assert record.icon == FAKE_JPEG
    assert record.publisher == "Test Yayıncı"
    assert record.name == "Deneme Oyunu"


def test_package_without_icon_or_with_bad_icon_falls_back(tmp_path: Path, keys: nxbuild.TestKeys) -> None:
    key_set = load_keys(tmp_path / "prod.keys")
    assert read_source(_nsp(tmp_path, keys, None), key_set).icon == b""
    bad = _nsp(tmp_path, keys, {"icon_AmericanEnglish.dat": b"jpeg degil"})
    record = read_source(bad, key_set)
    assert record.icon == b""
    assert record.name == "Deneme Oyunu"  # simge okunamasa da oyun adı gelir


def test_icon_cached_in_project_roundtrip(tmp_path: Path) -> None:
    source = SourceRecord(
        Path("o.nsp"), "base", "0100", "0100", 0, "1.0", "Deneme Oyunu", 10, publisher="Yayıncı", icon=FAKE_JPEG
    )
    project = Project.new()
    project.save_as(tmp_path / "p.nxproj")
    project.set_sources([source])
    project.close()
    reopened = Project.open(tmp_path / "p.nxproj")
    (loaded,) = reopened.sources()
    assert loaded == source
    assert loaded.icon == FAKE_JPEG
    reopened.close()


def test_old_project_without_icon_columns_opens(tmp_path: Path) -> None:
    """Şema 7'de kaydedilmiş proje açılır; kaynaklar boş yayıncı ve simgeyle gelir, veri kaybolmaz."""
    old = tmp_path / "eski.nxproj"
    conn = sqlite3.connect(old)
    for i, script in enumerate(store_module.MIGRATIONS[:7], start=1):
        conn.executescript(f"{script}\nPRAGMA user_version = {i};")
    conn.execute(f"PRAGMA application_id = {store_module.APPLICATION_ID}")
    conn.execute("INSERT INTO project (id, created_at, updated_at, app_version) VALUES (1, 'x', 'x', '0.70.0')")
    conn.execute(
        "INSERT INTO sources (path, kind, title_id, application_id, version, display_version, name, file_size, "
        "added_at) VALUES ('C:/o.nsp', 'base', '0100', '0100', 0, '1.0', 'Deneme Oyunu', 5, 'x')"
    )
    conn.commit()
    conn.close()
    migrated = Project.open(old)
    (source,) = migrated.sources()
    assert (source.name, source.publisher, source.icon) == ("Deneme Oyunu", "", b"")
    assert migrated._conn.execute("PRAGMA user_version").fetchone()[0] == store_module.SCHEMA_VERSION
    migrated.set_sources([source.__class__(**{**source.__dict__, "icon": FAKE_JPEG})])
    assert migrated.sources()[0].icon == FAKE_JPEG
    migrated.close()
