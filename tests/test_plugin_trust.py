"""Kullanıcı eklentisi onayı: onaysız eklentinin kodu çalışmaz, onaylanan içerik yüklenir, değişen yine sorulur."""

from __future__ import annotations

import json
import logging
import py_compile
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from nxceviri.core.formats import registry
from nxceviri.core.plugins import loader
from nxceviri.core.plugins.loader import load_plugins, plugin_fingerprint
from nxceviri.core.plugins.trust import TRUST_FILE_NAME, PluginTrust
from tests.test_plugins import PLUGIN_BODY, make_plugin


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    registry.reset_user_plugins()
    yield
    registry.reset_user_plugins()


def _side_effect_plugin(root: Path, marker: Path, folder: str = "demo") -> Path:
    """Modül düzeyinde `marker` dosyasını yazan eklenti: dosya varsa kod çalışmış demektir."""
    body = f"from pathlib import Path\nPath({str(marker)!r}).write_text('calisti')\n" + PLUGIN_BODY.format(
        kind="demo_kind"
    )
    return make_plugin(root, folder, body=body)


def test_trust_file_lives_in_user_data_dir() -> None:
    assert PluginTrust().path == loader.user_data_dir() / TRUST_FILE_NAME


def test_unapproved_plugin_is_not_imported(tmp_path: Path) -> None:
    marker = tmp_path / "calisti.txt"
    folder = _side_effect_plugin(tmp_path / "ek", marker)
    trust = PluginTrust(tmp_path / "onay.json")
    report = load_plugins([tmp_path / "ek"], set(), trust.is_trusted)
    (info,) = report.infos
    assert not marker.exists()
    assert info.onay_bekliyor
    assert not info.yuklu
    assert not info.hata
    assert info.plugin is None
    assert (info.ad, info.surum, info.yazar, info.yol) == ("demo", "1.0.0", "Deneme", folder)
    assert info.parmak_izi == plugin_fingerprint(folder)
    assert report.plugins == ()
    assert report.errors == ()
    assert not trust.path.exists()


def test_approved_plugin_loads_and_changed_content_asks_again(tmp_path: Path) -> None:
    marker = tmp_path / "calisti.txt"
    folder = _side_effect_plugin(tmp_path / "ek", marker)
    trust = PluginTrust(tmp_path / "onay.json")
    (pending,) = load_plugins([tmp_path / "ek"], set(), trust.is_trusted).infos
    assert not trust.known(folder)
    trust.approve(folder, pending.parmak_izi)
    assert trust.known(folder)
    (info,) = load_plugins([tmp_path / "ek"], set(), trust.is_trusted).infos
    assert info.yuklu
    assert not info.onay_bekliyor
    assert marker.exists()

    marker.unlink()
    (folder / "yardimci.py").write_text("X = 1\n", encoding="utf-8")
    (info,) = load_plugins([tmp_path / "ek"], set(), trust.is_trusted).infos
    assert info.onay_bekliyor
    assert not marker.exists()
    assert trust.known(folder)  # biliniyor ama içerik değişti


def test_approval_of_older_content_does_not_load_newer(tmp_path: Path) -> None:
    """Onaydan sonra içerik değişirse yüklemeden hemen önceki denetim bunu yakalar."""
    marker = tmp_path / "calisti.txt"
    folder = _side_effect_plugin(tmp_path / "ek", marker)
    trust = PluginTrust(tmp_path / "onay.json")
    (pending,) = load_plugins([tmp_path / "ek"], set(), trust.is_trusted).infos
    (folder / "plugin.py").write_text("raise SystemExit('kotu')\n", encoding="utf-8")
    trust.approve(folder, pending.parmak_izi)
    (info,) = load_plugins([tmp_path / "ek"], set(), trust.is_trusted).infos
    assert info.onay_bekliyor
    assert info.parmak_izi != pending.parmak_izi


def test_corrupt_trust_file_approves_nothing_and_is_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    marker = tmp_path / "calisti.txt"
    folder = _side_effect_plugin(tmp_path / "ek", marker)
    path = tmp_path / "onay.json"
    trust = PluginTrust(path)
    for content in ("{bozuk", "[1, 2]", json.dumps({"surum": 1, "eklentiler": {str(folder.resolve()): 5}})):
        path.write_text(content, encoding="utf-8")
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            (info,) = load_plugins([tmp_path / "ek"], set(), trust.is_trusted).infos
        assert info.onay_bekliyor
        assert not marker.exists()
        assert "onay" in caplog.text.lower()


def test_approve_writes_atomically_and_keeps_other_entries(tmp_path: Path) -> None:
    first = make_plugin(tmp_path / "ek", "a", ad="a", kind="a_kind")
    second = make_plugin(tmp_path / "ek", "b", ad="b", kind="b_kind")
    trust = PluginTrust(tmp_path / "alt" / "onay.json")
    trust.approve(first, plugin_fingerprint(first))
    trust.approve(second, plugin_fingerprint(second))
    data = json.loads(trust.path.read_text(encoding="utf-8"))
    assert set(data["eklentiler"]) == {str(first.resolve()), str(second.resolve())}
    assert [p.name for p in trust.path.parent.iterdir()] == ["onay.json"]  # geçici dosya kalmadı
    assert len(load_plugins([tmp_path / "ek"], set(), trust.is_trusted).plugins) == 2


