"""Paketleme: standart kütüphane modül listesi (PyInstaller olmadan) ve lisans toplama kuralı."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

PACKAGING = Path(__file__).resolve().parents[1] / "packaging"


@pytest.fixture(scope="module")
def stdlib() -> ModuleType:
    spec = importlib.util.spec_from_file_location("nxtr_stdlib_modules", PACKAGING / "stdlib_modules.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stdlib_list_includes_submodules_of_packages(stdlib: ModuleType) -> None:
    names = set(stdlib.stdlib_hidden_imports())
    for wanted in (
        "csv",
        "zipfile",
        "xml.etree.ElementTree",
        "xml.dom.minidom",
        "concurrent.futures",
        "json.decoder",
        "email.mime.text",
        "urllib.request",
        "http.client",
        "logging.handlers",
        "sqlite3.dbapi2",
        "ctypes.wintypes",
        "asyncio.events",
        "multiprocessing.pool",
        "html.parser",
        "importlib.metadata",
    ):
        assert wanted in names, wanted


def test_stdlib_list_excludes_unwanted_and_does_not_import(stdlib: ModuleType) -> None:
    sys.modules.pop("antigravity", None)
    names = set(stdlib.stdlib_hidden_imports())
    assert "antigravity" not in sys.modules  # içe aktarılsaydı tarayıcı açardı
    for unwanted in ("tkinter", "tkinter.ttk", "test", "idlelib", "antigravity", "this", "turtledemo"):
        assert unwanted not in names
    assert not [n for n in names if n.endswith(".__main__") or ".test" in n or n.startswith("_")]
    assert "asyncio.unix_events" not in names


def test_license_collection_fails_loudly_for_missing_distribution() -> None:
    text = (PACKAGING / "NXTR.spec").read_text(encoding="utf-8")
    assert "raise SystemExit" in text  # bulunamayan dağıtım sessizce atlanmaz
    from importlib import metadata

    for name in (
        "PySide6-Essentials",
        "cryptography",
        "zstandard",
        "UnityPy",
        "httpx",
        "keyring",
        "fonttools",
        "lz4",
        "Pillow",
    ):
        assert f'"{name}"' in text
        metadata.distribution(name)  # spec'teki adların hepsi gerçek dağıtım adıdır


def test_every_module_imports_for_release_check(tmp_path: Path) -> None:
    """Sürüm derlemesi .exe'yi `--paket-denetimi` ile çalıştırır; geliştirme ortamında her modül yüklenmelidir."""
    from nxceviri.__main__ import _run

    report = tmp_path / "denetim.txt"
    assert _run(["--paket-denetimi", str(report)]) == 0
    assert report.read_text(encoding="utf-8").startswith("Tamam")


def test_spec_bundles_data_of_runtime_dependencies() -> None:
    """etcpak açılışta archspec'in JSON verisini okur; paket bunu taşımazsa .exe açılmaz (0.79.0)."""
    spec = (PACKAGING / "NXTR.spec").read_text(encoding="utf-8")
    assert '"archspec"' in spec
    assert '"etcpak"' in spec


def test_release_runs_package_check() -> None:
    workflow = (PACKAGING.parent / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "--paket-denetimi" in workflow


def test_package_check_reports_broken_subpackage_instead_of_crashing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Paketin içe aktarılması (walk_packages'in kendi yaptığı da) ImportError dışı hatayla patlasa da denetim çökmez,
    hatayı rapora yazar (0.79.0'da FileNotFoundError, çökme penceresi açtırıyordu)."""
    import importlib as real_importlib

    from nxceviri import paket_denetimi

    original = real_importlib.import_module

    def broken(name: str, package: str | None = None) -> ModuleType:
        if name == "nxceviri.core.formats.fsdmsg":
            raise FileNotFoundError("microarchitectures.json")
        return original(name, package)

    monkeypatch.setattr(real_importlib, "import_module", broken)
    for loaded in [m for m in sys.modules if m.startswith("nxceviri.core.formats.fsdmsg")]:
        monkeypatch.delitem(sys.modules, loaded)
    problems = paket_denetimi.denetle()
    assert any("nxceviri.core.formats.fsdmsg" in p and "microarchitectures.json" in p for p in problems)
