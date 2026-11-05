"""`teshis`: yeni bir oyunun yapısını inceleyip `teshis-raporu.md` üretir.

Oyun dosyaları kullanıcının anahtarıyla açılır (base + update + DLC birleştirilir), tüm dosyalar taranır ve
motor, imza grupları, tanınan ve aday metin dosyaları özetlenir. Dosyalar diske çıkarılmaz, doğrudan okunur
(NCZ içerikleri uygulamanın önbelleğine açılır). Rapor oyun metni örnekleri içerir; yalnızca kullanıcının
bilgisayarında kalır.
"""

from __future__ import annotations

import argparse
import os
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from nxceviri import __version__
from nxceviri.arac.metin_sezgisi import MetinSezgisi, sezgi
from nxceviri.arac.ortak import IlerlemeYazici, anahtarlari_yukle, kisalt
from nxceviri.core.container.view import GameView
from nxceviri.core.errors import ContainerError
from nxceviri.core.formats.detection import FileKind
from nxceviri.core.formats.registry import plugin_for_kind
from nxceviri.core.formats.scanner import CONFIDENCE_LABELS, EngineGuess, ScanReport, scan_view
from nxceviri.core.pipeline import Inputs, default_cache_dir, opened_view
from nxceviri.core.progress import TaskContext

RAPOR_ADI = "teshis-raporu.md"
UYARI = "Bu rapor oyun metni örnekleri içerir; paylaşmadan önce gözden geçirin."
REHBER = "docs/rehber/yeni-oyun.md"
#: Aday metin araması için bir dosyadan okunan baş ve son parça boyutu; en çok bu kadar dosya, bu kadar saniye.
ORNEK_BOYUTU = 32 * 1024
EN_COK_ADAY_DOSYA = 1500
ADAY_BUTCESI_S = 90.0
EN_KUCUK_ADAY = 256
EN_BUYUK_ADAY = 64 * 1024 * 1024
TABLO_SATIRI = 15

#: Bilinen dosya imzaları (ilk baytlar → ad).
_IMZALAR: tuple[tuple[bytes, str], ...] = (
    (b"SARC", "SARC arşivi"),
    (b"Yaz0", "Yaz0 sıkıştırma"),
    (b"\x28\xb5\x2f\xfd", "ZSTD sıkıştırma"),
    (b"MsgS", "MsgStdBn (MSBT)"),
    (b"Unit", "UnityFS paketi"),
    (b"BNTX", "BNTX doku"),
    (b"BWAV", "BWAV ses"),
    (b"NSO0", "NSO çalıştırılabilir"),
    (b"RIFF", "RIFF (ses/video)"),
    (b"OggS", "Ogg ses"),
    (b"\x89PNG", "PNG resim"),
    (b"PK\x03\x04", "ZIP arşivi"),
    (b"\x1f\x8b", "GZIP sıkıştırma"),
    (b"\x7fELF", "ELF"),
    (b"CPK ", "CRI CPK arşivi"),
    (b"\xe1\x12\x6f\x5a", "Unreal PAK (alt bilgi imzası)"),
)


def imza_adi(bas: bytes, yol: str) -> str:
    """İlk baytlara (ve yoksa uzantıya) göre dosya imzasının adı; bilinmiyorsa boş."""
    for onek, ad in _IMZALAR:
        if bas.startswith(onek):
            return ad
    if yol.lower().endswith(".pak"):
        return "PAK (uzantıdan)"
    return ""


@dataclass
class ImzaGrubu:
    imza: bytes
    ad: str
    sayi: int = 0
    boyut: int = 0
    ornekler: list[str] = field(default_factory=list)


@dataclass
class AdayDosya:
    yol: str
    boyut: int
    sezgi: MetinSezgisi


@dataclass
class TeshisVerisi:
    oyun_adi: str
    title_id: str
    base_surum: int | None
    update_surum: int | None
    icerikler: list[tuple[str, str]]
    dosya_sayisi: int
    toplam_boyut: int
    uzantilar: list[tuple[str, int, int]]
    buyukler: list[tuple[str, int]]
    imzalar: list[ImzaGrubu]
    motor: EngineGuess
    taninanlar: list[tuple[str, int, list[str]]]
    adaylar: list[AdayDosya]
    uyarilar: list[str]
    tarama_suresi_s: float


def boyut_yaz(n: int) -> str:
    deger = float(n)
    for birim in ("B", "KB", "MB", "GB"):
        if deger < 1024 or birim == "GB":
            return f"{deger:.0f} {birim}" if birim == "B" else f"{deger:.1f} {birim}"
        deger /= 1024
    return f"{n} B"


