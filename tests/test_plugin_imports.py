"""Kullanıcı eklentisinin ana koddan içe aktardıkları: izinli liste, denetim ve araçlara bağlanması."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from nxceviri.arac import main as tool_main
from nxceviri.core.formats import registry
from nxceviri.core.plugins import load_plugins
from nxceviri.core.plugins.imports import ALLOWED_MODULES, audit_plugin
from nxceviri.core.plugins.scaffold import create_plugin

REPO = Path(__file__).resolve().parents[1]

MANIFEST = 'ad = "{ad}"\nsurum = "1.0.0"\nyazar = "Deneme"\napi = 1\noyunlar = []\n'

#: Elle yazılmış, uydurma `NXDEN` biçimi: satır başına `anahtar=metin`.
PLUGIN_BODY = """
from collections.abc import Mapping

{imports}

from nxceviri.core.formats.base import TextEntry
from nxceviri.core.plugins import FormatPluginBase

BASLIK = b"NXDEN\\n"


class Eklenti(FormatPluginBase):
    name = "{kind}"
    label = "Deneme"
    candidates_only = False
    path_suffixes = (".nxden",)

    def detect(self, path, head):
        return head.startswith(BASLIK)

    def extract(self, data, context=None):
        out = []
        for i, line in enumerate(data[len(BASLIK):].decode("utf-8").split("\\n")):
            key, sep, text = line.partition("=")
            if sep:
                out.append(TextEntry(key=key, index=i, source={transform}(text), codes=()))
        return out

    def inject(self, data, translations: Mapping[str, str]):
        lines = data[len(BASLIK):].decode("utf-8").split("\\n")
        for i, line in enumerate(lines):
            key, sep, _ = line.partition("=")
            if sep and key in translations:
                lines[i] = key + "=" + translations[key]
        return BASLIK + "\\n".join(lines).encode("utf-8")


