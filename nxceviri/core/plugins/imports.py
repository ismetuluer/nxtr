"""Kullanıcı eklentisinin ana koddan (`nxceviri`) içe aktardıklarının denetimi.

Eklenti kendine yeterlidir: standart kütüphane, paketlenmiş bağımlılıklar, kendi klasöründeki modüller ve yalnızca
`ALLOWED_MODULES`'teki çekirdek modülleri kullanır. Başka bir çekirdek modülü (ör. `core.fontpatch.*`, `gui.*`)
sürümler arasında değişebilir; başka bir kopyada ana koda eklenmiş bir modül ise bu kopyada hiç yoktur ve eklenti
yüklenemez. Denetim kodu çalıştırmaz: `.py` dosyaları `ast` ile okunur. Liste `docs/rehber/eklenti-yazma.md`
"İzinli çekirdek modülleri" ile aynı tutulur (test denetler).
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

#: Eklentilerin içe aktarabileceği çekirdek modülleri (tam ad; alt modülleri ayrıca listelenmedikçe izinli değildir).
ALLOWED_MODULES: tuple[str, ...] = (
    "nxceviri.core.plugins",
    "nxceviri.core.formats.base",
    "nxceviri.core.formats.derived",
    "nxceviri.core.formats.msbt",
    "nxceviri.core.formats.msbt.msbt",
    "nxceviri.core.translate.placeholders",
    "nxceviri.core.translate.markup",
    "nxceviri.core.archives.sarc",
    "nxceviri.core.archives.yaz0",
    "nxceviri.core.archives.zstd",
    "nxceviri.core.archives.nni",
    "nxceviri.core.archives.cpk",
    "nxceviri.core.archives.wad",
    "nxceviri.core.archives.pak",
    "nxceviri.core.archives.psb",
    "nxceviri.core.archives.psb_archive",
    "nxceviri.core.archives.nested",
    "nxceviri.core.archives.access",
)

ROOT = "nxceviri"
GUIDE = "docs/rehber/eklenti-yazma.md"
#: Taranmayan klasörler: yükleyici `tests/`'e bakmaz, `__pycache__` derlenmiş önbellektir.
_SKIPPED_DIRS = frozenset({"tests", "__pycache__"})
_MOVE = "gereken kodu eklenti klasörüne taşıyın"


@dataclass(frozen=True)
class ImportFinding:
    path: str  # eklenti klasörüne göre, `/` ile
    line: int
    module: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.message}"


def missing_message(module: str) -> str:
    return (
        f"eklenti, ana kodda olmayan `{module}` modülünü kullanıyor: bu NXTR kopyasında yok (başka bir kopyada ana "
        f"koda eklenmiş olabilir); {_MOVE} ({GUIDE})."
    )


def forbidden_message(module: str) -> str:
    return f"eklenti, ana koddaki izinli olmayan `{module}` modülünü kullanıyor; {_MOVE} (izinli liste: {GUIDE})."


def _exists(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):  # üst paket yok ya da ad geçersiz
        return False


def _is_package(module: str) -> bool:
    """Modül bir paket mi (içe aktarmadan; Qt gibi ağır bağımlılıklar yüklenmez)."""
    try:
        spec = importlib.util.find_spec(module)
    except (ImportError, ValueError):
        return False
    return spec is not None and spec.submodule_search_locations is not None


def _in_core(module: str) -> bool:
    return module == ROOT or module.startswith(ROOT + ".")


def _module_problem(module: str) -> str:
    if not _exists(module):
        return missing_message(module)
    if module not in ALLOWED_MODULES:
        return forbidden_message(module)
    return ""


def _from_problem(module: str, name: str) -> tuple[str, str]:
    """`from module import name`: (değerlendirilen modül adı, sorun ya da "")."""
    if module in ALLOWED_MODULES:
        if name == "*" or _exists(f"{module}.{name}"):
            return module, ""
        try:
            found = hasattr(importlib.import_module(module), name)
        except Exception as exc:  # çekirdek modülü bu ortamda içe aktarılamıyor: ad denetlenemez
            return module, f"`{module}` içe aktarılamadı ({type(exc).__name__}: {exc})."
        if found:
            return module, ""
        return module, f"eklenti, `{module}` içinde olmayan `{name}` adını kullanıyor; {_MOVE} ({GUIDE})."
    if not _exists(module):
        return module, missing_message(module)
    sub = f"{module}.{name}"
    if _exists(sub):
        return sub, _module_problem(sub)
    if _is_package(module):  # paketten alınan ad alt modül değil: büyük olasılıkla bu kopyada olmayan bir modül
        return sub, missing_message(sub)
    return module, forbidden_message(module)


def _dynamic_target(node: ast.Call) -> str | None:
    """`importlib.import_module("nxceviri…")` ya da `__import__("nxceviri…")` çağrısındaki sabit ad."""
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else ""
    if name not in {"import_module", "__import__"} or not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str) and _in_core(first.value):
        return first.value
    return None


def _tree_findings(tree: ast.AST, rel: str) -> Iterator[ImportFinding]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _in_core(alias.name) and (problem := _module_problem(alias.name)):
                    yield ImportFinding(rel, node.lineno, alias.name, problem)
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module or not _in_core(node.module):
                continue  # göreli içe aktarma: eklentinin kendi modülü
            for alias in node.names:
                module, problem = _from_problem(node.module, alias.name)
                if problem:
                    yield ImportFinding(rel, node.lineno, module, problem)
        elif isinstance(node, ast.Call) and (target := _dynamic_target(node)) and (problem := _module_problem(target)):
            yield ImportFinding(rel, node.lineno, target, problem)


def _sources(folder: Path) -> Iterator[Path]:
    for path in sorted(folder.rglob("*.py")):
        if not _SKIPPED_DIRS.intersection(path.relative_to(folder).parts[:-1]):
            yield path


def audit_plugin(folder: Path) -> list[ImportFinding]:
    """Eklenti klasöründeki `.py` dosyalarının (`tests/` hariç) çekirdekten izinsiz ya da olmayan içe aktarmaları."""
    findings: list[ImportFinding] = []
    for path in _sources(folder):
        rel = path.relative_to(folder).as_posix()
        try:
            tree = ast.parse(path.read_bytes(), filename=rel)
        except (SyntaxError, ValueError, OSError) as exc:
            findings.append(
                ImportFinding(rel, getattr(exc, "lineno", None) or 0, "", f"dosya ayrıştırılamadı ({exc}).")
            )
            continue
        findings += sorted(_tree_findings(tree, rel), key=lambda f: (f.line, f.module))
    return findings
