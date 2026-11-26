"""Yeni eklenti iskeleti: çalışan küçük bir örnek biçim, onun bayt bayt round-trip testi ve not şablonu.

İskelet bilerek çalışır durumdadır (satır başına `anahtar=metin` tutan uydurma bir biçim); yazar
`detect/extract/inject` gövdelerini kendi biçimiyle değiştirirken testler yol gösterici kalır.
"""

from __future__ import annotations

import re
from pathlib import Path

from nxceviri.core.formats.detection import FileKind
from nxceviri.core.formats.registry import BUILTIN_PLUGINS
from nxceviri.core.plugins.install import PluginInstallError
from nxceviri.core.plugins.loader import EKLENTI_API

_NAME = re.compile(r"^[a-z][a-z0-9_]{2,31}$")

_MANIFEST = f"""ad = "__AD__"
surum = "0.1.0"
yazar = "Adınızı yazın"
# Yalnızca bu oyunlarda denenir (16 haneli TitleID'ler). Boş liste: her oyunda denenir.
oyunlar = []
api = {EKLENTI_API}
aciklama = "Bu eklentinin hangi oyunun hangi dosyalarını çevirdiğini bir cümleyle yazın."
"""

_PLUGIN = '''"""__AD__ biçim eklentisi.

İskelet, satır başına `anahtar=metin` tutan uydurma bir biçimi çözer. Kendi biçiminiz için `detect`,
`extract` ve `inject` gövdelerini değiştirin; `tests/` içindeki round-trip testi (hiçbir şeyi
değiştirmeden çıkar → geri yaz = bayt bayt aynı dosya) eklenti bitene kadar geçmelidir.

Bütün kod bu klasörde durur; ana koda (`nxceviri/`) dosya eklenmez. Gereken yardımcıyı (arşiv okuyucu, font
yamacı, doku kodlayıcı) bu dosyanın yanına ayrı modül olarak yazıp `from . import yardimci` ile alın. Ana koddan
yalnızca docs/rehber/eklenti-yazma.md "İzinli çekirdek modülleri" listesindekiler içe aktarılır.
"""

from __future__ import annotations

from collections.abc import Mapping

from nxceviri.core.formats.base import Context, FormatError, TextEntry
from nxceviri.core.plugins import FormatPluginBase

BASLIK = b"NXORNEK\\n"


class Eklenti(FormatPluginBase):
    name = "__AD__"  # tarama raporundaki tür; benzersiz olmalı
    label = "__AD__ (örnek biçim)"
    candidates_only = False  # True: yalnızca tarama raporunda metin adayı olan dosyalar denenir
    path_suffixes = (".nxornek",)  # boş değilse yalnızca bu uzantılı dosyalar açılır

    def detect(self, path: str, head: bytes) -> bool:
        """Dosya bu eklentinin biçiminde mi? `head`, dosyanın ilk 64 baytıdır."""
        return head.startswith(BASLIK)

    def extract(self, data: bytes, context: Context | None = None) -> list[TextEntry]:
        """Çevrilecek metinleri çıkarır. `key` dosya içinde benzersiz ve kalıcı olmalıdır."""
        if not data.startswith(BASLIK):
            raise FormatError("Bu dosya __AD__ biçiminde değil.", "Başlık bulunamadı.")
        entries = []
        for index, line in enumerate(data[len(BASLIK) :].decode("utf-8").split("\\n")):
            key, sep, text = line.partition("=")
            if sep and text:
                entries.append(TextEntry(key=key, index=index, source=text, codes=()))
        return entries

    def inject(self, data: bytes, translations: Mapping[str, str]) -> bytes:
        """Yalnızca çevirisi verilen girdilerin metnini değiştirir; dosyanın geri kalanı bayt bayt aynı kalır."""
        lines = data[len(BASLIK) :].decode("utf-8").split("\\n")
        for index, line in enumerate(lines):
            key, sep, _text = line.partition("=")
            if sep and key in translations:
                if "\\n" in translations[key]:
                    raise FormatError(f"“{key}” çevirisi satır sonu içeriyor; bu biçim tek satırlık metin tutar.")
                lines[index] = f"{key}={translations[key]}"
        return BASLIK + "\\n".join(lines).encode("utf-8")


PLUGIN = Eklenti()
'''

