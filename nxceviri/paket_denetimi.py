"""Paket denetimi: `NXTR.exe --paket-denetimi <rapor.txt>` uygulamanın her modülünü içe aktarır ve sonucu dosyaya yazar.

Sürüm derlemesi (`.github/workflows/release.yml`) paketi yayımlamadan önce bunu çalıştırır: PyInstaller'ın eksik
bıraktığı bir veri dosyası ya da modül yüzünden .exe'nin açılışta çökmesi (0.79.0: etcpak → archspec JSON) böylece
derlemede yakalanır. Pencere açılmaz; hata yakalanıp rapora yazılır (çökme penceresi derlemeyi bekletmez).
Çıkış kodu: 0 her şey yüklendi, 1 en az bir modül yüklenemedi.
"""

from __future__ import annotations

import importlib
import pkgutil
import sys
import traceback
from pathlib import Path

import nxceviri


def _last_line(exc: BaseException) -> str:
    return traceback.format_exception_only(exc)[-1].strip()


def denetle() -> list[str]:
    """Yüklenemeyen modüller: "modül: hata" satırları (boşsa paket sağlam)."""
    problems: list[str] = []

    def package_failed(name: str) -> None:
        # `walk_packages` alt paketleri bulmak için paketleri kendisi içe aktarır; oradaki hata buraya gelir.
        exc = sys.exc_info()[1]
        problems.append(f"{name}: {_last_line(exc) if exc is not None else 'yüklenemedi'}")

    for module in pkgutil.walk_packages(nxceviri.__path__, "nxceviri.", onerror=package_failed):
        if module.name.endswith(".__main__"):
            continue  # giriş noktaları içe aktarılınca çalışır (`arac/__main__` komut ayrıştırır, çıkar)
        try:
            importlib.import_module(module.name)
        except Exception as exc:  # her hata rapora yazılır; denetim yarıda kesilmez
            problems.append(f"{module.name}: {_last_line(exc)}")
    return list(dict.fromkeys(problems))


def main(args: list[str]) -> int:
    try:
        problems = denetle()
    except Exception as exc:  # beklenmeyen hata da rapora: çökme penceresi derlemeyi bekletmesin
        problems = [f"denetim: {_last_line(exc)}"]
    text = "\n".join(problems) if problems else f"Tamam: NXTR {nxceviri.__version__} modülleri yüklendi."
    if args:
        Path(args[0]).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 1 if problems else 0