def _uzanti(yol: str) -> str:
    ad = yol.rsplit("/", 1)[-1]
    return ad[ad.rfind(".") :].lower() if "." in ad.strip(".") else "(uzantısız)"


def _imza_gruplari(gorunum: GameView, ctx: TaskContext) -> list[ImzaGrubu]:
    gruplar: dict[bytes, ImzaGrubu] = {}
    toplam = gorunum.file_count
    sira = 0
    for agac in gorunum.trees:
        for vf in agac.view.files.values():
            ctx.report(sira, toplam, f"İmzalar okunuyor: {vf.path}")
            sira += 1
            bas = agac.view.open(vf.path).read(0, min(4, vf.size)) if vf.size else b""
            grup = gruplar.setdefault(bas, ImzaGrubu(bas, imza_adi(bas, vf.path)))
            grup.sayi += 1
            grup.boyut += vf.size
            if len(grup.ornekler) < 3:
                grup.ornekler.append(vf.path)
    return sorted(gruplar.values(), key=lambda g: (-g.sayi, g.imza))


def _aday_dosyalar(gorunum: GameView, rapor: ScanReport, ctx: TaskContext, uyarilar: list[str]) -> list[AdayDosya]:
    """Tanınmayan üst düzey dosyaların baş ve son kısmında UTF-8 / UTF-16LE metin yoğunluğunu arar."""
    boyutlar = {(a.title_id, a.path): a for a in rapor.entries if ">" not in a.path}
    hedefler = sorted(
        (e for e in boyutlar.values() if e.kind == FileKind.OTHER.value and EN_KUCUK_ADAY <= e.size <= EN_BUYUK_ADAY),
        key=lambda e: -e.size,
    )
    if len(hedefler) > EN_COK_ADAY_DOSYA:
        uyarilar.append(
            f"Tanınmayan {len(hedefler):,} dosyadan yalnızca en büyük {EN_COK_ADAY_DOSYA:,} tanesi örneklendi."
        )
        hedefler = hedefler[:EN_COK_ADAY_DOSYA]
    agaclar = {a.title_id: a for a in gorunum.trees}
    baslangic = time.monotonic()
    adaylar: list[AdayDosya] = []
    for sira, e in enumerate(hedefler):
        ctx.report(sira, len(hedefler), f"Metin aranıyor: {e.path}")
        if time.monotonic() - baslangic > ADAY_BUTCESI_S:
            uyarilar.append(f"Metin örneklemesi {ADAY_BUTCESI_S:.0f} saniyelik süre sınırında kesildi.")
            break
        depo = agaclar[e.title_id].view.open(e.path)
        ornek = depo.read(0, min(ORNEK_BOYUTU, depo.size))
        if depo.size > 2 * ORNEK_BOYUTU:
            ornek += depo.read(depo.size - ORNEK_BOYUTU, ORNEK_BOYUTU)
        bulunan = sezgi(ornek)
        if bulunan is not None:
            adaylar.append(AdayDosya(e.path, e.size, bulunan))
    return sorted(adaylar, key=lambda a: -a.sezgi.yogunluk)


def veri_topla(gorunum: GameView, ctx: TaskContext) -> TeshisVerisi:
    rapor = scan_view(gorunum, ctx)
    uyarilar = list(rapor.warnings)
    dosyalar = [vf for agac in gorunum.trees for vf in agac.view.files.values()]
    uzanti_say: Counter[str] = Counter()
    uzanti_boyut: Counter[str] = Counter()
    for vf in dosyalar:
        uzanti_say[_uzanti(vf.path)] += 1
        uzanti_boyut[_uzanti(vf.path)] += vf.size
    taninan: dict[str, list[str]] = {}
    for e in rapor.entries:
        eklenti = plugin_for_kind(e.kind, e.title_id)
        if eklenti is not None:
            taninan.setdefault(eklenti.label, []).append(e.path)
    return TeshisVerisi(
        oyun_adi=gorunum.name,
        title_id=gorunum.title_id,
        base_surum=gorunum.base_version,
        update_surum=gorunum.update_version,
        icerikler=[(a.label, a.title_id) for a in gorunum.trees],
        dosya_sayisi=len(dosyalar),
        toplam_boyut=sum(vf.size for vf in dosyalar),
        uzantilar=[(u, n, uzanti_boyut[u]) for u, n in uzanti_say.most_common()],
        buyukler=[(vf.path, vf.size) for vf in sorted(dosyalar, key=lambda v: -v.size)[:20]],
        imzalar=_imza_gruplari(gorunum, ctx),
        motor=rapor.engine,
        taninanlar=[(ad, len(yollar), yollar[:5]) for ad, yollar in sorted(taninan.items())],
        adaylar=_aday_dosyalar(gorunum, rapor, ctx, uyarilar),
        uyarilar=uyarilar,
        tarama_suresi_s=rapor.duration_s,
    )