PLUGIN = Eklenti()
"""


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    registry.reset_user_plugins()
    yield
    registry.reset_user_plugins()


def make(
    root: Path, folder: str, *, imports: str = "", transform: str = "str", extra: dict[str, str] | None = None
) -> Path:
    path = root / folder
    path.mkdir(parents=True)
    (path / "eklenti.toml").write_text(MANIFEST.format(ad=folder), encoding="utf-8")
    body = PLUGIN_BODY.format(imports=imports, kind=f"{folder}_tur", transform=transform)
    (path / "plugin.py").write_text(body, encoding="utf-8")
    for rel, text in (extra or {}).items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return path


def modules(folder: Path) -> list[str]:
    return [f.module for f in audit_plugin(folder)]


# --- denetim ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "from nxceviri.core.formats.base import FormatError, TextEntry",
        "from nxceviri.core.archives import sarc, yaz0",
        "import nxceviri.core.archives.zstd",
        "import nxceviri.core.translate.placeholders as ph",
        "from nxceviri.core.translate import markup",
        "from nxceviri.core.formats.derived import Derived, GraphicsSupport",
        "from nxceviri.core.plugins import FormatPluginBase",
        "import json, struct",
        "from fontTools.ttLib import TTFont",
    ],
)
def test_allowed_imports_pass(tmp_path: Path, line: str) -> None:
    folder = make(tmp_path, "izinli", imports=line)
    assert audit_plugin(folder) == []


@pytest.mark.parametrize(
    ("line", "module"),
    [
        ("from nxceviri.core.fontpatch.ttf import patch_font", "nxceviri.core.fontpatch.ttf"),
        ("from nxceviri.core.fontpatch import ttf", "nxceviri.core.fontpatch.ttf"),
        ("import nxceviri.core.fontpatch.ttf", "nxceviri.core.fontpatch.ttf"),
        ("from nxceviri.gui import main_window", "nxceviri.gui.main_window"),
        ("from nxceviri.core.plugins.loader import load_plugins", "nxceviri.core.plugins.loader"),
        ("from nxceviri.core.archives import access as _a, nested as _n, pak as _p", None),
    ],
)
def test_core_modules_outside_the_list_are_reported(tmp_path: Path, line: str, module: str | None) -> None:
    folder = make(tmp_path, "izinsiz", imports=line)
    findings = audit_plugin(folder)
    if module is None:  # denetim izinli modülü yanlışlıkla reddetmemeli
        assert findings == []
        return
    (finding,) = findings
    assert finding.module == module
    assert finding.path == "plugin.py"
    assert finding.line == 4
    assert "izinli olmayan" in finding.message
    assert "eklenti klasörüne taşıyın" in finding.message
    assert str(finding).startswith("plugin.py:4: ")


@pytest.mark.parametrize(
    "line",
    [
        "from nxceviri.core.fontpatch import yok_modul",
        "from nxceviri.core.fontpatch.yok_modul import yama",
        "import nxceviri.core.fontpatch.yok_modul",
        "import importlib\nYAMA = importlib.import_module('nxceviri.core.fontpatch.yok_modul')",
    ],
)
def test_missing_core_modules_are_reported(tmp_path: Path, line: str) -> None:
    folder = make(tmp_path, "eksik", imports=line)
    (finding,) = audit_plugin(folder)
    assert finding.module == "nxceviri.core.fontpatch.yok_modul"
    assert "bu NXTR kopyasında yok" in finding.message
    assert "eklenti klasörüne taşıyın" in finding.message


def test_missing_name_in_allowed_module_is_reported(tmp_path: Path) -> None:
    folder = make(tmp_path, "adyok", imports="from nxceviri.core.formats.base import YokBoyleBirAd")
    (finding,) = audit_plugin(folder)
    assert finding.module == "nxceviri.core.formats.base"
    assert "YokBoyleBirAd" in finding.message


def test_own_submodules_pass_and_other_files_are_scanned(tmp_path: Path) -> None:
    folder = make(
        tmp_path,
        "cokdosya",
        imports="from . import yardimci\nfrom .alt.kod import ters",
        transform="yardimci.buyut",
        extra={
            "yardimci.py": "def buyut(text):\n    return text\n",
            "alt/__init__.py": "",
            "alt/kod.py": "from nxceviri.core.fontpatch import bc7\n\ndef ters(text):\n    return text[::-1]\n",
            "tests/test_x.py": "from nxceviri.core.fontpatch import ttf\n",  # testler yükleyiciye girmez, taranmaz
            "__pycache__/eski.py": "import nxceviri.gui\n",
        },
    )
    findings = audit_plugin(folder)
    assert [(f.path, f.line, f.module) for f in findings] == [("alt/kod.py", 1, "nxceviri.core.fontpatch.bc7")]


def test_unparsable_file_is_a_finding_not_a_crash(tmp_path: Path) -> None:
    folder = make(tmp_path, "bozuk", extra={"yardimci.py": "def (:\n"})
    (finding,) = audit_plugin(folder)
    assert finding.path == "yardimci.py"
    assert "ayrıştırılamadı" in finding.message


# --- izinli liste ----------------------------------------------------------------------------------


def test_every_allowed_module_exists() -> None:
    for name in ALLOWED_MODULES:
        assert name.startswith("nxceviri.")
        assert importlib.util.find_spec(name) is not None, name


def test_guide_lists_exactly_the_allowed_modules() -> None:
    text = (REPO / "docs" / "rehber" / "eklenti-yazma.md").read_text(encoding="utf-8")
    section = text.split("### İzinli çekirdek modülleri", 1)[1].split("\n#", 1)[0]
    listed = set(re.findall(r"`(nxceviri(?:\.\w+)+)`", section))
    assert listed == set(ALLOWED_MODULES)


# --- yükleyici, iskelet ve araçlar -----------------------------------------------------------------


def test_multi_file_plugin_loads_with_relative_imports(tmp_path: Path) -> None:
    make(
        tmp_path,
        "paket",
        imports="from . import yardimci",
        transform="yardimci.buyut",
        extra={"yardimci.py": "def buyut(text):\n    return text.upper()\n"},
    )
    (info,) = load_plugins([tmp_path], set()).infos
    assert info.yuklu, info.hata
    assert info.plugin is not None
    assert [e.source for e in info.plugin.extract(b"NXDEN\na=selam\n")] == ["SELAM"]


def test_loader_explains_missing_core_module(tmp_path: Path) -> None:
    make(tmp_path, "kayip", imports="from nxceviri.core.fontpatch import yok_modul")
    (info,) = load_plugins([tmp_path], set()).infos
    assert not info.yuklu
    assert "nxceviri.core.fontpatch.yok_modul" in info.hata
    assert "bu NXTR kopyasında yok" in info.hata
    assert "eklenti klasörüne taşıyın" in info.hata


def test_loader_keeps_plain_message_for_other_missing_modules(tmp_path: Path) -> None:
    make(tmp_path, "baska", imports="import olmayan_modul_xyz")
    (info,) = load_plugins([tmp_path], set()).infos
    assert "olmayan_modul_xyz" in info.hata
    assert "NXTR kopyasında" not in info.hata


def test_scaffold_output_is_clean(tmp_path: Path) -> None:
    folder = create_plugin("temiz_iskelet", tmp_path)
    assert audit_plugin(folder) == []


def test_scaffold_tests_allow_relative_imports(tmp_path: Path) -> None:
    """İskeletin testi `plugin.py`'yi paket olarak yükler: yanına eklenen modül `from . import` ile alınabilir."""
    folder = create_plugin("cok_dosyali", tmp_path)
    (folder / "yardimci.py").write_text("ONEK = ''\n", encoding="utf-8")
    plugin = folder / "plugin.py"
    text = plugin.read_text(encoding="utf-8")
    text = text.replace(
        "from nxceviri.core.plugins import FormatPluginBase\n",
        "from nxceviri.core.plugins import FormatPluginBase\n\nfrom . import yardimci\n",
    )
    text = text.replace("source=text,", "source=yardimci.ONEK + text,")
    plugin.write_text(text, encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(folder / "tests")],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(REPO)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "4 passed" in done.stdout