_TEST = '''"""__AD__ eklentisi testleri. Gerçek oyun dosyası kullanılmaz; örnek elle üretilir.

Çalıştırma (uygulama klasöründen): python -m pytest eklentiler/__AD__/tests
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# plugin.py, uygulamadaki gibi paket olarak yüklenir: yanındaki modüller `from . import yardimci` ile alınabilir.
KLASOR = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "eklenti___AD__", KLASOR / "plugin.py", submodule_search_locations=[str(KLASOR)]
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
PLUGIN = MODULE.PLUGIN

ORNEK = b"NXORNEK\\nbaslik=Hello World\\nsecim_1=Yes\\n\\nsecim_2=T\\xc3\\xbcrk\\xc3\\xa7e \\xc4\\xb1\\xc5\\x9f\\n"


def test_round_trip_is_byte_identical() -> None:
    entries = PLUGIN.extract(ORNEK)
    assert PLUGIN.inject(ORNEK, {e.key: e.source for e in entries}) == ORNEK
    assert PLUGIN.inject(ORNEK, {}) == ORNEK


def test_detect_and_extract() -> None:
    assert PLUGIN.detect("a.nxornek", ORNEK[:64])
    assert not PLUGIN.detect("a.nxornek", b"BASKA")
    assert [e.key for e in PLUGIN.extract(ORNEK)] == ["baslik", "secim_1", "secim_2"]


def test_inject_changes_only_the_translated_text() -> None:
    out = PLUGIN.inject(ORNEK, {"secim_1": "Evet"})
    assert out == ORNEK.replace(b"secim_1=Yes", b"secim_1=Evet")


def test_inject_rejects_newline_in_translation() -> None:
    with pytest.raises(Exception, match="satır sonu"):
        PLUGIN.inject(ORNEK, {"secim_1": "iki\\nsatır"})
'''

_NOTE = """# __AD__ eklentisi

Oyunun haritası: **kalıcı bilgi** (ne nerede, nasıl çözüldü). Bu oyuna gelen ajan dosyaları baştan didiklemeden
önce bunu okur. Bir şey bulduğunda (işin sonunda değil) buraya yaz. Kronoloji (ne zaman ne yapıldı, sıradaki adım)
`CALISMA_GUNLUGU.md`'dedir. Oyundan uzun metin ya da resim, anahtar içeriği, kişisel yol yazılmaz (`<oyun klasörü>`).

## Oyun ve dosyalar

- TitleID, base / güncelleme sürümü:
- Arşiv yerleşimi (kapsayıcı → iç arşiv → dosya):
- Dil dosyaları nasıl ayrılıyor (klasör, son ek, dosya içi) ve kaynak dil (İngilizce) hangisi:

## Metinler nerede

<!-- Dosya → satır sayısı → kapsayan eklenti ya da kapsanmama nedeni. Başka dosyaların içine gömülü metinler
(betik, paket içi mesaj), taramanın bulmadığı yerler ve bulma yöntemi (`ara` cümlesi) dahil. -->

| Dosya / iç yol | Ne var | Satır | Durum |
|---|---|---|---|

## Biçim

- Başlık ve alanlar:
- Metin kodlaması, sonlandırıcılar, uzunluk sınırları:
- Kontrol kodları (renk, değişken, satır sonu) ve `⟦n⟧` yer tutucularına nasıl çevrildiği:
- Geri yazarken güncellenen alanlar (uzunluk, ofset, hizalama, kapsayıcı dizini):

## Fontlar

<!-- Font dosyaları ve biçimi, `arac font` sonucu (a/b/c), eksik harfler, yamanın nasıl yapıldığı, harf kodlaması
(UTF-8 değilse tablo), dönüştürmeye kalan harfler ve kanıtı. -->

## Resimdeki yazılar

<!-- Hangi arşivde hangi resimler, doku biçimi (BC1/BC7/…), aynı resmin kopyaları (birden çok konum), oyunda
gerçekten hangi kopyanın kullanıldığı, animasyon kareleri, `grafik_temizleme/orijinal` ve `turkce` durumu. -->

## Video ve program kodu

<!-- Videoya gömülü yazılar (uyarı, jenerik), program kodundaki (exefs) metinler, IPS yaması dosya adı (yapı
kimliği), base ve güncelleme ayrı mı. Yoksa "yok" yaz. -->

## Mod çıktısı

<!-- Hangi dosyalar moda giriyor, boyut, sıkıştırma, Atmosphère / emülatör yolu, sürüm bağımlılığı. -->

## Belirti → neden → çözüm

<!-- Oyunda görülen sorun (ya da araç hatası) → asıl neden → çözüm. Başka oyunda da işe yarayacak dersi oyun adı
vermeden ilgili rehbere de yaz (`docs/rehber/sorun-giderme.md`, `font.md`, `grafik.md`). -->

| Belirti | Neden | Çözüm |
|---|---|---|
"""

