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

## Sonraki yapılacaklar (ürün sahibinin istek listesi, 2026-11-14)

Sırasız; her biri ayrı karar ve onay ister.

1. **Kontrol kodlarının önizlemesi (renk, kalın, italik).** İstek: satırdaki kod bir renk ya da biçim koduysa
   uygulama bunu çözüp metni o renkte/biçimde göstersin. Bugün eklentiler koda yalnızca etiket verir ("Renk",
   "Kod 0x05"); hangi renk ya da biçim olduğu bilgisi tutulmaz (`core/translate/codekinds.py` türü etiketten tahmin
   eder). Gerekenler: eklenti sözleşmesine isteğe bağlı anlam alanı (renk değeri, kalın/italik, açılış–kapanış eşi),
   biçim eklentilerinin bunu doldurması, tablo ve panel çiziminin (`gui/textmarks.py`, `gui/editor_pane.py`) bunu
   uygulaması. Maliyet yüksek (çok dosyalı, sözleşme değişir). Öneri: önce yalnızca MSBT'de renk; işe yaradığı
   görülürse diğer biçimler. Yalnızca çizim değişir; metin ve dışa aktarma etkilenmez.
2. **`gui/main_window.py` bölünmesi** (~3.700 satır; TECH_DEBT 69). Davranış değiştirmeyen, tam test setiyle
   yapılacak çok dosyalı iş.
3. **Adım listesinde klavye odağı.** Listenin çevresindeki mavi odak çerçevesi ürün sahibinin isteğiyle kaldırıldı
   (2026-11-14); seçili adımın vurgusu odağı gösterir. İstenirse öğe başına ince bir işaret `gui/step_nav.py`
   çiziminde yapılır.
4. **Boşluk ve köşe ölçeği.** Arayüzde 10 farklı aralık ve 9 farklı köşe yarıçapı var; ilgili ekran elden geçerken
   sadeleştirilecek (topluca değil).
5. **Başlatıcı adı ve kök klasör.** `NX Ceviri Studyosu.bat` eski adı taşıyor (ad değişirse kullanıcı kısayolları
   bozulur); tek oyuna özel `sd_kontrol.py` kökte duruyor (`tools/` altına taşınabilir).
6. **Güncelleme paketinde imza.** SHA-256 dosyası paketle aynı sürümden gelir: bozuk indirmeyi yakalar, ele geçirilmiş
   bir sürümü yakalamaz. İmza, yeni bağımlılık ve anahtar yönetimi ister.
7. **Kullanıcı eklentilerinde ilk yükleme uyarısı.** Eklenti klasöründeki kod doğrudan çalışır (tasarım gereği);
   arayüzün ilk yüklemede açıkça uyarıp uyarmadığı incelenmedi.
8. **Kararsız süre testi.** `tests/test_find_bar_fixes.py::test_keystroke_work_on_large_table_is_fast` tam test
   setinde yük altında bir kez süre sınırını aştı (tek başına geçiyor); eşik ya da ölçüm yöntemi gözden geçirilmeli.

### Görsel denetim bulguları (2026-11-14, 0.57.1 ekran görüntüleri)

Öncelik sırasıyla. İlk grup hata düzeyindedir; ikinci grup tasarım iyileştirmesidir.

