"""`font`: oyundaki fontları tarar; Türkçe harflerden eksik olanları ve ne yapılabileceğini söyler.

Arayüzdeki Kontrol Et > "Fontları Tara" ile aynı çekirdeği kullanır (`core/qa/fonts.py`). Oyun dosyalarına yazılmaz.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nxceviri.arac.ortak import IlerlemeYazici, anahtarlari_yukle
from nxceviri.core.errors import ContainerError
from nxceviri.core.pipeline import Inputs, default_cache_dir
from nxceviri.core.progress import TaskContext
from nxceviri.core.qa.fonts import FontInfo, FontVerdict, font_advice, font_verdict, scan_game_fonts


def _eksik_yaz(f: FontInfo) -> str:
    return "?" if f.chars is None else (f.missing() or "yok")


def _font_sozlugu(f: FontInfo) -> dict[str, object]:
    return {
        "ad": f.name,
        "dosya": f.source,
        "tur": f.kind,
        "dile_ozgu": f.language_specific,
        "eksik": "" if f.chars is None else f.missing(),
        "bilinmiyor": f.chars is None,
        "yamalanabilir": f.patchable,
        "ne_yapilabilir": font_advice(f),
    }


def calistir(args: argparse.Namespace) -> int:
    yollar: list[Path] = args.oyun
    yanlis = [p for p in yollar if not p.is_file()]
    if yanlis:
        raise ContainerError(
            "Şu dosyalar bulunamadı: " + ", ".join(str(p) for p in yanlis),
            "Font taraması için .nsp/.nsz dosyalarının yolunu verin (base, varsa update ve DLC).",
        )
    anahtarlar = anahtarlari_yukle(args.anahtar)
    girdi = Inputs(tuple(yollar), anahtarlar.keys, anahtarlar.title_keys, default_cache_dir())
    rapor = scan_game_fonts(girdi, TaskContext(IlerlemeYazici()))
    sonuc: FontVerdict = font_verdict(rapor)
    fontlar = sorted(rapor.fonts, key=lambda x: (x.language_specific, x.name))
    if args.json:
        print(
            json.dumps(
                {
                    "sonuc": sonuc.durum,
                    "eksik": sonuc.eksik,
                    "yamalanabilir": sonuc.yamalanabilir,
                    "kalan": sonuc.kalan,
                    "oneri": sonuc.oneri,
                    "fontlar": [_font_sozlugu(f) for f in fontlar],
                    "uyarilar": rapor.warnings,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if not fontlar:
        print("Oyunda okunabilen font bulunamadı (font bulunamadı).")
    for f in fontlar:
        dile = " — dile özgü" if f.language_specific else ""
        print(f"Font: {f.name}  [{f.kind}{dile}]")
        print(f"  Dosya: {f.source}")
        print(f"  Eksik Türkçe harfler: {_eksik_yaz(f)}")
        print(f"  Ne yapılabilir: {font_advice(f)}")
    for uyari in rapor.warnings[:10]:
        print(f"Uyarı: {uyari}")
    print()
    print(f"Sonuç: {sonuc.oneri}")
    return 0


def ekle(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "font",
        help="Oyunun fontlarında eksik Türkçe harfleri bulur ve ne yapılabileceğini söyler.",
        description=(
            "Oyun dosyalarındaki fontları tarar; ç ğ ı İ ö ş ü Ç Ğ Ö Ş Ü harflerinden eksik olanları ve font yaması "
            "ya da harf dönüştürme gerekip gerekmediğini yazar. Son satır tek satırlık sonuçtur."
        ),
        epilog='Örnek: python -m nxceviri.arac font "D:/Nintendo/Oyun.nsp" --anahtar prod.keys --json',
    )
    p.add_argument("oyun", nargs="+", type=Path, help="NSP/NSZ dosyaları (base, update, DLC)")
    p.add_argument("--anahtar", type=Path, help="prod.keys yolu (verilmezse uygulamadaki kayıtlı yol)")
    p.add_argument("--json", action="store_true", help="Aynı bilgiyi makinece okunur JSON olarak yazar")
    p.set_defaults(calistir=calistir)