def _hucre(metin: str) -> str:
    return metin.replace("|", "\\|").replace("\n", " ")


def _yol(yol: str) -> str:
    return f"`{_hucre(yol)}`"


def _imza_yaz(imza: bytes) -> str:
    yazi = "".join(chr(b) if 0x20 <= b < 0x7F else "." for b in imza)
    return f"`{imza.hex(' ').upper()}` ({_hucre(yazi)})" if imza else "(boş dosya)"


def _surum(deger: int | None) -> str:
    return "yok" if deger is None else f"v{deger}"


def sonraki_adim(veri: TeshisVerisi) -> list[str]:
    adimlar = []
    if veri.taninanlar:
        adimlar.append(
            "Uygulama bu oyundaki bazı dosyaları zaten tanıyor: uygulamada Metinleri Tara adımından devam edin, "
            "ardından Metinleri Çeviri Tablosuna Aktar'ı deneyin."
        )
    if veri.adaylar:
        adimlar.append(
            "Aday metin dosyalarındaki örnek satırları oyundaki metinlerle karşılaştırın; tanıdığınız bir satırı "
            '`python -m nxceviri.arac ara "<cümle>" <oyun dosyaları>` ile bütün dosyalarda arayın.'
        )
    else:
        adimlar.append(
            'Oyunda ekranda gördüğünüz bir cümleyi `python -m nxceviri.arac ara "<cümle>" <oyun dosyaları> '
            "--harf-duyarsiz` ile arayın; bulunamıyorsa metin sıkıştırılmış ya da başka bir kodlamada olabilir."
        )
    adimlar.append(f"Yeni bir biçim çıkarsa eklenti yazın ve `dogrula` ile doğrulayın; ayrıntı: `{REHBER}`.")
    return adimlar


def rapor_metni(veri: TeshisVerisi) -> str:
    s: list[str] = []
    s += [f"# Teşhis raporu: {veri.oyun_adi or 'Adsız oyun'}", "", f"> {UYARI}", ""]
    s += ["## Sürümler", "", f"- Ana TitleID: `{veri.title_id}`"]
    s += [f"- Ana oyun: {_surum(veri.base_surum)}", f"- Güncelleme: {_surum(veri.update_surum)}"]
    s += [f"- İçerik: {ad}" + ("" if tid in ad else f" (`{tid}`)") for ad, tid in veri.icerikler]
    s += ["", "## Genel", ""]
    s += [f"- Dosya sayısı: {veri.dosya_sayisi:,}", f"- Toplam boyut: {boyut_yaz(veri.toplam_boyut)}"]
    s += [f"- Tarama süresi: {veri.tarama_suresi_s:.1f} saniye", ""]

    s += ["## Uzantı dağılımı", "", "| Uzantı | Dosya | Boyut |", "|---|---:|---:|"]
    for uzanti, sayi, boyut in veri.uzantilar[:TABLO_SATIRI]:
        s.append(f"| `{_hucre(uzanti)}` | {sayi:,} | {boyut_yaz(boyut)} |")
    if len(veri.uzantilar) > TABLO_SATIRI:
        geri = veri.uzantilar[TABLO_SATIRI:]
        sayi, boyut = sum(n for _u, n, _b in geri), sum(b for _u, _n, b in geri)
        s.append(f"| diğer ({len(geri)} uzantı) | {sayi:,} | {boyut_yaz(boyut)} |")

    s += ["", "## En büyük 20 dosya", "", "| Dosya | Boyut |", "|---|---:|"]
    s += [f"| {_yol(yol)} | {boyut_yaz(boyut)} |" for yol, boyut in veri.buyukler]

    s += [
        "",
        "## İmza grupları (ilk 4 bayt)",
        "",
        "| İmza | Tür | Dosya | Boyut | Örnekler |",
        "|---|---|---:|---:|---|",
    ]
    for g in veri.imzalar[:TABLO_SATIRI]:
        ornek = ", ".join(_yol(y) for y in g.ornekler)
        s.append(f"| {_imza_yaz(g.imza)} | {_hucre(g.ad) or '—'} | {g.sayi:,} | {boyut_yaz(g.boyut)} | {ornek} |")
    if len(veri.imzalar) > TABLO_SATIRI:
        s.append(f"\n({len(veri.imzalar) - TABLO_SATIRI} imza grubu daha var.)")

    motor = veri.motor
    s += ["", "## Motor tahmini", "", f"**{motor.label}** (güven: {CONFIDENCE_LABELS[motor.confidence]})", ""]
    s += [f"- {kanit}" for kanit in motor.evidence] or ["- Bilinen bir motorun izine rastlanmadı."]

    s += ["", "## Uygulamanın tanıdığı dosyalar", ""]
    if veri.taninanlar:
        s += [
            f"- {ad}: {sayi:,} dosya (ör. {', '.join(_yol(y) for y in ornek)})" for ad, sayi, ornek in veri.taninanlar
        ]
    else:
        s.append("- Mevcut eklentilerin tanıdığı bir dosya yok.")

    s += ["", "## Aday metin dosyaları", ""]
    if veri.adaylar:
        s.append("Tanınmayan dosyalarda UTF-8 / UTF-16LE metin yoğunluğuna göre sezgisel tahmin; en yoğun 30 dosya:")
        for a in veri.adaylar[:30]:
            s += [
                "",
                f"- {_yol(a.yol)} ({boyut_yaz(a.boyut)}, {a.sezgi.kodlama}, yoğunluk %{a.sezgi.yogunluk * 100:.0f})",
            ]
            s += [f"  - `{_hucre(kisalt(o, 80))}`" for o in a.sezgi.ornekler]
    else:
        s.append("Tanınmayan dosyalarda okunabilir UTF-8 / UTF-16LE metin yoğunluğu bulunamadı.")

    if veri.uyarilar:
        s += ["", "## Uyarılar", ""]
        s += [f"- {_hucre(kisalt(u, 200))}" for u in veri.uyarilar[:20]]
        if len(veri.uyarilar) > 20:
            s.append(f"- … ve {len(veri.uyarilar) - 20} uyarı daha.")

    s += ["", "## Sonraki adım", ""]
    s += [f"{i}. {adim}" for i, adim in enumerate(sonraki_adim(veri), 1)]
    s.append("")
    return "\n".join(s)


