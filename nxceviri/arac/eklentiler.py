"""`eklentiler`: yüklü kullanıcı eklentilerini ve yüklenemeyenleri (nedenleriyle) listeler."""

from __future__ import annotations

import argparse
from typing import Any

from nxceviri.core.formats.registry import load_user_plugins
from nxceviri.core.plugins.loader import user_plugin_dirs


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
    return 1 if report.errors else 0
