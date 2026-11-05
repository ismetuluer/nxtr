# Yol haritası ve proje sahibine özgü kararlar

Bu belge **proje sahibinin** planıdır. Genel kurallar `AGENTS.md`'dedir; başka bir kullanıcının ajanı bu planı
kendiliğinden uygulamaya kalkmaz. (Eski `CLAUDE.md`'nin sahibe özgü bölümleri, değişmeden, buraya taşındı.)

## Sahibin oturumlarında "Devam" talimatı

"Devam" denince: mevcut durumu dosyalardan ve testlerden doğrula (önceki raporlara körü körüne güvenme), en önemli kalan
işi seç, uygula, test et, gerilemeleri kontrol et, arayüzü kontrol et, temizle, sürümü artır, `CHANGELOG.md`'yi güncelle,
ne yaptığını ve sıradaki adımı raporla.

## Sürüm ve devir kuralları

- Her anlamlı iterasyonda sürüm (SemVer) artırılır ve `CHANGELOG.md` gerçek değişiklikleri anlatır.
- Bağlam sınırına yaklaşınca `HANDOFF.md` yazılır: durum, yığın, bitenler, bilinen hatalar, teknik borç, önerilen sıradaki iş.
- Teknik kararlar ve gerekçeleri kısa Türkçe ile raporlanır (ürün sahibi programcı değildir).
- Paketleme: kurulum gerektirmeyen taşınabilir Windows klasörü. PyInstaller mi Nuitka mı sorusu çözüldü: PyInstaller
  `--onedir` (gerekçe: `ARCHITECTURE.md` §1.1). Python sürüm seçimi de oradadır.

## Yol haritası

| Aşama | İçerik | Bitti sayılma ölçütü |
|---|---|---|
| M1 | Proje iskeleti, anahtar yükleme, NSZ/NSP → RomFS çıkarma, base+update birleştirme, format tarama raporu | Gerçek bir oyunda RomFS çıkıyor, tespit edilen metin dosyaları ve türleri listeleniyor |
| M2 | SARC/Yaz0/ZSTD açma-kapama, MSBT extract/inject, çeviri tablosu arayüzü | MSBT round-trip testleri geçiyor, metinler tabloda düzenlenebiliyor |
| M3 | Ollama sağlayıcısı, yer tutucu koruma, çeviri belleği, sözlük | Toplu çeviri yapılıyor, kontrol kodları bozulmuyor, işlem kaldığı yerden devam ediyor |
| M4 | DeepL sağlayıcısı, sağlayıcı seçimi ve ayarlar ekranı | Aynı projede iki sağlayıcı arasında geçiş yapılabiliyor |
| M5 | QA ekranı, font glif kontrolü, harf dönüştürme, LayeredFS dışa aktarma | Üretilen mod, gerçek cihazda veya emülatörde Türkçe metinle açılıyor |
| M6 | Unity format eklentisi (Unity Localization string tabloları) | Silver Pines'ın metinleri çeviri tablosuna aktarılıyor, değişikliksiz geri yazım orijinalle aynı |
| M7 | Unreal (.locres) format eklentisi | — |
| M8 | Font yamalama | — |
| M9 | Taşınabilir paketleme ve son cila | Temiz bir Windows makinesinde kurulumsuz çalışıyor |

Aşamalar sırayla ilerler. Bir aşama bitmeden sonrakine başlanmaz.

**Sıra değişikliği (ürün sahibi kararı, 2026-10-21):** Kullanıcının hedef oyunu (Silver Pines) Unity kullandığı için
M6, M2'den hemen sonra yapılır. Güncel sıra: M1 → M2 → **M6** → M3 → M4 → M5 → M7 → M8 → M9.

> Güncel durum (sürüm, bitenler, bekleyenler) için `CHANGELOG.md`, `HANDOFF.md` ve `ARCHITECTURE.md` başındaki
> "Güncel durum" satırına bak; yukarıdaki tablo özgün plandır.

## Çeviri sağlayıcıları (eski CLAUDE.md §4.2)

Sözleşme:

```
TranslationProvider
  name, requires_api_key, supports_glossary, max_batch_chars
  test_connection() -> Status
  translate_batch(items, source_lang, target_lang, context, glossary) -> list[Result]
  estimate_cost(items) -> Optional[...]
```

Kod: `nxceviri/core/translate/providers/` (`base.py`, `ollama.py`, `deepl.py`). Kullanıcı kılavuzu: `docs/translation.md`.

- **Ollama (varsayılan, yerel):** Model kullanıcı tarafından seçilir; uygulama yüklü modelleri listeler. İstem (prompt)
  şablonu: oyun bağlamı, karakter/ton notları, sözlük, kontrol kodlarının dokunulmadan korunacağı kuralı, uzunluk
  sınırı. Sahibin GPU'su RTX A4000 (16 GB VRAM), RAM 64 GB; varsayılan model önerisi buna göre araştırılıp sunulur.
- **DeepL:** Free ve Pro uç noktalarını otomatik ayırt et. Kontrol kodlarını XML etiketi olarak gönder
  (`tag_handling`) ve DeepL sözlük (glossary) özelliğini kullan. Kota/karakter sayısını arayüzde göster.
- Yeni sağlayıcı (ör. OpenAI uyumlu uç nokta, Google) yalnızca bu arayüzü uygulayarak eklenir; çekirdekte başka
  değişiklik gerekmez.
- API anahtarları Windows Kimlik Bilgisi Yöneticisi'nde (keyring) saklanır, proje dosyasında saklanmaz.
- Ağ hataları, zaman aşımları ve kota dolması yakalanır, kullanıcıya Türkçe ve anlaşılır gösterilir. Yarıda kalan toplu
  çeviri kaldığı yerden devam edebilir.

## Bağımlılık adayları (eski CLAUDE.md §3)

Başlangıçta değerlendirilecek adaylar: `nsz` (NSZ↔NSP), hactool / hactoolnet (NCA/RomFS çıkarma), `oead` (SARC, Yaz0,
BYML), `zstandard`, `UnityPy` (Unity asset), `httpx` (Ollama/DeepL istekleri), `fontTools` (font glif kontrolü).
Her biri için kullanılıp kullanılmadığı ve gerekçesi `ARCHITECTURE.md` §2'dedir (ör. `nsz`, hactool, `oead`
kullanılmadı). Politika `AGENTS.md`'de: yeni bağımlılık yalnızca açıkça daha güvenilirse, "neden" satırıyla.

## Belge haritası (eski CLAUDE.md §9)

`CLAUDE.md` (ajan girişi, `@AGENTS.md`), `AGENTS.md` (kurallar), `ARCHITECTURE.md` (güncel mimari, bağımlılıklar ve
gerekçeleri, kararlar), `CHANGELOG.md` (sürüm geçmişi), `TECH_DEBT.md` (bilinçli bırakılmış işler ve nedenleri),
`HANDOFF.md` (oturum devri), `docs/formats/` (çözümlenen her dosya formatının notları: yapı, kaynaklar, bilinen
tuzaklar), `docs/rehber/` (ajan rehberleri), `docs/istemler.md` (hazır talimat kartları).