#: Ajanın devir günlüğü: kotası biten ajanın yerine geçen (başka sağlayıcının ajanı da olabilir) işi baştan yapmasın.
WORK_LOG = "CALISMA_GUNLUGU.md"

_WORK_LOG = """# __AD__ — çalışma günlüğü

Bu eklenti üzerinde çalışan yapay zekâ ajanının günlüğü. İşi devralan ajan **önce bu dosyayı** baştan sona okur ve
"Sıradaki adım"dan devam eder; burada yazan işleri baştan yapmaz. Her adımdan sonra (işin sonunda değil) güncellenir:
kota ya da oturum her an bitebilir. En yeni bilgi en üstteki iki bölümdedir. Kalıcı bilgi (metin, font, resim, video
nerede; nasıl çözüldü) `NOT.md`'dedir: önce onu, sonra bunu oku.

Yazılmaz: anahtar dosyası içeriği, oyundan uzun metin ya da resim, kullanıcının kişisel yolları (`<oyun klasörü>`
yaz). Bu dosya eklentinin onay parmak izine girmez; güncellemek eklentiyi yeniden onaylatmaz.

## Şimdiki durum

- Son güncelleme (tarih, ajan/model):
- Aşama (docs/rehber/yeni-oyun.md adımı):
- Çalışan / çalışmayan:

## Sıradaki adım

1.

## Yapılanlar

<!-- En yeni üstte. Her madde: ne yapıldı, hangi komut, sonucun kısa özeti (sayılar; uzun çıktı değil). -->

## Engeller ve çözümler

<!-- Engel → nasıl anlaşıldı → çözüm (ya da çözülemediyse kanıt: komut ve hata). -->

## Denenip işe yaramayanlar

<!-- Ne denendi, neden olmadı; aynı yolu yeniden denememek için. -->

## Eklenti dışındaki betikler ve dosyalar

<!-- Eklenti klasörü dışında bırakılan her şey: deneme betikleri, konum dizinleri, döküm klasörleri, kullanıcının
resim koyduğu klasörler. Her biri: yol (`<oyun klasörü>/…` ya da geçici klasör), ne yapar, nasıl yeniden çalıştırılır.
Kalıcı olması gereken betik eklentiye taşınır. -->

## Cihaz sonuçları

<!-- Kullanıcının cihazda / emülatörde denediği her mod: tarih, mod klasörü, ne çalıştı, ne İngilizce kaldı ya da
bozuk göründü (ekran görüntüsü adı), sonra ne yapıldı. -->

## Açık sorular

<!-- Kullanıcıya sorulacaklar ya da emin olunamayanlar. -->
"""


def validate_name(ad: str) -> None:
    if not _NAME.match(ad):
        raise PluginInstallError(
            f"“{ad}” geçerli bir eklenti adı değil.",
            "Ad küçük harfle başlamalı; yalnızca a-z, 0-9 ve _ içermeli; 3-32 karakter olmalı (ör. oyunadi_msg).",
        )
    reserved = {k.value for k in FileKind} | {p.name for p in BUILTIN_PLUGINS}
    if ad in reserved:
        raise PluginInstallError(f"“{ad}” yerleşik bir biçim adı.", "Farklı bir ad seçin (ör. oyunadi_msg).")


def create_plugin(ad: str, target_root: Path) -> Path:
    """`target_root/<ad>/` altına eklenti iskeletini yazar ve klasörü döndürür."""
    validate_name(ad)
    folder = target_root / ad
    if folder.exists():
        raise PluginInstallError(f"“{folder}” zaten var.", "Başka bir ad seçin ya da klasörü silin.")
    files = {
        "eklenti.toml": _MANIFEST,
        "plugin.py": _PLUGIN,
        "NOT.md": _NOTE,
        WORK_LOG: _WORK_LOG,
        f"tests/test_{ad}.py": _TEST,
    }
    try:
        for rel, template in files.items():
            path = folder / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(template.replace("__AD__", ad), encoding="utf-8", newline="\n")
    except OSError as exc:
        raise PluginInstallError(f"Eklenti iskeleti yazılamadı ({exc}).", f"Konum: {folder}") from exc
    return folder
