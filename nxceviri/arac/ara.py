"""`ara`: ekranda görülen bir cümleyi oyun dosyalarında farklı kodlamalarla arar.

UTF-8, UTF-16LE, UTF-16BE ve Shift-JIS aranır; SARC/Yaz0/ZSTD arşivlerinin içine özyinelemeli bakılır.
Dizini ayrı okunan büyük arşivlerin (pak, CPK, WAD, NNI, M2) içine bakılmaz; yalnızca ham baytları taranır
ve bu çıktıda belirtilir. Oyun dosyalarına yazılmaz.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from nxceviri.arac.ortak import Dosya, IlerlemeYazici, ic_dosyalar, kaynak_ac, kisalt
from nxceviri.core.errors import ContainerError

KODLAMALAR = (("UTF-8", "utf-8"), ("UTF-16LE", "utf-16-le"), ("UTF-16BE", "utf-16-be"), ("Shift-JIS", "shift_jis"))
VARSAYILAN_EN_FAZLA = 200
#: Bulgunun iki yanında gösterilen karakter sayısı.
KESIT_KARAKTER = 24


@dataclass(frozen=True)
class Bulgu:
    dosya: str  # iç içe arşivlerde "dış>iç" biçiminde
    ofset: int
    kodlama: str
    kesit: str


class Aranan:
    """Bir metnin tüm kodlamalardaki bayt desenleri."""

    def __init__(self, metin: str, harf_duyarsiz: bool) -> None:
        if not metin:
            raise ContainerError("Aranacak metin boş.", "Ekranda gördüğünüz bir cümleden birkaç kelime yazın.")
        gruplu: dict[bytes, tuple[list[str], str]] = {}
        for etiket, kodlama in KODLAMALAR:
            desen = self._desen(metin, kodlama, harf_duyarsiz)
            if desen is None:
                continue
            anahtar = desen.pattern
            if anahtar in gruplu:
                gruplu[anahtar][0].append(etiket)
            else:
                gruplu[anahtar] = ([etiket], kodlama)
        if not gruplu:
            raise ContainerError(
                "Bu metin hiçbir desteklenen kodlamada yazılamıyor.", "Metinde olağandışı karakterler olabilir."
            )
        self.desenler = [(" / ".join(e), re.compile(a), k) for a, (e, k) in gruplu.items()]
        self.en_uzun = max(self._en_uzun(metin, k, harf_duyarsiz) for _e, _d, k in self.desenler)

    @staticmethod
    def _bicimler(karakter: str, harf_duyarsiz: bool) -> list[str]:
        adaylar = {karakter}
        if harf_duyarsiz:
            adaylar |= {karakter.lower(), karakter.upper()}
        return sorted(c for c in adaylar if len(c) == 1)

    @classmethod
    def _desen(cls, metin: str, kodlama: str, harf_duyarsiz: bool) -> re.Pattern[bytes] | None:
        parcalar = []
        for karakter in metin:
            kodlu = []
            for bicim in cls._bicimler(karakter, harf_duyarsiz):
                try:
                    kodlu.append(re.escape(bicim.encode(kodlama)))
                except UnicodeEncodeError:
                    continue
            if not kodlu:
                return None
            parcalar.append(b"(?:" + b"|".join(sorted(set(kodlu))) + b")")
        return re.compile(b"".join(parcalar))

    @classmethod
    def _en_uzun(cls, metin: str, kodlama: str, harf_duyarsiz: bool) -> int:
        toplam = 0
        for karakter in metin:
            toplam += max(
                (len(b.encode(kodlama)) for b in cls._bicimler(karakter, harf_duyarsiz) if _kodlanabilir(b, kodlama)),
                default=0,
            )
        return toplam

    def tara(self, parcalar: Iterable[bytes]) -> Iterator[tuple[int, str, str]]:
        """Parçalı veride bulguları (ofset, kodlama, kesit) verir; parça sınırındaki eşleşmeler kaçmaz."""
        kuyruk = b""
        konum = 0
        for parca in parcalar:
            tampon = kuyruk + parca
            taban = konum - len(kuyruk)
            for etiket, desen, kodlama in self.desenler:
                for m in desen.finditer(tampon):
                    if m.end() <= len(kuyruk):
                        continue  # önceki turda zaten görüldü
                    yield taban + m.start(), etiket, _kesit(tampon, m.start(), m.end(), kodlama)
            konum += len(parca)
            kuyruk = tampon[-(self.en_uzun - 1) :] if self.en_uzun > 1 else b""


def _kodlanabilir(karakter: str, kodlama: str) -> bool:
    try:
        karakter.encode(kodlama)
    except UnicodeEncodeError:
        return False
    return True


def _kesit(tampon: bytes, bas: int, son: int, kodlama: str) -> str:
    birim = 2 if kodlama.startswith("utf-16") else 1
    onceki = max(bas - KESIT_KARAKTER * birim, bas % birim)
    onceki += (bas - onceki) % birim
    sonraki = son + KESIT_KARAKTER * birim
    sonraki -= (sonraki - son) % birim
    sol = tampon[onceki:bas].decode(kodlama, errors="replace")
    orta = tampon[bas:son].decode(kodlama, errors="replace")
    sag = tampon[son:sonraki].decode(kodlama, errors="replace")
    return kisalt(f"{sol}[{orta}]{sag}", 3 * KESIT_KARAKTER + len(orta))


def dosyada_ara(aranan: Aranan, dosya: Dosya, uyarilar: list[str]) -> list[Bulgu]:
    """Üst düzey bir dosyada ve (arşivse) içindeki dosyalarda arar."""
    bulgular = [Bulgu(dosya.etiket, o, k, s) for o, k, s in sorted(aranan.tara(dosya.parcalar()))]
    if dosya.arsiv_mi:
        for yol, veri in ic_dosyalar(dosya.etiket, dosya.oku(), uyarilar):
            bulgular.extend(Bulgu(yol, o, k, s) for o, k, s in sorted(aranan.tara([veri])))
    return bulgular


def ara(
    aranan: Aranan, dosyalar: list[Dosya], en_fazla: int, ilerleme: IlerlemeYazici | None = None
) -> tuple[list[Bulgu], list[str], bool]:
    """Tüm dosyalarda arar; (bulgular, uyarılar, sınıra takıldı mı) döndürür."""
    bulgular: list[Bulgu] = []
    uyarilar: list[str] = []
    for sira, dosya in enumerate(dosyalar):
        if ilerleme is not None:
            ilerleme(sira, len(dosyalar), dosya.etiket)
        bulgular.extend(dosyada_ara(aranan, dosya, uyarilar))
        if len(bulgular) >= en_fazla:
            return bulgular[:en_fazla], uyarilar, True
    return bulgular, uyarilar, False


def calistir(args: argparse.Namespace) -> int:
    aranan = Aranan(args.metin, args.harf_duyarsiz)
    yollar: list[Path] = args.oyun
    with kaynak_ac(yollar, args.anahtar) as kaynak:
        print(f"Aranıyor: {args.metin!r} ({kaynak.ad}, {len(kaynak.dosyalar):,} dosya)", file=sys.stderr)
        bulgular, uyarilar, kesildi = ara(aranan, kaynak.dosyalar, args.en_fazla, IlerlemeYazici())
        atlanan = [d.etiket for d in kaynak.dosyalar if d.uye_arsivi_mi]
    for b in bulgular:
        print(f"{b.dosya}  ofset {b.ofset:#x}  {b.kodlama}  {b.kesit}")
    print(f"\n{len(bulgular):,} bulgu.")
    if kesildi:
        print(f"Bulgu sayısı sınıra ({args.en_fazla}) ulaştı; daha uzun bir metin deneyin ya da --en-fazla artırın.")
    if atlanan:
        print(
            f"Not: {len(atlanan):,} büyük arşivin içine bakılmadı, yalnızca ham baytları arandı "
            f"(ör. {atlanan[0]}). Metin bunların içinde sıkıştırılmışsa bulunamaz."
        )
    for uyari in uyarilar[:10]:
        print(f"Uyarı: {uyari}")
    if not bulgular:
        print(
            "Metin hiçbir dosyada bulunamadı. Metin sıkıştırılmış, şifrelenmiş ya da grafik olarak saklanıyor olabilir."
        )
        return 1
    return 0


def ekle(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "ara",
        help="Bir metni oyun dosyalarında ve iç içe arşivlerde arar.",
        description="Metni UTF-8, UTF-16LE, UTF-16BE ve Shift-JIS olarak arar; SARC/Yaz0/ZSTD içlerine de bakar.",
    )
    p.add_argument("metin", help="Ekranda gördüğünüz cümle ya da kelimeler")
    p.add_argument("oyun", nargs="+", type=Path, help="NSP/NSZ dosyaları ya da çıkarılmış RomFS klasörü")
    p.add_argument("--anahtar", type=Path, help="prod.keys yolu (verilmezse uygulamadaki kayıtlı yol)")
    p.add_argument("--harf-duyarsiz", action="store_true", help="Büyük/küçük harf ayrımı yapma")
    p.add_argument("--en-fazla", type=int, default=VARSAYILAN_EN_FAZLA, help="En çok bu kadar bulgu yaz")
    p.set_defaults(calistir=calistir)
