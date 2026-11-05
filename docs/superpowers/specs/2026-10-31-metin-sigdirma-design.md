# Metin sığdırma — tasarım

Tarih: 2026-10-31 · Durum: uygulandı (0.32.0) · Kapsam: çekirdek mantık + Kontrol Et ekranında basit bir bölüm.
Arayüz yenilemesi (A düzeni, simgeler, durum çubuğu, hizalama, çeviri paneli) ayrı bir alt projedir ve bu belgenin dışındadır.

## 1. Amaç

Oyun ekranı sınırlıdır. Türkçe çeviri satırları kötü yerlerde bölününce metin taşar veya yanlış sayfaya düşer.
Ürün sahibi bugün satırları elle bölüyor; birkaç bin satırlık projede bu sürdürülemez.

Başarı ölçütü: kullanıcı satır sınırını karakter sayısıyla tanımlar (kendisi değiştirebilir), program sınırı aşan veya
gereksiz bölünmüş satırları bulur, noktalamadan, yoksa kelime bitiminden bölerek düzeltir, değişiklikleri önizletir ve
kontrol kodlarına dokunmaz.

Örnek (gerçek oyun alıntısı), sayfa sonu kodu `⟦1⟧`:

```
Yalnız bir uyarı.⟦1⟧Bu ayar bazen garip
sonuç verebilir. Örneğin başarısız olduğun
hâlde başarılı hareket sesi duyabilirsin.⟦2⟧Kusura
bakma; TV ayarını böyle değiştirdiğimizde
bazen oluyor.⟦3⟧Aa! Ama elde
taşınır modda hiç yaşanmamalı! Buna da şükür.
```

Satırlar sayfa sınırında değil, rastgele yerlerde kesilmiş. Hedef: her sayfa kendi içinde, sınıra göre doğru yerlerden bölünmüş.

## 2. Kavramlar

- **Sayfa:** metnin "sayfa sonu" türündeki kontrol kodlarıyla ayrılan bölümü. Sayfa sonu kodundan sonraki metin sonraki ekranda görünür.
- **Satır:** bir sayfanın içinde, düz `\n` karakteriyle veya "satır sonu" türündeki kontrol koduyla ayrılan bölüm.
- **Görünen uzunluk:** kontrol kodları çıkarıldıktan sonraki karakter sayısı (değişken kodları için §3.2).
- **Sınır:** satır başına en çok karakter (`genişlik`) ve sayfa başına en çok satır (`satır sayısı`).

## 3. Tasarım

### 3.1 Sınırlar (karakter sayısı, kullanıcı değiştirebilir)

`FitRules`: `width: int`, `max_lines: int`, `variable_width: int` (varsayılan 6).

- Proje varsayılanı ve dosya başına geçersiz kılma. Satır başına sınır yoktur (YAGNI).
- Mevcut `max_length` (biçimin koyduğu toplam uzunluk sınırı) aynen kalır, ayrı denetlenir.
- **Orijinalden öğren** düğmesi bir öneri üretir: kapsamdaki (dosya veya proje) orijinal metinlerde en uzun satırın görünen
  uzunluğu ve bir sayfadaki en çok satır sayısı. Öneri alanlara yazılır, kullanıcı değiştirebilir. Otomatik uygulanmaz.
