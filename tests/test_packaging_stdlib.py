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
