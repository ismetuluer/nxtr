"""Kullanıcı eklentilerinin keşfi, doğrulanması ve yüklenmesi.

Bir eklenti bir klasördür:

- `eklenti.toml`: `ad`, `surum`, `yazar`, `api`, isteğe bağlı `oyunlar` (TitleID listesi) ve `aciklama`.
- `plugin.py`: modül düzeyinde bir `PLUGIN` nesnesi (biçim eklentisi sözleşmesini uygular;
  `FormatPluginBase`'den türetmek en kolayıdır). Klasördeki diğer `.py` dosyaları `from . import x` ile alınabilir.
- `tests/`, `NOT.md`: eklenti yazarı içindir; yükleyici bunlara bakmaz.

Hatalı bir eklenti uygulamayı durdurmaz: nedeni `PluginInfo.hata` içinde, ne yapılacağıyla birlikte
Türkçe olarak raporlanır. Eklenti kodu korumasız çalışır (korumalı alan yoktur); yalnızca güvenilen
kaynaklardan eklenti kurulmalıdır.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import re
import sys
import tomllib
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from nxceviri.core.errors import NxError
from nxceviri.core.formats.base import Context, FormatError, FormatPlugin, TextEntry

log = logging.getLogger(__name__)

#: Eklenti sözleşmesinin sürümü. Sözleşme uyumsuz biçimde değişirse artırılır.
EKLENTI_API = 1
MANIFEST_NAME = "eklenti.toml"
ENTRY_NAME = "plugin.py"
#: Yüklenen eklenti modüllerinin `sys.modules` ön eki (eklenti başına benzersiz ad).
MODULE_PREFIX = "nxtr_eklenti_"
_REQUIRED_CALLS = ("detect", "collect_context", "language", "extract", "inject")
_TITLE_ID = re.compile(r"^[0-9A-Fa-f]{16}$")


def user_data_dir() -> Path:
    """Kullanıcıya özel uygulama verisi klasörü (`%LOCALAPPDATA%\\NXCeviri`; diğer sistemlerde karşılığı)."""
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / "NXCeviri"
    if os.name == "nt":
        return Path.home() / "AppData" / "Local" / "NXCeviri"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "NXCeviri"


def repo_plugin_dir() -> Path | None:
    """Kaynak koddan çalışırken depodaki `eklentiler/` klasörü; paketlenmiş sürümde None."""
    if getattr(sys, "frozen", False):
        return None
    return Path(__file__).resolve().parents[3] / "eklentiler"


def user_plugin_dirs() -> list[Path]:
    """Eklenti aranan klasörler, öncelik sırasıyla: kullanıcı klasörü, sonra (kaynak kurulumda) depo klasörü."""
    dirs = [user_data_dir() / "eklentiler"]
    repo = repo_plugin_dir()
    if repo is not None:
        dirs.append(repo)
    return dirs


@dataclass(frozen=True)
class PluginInfo:
    ad: str
    surum: str
    yazar: str
    yol: Path | None
    api: int | None
    oyunlar: tuple[str, ...]
    hata: str = ""
    aciklama: str = ""
    #: Hata değilse ama kullanıcının bilmesi gereken durum (ör. yerleşik bir eklentinin yerini aldı).
    uyari: str = ""
    #: Eklentinin biçim adı (`PLUGIN.name`; tarama raporundaki tür).
    tur: str = ""
    #: Aynı eklentinin öncelikli bir klasördeki kopyası kullanıldığı için bu kopya yüklenmedi (hata değil).
    golge: bool = False
    plugin: FormatPlugin | None = field(default=None, compare=False, repr=False)

    @property
    def yuklu(self) -> bool:
        return not self.hata


@dataclass(frozen=True)
class PluginReport:
    infos: tuple[PluginInfo, ...] = ()

    @property
    def plugins(self) -> tuple[FormatPlugin, ...]:
        return tuple(i.plugin for i in self.infos if i.plugin is not None)

    @property
    def errors(self) -> tuple[PluginInfo, ...]:
        return tuple(i for i in self.infos if i.hata)


class GuardedPlugin:
    """Kullanıcı eklentisini sarar: beklenmeyen istisnaları `FormatError`'a çevirir.

    İşlem hattı yalnızca `NxError` yakalar; kullanıcı kodundaki bir hata tüm içe/dışa aktarmayı
    çökertmesin, hangi eklentiden geldiği Türkçe olarak söylensin diye.
    """

    def __init__(self, inner: FormatPlugin, ad: str) -> None:
        self._inner = inner
        self._ad = ad
        self.name = inner.name
        self.label = inner.label
        self.candidates_only = inner.candidates_only
        self.path_suffixes = inner.path_suffixes

    def _call(self, fn: Any, *args: Any) -> Any:
        try:
            return fn(*args)
        except NxError:
            raise
        except Exception as exc:
            log.warning("Eklenti hatası (%s)", self._ad, exc_info=True)
            raise FormatError(
                f"“{self._ad}” eklentisi hata verdi ({type(exc).__name__}: {exc}).",
                "Eklentinin yazarına bildirin ya da Araçlar → Eklentiler'den kaldırıp yerleşik desteği kullanın.",
            ) from exc

    def detect(self, path: str, head: bytes) -> bool:
        return bool(self._call(self._inner.detect, path, head))

    def collect_context(self, data: bytes, path: str) -> dict[object, object]:
        return dict(self._call(self._inner.collect_context, data, path))

    def language(self, data: bytes) -> str | None:
        result = self._call(self._inner.language, data)
        return None if result is None else str(result)

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        return list(self._call(self._inner.extract, data, context))

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        return bytes(self._call(self._inner.inject, data, translations))

    def __getattr__(self, item: str) -> Any:
        """İsteğe bağlı dışa aktarma kancaları (`derived_files`, `game_file_patches`…): çağrılabilirler korunur.

        Kancanın döndürdüğü sözlükteki çağrılabilirler de (ör. `game_file_patches`'ın dönüştürücüleri,
        dışa aktarmada sonradan çağrılır) aynı korumayla sarılır. Çağrılabilir olmayan nitelikler olduğu gibi geçer."""
        value = getattr(self._inner, item)
        if not callable(value):
            return value

        def hook(*args: Any) -> Any:
            return self._guard_result(self._call(value, *args))

        return hook

    def _guard_result(self, result: Any) -> Any:
        if isinstance(result, dict) and any(callable(v) for v in result.values()):
            return {k: self._guard_callable(v) if callable(v) else v for k, v in result.items()}
        return result

    def _guard_callable(self, fn: Any) -> Any:
        def guarded(*args: Any) -> Any:
            return self._call(fn, *args)

        return guarded


def slug(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_").lower() or "eklenti"


def read_manifest(folder: Path) -> tuple[dict[str, Any] | None, str]:
    path = folder / MANIFEST_NAME
    if not path.is_file():
        return None, (
            f"{MANIFEST_NAME} bulunamadı. Eklenti klasörünün içinde {MANIFEST_NAME} ve {ENTRY_NAME} olmalı; "
            "klasörü bir seviye içeri/dışarı taşımayı deneyin."
        )
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle), ""
    except tomllib.TOMLDecodeError as exc:
        return None, f"{MANIFEST_NAME} bozuk ({exc}). Dosyayı düzeltin ya da eklentiyi yeniden indirin."
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"{MANIFEST_NAME} okunamadı ({exc}). Dosya izinlerini ve kodlamasını (UTF-8) denetleyin."


def manifest_problem(data: Mapping[str, Any]) -> str:
    for key in ("ad", "surum", "yazar"):
        value = data.get(key)
        if not isinstance(value, str) or not value.strip():
            return f"{MANIFEST_NAME} içinde “{key}” alanı eksik ya da boş (metin olmalı)."
    api = data.get("api")
    if isinstance(api, bool) or not isinstance(api, int):
        return f"{MANIFEST_NAME} içinde “api” alanı eksik (tam sayı olmalı; bu uygulama {EKLENTI_API} ister)."
    games = data.get("oyunlar", [])
    if not isinstance(games, list) or not all(isinstance(g, str) and _TITLE_ID.match(g) for g in games):
        return f"{MANIFEST_NAME} içinde “oyunlar” 16 haneli TitleID'lerden oluşan bir liste olmalı."
    if not isinstance(data.get("aciklama", ""), str):
        return f"{MANIFEST_NAME} içinde “aciklama” metin olmalı."
    return ""


def _api_problem(api: int) -> str:
    if api > EKLENTI_API:
        return (
            f"Bu eklenti eklenti API {api} sürümünü istiyor, kurulu uygulama API {EKLENTI_API} destekliyor. "
            "Uygulamayı güncelleyin (Yardım → Güncellemeleri Denetle)."
        )
    return (
        f"Bu eklenti eski eklenti API {api} sürümüyle yazılmış, kurulu uygulama API {EKLENTI_API} istiyor. "
        "Eklentinin güncel sürümünü isteyin ya da eklentiyi yeni sözleşmeye uyarlayın."
    )


def _contract_problems(obj: object) -> list[str]:
    missing = []
    for attr in ("name", "label"):
        if not isinstance(getattr(obj, attr, None), str) or not getattr(obj, attr):
            missing.append(f"{attr} (boş olmayan metin)")
    if not isinstance(getattr(obj, "candidates_only", None), bool):
        missing.append("candidates_only (True/False)")
    suffixes = getattr(obj, "path_suffixes", None)
    if not isinstance(suffixes, tuple) or not all(isinstance(s, str) for s in suffixes):
        missing.append("path_suffixes (metin demeti)")
    missing += [f"{call}()" for call in _REQUIRED_CALLS if not callable(getattr(obj, call, None))]
    return missing


def _import_plugin(folder: Path, module_name: str) -> ModuleType:
    """`plugin.py`'yi, klasörü paket sayarak (göreli içe aktarmalar çalışsın) benzersiz adla yükler."""
    spec = importlib.util.spec_from_file_location(
        module_name, folder / ENTRY_NAME, submodule_search_locations=[str(folder)]
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"{ENTRY_NAME} yüklenemedi")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        _forget_modules(module_name)
        raise
    return module