- Sınır tanımlı değilse yeni denetimler ve onarımlar hiçbir şey yapmaz (bazı oyunlarda gerekmez).
- Saklama: projenin `settings` tablosunda anahtar/değer, JSON. Anahtarlar: `fit_config` (`enabled` açık/kapalı bayrağı, proje varsayılanı, dosya başına
  sınırlar ve temizlik seçenekleri tek JSON'da; kapalıyken sınırlar saklanır ama uygulanmaz) ve `code_kinds`. Şema göçü gerekmez. Bozuk veya eksik değer varsayılana döner.

### 3.2 Kontrol kodu türleri

Türler: `satır sonu`, `sayfa sonu`, `değişken`, `sembol`, `biçim` (renk, yazı stili), `diğer`. Saklanan eşlemede serbest tür adı (davranışı `diğer` gibi) desteklenir ve arayüzde gösterilir; arayüzden yeni tür adı oluşturma henüz yoktur.

- Eşleme anahtarı kodun mevcut etiketi (`TextEntry` içindeki `code_labels`). Proje düzeyinde saklanır:
  `code_kinds` = `{etiket: tür}`.
- Varsayılan tahmin etiket adından: "satır sonu" → satır sonu; "sayfa", "bekle", "temizle" → sayfa sonu; "renk", "biçim" → biçim;
  "değişken", "oyuncu", "sayı" → değişken; "simge", "tuş", "düğme" → sembol; diğerleri → diğer. Kullanıcı Kontrol Et'te düzeltir.
- Tür etkisi: `satır sonu` ve `sayfa sonu` metni böler; `değişken` `variable_width` kadar, `sembol` 1 karakter sayılır;
  `biçim` ve `diğer` 0 sayılır ve bitişik kelimeye yapışık kalır (kod ile kelime arasından bölünmez).
- **Doğrulanacak risk:** formatların verdiği etiketler anlamlı mı? Uygulama planının ilk adımı gerçek örnek projelerde
  (MSBT, Unity) etiketlerin neye benzediğini kontrol etmektir. Etiket anlamsızsa eşleme anahtarı olarak ham kod kullanılır.

### 3.3 Bölme algoritması (`core/translate/fit.py`)

Girdi: çeviri metni, kod türleri, `FitRules`. Çıktı: yeni metin veya "sığmıyor".

1. Metin sayfa sonu kodlarında sayfalara ayrılır. Sayfa sonu kodları ve yerleri **değişmez**.
2. Bir sayfa şu durumda sorunlu sayılır: bir satır `width` aşıyor, satır sayısı `max_lines` aşıyor veya "gereksiz bölünmüş satır"
   var (§3.4). Sorunsuz sayfaya dokunulmaz (en az değişiklik).
3. Sorunlu sayfanın satırları boşlukla birleştirilir, sonra yeniden bölünür:
   - Aday kesim noktaları kelime sınırlarıdır. Kelime ortasından hiç bölünmez.
   - Dinamik programlama ile en düşük maliyetli bölüm seçilir. Sert kural: her satır `width` içinde, satır sayısı `max_lines` içinde.
     Maliyet: satır boşluğu (dengeli satırlar), satır sayısı için küçük ceza, tek kelimelik son satır cezası.
     Ödül: cümle sonu noktalamasından (`. ! ? …`) sonra kesmek büyük, virgül/`;`/`:` sonrası kesmek küçük.
   - Ağırlıklar sabit olarak tanımlanır ve testlerle ayarlanır.
4. Satır ayırıcının türü korunur:
   - Sayfa `\n` ile bölünüyorsa satır sayısı serbesttir (en az uygun sayıdan `max_lines`'a kadar).
   - Sayfa **satır sonu koduyla** bölünüyorsa kod sayısı ve sırası orijinalle aynı kalmak zorundadır (kontrol kodu kuralı); satır
     sayısı sabittir ve yalnızca kodların yeri değişir. Aynı sayfada hem `\n` hem satır sonu kodu varsa sayfa "karışık" diye atlanır.
5. Sığdırılamazsa (tek kelime `width`'ten uzun, ya da en az gereken satır sayısı `max_lines`'tan fazla) metin değişmez ve satır
   "sığmıyor" olarak kalır.
6. Sonuç yalnızca sayfanın birleştirilmiş metnine bağlıdır; ikinci kez çalıştırmak sonucu değiştirmez (idempotent).

### 3.4 Denetimler (`core/qa/checks.py`)

Yeni türler, hepsi **uyarı** (dışa aktarmayı engellemez), yalnızca sınır tanımlıysa çalışır:

| Tür | Anlam |
|---|---|
| `line_too_long` | Bir satır `width` aşıyor |
| `page_too_tall` | Bir sayfa `max_lines` aşıyor |
| `bad_break` | Bir satır `width` yarısından kısa, sonraki satırın ilk kelimesi sığardı ve satır noktalama ile bitmiyor |

Mesajlar Türkçe ve sayfa/satır numarası içerir ("2. sayfa, 1. satır 47 karakter; sınır 40.").

### 3.5 Onarım (`core/qa/autofix.py`)

- `LOCAL_KINDS`'e üç yeni tür eklenir; `local_fix` sınır tanımlıysa §3.3'ü uygular.
- Yerel olarak çözülemeyenler ("sığmıyor") mevcut model akışına gidebilir (`MODEL_KINDS`): mesaj "şu kadar karaktere kısalt" der,
  sonuç aynı denetimden geçer, sorun sürüyorsa eski çeviri korunur. Bu adım planın en sonundadır, isteğe bağlıdır.
- **Temizlik seçenekleri** (Subtitle Workshop'taki "hataları düzelt" seçeneklerinin oyuna uyarlanmışı), her biri projede açılıp
  kapanır ve yalnızca orijinalde olmayan kalıba dokunur (mevcut ilkeyle aynı):
  - gereksiz boşluk (çift boşluk)
  - noktalama öncesi boşluk
  - tekrarlı noktalama (`!!!`, `....`)
  Film altyazısına özgü olanlar (süre, çakışma, işitme engelli, OCR) alınmaz.
- Bir satıra sınır uygulanıyorsa mevcut "Satır sonu" denetimi (satır sayısı orijinalle aynı olmalı) ve ona bağlı yeniden
  dengeleme o satır için devre dışı kalır; satır sayısını sınırlar belirler. Sınır yoksa eski davranış aynen sürer.
- Onaylı satırlara dokunulmaz (mevcut kural). Uygulamadan önce "Değişiklikler" penceresi önceki/sonraki hâli gösterir;
  satırlar tek tek geri alınabilir (mevcut yapı).
- Kontrol kodu doğrulaması aynen çalışır: onarımdan sonra `placeholders.problems` temiz olmalı, değilse onarım reddedilir.

### 3.6 Arayüz (bu alt projede en az)

Kontrol Et ekranına **Sığdırma** sekmesi ("Satırları Sığdır" kartı, "Sığdırmayı aç" kutusu): iki sayı kutusu (karakter/satır, satır/sayfa), Orijinalden öğren düğmesi,
kod türleri tablosu (etiket → tür, açılır liste), temizlik seçenekleri. Uygulamak için ayrı düğme (Uygula) yoktur: sınırlar girilince
mevcut "Denetle" yeni bulguları gösterir, "Programla Düzelt" onarır. Çeviri tablosunda kodları ikonlu çip olarak
göstermek ve düzenleyicide karakter sayacı arayüz yenileme alt projesine bırakılır.

## 4. Hata durumları

- Sınır girilmemiş ya da Sığdırmayı aç kapalı: yeni denetimler ve onarımlar hiçbir şey yapmaz.
- Karışık satır ayırıcılı sayfa: değiştirilmez (yerelde sığmayan gibi model akışına gider).
- Kod yer değiştirirse veya sayısı tutmazsa onarım reddedilir, çeviri aynen kalır.
- Uzun kelime/çok satır: yerelde değiştirilmez, sınır bilgisiyle modele kısaltılmak üzere gönderilir; sonuç sığmazsa eski çeviri korunur.
- Sorunlu sayfa yeniden bölününce sayfadaki boş satırlar ve sekmeler kaldırılır.

## 5. Test planı

- Gerçek alıntıdan türetilmiş elle yazılmış örnekler (repoya oyun dosyası konmaz): kullanıcının verdiği 3 sayfalık metin.
- Noktalama önceliği, kelime ortasından bölmeme, dengeli bölme, tek kelimelik son satır, uzun kelime.
- Türkçe karakterler (ç ğ ı İ ö ş ü) uzunluğu ve büyük/küçük harf davranışını bozmuyor.
- Sayfa sonu kodlarının sayısı, sırası ve yeri değişmiyor; satır sonu kodu sayfalarında kod sayısı sabit.
- İdempotans: `fit(fit(x)) == fit(x)`. Sorunsuz sayfa değişmiyor.
- Sınır yokken hiçbir değişiklik yok. Boş metin, yalnızca kodlardan oluşan metin, çok büyük tablo (binlerce satır).
- Denetim ve onarım zinciri: `check_row` → `plan_fixes` → `acceptance_check`.
- Ayar saklama: sınırlar ve kod türleri proje kaydedip yeniden açınca geri geliyor.

## 6. Kapsam dışı

Piksel genişliği ölçümü (font gerekir), satır başına sınır, çeviri isteminde sınır bilgisini modele verme, tabloda kod çipleri,
düzenleyici karakter sayacı. Sonuncular ya arayüz yenilemesine ya da sonraki sürüme girer.

## 7. Dosyalar

Yeni: `nxceviri/core/translate/fit.py`, `nxceviri/core/translate/fitconfig.py`, `nxceviri/core/translate/codekinds.py`,
`tests/test_fit.py`, `tests/test_fitconfig.py`, `tests/test_codekinds.py`.
Değişen: `nxceviri/core/qa/checks.py`, `nxceviri/core/qa/autofix.py`, `nxceviri/gui/qa_page.py`, `nxceviri/gui/main_window.py`,
`CHANGELOG.md`, `ARCHITECTURE.md`, `docs/translation.md`.
