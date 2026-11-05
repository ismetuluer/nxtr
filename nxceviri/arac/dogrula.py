"""`dogrula`: bir format eklentisini gerçek oyun dosyalarında sınar.

1. Değişikliksiz `extract` -> `inject` sonucu orijinalle bayt bayt aynı olmalı.
2. En çok 3 girdiye işaret metni yazılıp `inject` -> `extract` ile geri okunur; işaretli girdiler işareti
   taşımalı, diğerleri değişmemeli.

Orijinal dosyalara hiçbir zaman yazılmaz; her şey bellekte yapılır.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path

from nxceviri.arac.ortak import EN_BUYUK_DOSYA, Dosya, IlerlemeYazici, ic_dosyalar, kaynak_ac, kisalt
from nxceviri.core.errors import ContainerError
from nxceviri.core.formats import registry
from nxceviri.core.formats.base import SOURCE_LANGUAGE, SOURCE_PATH, FormatPlugin, TextEntry

ISARET_SAYISI = 3
_YER_TUTUCU = re.compile(r"⟦\d+⟧")


@dataclass(frozen=True)
class DosyaSonucu:
    yol: str
    gecti: bool
    girdi_sayisi: int
    ayrinti: str = ""


def tum_eklentiler() -> tuple[FormatPlugin, ...]:
    return registry.all_plugins()


def eklenti_bul(ad: str) -> FormatPlugin:
    eklentiler = tum_eklentiler()
    for e in eklentiler:
        if e.name == ad:
            return e
    raise ContainerError(
        f"'{ad}' adlı bir eklenti yok.",
        "Kayıtlı eklentiler: " + ", ".join(sorted(e.name for e in eklentiler)) + ".",
    )


def ilk_fark(a: bytes, b: bytes) -> int:
    """İki baytın ilk farklı olduğu ofset; biri diğerinin başı ise kısa olanın uzunluğu."""
    ortak = min(len(a), len(b))
    blok = 65536
    for bas in range(0, ortak, blok):
        if a[bas : bas + blok] != b[bas : bas + blok]:
            parca_a, parca_b = a[bas : bas + blok], b[bas : bas + blok]
            return bas + next(
                (i for i, (x, y) in enumerate(zip(parca_a, parca_b, strict=False)) if x != y),
                min(len(parca_a), len(parca_b)),
            )
    return ortak


def adaylar(
    eklenti: FormatPlugin, dosyalar: list[Dosya], uyarilar: list[str], atlanan: list[str]
) -> Iterator[tuple[str, bytes]]:
    """Eklentinin `detect`'inin kabul ettiği (yol, veri) çiftleri; arşivlerin içi de gezilir."""

    def uygun(yol: str, bas: bytes) -> bool:
        if eklenti.path_suffixes and not yol.lower().endswith(eklenti.path_suffixes):
            return False
        return eklenti.detect(yol, bas[:64])

    for dosya in dosyalar:
        if dosya.boyut > EN_BUYUK_DOSYA:
            if uygun(dosya.yol, dosya.bas(64)):
                atlanan.append(f"{dosya.etiket}: çok büyük ({dosya.boyut:,} bayt); atlandı.")
            continue
        veri = dosya.oku()
        if uygun(dosya.yol, veri):
            yield dosya.yol, veri
        for yol, ic in ic_dosyalar(dosya.etiket, veri, uyarilar):
            if uygun(yol, ic):
                yield yol, ic


def _isaret(sira: int, giris: TextEntry) -> str | None:
    """Girdiye yazılacak işaret metni (kontrol kodu yer tutucuları korunur); sığmıyorsa None."""
    metin = f"NXTR-DOGRULAMA-{sira}" + "".join(_YER_TUTUCU.findall(giris.source))
    return None if giris.max_length is not None and len(metin) > giris.max_length else metin