def test_pycache_does_not_change_fingerprint(tmp_path: Path) -> None:
    folder = make_plugin(tmp_path, "demo")
    before = plugin_fingerprint(folder)
    (folder / "__pycache__").mkdir()
    (folder / "__pycache__" / "plugin.cpython-313.pyc").write_bytes(b"\x00derlenmis")
    assert plugin_fingerprint(folder) == before
    (folder / "plugin.py").write_text("X = 2\n", encoding="utf-8")
    assert plugin_fingerprint(folder) != before


def test_planted_bytecode_cache_does_not_run_instead_of_approved_source(tmp_path: Path) -> None:
    """`__pycache__` ize girmez; içindeki (kaynağı denetlemeyen) pyc onaylı `plugin.py` yerine çalışmamalı."""
    marker = tmp_path / "calisti.txt"
    folder = make_plugin(tmp_path / "ek", "demo")  # zararsız kaynak, tür demo_kind
    evil = tmp_path / "kotu_kaynak.py"
    evil.write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('calisti')\n"
        + PLUGIN_BODY.format(kind="kotu_kind"),
        encoding="utf-8",
    )
    cache = folder / "__pycache__" / f"plugin.{sys.implementation.cache_tag}.pyc"
    cache.parent.mkdir()
    py_compile.compile(
        str(evil), cfile=str(cache), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH
    )
    trust = PluginTrust(tmp_path / "onay.json")
    trust.approve(folder, plugin_fingerprint(folder))
    (info,) = load_plugins([tmp_path / "ek"], set(), trust.is_trusted).infos
    assert not marker.exists()
    assert info.yuklu
    assert info.tur == "demo_kind"


def test_cache_that_cannot_be_removed_blocks_loading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = make_plugin(tmp_path / "ek", "demo")
    (folder / "__pycache__").mkdir()
    trust = PluginTrust(tmp_path / "onay.json")
    trust.approve(folder, plugin_fingerprint(folder))

    def refuse(path: object, *_a: object, **_k: object) -> None:
        raise PermissionError("erişim engellendi")

    monkeypatch.setattr("nxceviri.core.plugins.loader.shutil.rmtree", refuse)
    (info,) = load_plugins([tmp_path / "ek"], set(), trust.is_trusted).infos
    assert "temizlenemedi" in info.hata
    assert info.plugin is None


def test_without_check_bytecode_cache_is_left_alone(tmp_path: Path) -> None:
    folder = make_plugin(tmp_path / "ek", "demo")
    (folder / "__pycache__").mkdir()
    (folder / "__pycache__" / "x.txt").write_text("1", encoding="utf-8")
    load_plugins([tmp_path / "ek"], set())
    assert (folder / "__pycache__" / "x.txt").exists()


def test_pyc_outside_pycache_changes_fingerprint(tmp_path: Path) -> None:
    folder = make_plugin(tmp_path, "demo")
    before = plugin_fingerprint(folder)
    (folder / "yardimci.pyc").write_bytes(b"\x00bayt kodu")
    assert plugin_fingerprint(folder) != before


def test_fingerprint_covers_relative_paths(tmp_path: Path) -> None:
    a = make_plugin(tmp_path, "a")
    b = make_plugin(tmp_path, "b")
    (a / "x.py").write_text("1", encoding="utf-8")
    (b / "y.py").write_text("1", encoding="utf-8")
    assert plugin_fingerprint(a) != plugin_fingerprint(b)


def test_repo_plugin_dir_loads_without_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    marker = tmp_path / "calisti.txt"
    _side_effect_plugin(tmp_path / "depo", marker)
    monkeypatch.setattr(loader, "repo_plugin_dir", lambda: tmp_path / "depo")
    trust = PluginTrust(tmp_path / "onay.json")
    (info,) = load_plugins([tmp_path / "kullanici", tmp_path / "depo"], set(), trust.is_trusted).infos
    assert info.yuklu
    assert marker.exists()


def test_manifest_errors_stay_errors_with_approval_check(tmp_path: Path) -> None:
    make_plugin(tmp_path / "ek", "bozuk", toml="ad = [\n")
    trust = PluginTrust(tmp_path / "onay.json")
    (info,) = load_plugins([tmp_path / "ek"], set(), trust.is_trusted).infos
    assert "bozuk" in info.hata
    assert not info.onay_bekliyor


def test_registry_without_check_loads_everything_like_before(tmp_path: Path) -> None:
    marker = tmp_path / "calisti.txt"
    _side_effect_plugin(tmp_path / "ek", marker)
    report = registry.load_user_plugins([tmp_path / "ek"])
    assert marker.exists()
    assert report.infos[0].yuklu
    assert registry.plugin_for_kind("demo_kind") is not None


def test_registry_with_check_keeps_pending_plugin_out(tmp_path: Path) -> None:
    marker = tmp_path / "calisti.txt"
    _side_effect_plugin(tmp_path / "ek", marker)
    trust = PluginTrust(tmp_path / "onay.json")
    report = registry.load_user_plugins([tmp_path / "ek"], trusted=trust.is_trusted)
    assert report.infos[0].onay_bekliyor
    assert registry.plugin_for_kind("demo_kind") is None
    assert not marker.exists()