**Hata düzeyinde** (hepsi 0.57.2'de düzeltildi)
1. Sığdırma: sayı kutularının ok düğmeleri boş kutu görünüyor (oklar çizilmiyor); açılır listelerin oku da aynı.
2. Sığdırma: "Grup ve anahtar sınırları" tablosunda başlıklar iki yandan kırpılıyor.
3. Sığdırma: "Sığdırma kapalı" bilgisi iki ayrı satırda yineleniyor (ayar özeti ve 0.57.1'de eklenen sonuç özeti);
   tek satırda birleşmeli.
4. Sorunlar: "Tür" ve "Açıklama" sütunları kırpılıyor; "Önem" sütunu her satırda aynı sözcüğü gösterip yer harcıyor
   (simgeye indirilmeli).
5. Font ve harfler: en önemli sütun "Ne yapılabilir" kırpılıyor.
6. Metinleri Tara: sayfa kaydırması içinde tablo kaydırması (iki kaydırma çubuğu); tablonun son satırı yarım görünüyor.
7. Dışa Aktar: seçili seçenek düğmesi (radyo) gri; onay kutuları gibi vurgu renginde olmalı.

Kalan küçük kusur: Sığdırma ayar kartında gizlenen sonuç satırının yerinde boşluk kalıyor.

**Tasarım iyileştirmesi**
8. Kontrol Et sekmeleri eski Windows sekmesi görünümünde; uygulamanın düz, yuvarlak köşeli diline uydurulmalı.
9. Sorunlar'da iki dolu ana düğme var ("Denetle", "Seçilenleri Düzelt"); ekranda tek ana eylem kalmalı.
10. Sorun türü çipleri hepsi aynı uyarı renginde; oyunu bozabilecek türler (kod yeri) kırmızı, üslup türleri nötr.
11. Tablo başlıkları ortalı, hücreler sola yaslı; başlık içerikle aynı hizada olmalı (metin sola, sayı sağa).
12. Metinleri Tara: "Kanıtlar" satırı (IL2CPP, AssetBundle sayıları) varsayılan olarak gizlenip "Ayrıntılar" altına
    alınmalı; üç büyük sayı kartı üstteki özet satırıyla birleşebilir.
13. Dışa Aktar: "İçeriği: atmosphere/contents/<TitleID>/romfs/…" yerine kullanıcıya ne yapacağını söyleyen yönerge.
14. Durum çubuğu simgeleri (anahtar, ¶, durum noktası, zil) etiketsiz; en az birkaçına kısa etiket.
15. Boş "Oyunu Ekle" ekranı pencerenin yarısını boş bırakıyor; beş adımı anlatan kısa yol ya da son projeler.
16. Koyu temada tablo satırlarının dönüşümlü zemini neredeyse ayırt edilmiyor.

### Ürün sahibinin 0.57.2 sonrası geri bildirimi (2026-11-14)

**Yapıldı (0.58.0)**
- Kontrol Et → Sorunlar yeniden kuruldu: solda önem sırasına göre gruplu tür listesi (çip bulutu ve "Tür" sütunu
  kalktı), bulgular üç satırlık liste (açıklama, orijinal, çeviri), sağdaki "Düzeltmeler" paneli yerine listenin
  üstünde bağlama göre düzeltme çubuğu, seçili satırdaki boş kutu hatası giderildi. Yukarıdaki görsel denetim
  listesinin 9. ve 10. maddeleri (tek ana düğme, çip renkleri) bu işle kapandı.
- Metinleri Tara'da dosya seçimi ("Aktar" kutusu, "Dil" sütunu, dili bilinmeyenler uyarısı), yeniden aktarmada
  kaldırma onayı ve bu sayfanın açıklama ipuçları.

**Yapıldı (0.58.1)**
- Sorunlar listesinde sağ tık → "Sırala": önem, satır numarası, bulguya göre, dosyaya göre; seçim hatırlanır.
- Terim denetimi büyük/küçük harfi Türkçe kurallarıyla karşılaştırır ("FIRLATMA" = "Fırlatma"); otomatik düzeltme de.
- Sorunlar satırında kontrol kodları çeviri tablosundaki gibi çip olarak çizilir.
- Açıklama ipuçları: Dışa Aktar (hedef, mod adı, konum, düğmeler) ve Kontrol Et (font tarama, harf dönüştürme
  seçenekleri, Denetle, sığdırma alanları). Çevir sayfasında ipucusuz kalanlar yalnızca kendini anlatan düğmeler
  (Bul, Yerine, Onayla, İptal).

**Sırada**
1. **Boş "Oyunu Ekle" ekranı** (görsel denetim madde 15): yeni içerik olduğu için ürün sahibinin kararı bekleniyor.
   Öneri: son açılan projelerin listesi (seçenek: beş adımı anlatan kısa yol gösterici).
2. **Yazım denetimi:** kesme işaretli sözcüklerin kökü ("Sifu'n" → Sifu) orijinalde geçmiyorsa denetlenmesi
   (ürün sahibinin sorusu, 2026-11-14; karar bekliyor).

**Yapıldı (0.58.2)**
- Metinleri Tara: Tür, Ayrıntı ve Dil sütunları içeriğe göre boyutlanır, kırpılmaz; dar pencerede dosya yolu ortadan
  kısalır (tam yol ipucunda, en az 160 px). Çok dar pencerede tabloda yatay kaydırma çıkar.
- Kontrol Et sekmeleri (görsel denetim madde 8): Windows sekmesi yerine düz, yuvarlak köşeli; seçili sekme seçim
  renginde dolgulu (ürün sahibinin onayıyla, 2026-11-15). Sekme çubuğunda klavye odağı için ayrı işaret yok.
- Görsel denetim 11, 12, 13, 14, 16: tablo başlıkları içerikle aynı hizada (metin sola, sayı sağa); Metinleri
  Tara'da motor kanıtları "Ayrıntılar" altında; Dışa Aktar hedef satırı ne yapılacağını söyler (klasör yapısı
  ipucunda); durum çubuğunda kısa etiketler ("Anahtarlar", "satır", "çevrildi", "hatalı"; dar çubukta ekler birlikte
  düşer, yarım sözcük kalmaz); koyu temada dönüşümlü satır zemini belirgin (`row_alt`).

**Ertelendi**
- **Metinleri Tara'da eklentinin içerikten bulduğu dil** (2026-11-14). Yerleşik eklentilerin neredeyse hepsi dili
  yoldan okur (`language()` → `None`); içerikten bulan yalnızca FMSB. Tarama dosyanın yalnızca baş/son baytlarını
  okur; içerikten dil için her dosya baştan sona okunmalı (tarama belirgin yavaşlar). Aktarımda eklentinin dili zaten
  denetlenip yanlış dildeki dosya atlanıyor (`core/pipeline.py`). İçerikten dil bulan eklentiler çoğalırsa yeniden ele
  alınır.

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
