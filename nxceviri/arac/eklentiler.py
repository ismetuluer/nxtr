"""`eklentiler`: yüklü kullanıcı eklentilerini ve yüklenemeyenleri (nedenleriyle) listeler."""

from __future__ import annotations

import argparse
from typing import Any

from nxceviri.core.formats.registry import load_user_plugins
from nxceviri.core.plugins.imports import audit_plugin
from nxceviri.core.plugins.loader import PluginInfo, user_plugin_dirs


def ekle(sub: Any) -> None:
    parser = sub.add_parser("eklentiler", help="yüklü kullanıcı eklentilerini ve hatalarını listeler")
    parser.set_defaults(calistir=calistir)


def calistir(_args: argparse.Namespace) -> int:
    report = load_user_plugins()
    print("Eklenti klasörleri: " + "; ".join(str(d) for d in user_plugin_dirs()))
    if not report.infos:
        print("Kullanıcı eklentisi yok.")
        return 0
    for info in report.infos:
        if info.hata:
            print(f"[HATA] {info.ad} ({info.yol}): {info.hata}")
            continue
        if info.golge:
            print(f"[GÖLGE] {info.ad} ({info.yol}): {info.uyari}")
            continue
        games = f", oyunlar: {', '.join(info.oyunlar)}" if info.oyunlar else ""
        print(f"[TAMAM] {info.ad} {info.surum} — {info.yazar} (tür: {info.tur}{games})")
        if info.uyari:
            print(f"        Uyarı: {info.uyari}")
        _bulgulari_yaz(info)
    return 1 if report.errors else 0


def _bulgulari_yaz(info: PluginInfo) -> None:
    """Yüklenen eklentinin ana koddan izinsiz ya da var olmayan içe aktarmaları (yükleme hatasını hata söyler)."""
    if info.yol is None:
        return
    for bulgu in audit_plugin(info.yol):
        print(f"        İçe aktarma: {bulgu}")
