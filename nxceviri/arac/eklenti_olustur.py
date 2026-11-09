"""`eklenti-olustur <ad> [--hedef klasör]`: yeni biçim eklentisi iskeleti oluşturur."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from nxceviri.core.errors import NxError
from nxceviri.core.plugins.loader import repo_plugin_dir, user_plugin_dirs
from nxceviri.core.plugins.scaffold import create_plugin


def ekle(sub: Any) -> None:
    parser = sub.add_parser("eklenti-olustur", help="yeni bir biçim eklentisi iskeleti oluşturur")
    parser.add_argument("ad", help="eklenti adı: küçük harf, rakam ve _ (ör. oyunadi_msg)")
    parser.add_argument(
        "--hedef",
        type=Path,
        help="iskeletin yazılacağı klasör (varsayılan: kaynak kurulumda deponun eklentiler/ klasörü, "
        "paketlenmiş sürümde kullanıcı eklenti klasörü)",
    )
    parser.set_defaults(calistir=calistir)


def calistir(args: argparse.Namespace) -> int:
    root = args.hedef or repo_plugin_dir() or user_plugin_dirs()[0]
    try:
        folder = create_plugin(args.ad, root)
    except NxError as exc:
        print(exc.user_text())
        return 1
    print(f"Eklenti iskeleti oluşturuldu: {folder}")
    print(f'Testleri çalıştırmak için: python -m pytest "{folder / "tests"}"')
    print("Uygulama açılışta eklentiyi yükler; Araçlar → Eklentiler'de görünür.")
    return 0
