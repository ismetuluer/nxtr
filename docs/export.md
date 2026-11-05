# Kontrol ve dışa aktarma (M5)

Kod: `nxceviri/core/qa/` (fonts, transliterate, checks), `nxceviri/core/export/layeredfs.py`.

## Font glif denetimi

- **Unity / TextMeshPro:** `TMP_FontAsset`'lerin `m_CharacterTable`'ı okunur. Statik atlaslar
  (`m_AtlasPopulationMode = 0`) yalnızca tablodaki karakterleri çizer. Dinamik atlasların (`1`)
  kaynak fontu (`m_SourceFontFile` → Unity `Font` nesnesindeki TTF) fontTools ile okunur.
- **TTF/OTF:** RomFS'teki dosyalar ve Unity `Font` nesneleri fontTools ile.
- Dile özgü fontlar (dosya/ad: japanese, chinese, russian…) hesaba katılmaz.
- "Eksik harf" = Latin statik fontların yarısından fazlasında olmayan harf.

**Silver Pines:** 13 Latin statik font; `ç ö ü Ç Ö Ü` 11/13 fontta var, `ğ ı İ ş Ğ Ş` yalnızca
2–3 fontta. Dinamik yedek "LiberationSans SDF - Fallback" fontunun kaynağı (LiberationSans TTF)
tüm Türkçe harfleri içeriyor. Oyun TMP yedek font zincirini kullanıyorsa eksik harfler bu fontla
(farklı görünümde) çizilebilir; kullanmıyorsa kutucuk/boşluk çıkar. Gerçek cihazda denenmeli.

## Harf dönüştürme

Seçenekler: yok / yalnızca eksik harfler / tüm Türkçe harfler. Yalnızca üretilen moda uygulanır;
projedeki çeviriler değişmez.

## Font yaması (M8)

Kontrol Et ekranındaki seçenek açıksa dışa aktarırken oyunun Latin TextMeshPro font bundle'larına
eksik `ı İ ş Ş ğ Ğ` harfleri eklenir (ayrıntı: `docs/formats/tmp-font.md`). Değişen font bundle'ları
moda yazılır; eklenen/eklenemeyen harfler bilgi dosyasında listelenir. Açıkken "yalnızca eksik
harfleri dönüştür" seçeneği yalnızca yamanın ekleyemediği harfleri dönüştürür.

## Satır denetimleri

Kontrol kodu (hata), uzunluk sınırı (hata), eksik harf, olası taşma (çeviri ≥ %60 uzun ve
orijinal ≥ 25 karakter), satır sonu sayısı, baş/son boşluk (uyarı), çevrilmedi (bilgi).
Taşma denetimi font ölçüsü kullanmaz; yalnızca uzunluk oranına bakar.

## LayeredFS çıktısı

| Hedef | Yapı | Kurulum |
|---|---|---|
| Atmosphère | `atmosphere/contents/<TitleID>/romfs/<yol>` | `atmosphere` klasörünü SD kartın köküne kopyalayın |
| Emülatör | `<TitleID>/<Mod Adı>/romfs/<yol>` | Ryujinx: `mods/contents/`; Yuzu türevleri: `load/` |

- Mod her zaman yeni/boş bir klasöre üretilir; var olan dosyaların üzerine yazılmaz.
- Önce geçici klasöre yazılır; her dosya yeniden açılıp her metnin beklenen değerde olduğu
  doğrulanır; sonra tek hamlede hedefe taşınır. İptal veya hatada hedefte hiçbir şey kalmaz.
- Yalnızca değişen dosyalar yazılır. İç içe arşivler (SARC/Yaz0/ZSTD) yeniden kapatılır.
- "Hatalı" satırlar yazılmaz (oyunda orijinal metin kalır).
- Kök klasöre `NXTR - Bilgi.txt` yazılır: oyun, TitleID, üretildiği sürüm, satır sayıları,
  harf dönüştürme ve kurulum adımları.
- Metinlerin aktarıldığı sürümle şu anki oyun dosyalarının sürümü farklıysa uyarılır.

## Unity Addressables CRC

Değiştirilmiş bir AssetBundle, katalog o bundle için CRC denetimi istiyorsa yüklenmez. Silver
Pines'ın `aa/catalog.bin` dosyasında İngilizce metin tablosu kaydında, bundle boyutundan hemen
önceki alan (AssetBundleRequestOptions'ın CRC alanı olduğu düşünülen) **0**; yani CRC denetimi
kapalı görünüyor. Katalog biçimi tam çözümlenmedi; kesin sonuç gerçek cihaz/emülatör testidir.