def _forget_modules(prefix: str) -> None:
    for name in [n for n in sys.modules if n == prefix or n.startswith(prefix + ".")]:
        del sys.modules[name]


def _failed(folder: Path, data: Mapping[str, Any] | None, error: str) -> PluginInfo:
    data = data or {}

    def text(key: str, default: str) -> str:
        value = data.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else default

    api = data.get("api")
    return PluginInfo(
        ad=text("ad", folder.name),
        surum=text("surum", "?"),
        yazar=text("yazar", "?"),
        yol=folder,
        api=api if isinstance(api, int) and not isinstance(api, bool) else None,
        oyunlar=(),
        hata=error,
    )


def _load_one(folder: Path, module_name: str, taken: Mapping[str, str], builtin_names: Collection[str]) -> PluginInfo:
    data, error = read_manifest(folder)
    if data is None:
        return _failed(folder, None, error)
    problem = manifest_problem(data)
    if problem:
        return _failed(folder, data, problem)
    if data["api"] != EKLENTI_API:
        return _failed(folder, data, _api_problem(data["api"]))
    if not (folder / ENTRY_NAME).is_file():
        return _failed(folder, data, f"{ENTRY_NAME} bulunamadı. Eklenti klasöründe {ENTRY_NAME} dosyası olmalı.")
    try:
        module = _import_plugin(folder, module_name)
    except Exception as exc:  # kullanıcı kodu: her türlü hata eklenti hatası olarak raporlanır
        log.warning("Eklenti yüklenemedi: %s", folder, exc_info=True)
        return _failed(
            folder,
            data,
            f"{ENTRY_NAME} yüklenemedi ({type(exc).__name__}: {exc}). "
            "Eklentinin yazarına bildirin ya da klasörü silin.",
        )
    plugin = getattr(module, "PLUGIN", None)
    if plugin is None:
        _forget_modules(module_name)
        return _failed(folder, data, f"{ENTRY_NAME} içinde modül düzeyinde PLUGIN nesnesi yok (PLUGIN = Eklenti()).")
    missing = _contract_problems(plugin)
    if missing:
        _forget_modules(module_name)
        return _failed(
            folder,
            data,
            "PLUGIN nesnesi biçim eklentisi sözleşmesini karşılamıyor; eksik: "
            + ", ".join(missing)
            + ". FormatPluginBase'den türetmek çoğunu kendiliğinden sağlar.",
        )
    kind = str(plugin.name)
    if kind in taken and taken[kind] == data["ad"].strip():
        _forget_modules(module_name)
        return PluginInfo(
            ad=data["ad"].strip(),
            surum=data["surum"].strip(),
            yazar=data["yazar"].strip(),
            yol=folder,
            api=data["api"],
            oyunlar=tuple(g.upper() for g in data.get("oyunlar", [])),
            aciklama=data.get("aciklama", "").strip(),
            uyari="Aynı eklentinin öncelikli klasördeki kopyası kullanılıyor; bu kopya gölgelendi.",
            tur=kind,
            golge=True,
        )
    if kind in taken:
        _forget_modules(module_name)
        return _failed(
            folder,
            data,
            f"“{kind}” biçim adı “{taken[kind]}” eklentisiyle çakışıyor. İkisinden birini kaldırın "
            "ya da birinin PLUGIN.name değerini değiştirin.",
        )
    note = ""
    if kind in builtin_names:
        note = f"Yerleşik “{kind}” desteğinin yerini alıyor; bu eklenti kaldırılana kadar yerleşik olan kullanılmaz."
    return PluginInfo(
        ad=data["ad"].strip(),
        surum=data["surum"].strip(),
        yazar=data["yazar"].strip(),
        yol=folder,
        api=data["api"],
        oyunlar=tuple(g.upper() for g in data.get("oyunlar", [])),
        aciklama=data.get("aciklama", "").strip(),
        uyari=note,
        tur=kind,
        plugin=GuardedPlugin(plugin, data["ad"].strip()),
    )


def load_plugins(dirs: Sequence[Path] | None = None, builtin_names: Collection[str] | None = None) -> PluginReport:
    """Eklenti klasörlerini tarar ve yükler. Hatalı eklenti atlanır, nedeni rapora yazılır."""
    if dirs is None:
        dirs = user_plugin_dirs()
    if builtin_names is None:
        from nxceviri.core.formats.registry import BUILTIN_PLUGINS  # noqa: PLC0415 - döngüsel içe aktarma

        builtin_names = {p.name for p in BUILTIN_PLUGINS}
    for name in [n for n in sys.modules if n.startswith(MODULE_PREFIX)]:
        del sys.modules[name]
    infos: list[PluginInfo] = []
    taken: dict[str, str] = {}
    counter = 0
    for base in dirs:
        if not base.is_dir():
            continue
        for folder in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
            counter += 1
            info = _load_one(folder, f"{MODULE_PREFIX}{counter}_{slug(folder.name)}", taken, builtin_names)
            if info.yuklu and not info.golge:
                taken[info.tur] = info.ad
            infos.append(info)
    return PluginReport(tuple(infos))