def rapor_uret(girdi: Inputs, cikti_klasoru: Path, ctx: TaskContext) -> Path:
    """Raporu `cikti_klasoru/teshis-raporu.md` olarak yazar (önce geçici dosya, sonra yerine taşıma)."""
    with opened_view(girdi, ctx) as gorunum:
        veri = veri_topla(gorunum, ctx)
    try:
        cikti_klasoru.mkdir(parents=True, exist_ok=True)
        hedef = cikti_klasoru / RAPOR_ADI
        gecici = cikti_klasoru / f".{RAPOR_ADI}.{uuid.uuid4().hex[:8]}.gecici"
        gecici.write_text(rapor_metni(veri), encoding="utf-8")
        os.replace(gecici, hedef)
    except OSError as exc:
        raise ContainerError(
            f"Rapor yazılamadı: {cikti_klasoru}", f"Klasörün yazılabilir olduğundan emin olun. ({exc.strerror})"
        ) from None
    return hedef


def calistir(args: argparse.Namespace) -> int:
    yollar: list[Path] = args.oyun
    yanlis = [p for p in yollar if not p.is_file()]
    if yanlis:
        raise ContainerError(
            "Şu dosyalar bulunamadı: " + ", ".join(str(p) for p in yanlis),
            "Teşhis için .nsp/.nsz dosyalarının yolunu verin (base, varsa update ve DLC).",
        )
    anahtarlar = anahtarlari_yukle(args.anahtar)
    girdi = Inputs(tuple(yollar), anahtarlar.keys, anahtarlar.title_keys, default_cache_dir())
    hedef = rapor_uret(girdi, args.cikti, TaskContext(IlerlemeYazici()))
    print(f"Teşhis raporu yazıldı: {hedef}")
    print(UYARI)
    return 0


def ekle(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "teshis",
        help="Yeni bir oyunu inceleyip teshis-raporu.md üretir.",
        description=f"Oyun dosyalarını açar, taramayı yapar ve {RAPOR_ADI} yazar. Araç sürümü: {__version__}.",
    )
    p.add_argument("oyun", nargs="+", type=Path, help="NSP/NSZ dosyaları (base, update, DLC)")
    p.add_argument("--anahtar", type=Path, help="prod.keys yolu (verilmezse uygulamadaki kayıtlı yol)")
    p.add_argument("--cikti", type=Path, default=Path.cwd(), help="Raporun yazılacağı klasör (varsayılan: bu klasör)")
    p.set_defaults(calistir=calistir)