def _user_dir() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "NXCeviri" / "eklentiler"


@pytest.fixture
def ornek_oyun(tmp_path: Path) -> Path:
    kok = tmp_path / "romfs"
    (kok / "Veri").mkdir(parents=True)
    (kok / "Veri" / "metin.nxden").write_bytes("NXDEN\na=Merhaba\nb=Görüşürüz\n".encode())
    return kok


def test_list_command_shows_findings(capsys: pytest.CaptureFixture[str]) -> None:
    root = _user_dir()
    make(root, "liste_temiz")
    make(root, "liste_izinsiz", imports="from nxceviri.core.fontpatch import ttf")
    try:
        tool_main(["eklentiler"])
        out = capsys.readouterr().out
        assert "[TAMAM] liste_izinsiz" in out
        assert "nxceviri.core.fontpatch.ttf" in out
        assert out.count("İçe aktarma:") == 1
    finally:
        shutil.rmtree(root / "liste_temiz")
        shutil.rmtree(root / "liste_izinsiz")


def test_dogrula_loads_user_plugins(ornek_oyun: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _user_dir()
    make(root, "dogrula_temiz")
    try:
        assert tool_main(["dogrula", "dogrula_temiz_tur", str(ornek_oyun)]) == 0
        out = capsys.readouterr().out
        assert "GEÇTİ  Veri/metin.nxden  (2 girdi)" in out
    finally:
        shutil.rmtree(root / "dogrula_temiz")


def test_dogrula_fails_on_forbidden_import(ornek_oyun: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _user_dir()
    make(root, "dogrula_izinsiz", imports="from nxceviri.core.fontpatch import ttf")
    try:
        assert tool_main(["dogrula", "dogrula_izinsiz_tur", str(ornek_oyun)]) == 1
        out = capsys.readouterr().out
        assert "GEÇTİ  Veri/metin.nxden" in out  # dosya sınaması yine yapılır
        assert "nxceviri.core.fontpatch.ttf" in out
        assert "izinsiz içe aktarma" in out
    finally:
        shutil.rmtree(root / "dogrula_izinsiz")


def test_dogrula_shows_load_error_of_named_plugin(ornek_oyun: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _user_dir()
    make(root, "dogrula_kayip", imports="from nxceviri.core.fontpatch import yok_modul")
    try:
        assert tool_main(["dogrula", "dogrula_kayip", str(ornek_oyun)]) == 1
        captured = capsys.readouterr()
        text = captured.out + captured.err
        assert "yüklenemedi" in text
        assert "bu NXTR kopyasında yok" in text
    finally:
        shutil.rmtree(root / "dogrula_kayip")