def dosya_dogrula(eklenti: FormatPlugin, yol: str, veri: bytes, baglam: Mapping[object, object]) -> DosyaSonucu:
    """Tek dosyada bayt eşitliği ve işaret metni sınamalarını yapar."""
    ortam = {**baglam, SOURCE_LANGUAGE: None, SOURCE_PATH: yol}
    try:
        girdiler = eklenti.extract(veri, ortam)
        ayni = eklenti.inject(veri, {g.key: g.source for g in girdiler})
        if ayni != veri:
            fark = ilk_fark(veri, ayni)
            return DosyaSonucu(
                yol,
                False,
                len(girdiler),
                f"değişikliksiz extract->inject sonucu orijinalden farklı (ilk fark ofseti {fark:#x}, "
                f"boyut {len(veri):,} -> {len(ayni):,})",
            )
        secilen = [(g, m) for i, g in enumerate(girdiler, 1) if (m := _isaret(i, g)) is not None][:ISARET_SAYISI]
        if not secilen:
            return DosyaSonucu(
                yol, True, len(girdiler), "bayt eşitliği geçti; işaret metni sınaması yapılamadı (girdi yok/sığmadı)"
            )
        isaretli = eklenti.inject(veri, {g.key: m for g, m in secilen})
        geri = {g.key: g.source for g in eklenti.extract(isaretli, ortam)}
        secili_anahtarlar = {g.key for g, _m in secilen}
        for g, m in secilen:
            if geri.get(g.key) != m:
                return DosyaSonucu(
                    yol,
                    False,
                    len(girdiler),
                    f"işaret metni geri okunamadı: '{g.key}' için beklenen {m!r}, "
                    f"okunan {kisalt(str(geri.get(g.key)), 60)!r}",
                )
        for g in girdiler:
            if g.key not in secili_anahtarlar and geri.get(g.key) != g.source:
                return DosyaSonucu(yol, False, len(girdiler), f"işaretlenmeyen '{g.key}' girdisi de değişti")
    except Exception as exc:
        neden = getattr(exc, "message", None) or str(exc) or type(exc).__name__
        return DosyaSonucu(yol, False, 0, f"eklenti hata verdi ({type(exc).__name__}): {kisalt(neden, 160)}")
    return DosyaSonucu(yol, True, len(girdiler), "")


def dogrula(
    eklenti: FormatPlugin, dosyalar: list[Dosya], ilerleme: IlerlemeYazici | None = None
) -> tuple[list[DosyaSonucu], list[str]]:
    """Eklentiyi kabul ettiği tüm dosyalarda sınar; (sonuçlar, uyarılar) döndürür."""
    uyarilar: list[str] = []
    atlanan: list[str] = []
    baglam: dict[object, object] = {}
    for yol, veri in adaylar(eklenti, dosyalar, uyarilar, atlanan):
        try:
            baglam.update(eklenti.collect_context(veri, yol))
        except Exception as exc:
            uyarilar.append(f"{yol}: bağlam toplanamadı ({type(exc).__name__}: {kisalt(str(exc), 120)})")
    sonuclar = []
    for sira, (yol, veri) in enumerate(adaylar(eklenti, dosyalar, [], []), 1):  # uyarılar ilk geçişte toplandı
        if ilerleme is not None:
            ilerleme(sira, 0, yol)
        sonuclar.append(dosya_dogrula(eklenti, yol, veri, baglam))
    return sonuclar, [*atlanan, *uyarilar]


def calistir(args: argparse.Namespace) -> int:
    eklenti = eklenti_bul(args.eklenti)
    with kaynak_ac(args.oyun, args.anahtar) as kaynak:
        sonuclar, uyarilar = dogrula(eklenti, kaynak.dosyalar, IlerlemeYazici())
    for s in sonuclar:
        durum = "GEÇTİ" if s.gecti else "KALDI"
        satir = f"{durum}  {s.yol}  ({s.girdi_sayisi:,} girdi)"
        print(satir + (f"  {s.ayrinti}" if s.ayrinti else ""))
    for uyari in uyarilar[:10]:
        print(f"Uyarı: {uyari}")
    kalan = [s for s in sonuclar if not s.gecti]
    print(f"\nÖzet: {len(sonuclar):,} dosya sınandı, {len(sonuclar) - len(kalan):,} geçti, {len(kalan):,} kaldı.")
    if not sonuclar:
        print(f"'{eklenti.name}' eklentisi hiçbir dosyayı tanımadı; detect() işlevini kontrol edin.")
        return 1
    return 1 if kalan else 0


def ekle(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "dogrula",
        help="Bir eklentiyi gerçek dosyalarda sınar (bayt eşitliği + işaret metni).",
        description="Eklentinin tanıdığı dosyalarda extract->inject bayt eşitliğini ve işaret metnini sınar.",
    )
    p.add_argument("eklenti", help="Eklenti adı (ör. msbt)")
    p.add_argument("oyun", nargs="+", type=Path, help="NSP/NSZ dosyaları ya da çıkarılmış RomFS klasörü")
    p.add_argument("--anahtar", type=Path, help="prod.keys yolu (verilmezse uygulamadaki kayıtlı yol)")
    p.set_defaults(calistir=calistir)
