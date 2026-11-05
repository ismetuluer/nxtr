"""Komut satırı araçları: `python -m nxceviri <komut> ...` (arayüz açılmaz).

Her komut kendi modülünde yaşar ve `def ekle(sub) -> None` ile argparse alt komutunu kaydeder;
alt komutun işlevi `set_defaults(calistir=...)` ile bağlanır (`calistir(args) -> int`, çıkış kodu).
Yeni komut modülü yalnızca `KOMUT_MODULLERI`'ne eklenir.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from collections.abc import Sequence

from nxceviri.core.errors import NxError

KOMUT_MODULLERI: tuple[str, ...] = (
    "nxceviri.arac.eklenti_olustur",
    "nxceviri.arac.eklentiler",
    "nxceviri.arac.teshis",
    "nxceviri.arac.ara",
    "nxceviri.arac.dogrula",
)


def _alt_komutlari_kaydet(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    for name in KOMUT_MODULLERI:
        importlib.import_module(name).ekle(sub)


def parser_olustur() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m nxceviri", description="NXTR komut satırı araçları")
    sub = parser.add_subparsers(dest="komut", metavar="komut", required=True)
    _alt_komutlari_kaydet(sub)
    return parser


def komut_mu(argv: Sequence[str]) -> bool:
    """İlk bağımsız değişken bilinen bir komut adı (ya da yardım bayrağı) mı; değilse arayüz açılmalıdır."""
    if not argv:
        return False
    if argv[0] in ("-h", "--help"):
        return True
    sub = argparse.ArgumentParser().add_subparsers()
    _alt_komutlari_kaydet(sub)
    return argv[0] in sub.choices


def main(argv: Sequence[str]) -> int:
    """Komutu çalıştırır. Çıkış kodları: 0 başarı, 1 kullanıcı/veri hatası, 2 kullanım hatası (argparse)."""
    for akim in (sys.stdout, sys.stderr):
        # Windows konsolu varsayılan olarak Türkçe karakterleri yazamayabilir.
        if hasattr(akim, "reconfigure"):
            akim.reconfigure(encoding="utf-8", errors="replace")
    args = parser_olustur().parse_args(list(argv))
    try:
        return int(args.calistir(args))
    except NxError as exc:
        print(f"Hata: {exc.message}", file=sys.stderr)
        if exc.hint:
            print(exc.hint, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("İşlem kullanıcı tarafından durduruldu.", file=sys.stderr)
        return 1
