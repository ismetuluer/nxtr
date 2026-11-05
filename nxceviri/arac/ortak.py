"""Araçların ortak parçaları: anahtar çözümleme, oyun kaynağı açma, iç arşivleri gezme, ilerleme yazımı.

Anahtar dosyasının yalnızca yolu işlenir; içeriği hiçbir çıktıya yazılmaz.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings

from nxceviri.core.archives import cpk, m2, nested, nni, sarc, wad, yaz0, zstd
from nxceviri.core.container.storage import FileStorage, Storage
from nxceviri.core.container.view import ContentTree
from nxceviri.core.errors import ArchiveError, ContainerError, KeyFileError
from nxceviri.core.keys import KeySet, load_keys, load_title_keys
from nxceviri.core.pipeline import Inputs, default_cache_dir, is_supported_file, opened_view
from nxceviri.core.progress import TaskContext

#: Uygulamanın QSettings anahtarları (gui/main_window.py ile aynı).
AYAR_KURULUS = "NXCeviri"
AYAR_UYGULAMA = "NXCeviri"
AYAR_PROD_KEYS = "keys/prod"
AYAR_TITLE_KEYS = "keys/title"

#: Bellekte açılıp içine bakılan arşivlerin en büyük boyutu (tarayıcıyla aynı sınır).
EN_BUYUK_ARSIV = 64 * 1024 * 1024
#: Bir eklentinin tümden okuyabileceği en büyük dosya.
EN_BUYUK_DOSYA = 512 * 1024 * 1024
ARSIV_DERINLIGI = 4
#: Dizini ayrı okunan büyük arşivler; içlerine bu araçlar bakmaz (ham baytları okunur).
UYE_ARSIVI_SONEKLERI = (".pak", cpk.SUFFIX, wad.SUFFIX, nni.INDEX_SUFFIX, m2.INDEX_SUFFIX)

_ARSIV_IMZALARI = (sarc.MAGIC, yaz0.MAGIC, zstd.MAGIC)


@dataclass
class AnahtarKaynagi:
    keys: KeySet
    title_keys: Mapping[bytes, bytes] | None


def ayardaki_yol(anahtar: str) -> Path | None:
    """Uygulamanın kayıtlı ayarından bir yol okur; yoksa None."""
    deger = QSettings(AYAR_KURULUS, AYAR_UYGULAMA).value(anahtar, "")
    return Path(str(deger)) if deger else None


def anahtarlari_yukle(anahtar_yolu: Path | None) -> AnahtarKaynagi:
    """`--anahtar` verildiyse onu, verilmediyse uygulamada seçilmiş `prod.keys` dosyasını yükler."""
    yol = anahtar_yolu or ayardaki_yol(AYAR_PROD_KEYS)
    if yol is None:
        raise KeyFileError(
            "prod.keys dosyası belirtilmedi ve uygulamada kayıtlı bir anahtar yolu bulunamadı.",
            "Komuta --anahtar <prod.keys yolu> ekleyin ya da uygulamayı açıp Dosya > Anahtarlar menüsünden "
            "prod.keys dosyasını bir kez seçin.",
        )
    keys = load_keys(yol)
    title_yolu = ayardaki_yol(AYAR_TITLE_KEYS) if anahtar_yolu is None else None
    title_keys = load_title_keys(title_yolu) if title_yolu is not None and title_yolu.is_file() else None
    return AnahtarKaynagi(keys, title_keys)


def _depoyu_kapat(storage: Storage) -> None:
    if isinstance(storage, FileStorage):
        storage.close()


@dataclass
class Dosya:
    """Bir oyun kaynağındaki üst düzey dosya."""

    yol: str  # tespit ve eklentiler için gerçek RomFS yolu
    etiket: str  # kullanıcıya gösterilen ad (birden çok içerikte kaynak başlığı eklenir)
    boyut: int
    acici: Callable[[], Storage]

    def parcalar(self) -> Iterator[bytes]:
        """Dosyayı bellekte tümden tutmadan 4 MB'lık parçalarla okur."""
        storage = self.acici()
        try:
            yield from storage.iter_chunks()
        finally:
            _depoyu_kapat(storage)

    def bas(self, n: int) -> bytes:
        storage = self.acici()
        try:
            return storage.read(0, min(n, storage.size))
        finally:
            _depoyu_kapat(storage)

    def oku(self) -> bytes:
        storage = self.acici()
        try:
            return storage.read_all()
        finally:
            _depoyu_kapat(storage)

    @property
    def arsiv_mi(self) -> bool:
        return self.boyut <= EN_BUYUK_ARSIV and arsiv_imzasi_var(self.bas(4))

    @property
    def uye_arsivi_mi(self) -> bool:
        return self.yol.lower().endswith(UYE_ARSIVI_SONEKLERI)


@dataclass
class Kaynak:
    dosyalar: list[Dosya]
    #: Kaynağın kısa tanımı (ör. "klasör: …" ya da oyun adı); raporlarda gösterilir.
    ad: str


def arsiv_imzasi_var(bas: bytes) -> bool:
    return bas.startswith(_ARSIV_IMZALARI)


