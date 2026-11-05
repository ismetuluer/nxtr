"""Kayıtlı format eklentileri: yerleşikler (buraya eklenerek etkinleşir) ve kullanıcı eklentileri.

Kullanıcı eklentileri açılışta bir kez `load_user_plugins()` ile yüklenir ve yerleşiklerden ÖNCE denenir."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from nxceviri.core.errors import NxError
from nxceviri.core.formats.base import FormatPlugin
from nxceviri.core.formats.danganronpa import DanganronpaPlugin
from nxceviri.core.formats.detection import KIND_LABELS, FileKind
from nxceviri.core.formats.dmc1 import Dmc1Plugin
from nxceviri.core.formats.fmsb import FmsbPlugin
from nxceviri.core.formats.gfmsg import GfMsgPlugin
from nxceviri.core.formats.m2text import M2TextPlugin
from nxceviri.core.formats.mina import MinaPlugin
from nxceviri.core.formats.msbt import MsbtPlugin
from nxceviri.core.formats.srt import SrtPlugin
from nxceviri.core.formats.unity import UnityPlugin
from nxceviri.core.formats.unreal import LocresPlugin
from nxceviri.core.formats.ysorigin import YsOriginPlugin
from nxceviri.core.plugins.loader import PluginInfo, PluginReport, load_plugins

log = logging.getLogger(__name__)

BUILTIN_PLUGINS: tuple[FormatPlugin, ...] = (
    MsbtPlugin(),
    UnityPlugin(),
    LocresPlugin(),
    GfMsgPlugin(),
    MinaPlugin(),
    Dmc1Plugin(),
    M2TextPlugin(),
    YsOriginPlugin(),
    FmsbPlugin(),
    SrtPlugin(),
    DanganronpaPlugin(),
)


#: Açılışta yüklenen kullanıcı eklentileri (yüklenmediyse boş rapor).
_user_report = PluginReport()
#: Tarama sırasında `detect` hatası verip günlüğe yazılmış eklentiler (her biri bir kez bildirilir).
_failed_detect: set[str] = set()


def load_user_plugins(dirs: Sequence[Path] | None = None) -> PluginReport:
    """Kullanıcı eklentilerini (yeniden) yükler ve kayıt defterine koyar."""
    global _user_report  # noqa: PLW0603 - uygulama genelinde tek kayıt defteri
    _failed_detect.clear()
    _user_report = load_plugins(dirs, {p.name for p in BUILTIN_PLUGINS})
    for info in _user_report.errors:
        log.warning("Eklenti yüklenemedi: %s: %s", info.ad, info.hata)
    return _user_report


def reset_user_plugins() -> None:
    """Yüklü kullanıcı eklentilerini bırakır (testler için)."""
    global _user_report  # noqa: PLW0603 - uygulama genelinde tek kayıt defteri
    _user_report = PluginReport()
    _failed_detect.clear()


def user_plugin_report() -> PluginReport:
    return _user_report


def all_plugins() -> tuple[FormatPlugin, ...]:
    """Tüm eklentiler; kullanıcı eklentileri yerleşiklerden önce gelir."""
    return (*_user_report.plugins, *BUILTIN_PLUGINS)


def plugin_for_kind(kind: str, title_id: str | None = None) -> FormatPlugin | None:
    """Tarama raporundaki tür (`ScanEntry.kind`) için eklenti; desteklenmiyorsa None.

    `title_id` verilirse, `oyunlar` sınırı bu oyunu içermeyen kullanıcı eklentileri atlanır ve yerleşik
    biçim kullanılır. Oyun bilinen her yerde (çıkarma, dışa aktarma) verilmelidir."""
    for info in _user_report.infos:
        plugin = info.plugin
        if plugin is None or plugin.name != kind:
            continue
        if title_id is None or not info.oyunlar or title_id.upper() in info.oyunlar:
            return plugin
    return next((p for p in BUILTIN_PLUGINS if p.name == kind), None)


def supported_kinds() -> set[str]:
    return {p.name for p in all_plugins()}


def user_plugin_info(kind: str) -> PluginInfo | None:
    """`kind` biçimini sağlayan yüklü kullanıcı eklentisi; yerleşik ya da yoksa None."""
    return next((i for i in _user_report.infos if i.plugin is not None and i.tur == kind), None)


def user_plugin_for_file(title_id: str, path: str, head: bytes) -> FormatPlugin | None:
    """Bu dosyayı tanıyan ilk kullanıcı eklentisi (yalnızca eklentinin oyunlarında); yoksa None."""
    for info in _user_report.infos:
        plugin = info.plugin
        if plugin is None or (info.oyunlar and title_id.upper() not in info.oyunlar):
            continue
        try:
            if plugin.detect(path, head):
                return plugin
        except NxError as exc:
            if info.ad not in _failed_detect:
                _failed_detect.add(info.ad)
                log.warning("Eklenti tarama sırasında hata verdi: %s: %s", info.ad, exc.message)
    return None


def kind_label(kind: str) -> str:
    """Tarama türünün Türkçe adı: yerleşik tür, eklenti biçimi ya da (bilinmiyorsa) türün kendi adı."""
    try:
        return KIND_LABELS[FileKind(kind)]
    except ValueError:
        plugin = plugin_for_kind(kind)
        return plugin.label if plugin is not None else kind