def _dosya_olustur(yol: str, etiket: str, boyut: int, acici: Callable[[], Storage]) -> Dosya:
    return Dosya(yol, etiket, boyut, acici)


def _klasor_dosyalari(kok: Path) -> list[Dosya]:
    dosyalar = []
    for dizin, alt, adlar in os.walk(kok):
        alt.sort()
        for ad in sorted(adlar):
            tam = Path(dizin) / ad
            yol = tam.relative_to(kok).as_posix()

            def ac(p: Path = tam) -> Storage:
                return FileStorage(p)

            dosyalar.append(_dosya_olustur(yol, yol, tam.stat().st_size, ac))
    return dosyalar


@contextmanager
def kaynak_ac(
    yollar: list[Path], anahtar: Path | None, ilerleme: Callable[[int, int, str], None] | None = None
) -> Iterator[Kaynak]:
    """NSP/NSZ dosyalarını (anahtarla) ya da çıkarılmış bir RomFS klasörünü ortak bir görünüme açar."""
    if not yollar:
        raise ContainerError(
            "Oyun dosyası ya da klasör belirtilmedi.", "Bir veya daha fazla .nsp/.nsz ya da bir klasör verin."
        )
    if len(yollar) == 1 and yollar[0].is_dir():
        yield Kaynak(_klasor_dosyalari(yollar[0]), f"klasör: {yollar[0]}")
        return
    yanlis = [p for p in yollar if not (p.is_file() and is_supported_file(p))]
    if yanlis:
        raise ContainerError(
            "Şu girdiler oyun dosyası ya da klasör değil: " + ", ".join(p.name for p in yanlis),
            "Yalnızca .nsp/.nsz dosyaları ya da çıkarılmış bir RomFS klasörü verilebilir.",
        )
    anahtarlar = anahtarlari_yukle(anahtar)
    girdi = Inputs(tuple(yollar), anahtarlar.keys, anahtarlar.title_keys, default_cache_dir())
    with ExitStack() as stack:
        gorunum = stack.enter_context(opened_view(girdi, TaskContext(ilerleme)))
        dosyalar: list[Dosya] = []
        for sira, agac in enumerate(gorunum.trees):
            onek = "" if sira == 0 else f"[{agac.title_id}] "
            for vf in agac.view.files.values():

                def ac(a: ContentTree = agac, p: str = vf.path) -> Storage:
                    return a.view.open(p)

                dosyalar.append(_dosya_olustur(vf.path, onek + vf.path, vf.size, ac))
        yield Kaynak(dosyalar, gorunum.name or gorunum.title_id)


def ic_dosyalar(yol: str, veri: bytes, uyarilar: list[str], derinlik: int = 0) -> Iterator[tuple[str, bytes]]:
    """`veri` bir SARC/Yaz0/ZSTD ise içindeki dosyaları (ve onların içlerini) `dış>iç` yoluyla verir."""
    if derinlik >= ARSIV_DERINLIGI or len(veri) > EN_BUYUK_ARSIV or not arsiv_imzasi_var(veri[:4]):
        return
    try:
        if veri.startswith(sarc.MAGIC):
            cocuklar = [(f"{yol}{nested.SEPARATOR}{e.name}", e.data) for e in sarc.parse(veri)]
        else:
            acik = (yaz0 if veri.startswith(yaz0.MAGIC) else zstd).decompress(veri, nested.MAX_OUTPUT)
            ad = yol.rsplit(nested.SEPARATOR, 1)[-1].rsplit("/", 1)[-1]
            for sonek in (".zs", ".zst", ".szs", ".yaz0"):
                if ad.lower().endswith(sonek) and len(ad) > len(sonek):
                    ad = ad[: -len(sonek)]
                    break
            else:
                ad += " (açılmış)"
            cocuklar = [(f"{yol}{nested.SEPARATOR}{ad}", acik)]
    except ArchiveError as exc:
        uyarilar.append(f"{yol}: {exc.message}")
        return
    for cocuk_yol, cocuk in cocuklar:
        yield cocuk_yol, cocuk
        yield from ic_dosyalar(cocuk_yol, cocuk, uyarilar, derinlik + 1)


def kisalt(metin: str, sinir: int) -> str:
    """Satır sonlarını ve kontrol karakterlerini temizleyip en fazla `sinir` karaktere kısaltır."""
    temiz = "".join(c if c.isprintable() else " " for c in metin)
    temiz = " ".join(temiz.split())
    return temiz if len(temiz) <= sinir else temiz[: sinir - 1] + "…"


class IlerlemeYazici:
    """Uzun işlemlerde stderr'e en çok 2 saniyede bir ilerleme satırı yazar."""

    def __init__(self) -> None:
        self._son = 0.0

    def __call__(self, bitti: int, toplam: int, mesaj: str) -> None:
        simdi = time.monotonic()
        if simdi - self._son < 2.0:
            return
        self._son = simdi
        sayi = f"{bitti:,}/{toplam:,} " if toplam else ""
        print(f"  … {sayi}{kisalt(mesaj, 70)}", file=sys.stderr)
